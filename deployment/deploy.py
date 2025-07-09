"""Incremental deployment orchestrator for Eidolon Engine infrastructure.

This script manages incremental AWS infrastructure deployments using CDK,
allowing for selective updates without full redeployment.
"""

import argparse
import os
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from build_executor import BuildExecutor
from cdk_api_integration import CDKApiIntegration, CDKDeploymentError, CDKProgressReporter
from deployment_logic import analyze_changes, prompt_missing_parameters
from resource_validator import (
    ResourceValidatorFactory,
    generate_drift_report,
)

from state_manager import ConfigurationManager, DeploymentState


class IncrementalDeploymentOrchestrator:
    """Orchestrates incremental infrastructure deployments."""

    def __init__(self, profile=None, region: str = "us-east-1", branch: str = None):
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

        # Set up AWS session
        session_args = {"region_name": region}
        if profile:
            session_args["profile_name"] = profile
        self.session = boto3.Session(**session_args)

        # Initialize AWS clients
        self.cfn_client = self.session.client("cloudformation")
        self.s3_client = self.session.client("s3")

        # CDK app directory
        self.cdk_dir = Path(__file__).parent / "cdk"

        # Initialize CDK API integration
        self.cdk_api = CDKApiIntegration(cdk_dir=str(self.cdk_dir), profile=profile, region=region)
        
        # Initialize build executor
        self.build_executor = BuildExecutor(self.session)

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met for deployment.

        Returns:
            True if all prerequisites are met
        """
        print("Checking prerequisites...")

        # Check AWS credentials
        try:
            sts = self.session.client("sts")
            identity = sts.get_caller_identity()
            print(f"AWS Account: {identity.get('Account', 'Unknown')}")
            print(f"AWS Region: {self.region}")
        except Exception as err:
            print(f"ERROR: Unable to access AWS: {err}")
            return False

        return True

    def load_parameters(self) -> dict:
        """Load deployment parameters from various sources.

        Returns:
            Dictionary of deployment parameters
        """
        params = {
            "game_name": "eidolon-engine",
            "contact_email": None,
            "github_owner": "robinje",
            "github_repo": "eidolon-engine",
            "github_branch": "develop",
            "log_retention_days": 365,
        }

        # Load from saved state
        saved_params = self.state_manager.get_parameters()
        params.update(saved_params)

        # Load from config file (which may have been initialized from template)
        config = self.config_manager.config
        if "Game" in config:
            game_config = config["Game"]
            params["game_name"] = game_config.get("name", params["game_name"])
            # Check for existing S3 buckets
            if "ScriptsS3Bucket" in game_config:
                params["scripts_bucket_name"] = game_config["ScriptsS3Bucket"]
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
            if "PortalS3Bucket" in codebuild_config:
                params["portal_bucket_name"] = codebuild_config["PortalS3Bucket"]

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

            choice = input("\nSelect deployment mode [1-3] (default: 3): ").strip()

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
        self.config_manager.update_section(
            "Deployment", {"Mode": params.get("deployment_mode", "hybrid")}
        )

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
        context = {}

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
        phases = [
            {
                "name": "Foundation",
                "stacks": ["iam", "s3", "dynamodb"],
                "description": "IAM roles, S3 buckets, and DynamoDB tables"
            },
            {
                "name": "Authentication & Monitoring",
                "stacks": ["cognito", "cloudwatch"],
                "description": "User authentication and logging infrastructure"
            },
            {
                "name": "Build Infrastructure",
                "stacks": ["codebuild"],
                "description": "CodeBuild projects for Lambda and portal builds"
            },
            {
                "name": "Build Execution",
                "stacks": [],  # No stacks, just build execution
                "description": "Execute CodeBuild projects to create deployment artifacts",
                "execute_builds": True
            },
            {
                "name": "Application Layer",
                "stacks": ["base-lambda", "lambda", "cognito-trigger"],
                "description": "Lambda functions and API Gateway"
            },
            {
                "name": "Distribution",
                "stacks": ["cloudfront"],
                "description": "CloudFront distribution for content delivery"
            }
        ]
        
        # Track overall success
        all_succeeded = True
        completed_phases = []
        
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
                stacks_to_deploy = [
                    stack for stack in phase_stacks 
                    if stack in plan.get("create_stacks", []) + plan.get("update_stacks", [])
                ]
                
                if not stacks_to_deploy:
                    print(f"No stacks to deploy in this phase")
                    completed_phases.append(phase["name"])
                    continue
                
                print(f"\nDeploying stacks: {', '.join(stacks_to_deploy)}")
                
                # Deploy phase stacks
                progress_reporter = CDKProgressReporter()
                result = self.cdk_api.deploy(
                    stacks=stacks_to_deploy,
                    context=context,
                    require_approval="never" if auto_approve else "broadening",
                    progress_callback=progress_reporter,
                )
                
                if result["success"]:
                    print(f"\n[SUCCESS] Phase {i} ({phase['name']}) completed successfully!")
                    completed_phases.append(phase["name"])
                    
                    # Update state after each phase
                    self.state_manager.add_deployment_event(
                        f"phase_{phase['name'].lower().replace(' ', '_')}_complete",
                        {
                            "stacks_deployed": stacks_to_deploy,
                            "outputs": result.get("outputs", {})
                        }
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
            print(f"  ✓ {phase_name}")
        
        if all_succeeded:
            print("\n[SUCCESS] All deployment phases completed successfully!")
            
            # Update configuration file with outputs
            self.update_configuration(plan["parameters"])
            
            # Record deployment completion
            self.state_manager.add_deployment_event(
                "deployment_complete",
                {
                    "phases_completed": completed_phases,
                    "total_phases": len(phases)
                }
            )
            self.state_manager.save_state()
        else:
            print("\n[ERROR] Deployment failed!")
            print("You can resume deployment by running the command again.")
            
        return all_succeeded
    
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
            
            # Execute Lambda builds first (dependencies before functions)
            if lambda_projects:
                print("\nExecuting Lambda builds sequentially...")
                if not self.build_executor.execute_builds(lambda_projects, parallel=False):
                    return False
                    
            # Execute portal/incremental builds
            if portal_projects:
                print("\nExecuting portal/incremental builds...")
                if not self.build_executor.execute_builds(portal_projects, parallel=True):
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
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            if response["Stacks"]:
                stack = response["Stacks"][0]
                outputs = {}
                for output in stack.get("Outputs", []):
                    outputs[output["OutputKey"]] = output["OutputValue"]
                return outputs
        except ClientError:
            pass
        return {}
    
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
                    
                result = validator.validate(table_name, {
                    "billing_mode": "PAY_PER_REQUEST"
                })
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
            
            user_pool_id = config["Cognito"].get("user_pool_id", "")
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
        if "Game" in config or "S3" in config:
            print("\nChecking S3 buckets...")
            validator = ResourceValidatorFactory.create_validator("s3_bucket", self.session)
            
            # Check portal bucket
            portal_bucket = config.get("Game", {}).get("PortalS3Bucket", "") or config.get("S3", {}).get("PortalBucket", "")
            if portal_bucket:
                result = validator.validate(portal_bucket, {})
                validation_results[f"S3:{portal_bucket}"] = result
                
                if result.exists and result.valid:
                    print(f"  ✓ Portal Bucket: {portal_bucket} - OK")
                else:
                    print(f"  ✗ Portal Bucket: {portal_bucket} - {'Access denied' if result.exists else 'Does not exist'}")
                    all_valid = False
                    
            # Check scripts bucket
            scripts_bucket = config.get("Game", {}).get("ScriptsS3Bucket", "") or config.get("S3", {}).get("ScriptsBucket", "")
            if scripts_bucket:
                result = validator.validate(scripts_bucket, {})
                validation_results[f"S3:{scripts_bucket}"] = result
                
                if result.exists and result.valid:
                    print(f"  ✓ Scripts Bucket: {scripts_bucket} - OK")
                else:
                    print(f"  ✗ Scripts Bucket: {scripts_bucket} - {'Access denied' if result.exists else 'Does not exist'}")
                    all_valid = False
                    
        # Validate CloudWatch Log Groups
        if "CloudWatch" in config or "Logging" in config:
            print("\nChecking CloudWatch log groups...")
            validator = ResourceValidatorFactory.create_validator("cloudwatch_log_group", self.session)
            
            log_group = config.get("CloudWatch", {}).get("log_group", "") or config.get("Logging", {}).get("LogGroup", "")
            if log_group:
                result = validator.validate(log_group, {
                    "retention_days": config.get("CloudWatch", {}).get("LogRetentionDays", 365)
                })
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
                    
        # Validate CloudFront Distribution
        if "CloudFront" in config:
            print("\nChecking CloudFront distribution...")
            distribution_id = config["CloudFront"].get("distribution_id", "")
            if distribution_id:
                try:
                    cf_client = self.session.client('cloudfront')
                    cf_client.get_distribution(Id=distribution_id)
                    print(f"  ✓ Distribution: {distribution_id} - OK")
                except ClientError as e:
                    if e.response['Error']['Code'] == 'NoSuchDistribution':
                        print(f"  ✗ Distribution: {distribution_id} - Does not exist")
                    else:
                        print(f"  ✗ Distribution: {distribution_id} - Error: {e}")
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

        # Get stack outputs
        game_name = params["game_name"]
        stacks_to_query = [
            f"{game_name}-cognito",
            f"{game_name}-dynamodb",
            f"{game_name}-cloudwatch",
            f"{game_name}-s3",
            f"{game_name}-cloudfront",
            f"{game_name}-codebuild",
            f"{game_name}-iam",
            f"{game_name}-lambda",
        ]

        for stack_name in stacks_to_query:
            try:
                response = self.cfn_client.describe_stacks(StackName=stack_name)
                stack = response.get("Stacks", [{}])[0]
                outputs = {output.get("OutputKey"): output.get("OutputValue") for output in stack.get("Outputs", [])}

                # Update config based on stack type
                if "cognito" in stack_name:
                    self.config_manager.update_section(
                        "Cognito",
                        {
                            "UserPoolId": outputs.get("UserPoolId", ""),
                            "UserPoolClientId": outputs.get("AppClientId", ""),
                        },
                    )
                elif "dynamodb" in stack_name:
                    # Extract table names
                    tables = {}
                    for key, value in outputs.items():
                        if key.endswith("TableName"):
                            # Convert PlayersTableName -> Players, CharactersTableName -> Characters, etc.
                            table_type = key.replace("TableName", "")
                            tables[table_type] = value
                    self.config_manager.update_section(
                        "DynamoDB", {"Tables": tables, "AccessPolicyArn": outputs.get("DynamoDBAccessPolicyArn", "")}
                    )
                elif "cloudwatch" in stack_name:
                    self.config_manager.update_section(
                        "Logging",
                        {
                            "LogGroup": outputs.get("LogGroupName", ""),
                            "MetricNamespace": outputs.get("MetricsNamespace", ""),
                        },
                    )
                    self.config_manager.update_section(
                        "CloudWatch", {"AccessPolicyArn": outputs.get("CloudWatchAccessPolicyArn", "")}
                    )
                elif "s3" in stack_name:
                    # Update S3 bucket names in config
                    self.config_manager.update_section(
                        "Game",
                        {
                            "ScriptsS3Bucket": outputs.get("ScriptsBucketName", ""),
                            "ScriptsS3Prefix": "scripts",
                        },
                    )
                    # Update CodeBuild with portal bucket
                    self.config_manager.update_section(
                        "CodeBuild",
                        {
                            "PortalS3Bucket": outputs.get("PortalBucketName", ""),
                        },
                    )
                elif "cloudfront" in stack_name:
                    # Update CloudFront configuration
                    self.config_manager.update_section(
                        "CloudFront",
                        {
                            "distribution_id": outputs.get("DistributionId", ""),
                            "domain_name": outputs.get("DistributionDomainName", ""),
                            "portal_url": outputs.get("PortalUrl", ""),
                        },
                    )
                elif "codebuild" in stack_name:
                    # Update CodeBuild configuration
                    codebuild_config = {"ProjectName": outputs.get("CodeBuildProjectName", "")}
                    # Add buildspec path if it was provided
                    if "portal_buildspec_path" in params:
                        codebuild_config["PortalBuildspecPath"] = params["portal_buildspec_path"]
                    self.config_manager.update_section("CodeBuild", codebuild_config)
                elif "iam" in stack_name:
                    # Update AWS configuration with server execution role
                    self.config_manager.update_section(
                        "AWS",
                        {
                            "ServerExecutionRoleArn": outputs.get("ServerExecutionRoleArn", ""),
                        },
                    )

            except Exception as err:
                print(f"Warning: Could not get outputs for {stack_name}: {err}")

        # Update game config
        self.config_manager.update_section("Game", {"name": params["game_name"]})

        # Save configuration
        self.config_manager.save_config()
        print(f"[OK] Configuration saved to {self.config_manager.config_path}")

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
            sts_client = self.session.client('sts')
            response = sts_client.get_caller_identity()
            
            account_id = response.get('Account', 'Unknown')
            user_arn = response.get('Arn', 'Unknown')
            
            print(f"  Account ID: {account_id}")
            print(f"  User/Role: {user_arn}")
            
            # Set account ID in environment for CDK
            os.environ['CDK_DEFAULT_ACCOUNT'] = account_id
            
            return True
        except ClientError as e:
            print(f"  Error: {e}")
            return False
        except Exception as e:
            print(f"  Unexpected error: {e}")
            return False
            
    def _update_config_from_aws(self) -> None:
        """Update configuration with current state from AWS.
        
        This queries AWS for actual resource names/IDs and updates config.yml
        """
        print("  Querying AWS for current resource state...")
        
        # Get all CloudFormation stacks
        try:
            stacks = []
            paginator = self.cfn_client.get_paginator('describe_stacks')
            for page in paginator.paginate():
                for stack in page.get('Stacks', []):
                    if stack['StackStatus'] in ['CREATE_COMPLETE', 'UPDATE_COMPLETE']:
                        stacks.append(stack)
            
            # Update config from stack outputs
            for stack in stacks:
                stack_name = stack['StackName']
                outputs = {}
                for output in stack.get('Outputs', []):
                    outputs[output['OutputKey']] = output['OutputValue']
                
                if outputs:
                    self._update_config_from_stack_outputs(stack_name, outputs)
                    
        except Exception as e:
            print(f"  Warning: Could not query CloudFormation stacks: {e}")
            
        # Also check for resources outside of CloudFormation
        self._check_standalone_resources()
        
    def _update_config_from_stack_outputs(self, stack_name: str, outputs: dict) -> None:
        """Update configuration based on CloudFormation stack outputs.
        
        Args:
            stack_name: Name of the stack
            outputs: Stack outputs dictionary
        """
        # This reuses the existing logic from update_configuration
        if "cognito" in stack_name:
            self.config_manager.update_section(
                "Cognito",
                {
                    "user_pool_id": outputs.get("UserPoolId", ""),
                    "app_client_id": outputs.get("AppClientId", ""),
                }
            )
        elif "dynamodb" in stack_name:
            # Extract table names
            tables = {}
            for key, value in outputs.items():
                if key.endswith("TableName"):
                    table_type = key.replace("TableName", "")
                    tables[table_type] = value
            if tables:
                self.config_manager.update_section("DynamoDB", {"Tables": tables})
        elif "s3" in stack_name:
            self.config_manager.update_section(
                "Game",
                {
                    "PortalS3Bucket": outputs.get("PortalBucketName", ""),
                    "ScriptsS3Bucket": outputs.get("ScriptsBucketName", ""),
                }
            )
        elif "cloudfront" in stack_name:
            self.config_manager.update_section(
                "CloudFront",
                {
                    "distribution_id": outputs.get("DistributionId", ""),
                    "domain_name": outputs.get("DistributionDomainName", ""),
                    "portal_url": outputs.get("PortalUrl", ""),
                }
            )
        elif "cloudwatch" in stack_name:
            self.config_manager.update_section(
                "CloudWatch",
                {
                    "log_group": outputs.get("LogGroupName", ""),
                    "metrics_namespace": outputs.get("MetricsNamespace", ""),
                }
            )
    
    def _check_standalone_resources(self) -> None:
        """Check for resources that might exist outside CloudFormation."""
        # Check for S3 buckets by common naming patterns
        try:
            s3_client = self.session.client('s3')
            response = s3_client.list_buckets()
            
            for bucket in response.get('Buckets', []):
                bucket_name = bucket['Name']
                if 'portal' in bucket_name or 'scripts' in bucket_name:
                    # Update config if these buckets aren't already configured
                    current_portal = self.config_manager.config.get('Game', {}).get('PortalS3Bucket', '')
                    current_scripts = self.config_manager.config.get('Game', {}).get('ScriptsS3Bucket', '')
                    
                    if not current_portal and 'portal' in bucket_name:
                        self.config_manager.update_section('Game', {'PortalS3Bucket': bucket_name})
                        print(f"  Found portal bucket: {bucket_name}")
                    elif not current_scripts and 'scripts' in bucket_name:
                        self.config_manager.update_section('Game', {'ScriptsS3Bucket': bucket_name})
                        print(f"  Found scripts bucket: {bucket_name}")
                        
        except Exception:
            pass  # Ignore errors in standalone resource checking


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

    orchestrator = IncrementalDeploymentOrchestrator(profile=args.profile, region=args.region, branch=args.branch)

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
