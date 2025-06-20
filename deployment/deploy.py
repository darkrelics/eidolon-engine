"""Incremental deployment orchestrator for Eidolon Engine infrastructure.

This script manages incremental AWS infrastructure deployments using CDK,
allowing for selective updates without full redeployment.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from resource_validator import ResourceValidatorFactory, generate_drift_report
from state_manager import ConfigurationManager, DeploymentState


class IncrementalDeploymentOrchestrator:
    """Orchestrates incremental infrastructure deployments."""

    def __init__(self, profile: str | None = None, region: str = "us-east-1"):
        """Initialize the deployment orchestrator.

        Args:
            profile: AWS profile to use
            region: AWS region for deployment
        """
        self.profile = profile
        self.region = region
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

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met for deployment.

        Returns:
            True if all prerequisites are met
        """
        print("Checking prerequisites...")

        # Check if CDK is installed
        try:
            result = subprocess.run(["cdk", "--version"], capture_output=True, text=True)
            if result.returncode != 0:
                print("ERROR: AWS CDK is not installed. Please install it with: npm install -g aws-cdk")
                return False
            print(f"✓ AWS CDK version: {result.stdout.strip()}")
        except FileNotFoundError:
            print("ERROR: AWS CDK is not installed. Please install it with: npm install -g aws-cdk")
            return False

        # Check AWS credentials
        try:
            sts = self.session.client("sts")
            identity = sts.get_caller_identity()
            print(f"✓ AWS Account: {identity.get('Account', 'Unknown')}")
            print(f"✓ AWS Region: {self.region}")
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
            "github_branch": "main",
            "log_retention_days": 365,
        }

        # Load from saved state
        saved_params = self.state_manager.get_parameters()
        params.update(saved_params)

        # Load from config file
        if self.config_manager.exists():
            config = self.config_manager.config
            if "Game" in config:
                game_config = config["Game"]
                params["game_name"] = game_config.get("name", params["game_name"])
                # Check for existing S3 buckets
                if "PortalS3Bucket" in game_config:
                    params["portal_bucket_name"] = game_config["PortalS3Bucket"]
                if "ScriptsS3Bucket" in game_config:
                    params["scripts_bucket_name"] = game_config["ScriptsS3Bucket"]
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

        return params

    def prompt_missing_parameters(self, params: dict) -> dict:
        """Prompt user for any missing required parameters.

        Args:
            params: Current parameters

        Returns:
            Updated parameters with user input
        """
        required_params = {
            "game_name": "Game name (e.g., eidolon-engine)",
            "contact_email": "Administrator contact email",
            "github_owner": "GitHub repository owner",
            "github_repo": "GitHub repository name",
            "github_branch": "GitHub branch to deploy from",
        }

        for param, description in required_params.items():
            if not params.get(param):
                value = input(f"{description} [{params.get(param, '')}]: ").strip()
                if value:
                    params[param] = value
                elif param in params and params[param]:
                    # Keep existing value
                    pass
                else:
                    print(f"ERROR: {param} is required")
                    sys.exit(1)

        return params

    def get_existing_stacks(self) -> dict:
        """Get information about existing CloudFormation stacks.

        Returns:
            Dictionary of stack name to stack information
        """
        existing_stacks = {}

        try:
            paginator = self.cfn_client.get_paginator("list_stacks")
            for page in paginator.paginate(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"]):
                for stack in page.get("StackSummaries", []):
                    stack_name = stack.get("StackName")
                    # Get detailed stack info
                    try:
                        response = self.cfn_client.describe_stacks(StackName=stack_name)
                        stack_detail = response.get("Stacks", [{}])[0]

                        # Get stack resources for mapping
                        resources_response = self.cfn_client.list_stack_resources(StackName=stack_name)
                        resources = {}
                        for resource in resources_response.get("StackResourceSummaries", []):
                            resources[resource.get("LogicalResourceId")] = {
                                "physical_id": resource.get("PhysicalResourceId"),
                                "type": resource.get("ResourceType"),
                            }

                        existing_stacks[stack_name] = {
                            "status": stack_detail.get("StackStatus"),
                            "outputs": {
                                output.get("OutputKey"): output.get("OutputValue") for output in stack_detail.get("Outputs", [])
                            },
                            "parameters": {
                                param.get("ParameterKey"): param.get("ParameterValue")
                                for param in stack_detail.get("Parameters", [])
                            },
                            "resources": resources,
                            "template_format": "CloudFormation",
                        }
                    except Exception:
                        # Stack might have been deleted between list and describe
                        pass
        except Exception as err:
            print(f"Warning: Error querying existing stacks: {err}")

        return existing_stacks

    def validate_resources(self, params: dict) -> dict:
        """Validate AWS resources for drift detection.

        Args:
            params: Deployment parameters

        Returns:
            Dictionary of resource validation results
        """
        all_results = {}

        # Validate DynamoDB tables
        try:
            validator = ResourceValidatorFactory.create_validator("dynamodb_table", self.session)
            # Use table names from params if provided, otherwise use defaults
            if "dynamodb_tables" in params:
                table_names = list(params["dynamodb_tables"].values())
            else:
                table_names = [
                    "eidolon-players",
                    "eidolon-characters",
                    "eidolon-rooms",
                    "eidolon-exits",
                    "eidolon-items",
                    "eidolon-prototypes",
                    "eidolon-archetypes",
                    "eidolon-motd",
                ]

            for table_name in table_names:
                expected_config = {
                    "billing_mode": "PAY_PER_REQUEST",
                    "point_in_time_recovery": True,
                }
                result = validator.validate(table_name, expected_config)
                all_results[table_name] = result
        except Exception as err:
            print(f"Warning: Error validating DynamoDB tables: {err}")

        # Validate CloudWatch log groups
        try:
            validator = ResourceValidatorFactory.create_validator("cloudwatch_log_group", self.session)
            log_group_name = "/aws/eidolon/server"
            expected_config = {
                "retention_days": params.get("log_retention_days", 365),
            }
            result = validator.validate(log_group_name, expected_config)
            all_results[log_group_name] = result
        except Exception as err:
            print(f"Warning: Error validating CloudWatch log groups: {err}")

        # Validate CodeBuild project
        try:
            validator = ResourceValidatorFactory.create_validator("codebuild_project", self.session)
            project_name = "eidolon-portal-build"
            expected_config = {
                "source_type": "GITHUB",
                "environment": {
                    "compute_type": "BUILD_GENERAL1_SMALL",
                    "type": "LINUX_CONTAINER",
                },
            }
            result = validator.validate(project_name, expected_config)
            all_results[project_name] = result
        except Exception as err:
            print(f"Warning: Error validating CodeBuild project: {err}")

        # Validate S3 buckets
        try:
            validator = ResourceValidatorFactory.create_validator("s3_bucket", self.session)

            # Check portal bucket
            portal_bucket = params.get("portal_bucket_name", "eidolon-portal")
            expected_config = {
                "website_enabled": True,
                "public_access_block": {
                    "block_public_acls": False,
                    "block_public_policy": False,
                    "ignore_public_acls": False,
                    "restrict_public_buckets": False,
                },
            }
            result = validator.validate(portal_bucket, expected_config)
            all_results[portal_bucket] = result

            # Check scripts bucket
            scripts_bucket = params.get("scripts_bucket_name", "eidolon-scripts")
            result = validator.validate(scripts_bucket, expected_config)
            all_results[scripts_bucket] = result
        except Exception as err:
            print(f"Warning: Error validating S3 buckets: {err}")

        return all_results

    def map_cloudformation_to_cdk(self, existing_stacks: dict, params: dict) -> dict:
        """Map existing CloudFormation stacks to CDK stacks.

        Args:
            existing_stacks: Dictionary of existing CloudFormation stacks
            params: Deployment parameters

        Returns:
            Mapping of resources and migration strategy
        """
        mapping = {
            "cloudformation_stacks": {},
            "resource_mapping": {},
            "migration_strategy": "adopt",  # adopt, replace, or coexist
        }

        # Check for legacy CloudFormation stacks
        legacy_stacks = ["eidolon-cognito", "eidolon-dynamodb", "eidolon-cloudwatch", "eidolon-codebuild"]

        for legacy_name in legacy_stacks:
            if legacy_name in existing_stacks:
                stack_info = existing_stacks[legacy_name]
                mapping["cloudformation_stacks"][legacy_name] = {
                    "outputs": stack_info["outputs"],
                    "resources": stack_info["resources"],
                    "can_adopt": self._can_adopt_stack(legacy_name, stack_info),
                }

                # Map resources to CDK expectations
                if legacy_name == "eidolon-cognito":
                    if "UserPoolId" in stack_info.get("outputs", {}):
                        mapping["resource_mapping"]["cognito_user_pool_id"] = stack_info.get("outputs", {}).get("UserPoolId")
                    if "AppClientId" in stack_info.get("outputs", {}):
                        mapping["resource_mapping"]["cognito_app_client_id"] = stack_info.get("outputs", {}).get("AppClientId")
                elif legacy_name == "eidolon-dynamodb":
                    # Map DynamoDB table names
                    for key, value in stack_info.get("outputs", {}).items():
                        if key.endswith("TableName"):
                            table_type = key.replace("TableName", "").lower()
                            mapping["resource_mapping"][f"dynamodb_{table_type}_table"] = value
                elif legacy_name == "eidolon-cloudwatch":
                    if "LogGroupName" in stack_info.get("outputs", {}):
                        mapping["resource_mapping"]["log_group_name"] = stack_info.get("outputs", {}).get("LogGroupName")

        # Determine migration strategy
        if mapping["cloudformation_stacks"]:
            # We have existing CloudFormation stacks
            can_adopt_all = all(stack.get("can_adopt", False) for stack in mapping["cloudformation_stacks"].values())
            if can_adopt_all:
                mapping["migration_strategy"] = "adopt"
            else:
                mapping["migration_strategy"] = "coexist"

        return mapping

    def _can_adopt_stack(self, stack_name: str, stack_info: dict) -> bool:
        """Check if a CloudFormation stack can be adopted by CDK.

        Args:
            stack_name: Name of the stack
            stack_info: Stack information

        Returns:
            True if stack can be adopted
        """
        # DynamoDB tables and CloudWatch log groups can be imported
        # Cognito and CodeBuild are more complex
        adoptable_stacks = ["eidolon-dynamodb", "eidolon-cloudwatch"]
        return stack_name in adoptable_stacks

    def analyze_changes(self, params: dict) -> dict:
        """Analyze what changes need to be deployed.

        Args:
            params: Deployment parameters

        Returns:
            Dictionary with deployment plan
        """
        print("\nAnalyzing infrastructure changes...")

        # Get existing stacks
        existing_stacks = self.get_existing_stacks()

        # Map CloudFormation resources if they exist
        cf_mapping = self.map_cloudformation_to_cdk(existing_stacks, params)

        # Expected CDK stack names
        expected_stacks = ["cognito", "dynamodb", "cloudwatch", "s3", "cloudfront", "codebuild"]

        plan = {
            "create_stacks": [],
            "update_stacks": [],
            "unchanged_stacks": [],
            "adopt_resources": {},
            "cloudformation_mapping": cf_mapping,
            "parameters": params,
            "drift_report": "",
        }

        # If we have CloudFormation stacks, we can adopt or coexist
        if cf_mapping["cloudformation_stacks"]:
            print("\nDetected existing CloudFormation stacks:")
            for stack_name, info in cf_mapping["cloudformation_stacks"].items():
                print(f"  • {stack_name} (can adopt: {info.get('can_adopt', False)})")

            if cf_mapping["migration_strategy"] == "adopt":
                print("\nStrategy: Adopt existing resources into CDK stacks")
                plan["adopt_resources"] = cf_mapping["resource_mapping"]
            else:
                print("\nStrategy: CDK stacks will coexist with CloudFormation stacks")
                print("Note: Some resources cannot be adopted and will need manual migration")

        # Check each expected stack
        for stack_name in expected_stacks:
            if stack_name in existing_stacks:
                # CDK stack already exists
                plan["update_stacks"].append(stack_name)
            else:
                # Need to create CDK stack
                plan["create_stacks"].append(stack_name)

        # Validate existing resources for drift detection
        if existing_stacks or cf_mapping["cloudformation_stacks"]:
            print("\nValidating existing resources for drift...")
            drift_results = self.validate_resources(params)
            if drift_results:
                plan["drift_report"] = generate_drift_report(drift_results)
                print(plan["drift_report"])

        return plan

    def execute_deployment(self, plan: dict, auto_approve: bool = False) -> bool:
        """Execute the deployment plan.

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
                print(f"  • {stack}")

        if plan["update_stacks"]:
            print(f"\nStacks to UPDATE: {len(plan['update_stacks'])}")
            for stack in plan["update_stacks"]:
                print(f"  • {stack}")

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

        # Set environment variables for CDK
        env = os.environ.copy()
        env["CDK_DEFAULT_ACCOUNT"] = self.session.client("sts").get_caller_identity().get("Account")
        env["CDK_DEFAULT_REGION"] = self.region

        # Add profile if specified
        if self.profile:
            env["AWS_PROFILE"] = self.profile

        # Pass adopted resources to CDK via context
        if plan.get("adopt_resources"):
            print("\nPreparing to adopt existing resources...")
            for key, value in plan["adopt_resources"].items():
                env[f"CDK_CONTEXT_{key}"] = value
                print(f"  • {key}: {value}")

        # Run CDK deploy
        print("\nDeploying infrastructure with CDK...")
        cdk_command = ["cdk", "deploy", "--all", "--require-approval", "never" if auto_approve else "broadening"]

        # Add context for adopted resources
        if plan.get("adopt_resources"):
            for key, value in plan["adopt_resources"].items():
                cdk_command.extend(["-c", f"{key}={value}"])

        try:
            result = subprocess.run(cdk_command, cwd=self.cdk_dir, env=env, check=True)

            if result.returncode == 0:
                print("\n✓ Deployment completed successfully!")

                # Update configuration file
                self.update_configuration(plan["parameters"])

                # Record deployment in state
                self.state_manager.add_deployment_event(
                    "deployment_complete", {"stacks_created": plan["create_stacks"], "stacks_updated": plan["update_stacks"]}
                )
                self.state_manager.save_state()

                return True
            else:
                print("\n✗ Deployment failed!")
                return False

        except subprocess.CalledProcessError as err:
            print(f"\n✗ Deployment failed: {err}")
            return False

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
                            "PortalS3Bucket": outputs.get("PortalBucketName", ""),
                            "ScriptsS3Bucket": outputs.get("ScriptsBucketName", ""),
                            "ScriptsS3Prefix": "scripts",
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

            except Exception as err:
                print(f"Warning: Could not get outputs for {stack_name}: {err}")

        # Update game config
        self.config_manager.update_section("Game", {"name": params["game_name"]})

        # Save configuration
        self.config_manager.save_config()
        print(f"✓ Configuration saved to {self.config_manager.config_path}")

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
                print(f"  ✓ Uploaded {lua_file.name}")

            return True

        except ClientError as err:
            print(f"Error deploying scripts: {err}")
            return False

    def run(self, auto_approve: bool = False, skip_scripts: bool = False, analyze_only: bool = False) -> bool:
        """Run the incremental deployment.

        Args:
            auto_approve: Skip confirmation prompts
            skip_scripts: Skip Lua script deployment
            analyze_only: Only analyze, don't deploy

        Returns:
            True if deployment succeeded
        """
        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Load and validate parameters
        params = self.load_parameters()
        if not auto_approve and not analyze_only:
            params = self.prompt_missing_parameters(params)

        # Analyze what needs to be deployed
        plan = self.analyze_changes(params)

        # If analyze-only, stop here
        if analyze_only:
            print("\n=== ANALYSIS COMPLETE ===")
            print("Run without --analyze-only to proceed with deployment.")
            return True

        # Execute deployment
        if not self.execute_deployment(plan, auto_approve):
            return False

        # Deploy scripts if requested
        if not skip_scripts:
            self.deploy_scripts(params)

        print("\n✓ Incremental deployment completed successfully!")
        return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Incremental deployment for Eidolon Engine infrastructure")
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--region", default="us-east-1", help="AWS region (default: us-east-1)")
    parser.add_argument("--auto-approve", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--skip-scripts", action="store_true", help="Skip Lua script deployment")
    parser.add_argument("--analyze-only", action="store_true", help="Only analyze existing infrastructure, don't deploy")

    args = parser.parse_args()

    orchestrator = IncrementalDeploymentOrchestrator(profile=args.profile, region=args.region)

    success = orchestrator.run(auto_approve=args.auto_approve, skip_scripts=args.skip_scripts, analyze_only=args.analyze_only)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
