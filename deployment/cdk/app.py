"""AWS CDK application for Eidolon Engine infrastructure.

This application defines all AWS resources needed for the Eidolon Engine
game server using AWS CDK for infrastructure as code. Separates MUD
and Incremental deployments.
"""

import json
import os
import sys
from datetime import datetime, timedelta
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


def load_json_file(file_path: Path) -> dict:
    """Load JSON data from file.

    Args:
        file_path: Path to JSON file

    Returns:
        Loaded JSON data or empty dict if file doesn't exist
    """
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Warning: Failed to load {file_path}: {e}")
            return {}
    return {}


def save_json_file(file_path: Path, data: dict) -> bool:
    """Save JSON data to file.

    Args:
        file_path: Path to save JSON file
        data: Data to save

    Returns:
        True if successful, False otherwise
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except IOError as e:
        print(f"Error: Failed to save {file_path}: {e}")
        return False


def load_yaml_file(file_path: Path) -> dict:
    """Load YAML data from file.

    Args:
        file_path: Path to YAML file

    Returns:
        Loaded YAML data or empty dict if file doesn't exist
    """
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError) as e:
            print(f"Warning: Failed to load {file_path}: {e}")
            return {}
    return {}


def save_yaml_file(file_path: Path, data: dict) -> bool:
    """Save YAML data to file.

    Args:
        file_path: Path to save YAML file
        data: Data to save

    Returns:
        True if successful, False otherwise
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except IOError as e:
        print(f"Error: Failed to save {file_path}: {e}")
        return False


def deep_merge(base: dict, override: dict) -> None:
    """Deep merge override dict into base dict.

    Args:
        base: Base dictionary to merge into
        override: Dictionary with values to override
    """
    for key, value in override.items():
        if key in base and isinstance(base.get(key), dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def validate_required_config(config: dict) -> tuple:
    """Validate required configuration parameters.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check API configuration
    api_config = config.get("API", {})
    if not api_config:
        errors.append("Missing required 'API' section in configuration")
    else:
        if not api_config.get("Domain"):
            errors.append("API.Domain is required")
        if not api_config.get("HostedZoneId"):
            errors.append("API.HostedZoneId is required")

    return len(errors) == 0, errors


def get_boolean_context(app: cdk.App, key: str, default: bool = False) -> bool:
    """Get boolean value from CDK context.

    Args:
        app: CDK application
        key: Context key
        default: Default value if not found

    Returns:
        Boolean value
    """
    value = app.node.try_get_context(key)
    if value is not None:
        return str(value).lower() in ["true", "1", "yes"]
    return default


def get_environment_bool(key: str, default: str = "false") -> bool:
    """Get boolean value from environment variable.

    Args:
        key: Environment variable key
        default: Default value if not found

    Returns:
        Boolean value
    """
    return os.getenv(key, default).lower() in ["true", "1", "yes"]


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
        state = load_json_file(self.state_file)
        if not state:
            state = {
                "version": "1.0",
                "last_deployment": None,
                "stacks": {},
                "resources": {},
                "parameters": {},
                "deployment_history": [],
            }
        return state

    def save_state(self) -> None:
        """Persist current state to file."""
        self.state["last_deployment"] = datetime.now().isoformat()
        save_json_file(self.state_file, self.state)

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

    def get_stack(self, stack_name: str) -> dict:
        """Get information about a deployed stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Stack information if exists, empty dict otherwise
        """
        return self.state.get("stacks", {}).get(stack_name, {})

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

    def get_resource(self, resource_type: str, resource_id: str) -> dict:
        """Get information about a deployed resource.

        Args:
            resource_type: AWS resource type
            resource_id: Resource identifier

        Returns:
            Resource information if exists, empty dict otherwise
        """
        return self.state.get("resources", {}).get(resource_type, {}).get(resource_id, {})

    def update_parameters(self, parameters: dict) -> None:
        """Update deployment parameters.

        Args:
            parameters: Dictionary of parameter key-value pairs
        """
        self.state["parameters"].update(parameters)

    def get_parameters(self) -> dict:
        """Get all stored deployment parameters."""
        return self.state.get("parameters", {}).copy()

    def add_deployment_event(self, event_type: str, event_data: dict) -> None:
        """Add entry to deployment history.

        Args:
            event_type: Type of deployment event
            event_data: Event details
        """
        self.state["deployment_history"].append(
            {"timestamp": datetime.now().isoformat(), "event_type": event_type, "data": event_data}
        )

        # Keep only events from the last 7 days
        cutoff_date = datetime.now() - timedelta(days=7)
        self.state["deployment_history"] = [
            event for event in self.state.get("deployment_history", []) if datetime.fromisoformat(event["timestamp"]) > cutoff_date
        ]

    def get_deployed_stacks(self) -> set:
        """Get set of all deployed stack names."""
        return set(self.state.get("stacks", {}).keys())

    def get_deployment_summary(self) -> dict:
        """Get summary of current deployment state."""
        resources = self.state.get("resources", {})
        return {
            "last_deployment": self.state.get("last_deployment"),
            "deployed_stacks": list(self.get_deployed_stacks()),
            "total_resources": sum(len(res_dict) for res_dict in resources.values()),
            "parameter_count": len(self.state.get("parameters", {})),
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
        return load_yaml_file(self.config_path)

    def save_config(self) -> None:
        """Save configuration to file."""
        save_yaml_file(self.config_path, self.config)

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
        template = load_yaml_file(Path(template_path))
        if template:
            # Deep merge template with existing config
            deep_merge(template, self.config)
            self.config = template


class EidolonEngineApp:
    """Main CDK application for Eidolon Engine infrastructure."""

    def __init__(self):
        """Initialize the CDK app with configuration."""
        print("\n🚀 Initializing Eidolon Engine CDK Application")
        print("=" * 60)

        self.app = cdk.App()

        # Initialize managers
        print("📁 Loading configuration...")
        self.config_manager = ConfigurationManager()

        print("📊 Loading deployment state...")
        self.state_manager = DeploymentState()

        # Load configuration
        self.config = self.load_configuration()

        # Validate environment early
        self._validate_environment()

        # Create stacks with dependencies
        print("\n🏗️  Creating CDK stacks...")
        self.create_stacks()

        print("\n✅ CDK app initialization complete!")
        print("=" * 60)

    def _validate_environment(self) -> None:
        """Validate AWS environment and CDK requirements."""
        print("\n🔍 Validating environment...")

        # Check AWS credentials
        account = os.getenv("CDK_DEFAULT_ACCOUNT")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        if not account:
            print("❌ ERROR: CDK_DEFAULT_ACCOUNT environment variable not set!")
            print("   Please set your AWS account ID:")
            print("   export CDK_DEFAULT_ACCOUNT=123456789012")
            sys.exit(1)

        print(f"   ✓ AWS Account: {account}")
        print(f"   ✓ AWS Region: {region}")

        # Validate configuration
        is_valid, errors = validate_required_config(self.config)
        if not is_valid:
            print("\n❌ ERROR: Invalid configuration!")
            for error in errors:
                print(f"   - {error}")
            print("\n   Please update your config.yml with the required values.")
            sys.exit(1)

        # Validate critical parameters
        params = self.get_deployment_parameters()
        domain_name = params.get("domain_name")
        hosted_zone_id = params.get("hosted_zone_id")

        if not domain_name or not isinstance(domain_name, str):
            print("\n❌ ERROR: domain_name must be a non-empty string!")
            sys.exit(1)

        if not hosted_zone_id or not isinstance(hosted_zone_id, str):
            print("\n❌ ERROR: hosted_zone_id must be a non-empty string!")
            sys.exit(1)

    def load_configuration(self) -> dict:
        """Load configuration from config.yml or use defaults."""
        if self.config_manager.exists():
            return self.config_manager.config
        else:
            # Load from template if no config exists
            template_path = Path(__file__).parent.parent / "config.yml.template"
            return load_yaml_file(template_path)

    def create_stacks(self) -> None:
        """Create all CDK stacks with proper dependencies."""
        env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))

        # Get deployment parameters
        params = self.get_deployment_parameters()

        # Determine which applications to deploy
        deploy_mud = get_boolean_context(
            self.app, "deploy_mud", get_environment_bool("DEPLOY_MUD", str(params.get("deploy_mud", True)))
        )

        deploy_incremental = get_boolean_context(
            self.app, "deploy_incremental", get_environment_bool("DEPLOY_INCREMENTAL", str(params.get("deploy_incremental", False)))
        )

        print(f"Deployment configuration: MUD={deploy_mud}, Incremental={deploy_incremental}")

        # Create shared infrastructure stacks
        self._create_shared_stacks(env, params)

        # Deploy MUD-specific infrastructure
        if deploy_mud:
            self._create_mud_stacks(env, params)

        # Deploy Incremental-specific infrastructure
        if deploy_incremental:
            self._create_incremental_stacks(env, params)

        # Create IAM stack with server execution role
        self._create_iam_stack(env, params)

    def _create_shared_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create shared infrastructure stacks."""
        # Create Cognito stack (shared)
        self.cognito_stack = CognitoStack(
            self.app,
            "cognito",
            game_name=params.get("game_name", "eidolon-engine"),
            contact_email=params.get("contact_email", "contact@darkrelics.net"),
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
            game_name=params.get("game_name", "eidolon-engine"),
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
        from aws_cdk import aws_lambda as lambda_

        cognito_trigger_function = lambda_.Function.from_function_arn(
            self.cognito_stack, "CognitoTriggerFunction", self.base_lambda_stack.cognito_new_player_function.function_arn
        )
        self.cognito_stack.add_lambda_trigger("PostConfirmation", cognito_trigger_function)

    def _create_mud_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create MUD-specific infrastructure stacks."""
        # Create MUD DynamoDB tables
        mud_tables = params.get("mud_dynamodb_tables", {})
        self.mud_dynamodb_stack = DynamoDBStack(self.app, "mud-dynamodb", game_name="mud", table_names=mud_tables, env=env)

        # Get domain configuration with validation
        domain_name = params.get("domain_name", "")
        hosted_zone_id = params.get("hosted_zone_id", "")

        # Create MUD Lambda stack
        self.mud_lambda_stack = MudLambdaStack(
            self.app,
            "mud-lambda",
            lambda_bucket=self.s3_stack.lambda_bucket,
            shared_players_table=params.get("shared_dynamodb_tables", {}).get("Players", "players"),
            mud_characters_table=mud_tables.get("Characters", "mud-characters"),
            mud_items_table=mud_tables.get("Items", "mud-items"),
            mud_ARCHETYPES_TABLE=mud_tables.get("Archetypes", "mud-archetypes"),
            cognito_user_pool_arn=self.cognito_stack.user_pool.user_pool_arn,
            shared_dependencies_layer_arn=self.base_lambda_stack.dependencies_layer.layer_version_arn,
            domain_name=domain_name,
            hosted_zone_id=hosted_zone_id,
            api_subdomain=params.get("mud_api_subdomain", "mud-api"),
            allowed_cors_origins=params.get("mud_cors_origins", []),
            env=env,
        )
        self.mud_lambda_stack.add_dependency(self.base_lambda_stack)
        self.mud_lambda_stack.add_dependency(self.mud_dynamodb_stack)
        self.mud_lambda_stack.add_dependency(self.cognito_stack)

        # Create MUD frontend stacks
        self._create_mud_frontend_stacks(env, params)

    def _create_mud_frontend_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create MUD frontend infrastructure (CloudFront and CodeBuild)."""
        # Create Portal CloudFront stack
        self.portal_cloudfront_stack = CloudFrontStack(
            self.app,
            "portal-cloudfront",
            portal_bucket=self.s3_stack.portal_bucket,
            existing_distribution_id=params.get("portal_cloudfront_distribution_id", ""),
            env=env,
        )
        self.portal_cloudfront_stack.add_dependency(self.s3_stack)

        # Create Portal CodeBuild stack
        self.portal_codebuild_stack = CodeBuildStack(
            self.app,
            "portal-codebuild",
            game_name="portal",
            github_owner=params.get("github_owner", "robinje"),
            github_repo=params.get("github_repo", "eidolon-engine"),
            github_branch=params.get("github_branch", "main"),
            cognito_user_pool_id=self.cognito_stack.user_pool.user_pool_id,
            cognito_app_client_id=self.cognito_stack.app_client.user_pool_client_id,
            portal_bucket=self.s3_stack.portal_bucket,
            buildspec_path=params.get("portal_buildspec_path", "buildspec/portal.yml"),
            cloudfront_distribution_id=self.portal_cloudfront_stack.distribution.distribution_id,
            lambda_bucket=self.s3_stack.lambda_bucket,
            env=env,
        )
        self.portal_codebuild_stack.add_dependency(self.cognito_stack)
        self.portal_codebuild_stack.add_dependency(self.s3_stack)
        self.portal_codebuild_stack.add_dependency(self.portal_cloudfront_stack)

    def _create_incremental_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create Incremental-specific infrastructure stacks."""
        # Create Incremental DynamoDB tables
        incremental_tables = params.get("incremental_dynamodb_tables", {})
        self.incremental_dynamodb_stack = DynamoDBStack(
            self.app, "incremental-dynamodb", game_name="incremental", table_names=incremental_tables, env=env
        )

        # Get domain configuration
        domain_name = params.get("domain_name", "")
        hosted_zone_id = params.get("hosted_zone_id", "")

        # Create Incremental Lambda stack
        self.incremental_lambda_stack = IncrementalLambdaStack(
            self.app,
            "incremental-lambda",
            lambda_bucket=self.s3_stack.lambda_bucket,
            shared_players_table=params.get("shared_dynamodb_tables", {}).get("Players", "players"),
            incremental_progress_table_name=incremental_tables.get("Progress", "incremental-progress"),
            incremental_resources_table_name=incremental_tables.get("Resources", "incremental-resources"),
            cognito_user_pool_arn=self.cognito_stack.user_pool.user_pool_arn,
            shared_dependencies_layer_arn=self.base_lambda_stack.dependencies_layer.layer_version_arn,
            domain_name=domain_name,
            hosted_zone_id=hosted_zone_id,
            api_subdomain=params.get("incremental_api_subdomain", "incremental-api"),
            allowed_cors_origins=params.get("incremental_cors_origins", []),
            env=env,
        )
        self.incremental_lambda_stack.add_dependency(self.base_lambda_stack)
        self.incremental_lambda_stack.add_dependency(self.incremental_dynamodb_stack)
        self.incremental_lambda_stack.add_dependency(self.cognito_stack)

        # Create Incremental frontend stacks
        self._create_incremental_frontend_stacks(env, params)

    def _create_incremental_frontend_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create Incremental frontend infrastructure (CloudFront and CodeBuild)."""
        # Create Incremental CloudFront stack
        self.incremental_cloudfront_stack = CloudFrontStack(
            self.app,
            "incremental-cloudfront",
            portal_bucket=self.s3_stack.portal_bucket,
            existing_distribution_id=params.get("incremental_cloudfront_distribution_id", ""),
            env=env,
        )
        self.incremental_cloudfront_stack.add_dependency(self.s3_stack)

        # Create Incremental CodeBuild stack
        self.incremental_codebuild_stack = CodeBuildStack(
            self.app,
            "incremental-codebuild",
            game_name="incremental",
            github_owner=params.get("github_owner", "robinje"),
            github_repo=params.get("github_repo", "eidolon-engine"),
            github_branch=params.get("github_branch", "main"),
            cognito_user_pool_id=self.cognito_stack.user_pool.user_pool_id,
            cognito_app_client_id=self.cognito_stack.app_client.user_pool_client_id,
            portal_bucket=self.s3_stack.portal_bucket,
            buildspec_path=params.get("incremental_buildspec_path", "buildspec/incremental.yml"),
            cloudfront_distribution_id=self.incremental_cloudfront_stack.distribution.distribution_id,
            lambda_bucket=self.s3_stack.lambda_bucket,
            env=env,
        )
        self.incremental_codebuild_stack.add_dependency(self.cognito_stack)
        self.incremental_codebuild_stack.add_dependency(self.s3_stack)
        self.incremental_codebuild_stack.add_dependency(self.incremental_cloudfront_stack)

    def _create_iam_stack(self, env: cdk.Environment, params: dict) -> None:
        """Create IAM stack with server execution role."""
        self.iam_stack = IAMStack(
            self.app,
            "iam",
            game_name=params.get("game_name", "eidolon-engine"),
            cloudwatch_policy_arn=self.cloudwatch_stack.access_policy.managed_policy_arn,
            dynamodb_policy_arn=self.shared_dynamodb_stack.access_policy.managed_policy_arn,
            env=env,
        )
        self.iam_stack.add_dependency(self.cloudwatch_stack)
        self.iam_stack.add_dependency(self.shared_dynamodb_stack)

    def get_deployment_parameters(self) -> dict:
        """Get deployment parameters from config or state."""
        print("\n📝 Loading deployment parameters...")

        # Start with defaults
        params: dict = {
            "game_name": "eidolon-engine",
            "contact_email": "contact@darkrelics.net",
            "github_owner": "robinje",
            "github_repo": "eidolon-engine",
            "github_branch": "main",
            "log_retention_days": 365,
            "deploy_mud": True,
            "deploy_incremental": False,
            "shared_dynamodb_tables": {},
            "mud_dynamodb_tables": {},
            "incremental_dynamodb_tables": {},
            "mud_cors_origins": [],
            "incremental_cors_origins": [],
            "shared_cors_origins": [],
        }
        print("   ✓ Loaded default parameters")

        # Override with stored parameters
        stored_params = self.state_manager.get_parameters()
        if stored_params:
            print(f"   ✓ Found {len(stored_params)} stored parameters")
            params.update(stored_params)

        # Override with config values
        self._load_game_config(params)
        self._load_deployment_config(params)
        self._load_dynamodb_config(params)
        self._load_codebuild_config(params)
        self._load_api_config(params)
        self._load_cors_config(params)

        print("\n   ✓ Parameter loading complete")
        return params

    def _load_game_config(self, params: dict) -> None:
        """Load game configuration section."""
        game_config = self.config.get("Game", {})
        if game_config:
            print("   ✓ Loading Game configuration")
            params["game_name"] = game_config.get("name", params.get("game_name", "eidolon-engine"))

            # Check for existing bucket configurations
            if "PortalS3Bucket" in game_config:
                params["portal_bucket_name"] = game_config.get("PortalS3Bucket")
                print(f"     - Using existing portal bucket: {params['portal_bucket_name']}")
            if "ScriptsS3Bucket" in game_config:
                params["scripts_bucket_name"] = game_config.get("ScriptsS3Bucket")
                print(f"     - Using existing scripts bucket: {params['scripts_bucket_name']}")

    def _load_deployment_config(self, params: dict) -> None:
        """Load deployment configuration section."""
        deploy_config = self.config.get("Deployment", {})
        if deploy_config:
            print("   ✓ Loading Deployment configuration")
            # Only use config values if not already set by context
            if self.app.node.try_get_context("deploy_mud") is None:
                params["deploy_mud"] = deploy_config.get("MUD", True)
            if self.app.node.try_get_context("deploy_incremental") is None:
                params["deploy_incremental"] = deploy_config.get("Incremental", False)

    def _load_dynamodb_config(self, params: dict) -> None:
        """Load DynamoDB configuration section."""
        dynamodb_config = self.config.get("DynamoDB", {})
        if dynamodb_config:
            print("   ✓ Loading DynamoDB configuration")
            if "SharedTables" in dynamodb_config:
                params["shared_dynamodb_tables"] = dynamodb_config.get("SharedTables", {})
                print(f"     - Found {len(params['shared_dynamodb_tables'])} shared tables")

            if "MUDTables" in dynamodb_config:
                params["mud_dynamodb_tables"] = dynamodb_config.get("MUDTables", {})
                print(f"     - Found {len(params['mud_dynamodb_tables'])} MUD tables")

            if "IncrementalTables" in dynamodb_config:
                params["incremental_dynamodb_tables"] = dynamodb_config.get("IncrementalTables", {})
                print(f"     - Found {len(params['incremental_dynamodb_tables'])} Incremental tables")

    def _load_codebuild_config(self, params: dict) -> None:
        """Load CodeBuild configuration section."""
        codebuild_config = self.config.get("CodeBuild", {})
        if codebuild_config:
            print("   ✓ Loading CodeBuild configuration")
            if "PortalBuildspecPath" in codebuild_config:
                params["portal_buildspec_path"] = codebuild_config.get("PortalBuildspecPath")
            if "IncrementalBuildspecPath" in codebuild_config:
                params["incremental_buildspec_path"] = codebuild_config.get("IncrementalBuildspecPath")

    def _load_api_config(self, params: dict) -> None:
        """Load API configuration section."""
        api_config = self.config.get("API", {})
        if api_config:
            print("   ✓ Loading API configuration")
            params["domain_name"] = api_config.get("Domain", "")
            params["hosted_zone_id"] = api_config.get("HostedZoneId", "")
            params["mud_api_subdomain"] = api_config.get("MUDSubdomain", "mud-api")
            params["incremental_api_subdomain"] = api_config.get("IncrementalSubdomain", "incremental-api")

            print(f"     - Domain: {params['domain_name']}")
            print(f"     - Hosted Zone ID: {params['hosted_zone_id']}")

    def _load_cors_config(self, params: dict) -> None:
        """Load CORS configuration section."""
        cors_config = self.config.get("CORS", {})
        if cors_config:
            print("   ✓ Loading CORS configuration")
            params["mud_cors_origins"] = cors_config.get("MUDOrigins", [])
            params["incremental_cors_origins"] = cors_config.get("IncrementalOrigins", [])

            # Shared CORS origins include all configured origins
            all_origins = []
            all_origins.extend(params.get("mud_cors_origins", []))
            all_origins.extend(params.get("incremental_cors_origins", []))
            params["shared_cors_origins"] = list(set(all_origins))  # Remove duplicates

            print(f"     - MUD origins: {len(params['mud_cors_origins'])}")
            print(f"     - Incremental origins: {len(params['incremental_cors_origins'])}")
            print(f"     - Total unique origins: {len(params['shared_cors_origins'])}")

    def synth(self):
        """Synthesize the CDK app."""
        return self.app.synth()


def main() -> None:
    """Main entry point for CDK app."""
    app = EidolonEngineApp()
    app.synth()


if __name__ == "__main__":
    main()
