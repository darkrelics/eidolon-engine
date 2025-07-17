"""Incremental deployment orchestrator for Eidolon Engine infrastructure.

This script manages incremental AWS infrastructure deployments using CDK,
allowing for selective updates without full redeployment.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from aws_client_factory import AWSClientFactory
from build_executor import BuildExecutor
from cdk_api_integration import CDKApiIntegration, CDKDeploymentError, CDKProgressReporter
from config_updater import ConfigurationUpdater
from config_validator import validate_deployment_config, validate_stack_config
from deployment_logic import analyze_changes, prompt_missing_parameters
from error_handlers import handle_client_errors
from health_checks import run_phase_health_check
from resource_validator import ResourceValidatorFactory, generate_drift_report
from stack_utils import StackOutputHelper
from state_manager import ConfigurationManager, DeploymentState


class IncrementalDeploymentOrchestrator:
    """Orchestrates incremental infrastructure deployments."""

    def __init__(self, profile=None, region: str = "us-east-1", branch=None) -> None:
        """Initialize the deployment orchestrator.

        Args:
            profile: AWS profile to use
            region: AWS region for deployment
            branch: GitHub branch to deploy from (overrides default)
        """
        self.profile = profile
        self.region = region
        self.branch = branch
        self.config_manager = ConfigurationManager()
        self.state_manager = DeploymentState()

        # Set up AWS client factory
        self.aws_factory = AWSClientFactory(profile=profile, region=region)
        self.session = self.aws_factory.session

        # Initialize AWS clients through factory
        self.cfn_client = self.aws_factory.get_client("cloudformation")
        self.s3_client = self.aws_factory.get_client("s3")

        # Initialize helper classes
        self.stack_helper = StackOutputHelper(self.cfn_client)
        self.config_updater = ConfigurationUpdater(self.config_manager)

        # CDK app directory
        self.cdk_dir = Path(__file__).parent / "cdk"

        # Initialize CDK API integration
        self.cdk_api = CDKApiIntegration(cdk_dir=str(self.cdk_dir), profile=profile, region=region)  # type: ignore

        # Initialize build executor
        self.build_executor = BuildExecutor(self.session)

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met for deployment.

        Returns:
            True if all prerequisites are met
        """
        print("Checking prerequisites...")

        # Check AWS credentials
        if not self.aws_factory.validate_credentials():
            print("ERROR: Unable to access AWS. Please check your credentials.")
            return False

        try:
            identity = self.aws_factory.get_caller_identity()
            print(f"AWS Account: {identity.get('Account', 'Unknown')}")
            print(f"AWS Region: {self.region}")
        except Exception as err:
            print(f"ERROR: Unable to get AWS identity: {err}")
            return False

        return True

    def load_parameters(self) -> dict:
        """Load deployment parameters from various sources.

        Returns:
            Dictionary of deployment parameters
        """
        params: dict = {
            "game_name": "eidolon-engine",
            "contact_email": None,
            "github_owner": "robinje",
            "github_repo": "eidolon-engine",
            "github_branch": "develop",
            "log_retention_days": 365,
        }

        # Load from saved state
        saved_params: dict = self.state_manager.get_parameters()
        params.update(saved_params)

        # Load from config file (which may have been initialized from template)
        config: dict = self.config_manager.config
        if "Game" in config:
            game_config = config["Game"]
            params["game_name"] = game_config.get("name", params["game_name"])
        # Check both AWS and Contact sections for email (template uses Contact)
        if "Contact" in config:
            params["contact_email"] = config["Contact"].get("Email", params["contact_email"])
        if "AWS" in config:
            aws_config = config["AWS"]
            params["contact_email"] = aws_config.get("contact_email", params["contact_email"])
        if "CloudFront" in config:
            cf_config = config["CloudFront"]
            params["cloudfront_distribution_id"] = cf_config.get("distribution_id", params.get("cloudfront_distribution_id"))
        if "DynamoDB" in config and "Tables" in config["DynamoDB"]:
            # Load existing DynamoDB table names if configured
            params["dynamodb_tables"] = config["DynamoDB"]["Tables"]
        if "CodeBuild" in config:
            codebuild_config = config["CodeBuild"]
            if "PortalBuildspecPath" in codebuild_config:
                params["portal_buildspec_path"] = codebuild_config["PortalBuildspecPath"]

        # Load from template structure
        if "GitHub" in config:
            github_config = config["GitHub"]
            params["github_owner"] = github_config.get("Owner", params["github_owner"])
            params["github_repo"] = github_config.get("Repo", params["github_repo"])
            params["github_branch"] = github_config.get("Branch", params["github_branch"])

        # Override branch if specified via command line
        if self.branch:
            params["github_branch"] = self.branch

        if "CloudWatch" in config:
            params["log_retention_days"] = config["CloudWatch"].get("LogRetentionDays", params["log_retention_days"])

        if "S3" in config:
            s3_config = config["S3"]
            if s3_config.get("PortalBucket"):
                params["portal_bucket_name"] = s3_config["PortalBucket"]
            if s3_config.get("ScriptsBucket"):
                params["scripts_bucket_name"] = s3_config["ScriptsBucket"]
            if s3_config.get("ArtifactsBucket"):
                params["lambda_bucket_name"] = s3_config["ArtifactsBucket"]

        # Load deployment mode from config
        if "Deployment" in config:
            deploy_config = config["Deployment"]
            if "Mode" in deploy_config:
                params["deployment_mode"] = deploy_config.get("Mode", "hybrid")
            else:
                # Legacy support
                deploy_mud = deploy_config.get("MUD", False)
                deploy_incremental = deploy_config.get("Incremental", False)
                if deploy_mud and deploy_incremental:
                    params["deployment_mode"] = "hybrid"
                elif deploy_mud:
                    params["deployment_mode"] = "mud"
                elif deploy_incremental:
                    params["deployment_mode"] = "incremental"
                else:
                    params["deployment_mode"] = "hybrid"

        # Load API configuration
        if "API" in config:
            api_config = config["API"]
            if api_config.get("Domain"):
                params["domain_name"] = api_config["Domain"]
            if api_config.get("HostedZoneId"):
                params["hosted_zone_id"] = api_config["HostedZoneId"]
            if api_config.get("Subdomain"):
                params["api_subdomain"] = api_config["Subdomain"]

        # Load Cognito configuration
        if "Cognito" in config:
            cognito_config = config["Cognito"]
            if cognito_config.get("UserPoolId"):
                params["existing_user_pool_id"] = cognito_config["UserPoolId"]
            if cognito_config.get("UserPoolClientId"):
                params["existing_app_client_id"] = cognito_config["UserPoolClientId"]

        return params

    def handle_deployment_selection(
        self, params: dict, deploy_mud: bool, deploy_incremental: bool, deploy_both: bool, non_interactive: bool
    ) -> dict:
        """Handle deployment type selection with interactive mode.

        Args:
            params: Current parameters
            deploy_mud: CLI flag to deploy only MUD
            deploy_incremental: CLI flag to deploy only Incremental
            deploy_both: CLI flag to deploy both (hybrid)
            non_interactive: Skip interactive prompts

        Returns:
            Updated parameters with deployment selection
        """
        # If any CLI flag is provided, use it
        if deploy_mud:
            params["deployment_mode"] = "mud"
            print("Deployment mode: MUD (Portal frontend)")
        elif deploy_incremental:
            params["deployment_mode"] = "incremental"
            print("Deployment mode: Incremental")
        elif deploy_both:
            params["deployment_mode"] = "hybrid"
            print("Deployment mode: Hybrid (Incremental frontend, supports both games)")
        elif not non_interactive and "deployment_mode" not in params:
            # Interactive mode - ask user what to deploy
            print("\n=== EIDOLON ENGINE DEPLOYMENT ===")
            print("\nSelect deployment mode:")
            print("1. MUD - Multi-User Dungeon with Portal frontend")
            print("2. Incremental - Idle/incremental game with Incremental frontend")
            print("3. Hybrid - Both game modes with Incremental frontend")

            choice: str = input("\nSelect deployment mode [1-3] (default: 3): ").strip()

            if choice == "1":
                params["deployment_mode"] = "mud"
                print("\n[OK] Selected: MUD mode")
            elif choice == "2":
                params["deployment_mode"] = "incremental"
                print("\n[OK] Selected: Incremental mode")
            else:  # Default to hybrid
                params["deployment_mode"] = "hybrid"
                print("\n[OK] Selected: Hybrid mode")
        else:
            # Use existing params or default
            if "deployment_mode" not in params:
                params["deployment_mode"] = "hybrid"
                print("Deployment mode: Hybrid (default)")

        # Update config manager with deployment choice
        self.config_manager.update_section("Deployment", {"Mode": params.get("deployment_mode", "hybrid")})

        return params


    def execute_deployment(self, plan: dict, auto_approve: bool = False) -> bool:
        """Execute the deployment plan in phases.

        Args:
            plan: Deployment plan from analyze_changes
            auto_approve: Skip confirmation prompt

        Returns:
            True if deployment succeeded
        """
        # Show deployment plan
        print("\n=== DEPLOYMENT PLAN ===")
        if plan["create_stacks"]:
            print(f"\nStacks to CREATE: {len(plan['create_stacks'])}")
            for stack in plan["create_stacks"]:
                print(f"  - {stack}")

        if plan["update_stacks"]:
            print(f"\nStacks to UPDATE: {len(plan['update_stacks'])}")
            for stack in plan["update_stacks"]:
                print(f"  - {stack}")

        if plan["unchanged_stacks"]:
            print(f"\nUnchanged stacks: {len(plan['unchanged_stacks'])}")

        if not auto_approve:
            response = input("\nProceed with deployment? [y/N]: ").strip().lower()
            if response != "y":
                print("Deployment cancelled.")
                return False

        # Save parameters to state
        self.state_manager.update_parameters(plan["parameters"])
        self.state_manager.save_state()

        # Prepare CDK context
        context: dict = {}

        # Add adopted resources to context
        if plan.get("adopt_resources"):
            print("\nPreparing to adopt existing resources...")
            for key, value in plan["adopt_resources"].items():
                context[key] = value
                print(f"  - {key}: {value}")

        # Add deployment mode context
        context["deployment_mode"] = plan["parameters"].get("deployment_mode", "hybrid")

        # Add GitHub branch to context
        context["github_branch"] = plan["parameters"].get("github_branch", "develop")

        # Execute phased deployment
        return self._execute_phased_deployment(context, plan, auto_approve)

    def _execute_phased_deployment(self, context: dict, plan: dict, auto_approve: bool) -> bool:
        """Execute deployment in phases with build execution.

        Args:
            context: CDK context
            plan: Deployment plan
            auto_approve: Skip confirmation prompts

        Returns:
            True if all phases succeeded
        """
        # Define deployment phases
        phases: list = [
            {
                "name": "Foundation",
                "stacks": ["iam", "s3", "dynamodb"],  # Order matters: IAM first, then S3, then DynamoDB
                "description": "IAM roles, S3 buckets, and DynamoDB tables",
            },
            {
                "name": "Authentication & Monitoring",
                "stacks": ["cognito", "cloudwatch"],
                "description": "User authentication and logging infrastructure",
            },
            {
                "name": "Build Infrastructure",
                "stacks": ["codebuild"],
                "description": "CodeBuild projects for Lambda and portal builds",
            },
            {
                "name": "Build Execution",
                "stacks": [],  # No stacks, just build execution
                "description": "Execute CodeBuild projects to create deployment artifacts",
                "execute_builds": True,
            },
            {
                "name": "Application Layer",
                "stacks": ["base-lambda", "lambda"],
                "description": "Lambda functions and API Gateway",
            },
            {"name": "Distribution", "stacks": ["cloudfront"], "description": "CloudFront distribution for content delivery"},
        ]

        # Track overall success
        all_succeeded = True
        completed_phases: list = []

        try:
            for i, phase in enumerate(phases, 1):
                print(f"\n{'='*60}")
                print(f"Phase {i}/{len(phases)}: {phase['name']}")
                print(f"Description: {phase['description']}")
                print(f"{'='*60}")

                # Execute build phase
                if phase.get("execute_builds"):
                    if not self._execute_build_phase(plan["parameters"]):
                        print(f"\n[ERROR] Phase {i} ({phase['name']}) failed!")
                        all_succeeded = False
                        break
                    completed_phases.append(phase["name"])
                    continue

                # Deploy stacks in this phase
                phase_stacks = phase["stacks"]
                if not phase_stacks:
                    continue

                # Filter to only stacks that need deployment
                stacks_to_deploy: list = [
                    stack for stack in phase_stacks if stack in plan.get("create_stacks", []) + plan.get("update_stacks", [])
                ]

                if not stacks_to_deploy:
                    print("No stacks to deploy in this phase")
                    completed_phases.append(phase["name"])
                    continue

                print(f"\nDeploying stacks: {', '.join(stacks_to_deploy)}")

                # Pre-deployment actions for specific phases
                # S3 buckets are now all managed by the S3 stack

                # Deploy stacks serially for safety
                phase_success = True
                stack_results: dict = {}  # Track individual stack results
                for stack in stacks_to_deploy:
                    print(f"\n  Deploying {stack}...")
                    progress_reporter = CDKProgressReporter()
                    result: dict = self.cdk_api.deploy(
                        stacks=[stack],  # Deploy one stack at a time
                        context=context,
                        require_approval="never",  # User already approved deployment plan
                        progress_callback=progress_reporter,
                    )

                    if not result["success"]:
                        print(f"\n  [ERROR] Failed to deploy {stack}")
                        phase_success = False
                        break
                    else:
                        print(f"\n  [SUCCESS] {stack} deployed successfully")
                        # Store the result including stack_changes info
                        stack_results[stack] = result

                result = {"success": phase_success, "stack_results": stack_results}

                # Post-deployment actions for specific phases
                if phase_success and phase["name"] == "Distribution":
                    # Always update S3 bucket policy for CloudFront access, even if cloudfront stack wasn't deployed
                    # This ensures the policy is correct even after manual changes or drift
                    if self.config_manager.config.get("CloudFront", {}).get("distribution_id"):
                        print("\n  Ensuring S3 bucket policy is configured for CloudFront...")
                        self.update_s3_bucket_policy_for_cloudfront(plan["parameters"])

                # Check if we need to update Lambda functions after Application Layer
                if phase_success and phase["name"] == "Application Layer":
                    # Configure Cognito triggers via boto3
                    self.configure_cognito_triggers()

                    # Check if any Lambda stack reported no changes
                    lambda_stacks: list = ["lambda", "base-lambda"]
                    needs_lambda_update = False

                    for stack in lambda_stacks:
                        if stack in stack_results:
                            stack_changes = stack_results[stack].get("stack_changes", {})
                            # If this specific stack had no changes, we need to update
                            if stack in stack_changes and not stack_changes[stack]:
                                needs_lambda_update = True
                                print(f"\n  Note: {stack} had no changes, Lambda update required")
                                break

                    if needs_lambda_update:
                        # Get Lambda bucket name
                        lambda_bucket = plan["parameters"].get("lambda_bucket_name")
                        if not lambda_bucket:
                            # Try to construct it
                            game_name = plan["parameters"].get("game_name", "eidolon-engine")
                            account_id = self.aws_factory.get_account_id()
                            lambda_bucket: str = f"{game_name}-lambda-{account_id}"

                        if lambda_bucket:
                            self._update_lambda_functions_from_s3(lambda_bucket)
                        else:
                            print("  ⚠ Could not determine Lambda bucket name for updates")

                if result["success"]:
                    print(f"\n[SUCCESS] Phase {i} ({phase['name']}) completed successfully!")

                    # Run health checks for this phase
                    health_check_passed = run_phase_health_check(self.session, phase["name"], stacks_to_deploy, plan["parameters"])

                    if not health_check_passed:
                        print(f"\n[WARNING] Health checks failed for {phase['name']}")
                        print("Review the issues above and fix if needed before continuing.")
                        if not auto_approve:
                            response = input("\nContinue with deployment anyway? [y/N]: ").strip().lower()
                            if response != "y":
                                print("Deployment stopped due to health check failures.")
                                all_succeeded = False
                                break

                    completed_phases.append(phase["name"])

                    # Update state after each phase
                    self.state_manager.add_deployment_event(
                        f"phase_{phase['name'].lower().replace(' ', '_')}_complete",
                        {"stacks_deployed": stacks_to_deploy, "outputs": result.get("outputs", {})},
                    )
                    self.state_manager.save_state()
                else:
                    print(f"\n[ERROR] Phase {i} ({phase['name']}) failed!")
                    all_succeeded = False
                    break

        except CDKDeploymentError as err:
            print(f"\n[ERROR] Deployment failed: {err}")
            if err.details:
                print(f"Details: {err.details}")
            all_succeeded = False
        except Exception as err:
            print(f"\n[ERROR] Unexpected error during deployment: {err}")
            all_succeeded = False

        # Final summary
        print(f"\n{'='*60}")
        print("DEPLOYMENT SUMMARY")
        print(f"{'='*60}")
        print(f"Completed phases: {len(completed_phases)}/{len(phases)}")
        for phase_name in completed_phases:
            print(f"{phase_name}")

        if all_succeeded:
            print("\n[SUCCESS] All deployment phases completed successfully!")

            # Update configuration file with outputs
            self.update_configuration(plan["parameters"])

            # Record deployment completion
            self.state_manager.add_deployment_event(
                "deployment_complete", {"phases_completed": completed_phases, "total_phases": len(phases)}
            )
            self.state_manager.save_state()
        else:
            print("\n[ERROR] Deployment failed!")
            print("You can resume deployment by running the command again.")

        return all_succeeded

    def _validate_lambda_artifacts(self, params: dict) -> bool:
        """Validate that Lambda build artifacts were created correctly.

        Args:
            params: Deployment parameters

        Returns:
            True if all expected artifacts exist
        """

        s3_client = self.session.client("s3")
        game_name = params.get("game_name", "eidolon-engine")
        account_id = self.aws_factory.get_account_id()
        bucket_name = params.get("lambda_bucket_name", f"{game_name}-lambda-{account_id}")

        # Expected artifacts
        expected_artifacts: list = [
            "lambda-layer/lambda-layer.zip",  # CodeBuild artifacts path
            "api-add-character.zip",
            "api-delete-character.zip",
            "api-get-archetypes.zip",
            "api-get-character.zip",
            "api-list-characters.zip",
            "cognito-new-player.zip",
            "cognito-delete-player.zip",
        ]

        print("\nValidating Lambda build artifacts...")
        all_valid = True

        for artifact in expected_artifacts:
            try:
                # Check if artifact exists
                s3_client.head_object(Bucket=bucket_name, Key=artifact)
                print(f"  ✓ {artifact}")
            except ClientError as err:
                if err.response["Error"]["Code"] == "404":
                    print(f"  ✗ {artifact} - Not found")
                    all_valid = False
                else:
                    print(f"  ✗ {artifact} - Error: {err}")
                    all_valid = False

        return all_valid

    def _execute_build_phase(self, params: dict) -> bool:
        """Execute CodeBuild projects.

        Args:
            params: Deployment parameters

        Returns:
            True if builds succeeded
        """
        print("\nPreparing to execute CodeBuild projects...")

        # Get CodeBuild project names from stack outputs
        try:
            stacks = self.cdk_api.list_stacks()
            codebuild_stack = next((s for s in stacks if s == "codebuild"), None)

            if not codebuild_stack:
                print("[WARNING] CodeBuild stack not found, skipping build execution")
                return True

            # Get stack outputs
            outputs = self._get_stack_outputs("codebuild")

            # Collect project names
            project_names = []

            # Portal/Incremental build project
            if "CodeBuildProjectName" in outputs:
                project_names.append(outputs["CodeBuildProjectName"])

            # Lambda layer build project
            if "LambdaLayerProjectName" in outputs:
                project_names.append(outputs["LambdaLayerProjectName"])

            # Lambda functions build project
            if "LambdaFunctionsProjectName" in outputs:
                project_names.append(outputs["LambdaFunctionsProjectName"])

            if not project_names:
                print("[WARNING] No CodeBuild projects found in stack outputs")
                return True

            print(f"\nFound {len(project_names)} CodeBuild project(s):")
            for name in project_names:
                print(f"  - {name}")

            # Execute builds (Lambda builds sequentially, portal in parallel with them)
            lambda_projects = [p for p in project_names if "lambda" in p.lower()]
            portal_projects = [p for p in project_names if "lambda" not in p.lower()]

            # Execute all builds sequentially
            all_projects = lambda_projects + portal_projects
            if all_projects:
                print("\nExecuting all builds sequentially...")
                if not self.build_executor.execute_builds(all_projects, parallel=False):
                    return False

                # Validate Lambda artifacts were created if we built Lambda projects
                if lambda_projects and not self._validate_lambda_artifacts(params):
                    print("[ERROR] Lambda build artifacts validation failed")
                    return False

            return True

        except Exception as err:
            print(f"[ERROR] Failed to execute builds: {err}")
            return False

    def _get_stack_outputs(self, stack_name: str) -> dict:
        """Get outputs from a CloudFormation stack.

        Args:
            stack_name: Stack name

        Returns:
            Dictionary of output key-value pairs
        """
        return self.stack_helper.get_outputs(stack_name)

    def validate_configuration(self, fix_drift: bool = False) -> bool:
        """Validate config.yml against actual AWS resources.

        Args:
            fix_drift: Whether to attempt to fix configuration drift

        Returns:
            True if all resources are valid and present
        """
        print("\n=== Configuration Validation ===")
        print("Validating config.yml against AWS resources...\n")

        # Load configuration
        config = self.config_manager.config
        if not config:
            print("[ERROR] No configuration found. Run deployment first.")
            return False

        validation_results = {}
        all_valid = True

        # Validate DynamoDB tables
        if "DynamoDB" in config and "Tables" in config["DynamoDB"]:
            print("Checking DynamoDB tables...")
            validator = ResourceValidatorFactory.create_validator("dynamodb_table", self.session)

            for table_type, table_name in config["DynamoDB"]["Tables"].items():
                if not table_name:
                    print(f"  ✗ {table_type}: Not configured")
                    all_valid = False
                    continue

                result = validator.validate(table_name, {"billing_mode": "PAY_PER_REQUEST"})
                validation_results[f"DynamoDB:{table_name}"] = result

                if result.exists and result.valid:
                    print(f"  ✓ {table_type}: {table_name} - OK")
                elif result.exists and not result.valid:
                    print(f"  ⚠ {table_type}: {table_name} - Configuration drift detected")
                    for msg in result.messages:
                        print(f"    - {msg}")
                else:
                    print(f"  ✗ {table_type}: {table_name} - Does not exist")
                    all_valid = False

        # Validate Cognito User Pool
        if "Cognito" in config:
            print("\nChecking Cognito User Pool...")
            validator = ResourceValidatorFactory.create_validator("cognito_user_pool", self.session)

            user_pool_id = config["Cognito"].get("UserPoolId", "")
            if user_pool_id:
                result = validator.validate(user_pool_id, {})
                validation_results[f"Cognito:{user_pool_id}"] = result

                if result.exists and result.valid:
                    print(f"  ✓ User Pool: {user_pool_id} - OK")
                else:
                    print(f"  ✗ User Pool: {user_pool_id} - {'Invalid' if result.exists else 'Does not exist'}")
                    all_valid = False
            else:
                print("  ✗ User Pool: Not configured")
                all_valid = False

        # Validate S3 Buckets
        if "S3" in config:
            print("\nChecking S3 buckets...")
            validator = ResourceValidatorFactory.create_validator("s3_bucket", self.session)

            # Map of bucket types to their configuration keys
            bucket_types = {
                "Portal": "PortalBucket",
                "Scripts": "ScriptsBucket",
                "Artifacts": "ArtifactsBucket"
            }

            s3_config = config.get("S3", {})
            for bucket_type, config_key in bucket_types.items():
                bucket_name = s3_config.get(config_key, "")
                if bucket_name:
                    result = validator.validate(bucket_name, {})
                    validation_results[f"S3:{bucket_name}"] = result

                    if result.exists and result.valid:
                        print(f"  ✓ {bucket_type} Bucket: {bucket_name} - OK")
                    else:
                        print(f"  ✗ {bucket_type} Bucket: {bucket_name} - {'Access denied' if result.exists else 'Does not exist'}")
                        all_valid = False
                else:
                    print(f"  - {bucket_type} Bucket: Not configured")
            
            # Check if any buckets are missing
            if not any(s3_config.get(key) for key in bucket_types.values()):
                print("  ⚠ No S3 buckets configured")

        # Validate CloudWatch Log Groups
        if "CloudWatch" in config or "Logging" in config:
            print("\nChecking CloudWatch log groups...")
            validator = ResourceValidatorFactory.create_validator("cloudwatch_log_group", self.session)

            log_group = config.get("CloudWatch", {}).get("log_group", "") or config.get("Logging", {}).get("LogGroup", "")
            if log_group:
                result = validator.validate(
                    log_group, {"retention_days": config.get("CloudWatch", {}).get("LogRetentionDays", 365)}
                )
                validation_results[f"CloudWatch:{log_group}"] = result

                if result.exists and result.valid:
                    print(f"  ✓ Log Group: {log_group} - OK")
                elif result.exists and result.drift_detected:
                    print(f"  ⚠ Log Group: {log_group} - Configuration drift")
                    for msg in result.messages:
                        print(f"    - {msg}")
                else:
                    print(f"  ✗ Log Group: {log_group} - Does not exist")
                    all_valid = False

        # Validate IAM resources
        print("\nChecking IAM resources...")

        # Check IAM role
        game_name = config.get("Game", {}).get("name", "eidolon-engine")
        role_name = f"{game_name}-server-execution-role"

        validator = ResourceValidatorFactory.create_validator("iam_role", self.session)
        result = validator.validate(role_name, {"resource_type": "role"})
        validation_results[f"IAM:role:{role_name}"] = result

        if result.exists and result.valid:
            print(f"  ✓ Execution Role: {role_name} - OK")
        else:
            print(f"  ✗ Execution Role: {role_name} - Does not exist")
            all_valid = False

        # Check IAM policies
        policy_names = [f"eidolon-{game_name}-cloudwatch-access", f"eidolon-{game_name}-dynamodb-access"]

        validator = ResourceValidatorFactory.create_validator("iam_policy", self.session)
        for policy_name in policy_names:
            result = validator.validate(policy_name, {"resource_type": "policy"})
            validation_results[f"IAM:policy:{policy_name}"] = result

            if result.exists and result.valid:
                print(f"  ✓ Policy: {policy_name} - OK")
            else:
                print(f"  ✗ Policy: {policy_name} - Does not exist")
                all_valid = False

        # Validate CloudFront Distribution
        if "CloudFront" in config:
            print("\nChecking CloudFront distribution...")
            if config.get("CloudFront") is None:
                print("  ⚠ CloudFront: Not configured")
            else:
                distribution_id = config.get("CloudFront", {}).get("distribution_id", "")
                if distribution_id:
                    try:
                        cf_client = self.session.client("cloudfront")
                        cf_client.get_distribution(Id=distribution_id)
                        print(f"  ✓ Distribution: {distribution_id} - OK")
                    except ClientError as err:
                        if err.response["Error"]["Code"] == "NoSuchDistribution":
                            print(f"  ✗ Distribution: {distribution_id} - Does not exist")
                        else:
                            print(f"  ✗ Distribution: {distribution_id} - Error: {err}")
                        all_valid = False
                else:
                    print("  ⚠ Distribution: Not configured")

        # Generate drift report if needed
        drift_count = sum(1 for r in validation_results.values() if r.drift_detected)
        if drift_count > 0:
            print("\n" + generate_drift_report(validation_results))

            if fix_drift:
                print("\n[INFO] Drift correction requested. Run deployment to fix configuration drift.")

        # Summary
        print(f"\n{'='*60}")
        print("VALIDATION SUMMARY")
        print(f"{'='*60}")

        total_resources = len(validation_results)
        existing_resources = sum(1 for r in validation_results.values() if r.exists)
        valid_resources = sum(1 for r in validation_results.values() if r.valid)

        print(f"Total resources checked: {total_resources}")
        print(f"Existing resources: {existing_resources}")
        print(f"Valid resources: {valid_resources}")
        print(f"Resources with drift: {drift_count}")

        if all_valid:
            print("\n✓ All configured resources are present and valid!")
        else:
            missing = total_resources - existing_resources
            print(f"\n✗ Validation failed: {missing} missing resource(s)")
            print("\nRun deployment to create missing resources.")

        return all_valid

    def update_configuration(self, params: dict) -> None:
        """Update server configuration file with deployment outputs.

        Args:
            params: Deployment parameters
        """
        print("\nUpdating server configuration...")

        # Get stack outputs and update configuration
        stacks_to_query = [
            "cognito",
            "dynamodb",
            "cloudwatch",
            "s3",
            "cloudfront",
            "codebuild",
            "iam",
            "lambda",
        ]

        for stack_name in stacks_to_query:
            try:
                outputs = self.stack_helper.get_outputs(stack_name)
                if outputs:
                    self.config_updater.update_from_stack_outputs(stack_name, outputs)
            except Exception as err:
                print(f"Warning: Could not get outputs for {stack_name}: {err}")

        # Update game config
        self.config_updater.update_game_config(params["game_name"])

        # Add buildspec path if it was provided
        if "portal_buildspec_path" in params:
            self.config_manager.update_section("CodeBuild", {"PortalBuildspecPath": params["portal_buildspec_path"]})

        # Save configuration
        config_path = self.config_updater.save_configuration()
        print(f"[OK] Configuration saved to {config_path}")

    def deploy_scripts(self, params: dict) -> bool:
        """Deploy Lua scripts to S3.

        Args:
            params: Deployment parameters

        Returns:
            True if deployment succeeded
        """
        print("\nDeploying Lua scripts...")

        # Get S3 bucket name from parameters or config
        bucket_name = params.get("scripts_bucket_name", params.get("scripts_s3_bucket", "eidolon-scripts"))
        prefix = params.get("scripts_s3_prefix", "scripts")

        scripts_dir = Path(__file__).parent.parent / "scripts_lua"
        if not scripts_dir.exists():
            print(f"Warning: Scripts directory not found at {scripts_dir}")
            return True

        try:
            # Check if bucket exists
            self.s3_client.head_bucket(Bucket=bucket_name)

            # Upload scripts
            lua_files = list(scripts_dir.glob("*.lua"))
            if not lua_files:
                print("No Lua scripts found to deploy")
                return True

            print(f"Deploying {len(lua_files)} scripts to s3://{bucket_name}/{prefix}/")

            for lua_file in lua_files:
                key = f"{prefix}/{lua_file.name}"
                with open(lua_file, "rb") as f:
                    self.s3_client.put_object(Bucket=bucket_name, Key=key, Body=f, ContentType="text/x-lua")
                print(f"  [OK] Uploaded {lua_file.name}")

            return True

        except ClientError as err:
            print(f"Error deploying scripts: {err}")
            return False

    def run(
        self,
        auto_approve: bool = False,
        skip_scripts: bool = False,
        analyze_only: bool = False,
        deploy_mud: bool = False,
        deploy_incremental: bool = False,
        deploy_both: bool = False,
        non_interactive: bool = False,
    ) -> bool:
        """Run the deployment following the desired order of operations.

        Order:
        1. Check AWS account access
        2. Check for config.yml
        3. If exists, validate resources and update config with current state
        4. Deploy/update infrastructure
        5. Build Lambda functions and portal
        6. Update Lambda functions
        7. Provide final config.yml

        Args:
            auto_approve: Skip confirmation prompts
            skip_scripts: Skip Lua script deployment
            analyze_only: Only analyze, don't deploy
            deploy_mud: Deploy only MUD infrastructure
            deploy_incremental: Deploy only Incremental infrastructure
            deploy_both: Deploy both infrastructures
            non_interactive: Run in non-interactive mode

        Returns:
            True if deployment succeeded
        """
        # Set non-interactive mode in environment
        if non_interactive:
            os.environ["NON_INTERACTIVE"] = "1"

        # Show welcome message in interactive mode
        if not non_interactive and not analyze_only:
            print("========================================================")
            print("         EIDOLON ENGINE DEPLOYMENT WIZARD             ")
            print("========================================================")
            print(f"\nRegion: {self.region}")
            print("This wizard will guide you through deploying the")
            print("Eidolon Engine infrastructure to AWS.\n")

        # Step 1: Check AWS account access
        print("\n[Step 1/7] Checking AWS account access...")
        if not self._check_aws_access():
            print("\n[ERROR] Cannot access AWS account. Please check your credentials.")
            return False
        print("✓ AWS access confirmed")

        # Step 2: Check for config.yml
        print("\n[Step 2/7] Checking for existing configuration...")
        config_exists = self.config_manager.exists()

        if config_exists:
            print("✓ Found existing config.yml")

            # Step 3: Validate existing resources and update config
            print("\n[Step 3/7] Validating existing resources...")
            validation_passed = self.validate_configuration(fix_drift=False)

            # Update config with current state from AWS
            print("\nUpdating configuration with current AWS state...")
            self._update_config_from_aws()
            self.config_manager.save_config()
            print("✓ Configuration updated with current state")
        else:
            print("⚠ No config.yml found, will create from template")
            template_path = Path(__file__).parent / "../config.template.yml"
            if template_path.exists():
                print("✓ Initializing configuration from template...")
                self.config_manager.merge_with_template(str(template_path))
            validation_passed = False

        # Load and validate parameters
        params = self.load_parameters()

        # Handle deployment type selection
        params = self.handle_deployment_selection(params, deploy_mud, deploy_incremental, deploy_both, non_interactive)

        if not auto_approve and not analyze_only and not non_interactive:
            params = prompt_missing_parameters(params)

        # Validate configuration before proceeding
        validation_errors = validate_deployment_config(params)
        if validation_errors:
            print("\n[ERROR] Configuration validation failed:")
            for error in validation_errors:
                print(f"  - {error}")
            print("\nPlease fix these issues and try again.")
            return False

        # Analyze what needs to be deployed
        plan = analyze_changes(self.cfn_client, self.session, params)

        # If analyze-only, stop here
        if analyze_only:
            print("\n=== ANALYSIS COMPLETE ===")
            if not validation_passed:
                print("⚠ Resource validation showed missing or invalid resources")
            print("Run without --analyze-only to proceed with deployment.")
            return True

        # Step 4: Deploy/update infrastructure (includes build execution)
        print("\n[Step 4/7] Deploying infrastructure...")
        if not self.execute_deployment(plan, auto_approve):
            return False

        # Step 5: Build execution is now part of phased deployment
        print("\n[Step 5/7] Build execution completed during deployment")

        # Step 6: Lambda functions already updated during deployment
        print("\n[Step 6/7] Lambda functions updated during deployment")

        # Deploy scripts if requested
        if not skip_scripts:
            self.deploy_scripts(params)

        # Step 7: Final configuration update
        print("\n[Step 7/7] Finalizing configuration...")
        self._update_config_from_aws()
        self.config_manager.save_config()
        print(f"✓ Final configuration saved to: {self.config_manager.config_path}")

        # Show deployment summary
        print("\n========================================================")
        print("            DEPLOYMENT COMPLETED SUCCESSFULLY          ")
        print("========================================================")

        deployment_mode = params.get("deployment_mode", "hybrid")
        if deployment_mode == "mud":
            print("\n[OK] Unified backend infrastructure deployed")
            print("[OK] Frontend: Portal (MUD mode)")
        elif deployment_mode == "incremental":
            print("\n[OK] Unified backend infrastructure deployed")
            print("[OK] Frontend: Incremental")
        elif deployment_mode == "hybrid":
            print("\n[OK] Unified backend infrastructure deployed")
            print("[OK] Frontend: Incremental (supports both MUD and Incremental modes)")

        print(f"\nConfiguration file: {self.config_manager.config_path}")
        print("\nDeployment complete! Your infrastructure is ready.")

        # Final validation
        print("\nRunning final validation...")
        if self.validate_configuration(fix_drift=False):
            print("✓ All resources validated successfully!")
        else:
            print("⚠ Some resources may need attention. Run with --validate for details.")

        return True

    def _check_aws_access(self) -> bool:
        """Check if we have access to AWS account.

        Returns:
            True if AWS access is available
        """
        try:
            # Try to get caller identity
            sts_client = self.session.client("sts")
            response = sts_client.get_caller_identity()

            account_id = response.get("Account", "Unknown")
            user_arn = response.get("Arn", "Unknown")

            print(f"  Account ID: {account_id}")
            print(f"  User/Role: {user_arn}")

            # Set account ID in environment for CDK
            os.environ["CDK_DEFAULT_ACCOUNT"] = account_id

            return True
        except ClientError as err:
            print(f"  Error: {err}")
            return False
        except Exception as err:
            print(f"  Unexpected error: {err}")
            return False

    def _update_config_from_aws(self) -> None:
        """Update configuration with current state from AWS.

        This queries AWS for actual resource names/IDs and updates config.yml
        """
        print("  Querying AWS for current resource state...")

        # Get all CloudFormation stacks
        try:
            stacks = []
            paginator = self.cfn_client.get_paginator("describe_stacks")
            for page in paginator.paginate():
                for stack in page.get("Stacks", []):
                    if stack["StackStatus"] in ["CREATE_COMPLETE", "UPDATE_COMPLETE"]:
                        stacks.append(stack)

            # Update config from stack outputs
            for stack in stacks:
                stack_name = stack["StackName"]
                outputs = {}
                for output in stack.get("Outputs", []):
                    outputs[output["OutputKey"]] = output["OutputValue"]

                if outputs:
                    self._update_config_from_stack_outputs(stack_name, outputs)

        except Exception as err:
            print(f"  Warning: Could not query CloudFormation stacks: {err}")

        # Also check for resources outside of CloudFormation
        self._check_standalone_resources()

    def _update_config_from_stack_outputs(self, stack_name: str, outputs: dict) -> None:
        """Update configuration based on CloudFormation stack outputs.

        Args:
            stack_name: Name of the stack
            outputs: Stack outputs dictionary
        """
        # Use the configuration updater to handle all stack types
        self.config_updater.update_from_stack_outputs(stack_name, outputs)

    def _check_standalone_resources(self) -> None:
        """Check for resources that might exist outside CloudFormation."""
        # Check for S3 buckets by common naming patterns
        try:
            s3_client = self.session.client("s3")
            response = s3_client.list_buckets()

            for bucket in response.get("Buckets", []):
                bucket_name = bucket["Name"]
                if "portal" in bucket_name or "scripts" in bucket_name:
                    # Update config if these buckets aren't already configured
                    current_portal = self.config_manager.config.get("S3", {}).get("PortalBucket", "")
                    current_scripts = self.config_manager.config.get("S3", {}).get("ScriptsBucket", "")

                    if not current_portal and "portal" in bucket_name:
                        self.config_manager.update_section("S3", {"PortalBucket": bucket_name})
                        print(f"  Found portal bucket: {bucket_name}")
                    elif not current_scripts and "scripts" in bucket_name:
                        self.config_manager.update_section("S3", {"ScriptsBucket": bucket_name})
                        print(f"  Found scripts bucket: {bucket_name}")

        except Exception:
            pass  # Ignore errors in standalone resource checking

    def _update_lambda_functions_from_s3(self, lambda_bucket: str):
        """Update all Lambda functions to use latest code from S3.

        Args:
            lambda_bucket: S3 bucket containing Lambda deployment packages
        """
        print("\n  Updating Lambda functions with latest code from S3...")

        lambda_client = self.aws_factory.get_client("lambda")
        s3_client = self.aws_factory.get_client("s3")

        # List all Lambda function ZIPs in the S3 bucket
        try:
            response = s3_client.list_objects_v2(Bucket=lambda_bucket)
            if "Contents" not in response:
                print("    ⚠ No objects found in Lambda bucket")
                return

            # Filter for .zip files (excluding the lambda-layer directory)
            lambda_artifacts = [
                obj["Key"]
                for obj in response["Contents"]
                if obj["Key"].endswith(".zip") and not obj["Key"].startswith("lambda-layer/")
            ]

            if not lambda_artifacts:
                print("    ⚠ No Lambda function ZIPs found in bucket")
                return

            print(f"    Found {len(lambda_artifacts)} Lambda function(s) to update")

            # First, list all Lambda functions to find the actual names
            print("    Discovering Lambda function names...")
            try:
                paginator = lambda_client.get_paginator("list_functions")
                all_functions = []
                for page in paginator.paginate():
                    all_functions.extend(page["Functions"])

                # Create a mapping from artifact name to actual function name
                function_mapping = {}
                for artifact in lambda_artifacts:
                    # Remove .zip extension to get function name
                    # e.g., "api-get-archetypes.zip" -> "api-get-archetypes"
                    expected_name = artifact.replace(".zip", "")

                    # Check if this exact function exists
                    for func in all_functions:
                        if func["FunctionName"] == expected_name:
                            function_mapping[artifact] = func["FunctionName"]
                            break

                if not function_mapping:
                    print("    ⚠ No matching Lambda functions found")
                    return

                # Update the functions we found
                updated_count = 0
                for artifact, func_name in function_mapping.items():
                    try:
                        # Update function code
                        lambda_client.update_function_code(FunctionName=func_name, S3Bucket=lambda_bucket, S3Key=artifact)
                        print(f"    ✓ Updated {func_name}")
                        updated_count += 1
                    except ClientError as err:
                        print(f"    ✗ Failed to update {func_name}: {err}")
                    except Exception as err:
                        print(f"    ✗ Error updating {func_name}: {err}")

                print(f"    Successfully updated {updated_count} Lambda function(s)")

            except Exception as err:
                print(f"    ✗ Error listing Lambda functions: {err}")

        except ClientError as err:
            print(f"    ✗ Failed to list objects in bucket {lambda_bucket}: {err}")
        except Exception as err:
            print(f"    ✗ Unexpected error: {err}")

    def configure_cognito_triggers(self) -> None:
        """Configure Cognito user pool Lambda triggers and email verification using boto3.

        This is done post-deployment to avoid circular dependencies in CDK.
        """
        print("\n  Configuring Cognito settings...")

        try:
            cognito_client = self.session.client("cognito-idp")
            lambda_client = self.session.client("lambda")

            # Get user pool ID from config
            user_pool_id = self.config_manager.config.get("Cognito", {}).get("UserPoolId", "")
            if not user_pool_id:
                print("    Cognito User Pool ID not found, skipping configuration")
                return

            # Check if Lambda functions exist
            new_player_function = "cognito-new-player"
            delete_player_function = "cognito-delete-player"

            try:
                # Get function ARNs
                new_player_response = lambda_client.get_function(FunctionName=new_player_function)
                new_player_arn = new_player_response["Configuration"]["FunctionArn"]

                delete_player_response = lambda_client.get_function(FunctionName=delete_player_function)
                delete_player_arn = delete_player_response["Configuration"]["FunctionArn"]

                # First, add permissions for Cognito to invoke the Lambda functions
                print("    Adding permissions for Cognito to invoke Lambda functions...")

                # Add permission for PostConfirmation trigger
                try:
                    lambda_client.add_permission(
                        FunctionName=new_player_function,
                        StatementId="CognitoPostConfirmationInvoke",
                        Action="lambda:InvokeFunction",
                        Principal="cognito-idp.amazonaws.com",
                        SourceArn=f"arn:aws:cognito-idp:{self.region}:{self.session.client('sts').get_caller_identity()['Account']}:userpool/{user_pool_id}",
                    )
                    print(f"    Added permission for {new_player_function}")
                except lambda_client.exceptions.ResourceConflictException:
                    print(f"    Permission already exists for {new_player_function}")

                # Update user pool with triggers and email verification
                print(f"    Setting PostConfirmation trigger to {new_player_function}...")
                print("    Enabling email auto-verification...")
                cognito_client.update_user_pool(
                    UserPoolId=user_pool_id,
                    AutoVerifiedAttributes=["email"],  # Enable email verification
                    LambdaConfig={
                        "PostConfirmation": new_player_arn
                        # Could add PreSignUp, CustomMessage, etc. triggers here
                    },
                )

                print("    Cognito settings configured successfully")

            except lambda_client.exceptions.ResourceNotFoundException as err:
                print(f"    Lambda function not found: {err}")
                print("    Triggers will need to be configured manually")

        except Exception as err:
            print(f"    Error configuring Cognito: {err}")
            print("    Settings will need to be configured manually")

    def update_s3_bucket_policy_for_cloudfront(self, parameters: dict):
        """Update S3 bucket policy to allow CloudFront access.

        Args:
            parameters: Deployment parameters containing bucket and distribution info
        """
        print("\n  Updating CloudFront configuration and S3 bucket policy...")

        # Initialize variables outside try block
        bucket_name = ""

        try:
            # Get bucket name from config
            bucket_name = self.config_manager.config.get("S3", {}).get("PortalBucket", "")
            if not bucket_name:
                print("    Portal bucket not configured, skipping policy update")
                return

            # Get distribution ID from config
            distribution_id = self.config_manager.config.get("CloudFront", {}).get("distribution_id", "")
            if not distribution_id:
                print("    CloudFront distribution ID not found, skipping policy update")
                return

            # Get account ID
            account_id = self.aws_factory.get_account_id()

            # Get CloudFront client
            cf_client = self.session.client("cloudfront", region_name="us-east-1")
            s3_client = self.session.client("s3")

            # Get current distribution configuration
            print("    Checking CloudFront distribution configuration...")
            dist_response = cf_client.get_distribution(Id=distribution_id)
            dist_config = dist_response["Distribution"]["DistributionConfig"]
            etag = dist_response["ETag"]

            # Track if we need to update the distribution
            needs_distribution_update = False
            
            # Check if OAI already exists in the distribution
            oai_id = None
            origin_to_update = None
            print(f"    Looking for origin matching bucket: {bucket_name}")
            for i, origin in enumerate(dist_config["Origins"]["Items"]):
                # Check if this is the S3 origin for our bucket
                # CDK might create it with various domain patterns
                domain_name = origin["DomainName"]
                print(f"      Checking origin {i}: {domain_name}")
                if (domain_name.startswith(f"{bucket_name}.s3") or 
                    domain_name == f"{bucket_name}.s3.amazonaws.com" or
                    domain_name.startswith(f"{bucket_name}.s3-")):
                    origin_to_update = i
                    print(f"      Found matching origin at index {i}")
                    # Check if it has S3OriginConfig (it might be a CustomOriginConfig)
                    if "S3OriginConfig" in origin:
                        oai_config = origin["S3OriginConfig"]
                        oai_value = oai_config.get("OriginAccessIdentity", "")
                        if oai_value:
                            # Extract OAI ID from the full path
                            oai_id = oai_value.split("/")[-1]
                            print(f"      Origin already has OAI: {oai_id}")
                        else:
                            print("      Origin has S3OriginConfig but no OAI")
                            needs_distribution_update = True
                    else:
                        # Origin exists but doesn't have S3OriginConfig - needs to be converted
                        print(f"      Origin lacks S3OriginConfig, has: {list(origin.keys())}")
                        needs_distribution_update = True
                    break
            
            if origin_to_update is None:
                print(f"    WARNING: No origin found for bucket {bucket_name}")
                print("    Available origins:")
                for i, origin in enumerate(dist_config["Origins"]["Items"]):
                    print(f"      {i}: {origin['DomainName']}")

            # Create OAI if it doesn't exist
            if not oai_id:
                print("    Creating Origin Access Identity...")
                try:
                    oai_response = cf_client.create_cloud_front_origin_access_identity(
                        CloudFrontOriginAccessIdentityConfig={
                            "CallerReference": f"eidolon-portal-oai-{distribution_id}",
                            "Comment": "OAI for Eidolon portal S3 access",
                        }
                    )
                    oai_id = oai_response["CloudFrontOriginAccessIdentity"]["Id"]
                    print(f"    Created OAI: {oai_id}")
                    needs_distribution_update = True
                except ClientError as err:
                    if err.response.get("Error", {}).get("Code") == "CloudFrontOriginAccessIdentityAlreadyExists":
                        # OAI with this caller reference already exists, try to find it
                        print("    OAI already exists, searching for existing OAI...")
                        paginator = cf_client.get_paginator("list_cloud_front_origin_access_identities")
                        for page in paginator.paginate():
                            for item in page.get("CloudFrontOriginAccessIdentityList", {}).get("Items", []):
                                if item.get("Comment") == "OAI for Eidolon portal S3 access":
                                    oai_id = item.get("Id")
                                    print(f"    Found existing OAI: {oai_id}")
                                    needs_distribution_update = True
                                    break
                            if oai_id:
                                break
                        if not oai_id:
                            print("    ERROR: Could not find existing OAI")
                            print(f"    Please manually check CloudFront OAIs for: {distribution_id}")
                            return
                    else:
                        print(f"    ERROR: Failed to create OAI: {err}")
                        return

            # Update distribution to use the OAI if needed
            if needs_distribution_update and origin_to_update is not None and oai_id:
                print("    Updating CloudFront distribution to use OAI...")
                # Remove CustomOriginConfig if it exists
                if "CustomOriginConfig" in dist_config["Origins"]["Items"][origin_to_update]:
                    del dist_config["Origins"]["Items"][origin_to_update]["CustomOriginConfig"]
                # Set S3OriginConfig with OAI
                dist_config["Origins"]["Items"][origin_to_update]["S3OriginConfig"] = {
                    "OriginAccessIdentity": f"origin-access-identity/cloudfront/{oai_id}"
                }

                # Update the distribution
                try:
                    cf_client.update_distribution(DistributionConfig=dist_config, Id=distribution_id, IfMatch=etag)
                    print("    Updated CloudFront distribution to use OAI")
                except Exception as err:
                    print(f"    Failed to update distribution: {err}")
                    print("      Continuing with bucket policy update...")
            else:
                if oai_id:
                    print(f"    Found existing OAI: {oai_id}")

            # Wait a moment for distribution update to propagate if we just updated it
            if needs_distribution_update:
                print("    Waiting for distribution update to propagate...")
                import time

                time.sleep(5)

            # Always replace S3 bucket policy with the correct one
            print("\n    Replacing S3 bucket policy...")
            print(f"    Distribution ID: {distribution_id}")
            print(f"    OAI ID: {oai_id if oai_id else 'None'}")

            # Delete existing bucket policy first to ensure clean state
            try:
                s3_client.delete_bucket_policy(Bucket=bucket_name)
                print("    Deleted existing bucket policy")
            except ClientError as err:
                if err.response.get("Error", {}).get("Code") != "NoSuchBucketPolicy":
                    print(f"    Note: Could not delete existing policy: {err}")
            
            # Only create and apply new policy if we have an OAI
            if oai_id:
                # Create policy statements
                statements = [
                    {
                        "Sid": "AllowCloudFrontOAI",
                        "Effect": "Allow",
                        "Principal": {"AWS": f"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity {oai_id}"},
                        "Action": "s3:GetObject",
                        "Resource": f"arn:aws:s3:::{bucket_name}/*",
                    }
                ]
                
                # Create the complete policy
                policy: dict = {"Version": "2012-10-17", "Statement": statements}
                
                # Apply the policy
                s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
                print(f"    Applied new bucket policy")
            else:
                print("    WARNING: No OAI found - bucket will not be accessible via CloudFront!")
                print("    The CloudFront distribution may need to be reconfigured")

            print(f"    Updated bucket policy for {bucket_name}")
            print(f"      - CloudFront distribution {distribution_id} now has access")
            if oai_id:
                print(f"      - OAI {oai_id} also has access")

        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "NoSuchBucket":
                print(f"    Bucket {bucket_name} not found")
            else:
                print(f"    Failed to update bucket policy: {err}")
        except Exception as err:
            print(f"    Error updating bucket policy: {err}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Incremental deployment for Eidolon Engine infrastructure")
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--auto-approve", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--skip-scripts", action="store_true", help="Skip Lua script deployment")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze existing infrastructure, don't deploy")
    parser.add_argument("--deploy-mud", action="store_true", help="Deploy only MUD infrastructure")
    parser.add_argument("--deploy-incremental", action="store_true", help="Deploy only Incremental infrastructure")
    parser.add_argument("--deploy-both", action="store_true", help="Deploy both MUD and Incremental infrastructure (default)")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode")
    parser.add_argument("--validate", action="store_true", help="Validate config.yml against AWS resources")
    parser.add_argument("--fix-drift", action="store_true", help="Attempt to fix configuration drift (use with --validate)")
    parser.add_argument("--branch", help="GitHub branch to deploy from (default: develop)")

    args = parser.parse_args()

    try:
        orchestrator = IncrementalDeploymentOrchestrator(profile=args.profile, region=args.region, branch=args.branch)
    except CDKDeploymentError as e:
        # Check if this is specifically the CDK not installed error
        if "AWS CDK CLI is not installed" in str(e):
            print("\n❌ AWS CDK is not installed on your system.")
            print("\nTo install AWS CDK, you need Node.js installed first, then run:")
            print("  npm install -g aws-cdk")
            print("\nFor more information, visit: https://docs.aws.amazon.com/cdk/latest/guide/getting_started.html")
            sys.exit(1)
        else:
            # Re-raise other CDK deployment errors
            raise

    # Handle validation mode
    if args.validate:
        success = orchestrator.validate_configuration(fix_drift=args.fix_drift)
    else:
        success = orchestrator.run(
            auto_approve=args.auto_approve,
            skip_scripts=args.skip_scripts,
            analyze_only=args.analyze_only,
            deploy_mud=args.deploy_mud,
            deploy_incremental=args.deploy_incremental,
            deploy_both=args.deploy_both,
            non_interactive=args.non_interactive,
        )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
