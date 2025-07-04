"""AWS CDK application for Eidolon Engine infrastructure.

This application defines all AWS resources needed for the Eidolon Engine
game server using AWS CDK for infrastructure as code. Separates MUD
and Incremental deployments.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import aws_cdk as cdk
import yaml
from stacks.base_lambda_stack import BaseLambdaStack
from stacks.cloudfront_stack import CloudFrontStack
from stacks.cloudwatch_stack import CloudWatchStack
from stacks.codebuild_stack import CodeBuildStack
from stacks.cognito_stack import CognitoStack
from stacks.dynamodb_stack import DynamoDBStack
from stacks.iam_stack import IAMStack
from stacks.incremental_lambda_stack import IncrementalLambdaStack
from stacks.mud_lambda_stack import MudLambdaStack
from stacks.s3_stack import S3Stack


class DeploymentState:
    """Represents the current state of deployed infrastructure."""

    def __init__(self, state_file: str = ".deployment_state.json"):
        """Initialize deployment state manager.

        Args:
            state_file: Path to state file for persistence
        """
        self.state_file = Path(state_file)
        self.state: dict = self._load_state()

    def _load_state(self) -> dict:
        """Load state from file or create new state."""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "version": "1.0",
            "last_deployment": None,
            "stacks": {},
            "resources": {},
            "parameters": {},
            "deployment_history": [],
        }

    def save_state(self) -> None:
        """Persist current state to file."""
        self.state["last_deployment"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)

    def add_stack(self, stack_name: str, stack_info: dict) -> None:
        """Record CloudFormation stack deployment.

        Args:
            stack_name: Name of the CloudFormation stack
            stack_info: Stack metadata including outputs, parameters, etc.
        """
        self.state["stacks"][stack_name] = {
            "deployed_at": datetime.now().isoformat(),
            "stack_id": stack_info.get("stack_id"),
            "outputs": stack_info.get("outputs", {}),
            "parameters": stack_info.get("parameters", {}),
            "template_hash": stack_info.get("template_hash"),
            "status": stack_info.get("status", "CREATE_COMPLETE"),
        }

    def get_stack(self, stack_name: str):
        """Get information about a deployed stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Stack information if exists, None otherwise
        """
        return self.state["stacks"].get(stack_name)

    def add_resource(self, resource_type: str, resource_id: str, resource_info: dict) -> None:
        """Track individual AWS resource.

        Args:
            resource_type: AWS resource type (e.g., 'dynamodb_table')
            resource_id: Unique identifier for the resource
            resource_info: Resource metadata and configuration
        """
        if resource_type not in self.state["resources"]:
            self.state["resources"][resource_type] = {}

        self.state["resources"][resource_type][resource_id] = {
            "created_at": datetime.now().isoformat(),
            "configuration": resource_info.get("configuration", {}),
            "stack_name": resource_info.get("stack_name"),
            "physical_id": resource_info.get("physical_id"),
        }

    def get_resource(self, resource_type: str, resource_id: str):
        """Get information about a deployed resource.

        Args:
            resource_type: AWS resource type
            resource_id: Resource identifier

        Returns:
            Resource information if exists, None otherwise
        """
        return self.state["resources"].get(resource_type, {}).get(resource_id)

    def update_parameters(self, parameters: dict) -> None:
        """Update deployment parameters.

        Args:
            parameters: Dictionary of parameter key-value pairs
        """
        self.state["parameters"].update(parameters)

    def get_parameters(self) -> dict:
        """Get all stored deployment parameters."""
        return self.state["parameters"].copy()

    def add_deployment_event(self, event_type: str, event_data: dict) -> None:
        """Add entry to deployment history.

        Args:
            event_type: Type of deployment event
            event_data: Event details
        """
        self.state["deployment_history"].append(
            {"timestamp": datetime.now().isoformat(), "event_type": event_type, "data": event_data}
        )

        # Keep only last 100 events
        if len(self.state["deployment_history"]) > 100:
            self.state["deployment_history"] = self.state["deployment_history"][-100:]

    def get_deployed_stacks(self) -> set[str]:
        """Get set of all deployed stack names."""
        return set(self.state["stacks"].keys())

    def get_deployment_summary(self) -> dict:
        """Get summary of current deployment state."""
        return {
            "last_deployment": self.state["last_deployment"],
            "deployed_stacks": list(self.get_deployed_stacks()),
            "total_resources": sum(len(resources) for resources in self.state["resources"].values()),
            "parameter_count": len(self.state["parameters"]),
        }


class ConfigurationManager:
    """Manages server configuration file operations."""

    def __init__(self, config_path: str = "../config.yml"):
        """Initialize configuration manager.

        Args:
            config_path: Path to server configuration file
        """
        self.config_path = Path(config_path)
        self.config: dict = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from file."""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def save_config(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

    def update_section(self, section: str, values: dict) -> None:
        """Update a configuration section.

        Args:
            section: Configuration section name
            values: Values to update in the section
        """
        if section not in self.config:
            self.config[section] = {}
        self.config[section].update(values)

    def get_section(self, section: str) -> dict:
        """Get a configuration section.

        Args:
            section: Configuration section name

        Returns:
            Section configuration or empty dict
        """
        return self.config.get(section, {})

    def exists(self) -> bool:
        """Check if configuration file exists."""
        return self.config_path.exists()

    def get_aws_config(self) -> dict:
        """Get AWS-specific configuration."""
        return self.config.get("AWS", {})

    def merge_with_template(self, template_path: str) -> None:
        """Merge current config with template, preserving existing values.

        Args:
            template_path: Path to configuration template
        """
        if Path(template_path).exists():
            with open(template_path, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f) or {}

            # Deep merge template with existing config
            self._deep_merge(template, self.config)
            self.config = template

    def _deep_merge(self, base: dict, override: dict) -> None:
        """Deep merge override dict into base dict.

        Args:
            base: Base dictionary to merge into
            override: Dictionary with values to override
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value


class EidolonEngineApp:
    """Main CDK application for Eidolon Engine infrastructure."""

    def __init__(self):
        """Initialize the CDK app with configuration."""
        self.app = cdk.App()
        self.config_manager = ConfigurationManager()
        self.state_manager = DeploymentState()

        # Load configuration if exists
        self.config = self.load_configuration()

        # Create stacks with dependencies
        self.create_stacks()

    def load_configuration(self) -> dict:
        """Load configuration from config.yml or use defaults."""
        if self.config_manager.exists():
            return self.config_manager.config
        else:
            # Load from template if no config exists
            template_path = Path(__file__).parent.parent / "config.yml.template"
            if template_path.exists():
                with open(template_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            return {}

    def create_stacks(self):
        """Create all CDK stacks with proper dependencies."""
        env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))

        # Get deployment parameters
        params = self.get_deployment_parameters()

        # Determine which applications to deploy from context or parameters
        # Check CDK context first (from command line), then environment, then config
        deploy_mud = self.app.node.try_get_context("deploy_mud")
        if deploy_mud is not None:
            deploy_mud = str(deploy_mud).lower() in ["true", "1", "yes"]
        else:
            deploy_mud = os.getenv("DEPLOY_MUD", str(params.get("deploy_mud", True))).lower() in ["true", "1", "yes"]

        deploy_incremental = self.app.node.try_get_context("deploy_incremental")
        if deploy_incremental is not None:
            deploy_incremental = str(deploy_incremental).lower() in ["true", "1", "yes"]
        else:
            deploy_incremental = os.getenv("DEPLOY_INCREMENTAL", str(params.get("deploy_incremental", False))).lower() in [
                "true",
                "1",
                "yes",
            ]

        print(f"Deployment configuration: MUD={deploy_mud}, Incremental={deploy_incremental}")

        # Create shared infrastructure stacks

        # Create Cognito stack (shared)
        self.cognito_stack = CognitoStack(
            self.app,
            "cognito",
            game_name=params["game_name"],
            contact_email=params["contact_email"],
            env=env,
        )

        # Create shared DynamoDB tables
        shared_tables = {"Players": params.get("shared_dynamodb_tables", {}).get("Players", "players")}

        self.shared_dynamodb_stack = DynamoDBStack(
            self.app, "shared-dynamodb", game_name="shared", table_names=shared_tables, env=env
        )

        # Create CloudWatch stack
        self.cloudwatch_stack = CloudWatchStack(
            self.app,
            "cloudwatch",
            dynamodb_policy_arn=self.shared_dynamodb_stack.access_policy.managed_policy_arn,
            retention_days=params.get("log_retention_days", 365),
            env=env,
        )

        # Create S3 stack (handles existing buckets)
        self.s3_stack = S3Stack(
            self.app,
            "s3",
            game_name=params["game_name"],
            portal_bucket_name=params.get("portal_bucket_name"),
            scripts_bucket_name=params.get("scripts_bucket_name"),
            env=env,
        )

        # Create base Lambda stack for shared functions
        self.base_lambda_stack = BaseLambdaStack(
            self.app,
            "base-lambda",
            lambda_bucket=self.s3_stack.lambda_bucket,
            shared_players_table=shared_tables["Players"],
            cognito_user_pool_arn=self.cognito_stack.user_pool.user_pool_arn,
            allowed_cors_origins=params.get("shared_cors_origins", []),
            env=env,
        )
        self.base_lambda_stack.add_dependency(self.s3_stack)
        self.base_lambda_stack.add_dependency(self.shared_dynamodb_stack)
        self.base_lambda_stack.add_dependency(self.cognito_stack)

        # Add Cognito Lambda trigger
        self.cognito_stack.add_lambda_trigger("PostConfirmation", self.base_lambda_stack.cognito_new_player_function)

        # Deploy MUD-specific infrastructure
        if deploy_mud:
            # Create MUD DynamoDB tables
            mud_tables = params.get("mud_dynamodb_tables", {})
            self.mud_dynamodb_stack = DynamoDBStack(self.app, "mud-dynamodb", game_name="mud", table_names=mud_tables, env=env)

            # Create MUD Lambda stack
            self.mud_lambda_stack = MudLambdaStack(
                self.app,
                "mud-lambda",
                lambda_bucket=self.s3_stack.lambda_bucket,
                shared_players_table=shared_tables["Players"],
                mud_characters_table=mud_tables.get("Characters", "mud-characters"),
                mud_items_table=mud_tables.get("Items", "mud-items"),
                mud_ARCHETYPES_TABLE=mud_tables.get("Archetypes", "mud-archetypes"),
                cognito_user_pool_arn=self.cognito_stack.user_pool.user_pool_arn,
                shared_dependencies_layer_arn=self.base_lambda_stack.dependencies_layer.layer_version_arn,
                domain_name=params.get("domain_name"),
                hosted_zone_id=params.get("hosted_zone_id"),
                api_subdomain=params.get("mud_api_subdomain", "mud-api"),
                allowed_cors_origins=params.get("mud_cors_origins", []),
                env=env,
            )
            self.mud_lambda_stack.add_dependency(self.base_lambda_stack)
            self.mud_lambda_stack.add_dependency(self.mud_dynamodb_stack)
            self.mud_lambda_stack.add_dependency(self.cognito_stack)

        # Deploy Incremental-specific infrastructure
        if deploy_incremental:
            # Create Incremental DynamoDB tables
            incremental_tables = params.get("incremental_dynamodb_tables", {})
            self.incremental_dynamodb_stack = DynamoDBStack(
                self.app, "incremental-dynamodb", game_name="incremental", table_names=incremental_tables, env=env
            )

            # Create Incremental Lambda stack
            self.incremental_lambda_stack = IncrementalLambdaStack(
                self.app,
                "incremental-lambda",
                lambda_bucket=self.s3_stack.lambda_bucket,
                shared_players_table=shared_tables["Players"],
                incremental_progress_table_name=incremental_tables.get("Progress", "incremental-progress"),
                incremental_resources_table_name=incremental_tables.get("Resources", "incremental-resources"),
                cognito_user_pool_arn=self.cognito_stack.user_pool.user_pool_arn,
                shared_dependencies_layer_arn=self.base_lambda_stack.dependencies_layer.layer_version_arn,
                domain_name=params.get("domain_name"),
                hosted_zone_id=params.get("hosted_zone_id"),
                api_subdomain=params.get("incremental_api_subdomain", "incremental-api"),
                allowed_cors_origins=params.get("incremental_cors_origins", []),
                env=env,
            )
            self.incremental_lambda_stack.add_dependency(self.base_lambda_stack)
            self.incremental_lambda_stack.add_dependency(self.incremental_dynamodb_stack)
            self.incremental_lambda_stack.add_dependency(self.cognito_stack)

        # Create unified CloudFront and CodeBuild stacks
        # Logic: If deploying Incremental (with or without MUD), build Incremental
        #        If deploying MUD only, build Portal
        if deploy_mud or deploy_incremental:
            # Determine which frontend to build
            if deploy_incremental:
                # Build Incremental frontend if Incremental is being deployed
                frontend_type = "incremental"
                buildspec_path = params.get("incremental_buildspec_path", "buildspec/incremental.yml")
                distribution_id_param = "incremental_cloudfront_distribution_id"
            else:
                # Build Portal frontend if only MUD is being deployed
                frontend_type = "portal"
                buildspec_path = params.get("portal_buildspec_path", "buildspec/portal.yml")
                distribution_id_param = "portal_cloudfront_distribution_id"

            # Create CloudFront stack
            self.cloudfront_stack = CloudFrontStack(
                self.app,
                "cloudfront",
                game_name=frontend_type,
                portal_bucket=self.s3_stack.portal_bucket,
                existing_distribution_id=params.get(distribution_id_param),
                env=env,
            )
            self.cloudfront_stack.add_dependency(self.s3_stack)

            # Create CodeBuild stack
            self.codebuild_stack = CodeBuildStack(
                self.app,
                "codebuild",
                game_name=frontend_type,
                github_owner=params["github_owner"],
                github_repo=params["github_repo"],
                github_branch=params.get("github_branch", "main"),
                cognito_user_pool_id=self.cognito_stack.user_pool.user_pool_id,
                cognito_app_client_id=self.cognito_stack.app_client.user_pool_client_id,
                portal_bucket=self.s3_stack.portal_bucket,
                buildspec_path=buildspec_path,
                cloudfront_distribution_id=self.cloudfront_stack.distribution.distribution_id,
                lambda_bucket=self.s3_stack.lambda_bucket,
                env=env,
            )
            self.codebuild_stack.add_dependency(self.cognito_stack)
            self.codebuild_stack.add_dependency(self.s3_stack)
            self.codebuild_stack.add_dependency(self.cloudfront_stack)

        # Create IAM stack with server execution role
        self.iam_stack = IAMStack(
            self.app,
            "iam",
            game_name=params["game_name"],
            cloudwatch_policy_arn=self.cloudwatch_stack.access_policy.managed_policy_arn,
            dynamodb_policy_arn=self.shared_dynamodb_stack.access_policy.managed_policy_arn,
            env=env,
        )
        self.iam_stack.add_dependency(self.cloudwatch_stack)
        self.iam_stack.add_dependency(self.shared_dynamodb_stack)

    def get_deployment_parameters(self) -> dict:
        """Get deployment parameters from config or state."""
        # Start with defaults
        params = {
            "game_name": "eidolon-engine",
            "contact_email": "admin@example.com",
            "github_owner": "robinje",
            "github_repo": "eidolon-engine",
            "github_branch": "main",
            "log_retention_days": 365,
            "deploy_mud": True,
            "deploy_incremental": False,
        }

        # Override with stored parameters
        stored_params = self.state_manager.get_parameters()
        params.update(stored_params)

        # Override with config values
        if "Game" in self.config:
            game_config = self.config["Game"]
            params["game_name"] = game_config.get("name", params["game_name"])

            # Check for existing bucket configurations
            if "PortalS3Bucket" in game_config:
                params["portal_bucket_name"] = game_config["PortalS3Bucket"]
            if "ScriptsS3Bucket" in game_config:
                params["scripts_bucket_name"] = game_config["ScriptsS3Bucket"]

        # Check for deployment configuration
        if "Deployment" in self.config:
            deploy_config = self.config["Deployment"]
            # Only use config values if not already set by context
            if self.app.node.try_get_context("deploy_mud") is None:
                params["deploy_mud"] = deploy_config.get("MUD", True)
            if self.app.node.try_get_context("deploy_incremental") is None:
                params["deploy_incremental"] = deploy_config.get("Incremental", False)

        # Check for shared DynamoDB table configurations
        if "DynamoDB" in self.config and "SharedTables" in self.config["DynamoDB"]:
            params["shared_dynamodb_tables"] = self.config["DynamoDB"]["SharedTables"]

        # Check for MUD-specific DynamoDB tables
        if "DynamoDB" in self.config and "MUDTables" in self.config["DynamoDB"]:
            params["mud_dynamodb_tables"] = self.config["DynamoDB"]["MUDTables"]

        # Check for Incremental-specific DynamoDB tables
        if "DynamoDB" in self.config and "IncrementalTables" in self.config["DynamoDB"]:
            params["incremental_dynamodb_tables"] = self.config["DynamoDB"]["IncrementalTables"]

        # Check for CodeBuild configuration
        if "CodeBuild" in self.config:
            codebuild_config = self.config["CodeBuild"]
            if "PortalBuildspecPath" in codebuild_config:
                params["portal_buildspec_path"] = codebuild_config["PortalBuildspecPath"]
            if "IncrementalBuildspecPath" in codebuild_config:
                params["incremental_buildspec_path"] = codebuild_config["IncrementalBuildspecPath"]

        # Check for API configuration (required)
        if "API" in self.config:
            api_config = self.config["API"]
            params["domain_name"] = api_config.get("Domain")
            params["hosted_zone_id"] = api_config.get("HostedZoneId")
            params["mud_api_subdomain"] = api_config.get("MUDSubdomain", "mud-api")
            params["incremental_api_subdomain"] = api_config.get("IncrementalSubdomain", "incremental-api")

            # Validate required API parameters
            if not params["domain_name"]:
                raise ValueError("API.Domain is required in configuration")
            if not params["hosted_zone_id"]:
                raise ValueError("API.HostedZoneId is required in configuration")
        else:
            raise ValueError("API configuration section is required")

        # Check for CORS configuration
        if "CORS" in self.config:
            cors_config = self.config["CORS"]
            params["mud_cors_origins"] = cors_config.get("MUDOrigins", [])
            params["incremental_cors_origins"] = cors_config.get("IncrementalOrigins", [])
            # Shared CORS origins include all configured origins
            all_origins = []
            all_origins.extend(params["mud_cors_origins"])
            all_origins.extend(params["incremental_cors_origins"])
            params["shared_cors_origins"] = list(set(all_origins))  # Remove duplicates

        return params

    def synth(self):
        """Synthesize the CDK app."""
        return self.app.synth()


def main():
    """Main entry point for CDK app."""
    app = EidolonEngineApp()
    app.synth()


if __name__ == "__main__":
    main()
