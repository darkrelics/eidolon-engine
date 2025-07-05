"""Incremental deployment orchestrator for Eidolon Engine infrastructure.

This script manages incremental AWS infrastructure deployments using CDK,
allowing for selective updates without full redeployment.
"""

import argparse
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from cdk_api_integration import (CDKApiIntegration, CDKDeploymentError,
                                 CDKProgressReporter)
from deployment_logic import (analyze_changes, get_existing_stacks,
                              map_cloudformation_to_cdk,
                              prompt_missing_parameters, validate_resources)

from eidolon.state_manager import ConfigurationManager, DeploymentState


class IncrementalDeploymentOrchestrator:
    """Orchestrates incremental infrastructure deployments."""

    def __init__(self, profile=None, region: str = "us-east-1"):
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

        # Initialize CDK API integration
        self.cdk_api = CDKApiIntegration(cdk_dir=str(self.cdk_dir), profile=profile, region=region)

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
            "github_branch": "main",
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

        if "CloudWatch" in config:
            params["log_retention_days"] = config["CloudWatch"].get("LogRetentionDays", params["log_retention_days"])

        if "S3" in config:
            s3_config = config["S3"]
            if s3_config.get("PortalBucket"):
                params["portal_bucket_name"] = s3_config["PortalBucket"]
            if s3_config.get("ScriptsBucket"):
                params["scripts_bucket_name"] = s3_config["ScriptsBucket"]

        # Load deployment type from config
        if "Deployment" in config:
            deploy_config = config["Deployment"]
            params["deploy_mud"] = deploy_config.get("MUD", True)
            params["deploy_incremental"] = deploy_config.get("Incremental", False)

        return params

    def handle_deployment_selection(
        self, params: dict, deploy_mud: bool, deploy_incremental: bool, deploy_both: bool, non_interactive: bool
    ) -> dict:
        """Handle deployment type selection with interactive mode.

        Args:
            params: Current parameters
            deploy_mud: CLI flag to deploy only MUD
            deploy_incremental: CLI flag to deploy only Incremental
            deploy_both: CLI flag to deploy both
            non_interactive: Skip interactive prompts

        Returns:
            Updated parameters with deployment selection
        """
        # If any CLI flag is provided, use it
        if deploy_mud:
            params["deploy_mud"] = True
            params["deploy_incremental"] = False
            print("Deployment mode: MUD only")
        elif deploy_incremental:
            params["deploy_incremental"] = False
            params["deploy_incremental"] = True
            print("Deployment mode: Incremental only")
        elif deploy_both:
            params["deploy_mud"] = True
            params["deploy_incremental"] = True
            print("Deployment mode: Both MUD and Incremental")
        elif not non_interactive and "deploy_mud" not in params and "deploy_incremental" not in params:
            # Interactive mode - ask user what to deploy
            print("\n=== EIDOLON ENGINE DEPLOYMENT ===")
            print("\nWhich game infrastructure would you like to deploy?")
            print("1. MUD only (builds Portal frontend)")
            print("2. Incremental Game only (builds Incremental frontend)")
            print("3. Both MUD and Incremental (builds Incremental frontend)")

            choice = input("\nSelect deployment type [1-3] (default: 3): ").strip()

            if choice == "1":
                params["deploy_mud"] = True
                params["deploy_incremental"] = False
                print("\n[OK] Selected: MUD only (Portal frontend)")
            elif choice == "2":
                params["deploy_mud"] = False
                params["deploy_incremental"] = True
                print("\n[OK] Selected: Incremental Game only")
            else:  # Default to both
                params["deploy_mud"] = True
                params["deploy_incremental"] = True
                print("\n[OK] Selected: Both games (Incremental frontend)")
        else:
            # Use existing params or defaults
            if "deploy_mud" not in params and "deploy_incremental" not in params:
                # Default to both if nothing specified
                params["deploy_mud"] = True
                params["deploy_incremental"] = True
                print("Deployment mode: Both MUD and Incremental (default)")

        # Update config manager with deployment choices
        self.config_manager.update_section(
            "Deployment", {"MUD": params.get("deploy_mud", True), "Incremental": params.get("deploy_incremental", False)}
        )

        return params

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

        # Add deployment type context
        context["deploy_mud"] = str(plan["parameters"].get("deploy_mud", True))
        context["deploy_incremental"] = str(plan["parameters"].get("deploy_incremental", False))

        # Deploy using CDK Python API
        print("\nDeploying infrastructure with CDK...")

        try:
            # Create progress reporter
            progress_reporter = CDKProgressReporter()

            # Execute deployment
            result = self.cdk_api.deploy(
                stacks=None,  # Deploy all stacks
                context=context,
                require_approval="never" if auto_approve else "broadening",
                progress_callback=progress_reporter,
            )

            if result["success"]:
                print("\n[SUCCESS] Deployment completed successfully!")

                # Update configuration file with outputs
                self.update_configuration(plan["parameters"])

                # Record deployment in state
                self.state_manager.add_deployment_event(
                    "deployment_complete",
                    {
                        "stacks_created": plan["create_stacks"],
                        "stacks_updated": plan["update_stacks"],
                        "outputs": result.get("outputs", {}),
                    },
                )
                self.state_manager.save_state()

                return True
            else:
                print("\n[ERROR] Deployment failed!")
                return False

        except CDKDeploymentError as err:
            print(f"\n[ERROR] Deployment failed: {err}")
            if err.details:
                print(f"Details: {err.details}")
            return False
        except Exception as err:
            print(f"\n[ERROR] Unexpected error during deployment: {err}")
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
            f"{game_name}-iam",
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
        """Run the incremental deployment.

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

        # Check prerequisites
        if not self.check_prerequisites():
            return False

        # Load and validate parameters
        params = self.load_parameters()

        # Initialize config from template if config.yml doesn't exist
        if not self.config_manager.exists():
            template_path = Path(__file__).parent / "config.yml.template"
            if template_path.exists():
                print("Initializing configuration from template...")
                self.config_manager.merge_with_template(str(template_path))

        # Handle deployment type selection
        params = self.handle_deployment_selection(params, deploy_mud, deploy_incremental, deploy_both, non_interactive)

        if not auto_approve and not analyze_only and not non_interactive:
            params = prompt_missing_parameters(params)

        # Analyze what needs to be deployed
        plan = analyze_changes(self.cfn_client, self.session, params)

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

        # Show deployment summary
        print("\n========================================================")
        print("            DEPLOYMENT COMPLETED SUCCESSFULLY          ")
        print("========================================================")

        if params.get("deploy_mud") and params.get("deploy_incremental"):
            print("\n[OK] MUD backend infrastructure deployed")
            print("[OK] Incremental Game infrastructure deployed")
            print("[OK] Frontend build: Incremental (serves both games)")
        elif params.get("deploy_mud"):
            print("\n[OK] MUD infrastructure deployed")
            print("[OK] Frontend build: Portal")
        elif params.get("deploy_incremental"):
            print("\n[OK] Incremental Game infrastructure deployed")
            print("[OK] Frontend build: Incremental")

        print(f"\nConfiguration saved to: {self.config_manager.config_path}")
        print("\nNext steps:")
        print("1. Review the generated config.yml file")
        print("2. Deploy your game code using the CodeBuild project")
        if not skip_scripts:
            print("3. Lua scripts have been uploaded to S3")

        return True


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

    args = parser.parse_args()

    orchestrator = IncrementalDeploymentOrchestrator(profile=args.profile, region=args.region)

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
