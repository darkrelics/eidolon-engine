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
from stacks.lambda_stack import LambdaStack
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
        except (json.JSONDecodeError, IOError) as err:
            print(f"Warning: Failed to load {file_path}: {err}")
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
    except IOError as err:
        print(f"Error: Failed to save {file_path}: {err}")
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
        except (yaml.YAMLError, IOError) as err:
            print(f"Warning: Failed to load {file_path}: {err}")
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
    except IOError as err:
        print(f"Error: Failed to save {file_path}: {err}")
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


def validate_required_config(config: dict) -> tuple[bool, list[str]]:
    """Validate required configuration parameters.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors: list = []

    # Check API configuration
    api_config = config.get("API", {})
    if not api_config:
        errors.append("Missing required 'API' section in configuration")
    else:
        domain = api_config.get("Domain", "")
        hosted_zone_id = api_config.get("HostedZoneId", "")

        if not domain or not domain.strip():
            errors.append("API.Domain is required and cannot be empty")
        if not hosted_zone_id or not hosted_zone_id.strip():
            errors.append("API.HostedZoneId is required and cannot be empty")

    return len(errors) == 0, errors


def get_deployment_mode(app: cdk.App, params: dict) -> str:
    """Determine deployment mode from context or parameters.

    Returns:
        One of: 'mud', 'incremental', or 'hybrid'
    """
    # Check for explicit mode in context
    mode = app.node.try_get_context("deployment_mode")
    if mode and mode in ["mud", "incremental", "hybrid"]:
        return mode

    # Check environment variable
    env_mode: str = os.getenv("DEPLOYMENT_MODE", "").lower()
    if env_mode in ["mud", "incremental", "hybrid"]:
        return env_mode

    deploy_mud: bool = get_boolean_context(app, "deploy_mud", params.get("deploy_mud", False))
    deploy_incremental: bool = get_boolean_context(app, "deploy_incremental", params.get("deploy_incremental", False))

    if deploy_mud and deploy_incremental:
        return "hybrid"
    elif deploy_mud:
        return "mud"
    elif deploy_incremental:
        return "incremental"
    else:
        return "hybrid"


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

    def __init__(self, state_file: str = ".deployment_state.json") -> None:
        """Initialize deployment state manager.

        Args:
            state_file: Path to state file for persistence
        """
        self.state_file = Path(state_file)
        self.state: dict = self.load_state()

    def load_state(self) -> dict:
        """Load state from file or create new state."""
        state: dict = load_json_file(self.state_file)
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
        cutoff_date: datetime = datetime.now() - timedelta(days=7)
        self.state["deployment_history"] = [
            event for event in self.state.get("deployment_history", []) if datetime.fromisoformat(event["timestamp"]) > cutoff_date
        ]

    def get_deployed_stacks(self) -> set[str]:
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

    def __init__(self, config_path: str = "../config.yml") -> None:
        """Initialize configuration manager.

        Args:
            config_path: Path to server configuration file
        """
        self.config_path = Path(config_path)
        self.config: dict = self.load_config()

    def load_config(self) -> dict:
        """Load configuration from file merged with template."""
        config: dict = load_yaml_file(self.config_path)

        if config:
            template_path = self.config_path.parent.parent / "config.template.yml"
            if template_path.exists():
                template: dict = load_yaml_file(template_path)
                if template:
                    deep_merge(template, config)
                    return template

        return config or {}

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
        template: dict = load_yaml_file(Path(template_path))
        if template:
            deep_merge(template, self.config)
            self.config = template


class EidolonEngineApp:
    """Main CDK application for Eidolon Engine infrastructure."""

    def __init__(self) -> None:
        """Initialize the CDK app with configuration."""
        print("\nInitializing Eidolon Engine CDK Application")
        print("=" * 60)

        self.app = cdk.App()

        # Initialize managers
        print("Loading configuration...")
        # Use absolute path to config.yml in project root
        config_path = Path(__file__).parent / "../../config.yml"
        self.config_manager = ConfigurationManager(str(config_path))

        print("Loading deployment state...")
        self.state_manager = DeploymentState()

        # Load configuration
        self.config: dict = self.load_configuration()

        # Validate environment early
        self.validate_environment()

        # Create stacks with dependencies
        print("\nCreating CDK stacks...")
        self.create_stacks()

        print("\nCDK app initialization complete!")
        print("=" * 60)

    def validate_environment(self) -> None:
        """Validate AWS environment and CDK requirements."""
        print("\nValidating environment...")

        # Check AWS credentials
        account = os.getenv("CDK_DEFAULT_ACCOUNT", "")
        region = os.getenv("CDK_DEFAULT_REGION", "us-east-1")

        if not account:
            print("ERROR: CDK_DEFAULT_ACCOUNT environment variable not set!")
            print("   Please set your AWS account ID:")
            print("   export CDK_DEFAULT_ACCOUNT=123456789012")
            sys.exit(1)

        print(f"   AWS Account: {account}")
        print(f"   AWS Region: {region}")

        # Validate configuration
        is_valid, errors = validate_required_config(self.config)
        if not is_valid:
            print("\nERROR: Invalid configuration!")
            for error in errors:
                print(f"   - {error}")
            print("\n   Please update your config.yml with the required values.")
            sys.exit(1)

        # Validate critical parameters
        params: dict = self.get_deployment_parameters()
        domain_name = params.get("domain_name", "")
        hosted_zone_id = params.get("hosted_zone_id", "")

        if not domain_name or not isinstance(domain_name, str):
            print("\nERROR: domain_name must be a non-empty string!")
            sys.exit(1)

        if not hosted_zone_id or not isinstance(hosted_zone_id, str):
            print("\nERROR: hosted_zone_id must be a non-empty string!")
            sys.exit(1)

    def load_configuration(self) -> dict:
        """Load configuration from config.yml merged with template defaults."""
        template_path = Path(__file__).parent / "../../config.template.yml"

        template_config: dict = load_yaml_file(template_path)
        if not template_config:
            template_config = {}

        if self.config_manager.exists():
            # Merge existing config over template
            deep_merge(template_config, self.config_manager.config)
            return template_config
        else:
            # Just use template if no config exists
            return template_config

    def create_stacks(self) -> None:
        """Create all CDK stacks with proper dependencies."""
        env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))

        # Get deployment parameters
        params: dict = self.get_deployment_parameters()

        # Determine deployment mode
        deploy_mode: str = get_deployment_mode(self.app, params)

        print(f"Deployment mode: {deploy_mode}")

        # Create IAM stack early (no dependencies)
        self.create_iam_stack(env, params)

        # Create foundation stacks (S3, DynamoDB, Cognito, CloudWatch)
        self.create_foundation_stacks(env, params)

        # Create build infrastructure (CodeBuild)
        self.create_build_infrastructure(env, params, deploy_mode)

        # Note: Build execution will happen here in phase 2

        # Create application stacks (Lambda, API Gateway)
        self.create_application_stacks(env, params)

        # Create distribution layer (CloudFront)
        self.create_distribution_layer(env, params)

    def create_foundation_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create foundation infrastructure stacks."""
        # Create S3 stack first (no dependencies)
        self.s3_stack = S3Stack(
            self.app,
            "s3",
            game_name=params.get("game_name", "eidolon-engine"),
            portal_bucket_name=params.get("portal_bucket_name"), # type: ignore
            scripts_bucket_name=params.get("scripts_bucket_name"), # type: ignore
            env=env,
        )

        # Create unified DynamoDB tables (depends on IAM for role)
        unified_tables = self.get_unified_table_names(params)

        self.dynamodb_stack = DynamoDBStack(
            self.app,
            "dynamodb",
            game_name=params.get("game_name", "eidolon-engine"),
            table_names=unified_tables,
            execution_role_arn=self.iam_stack.execution_role.role_arn,
            lambda_execution_role_arn=self.iam_stack.lambda_execution_role.role_arn,
            env=env,
        )
        self.dynamodb_stack.add_dependency(self.iam_stack)

        dev_mode = params.get("dev_mode", True)

        # Check if we should skip Cognito stack creation
        if params.get("existing_user_pool_id"):
            print(f"Skipping Cognito stack creation - using existing user pool: {params['existing_user_pool_id']}")
            self.cognito_stack = None
            self.existing_cognito_user_pool_id = params.get("existing_user_pool_id")
            self.existing_cognito_app_client_id = params.get("existing_app_client_id")
        else:
            # Get portal domain from CloudFront configuration
            domain_name = params.get("domain_name", "")
            portal_subdomain = self.config.get("CloudFront", {}).get("Subdomain", "portal")
            portal_domain = f"{portal_subdomain}.{domain_name}" if domain_name else None

            self.cognito_stack = CognitoStack(
                self.app,
                "cognito",
                contact_email=params.get("contact_email", "contact@darkrelics.net"),
                dev_mode=dev_mode,
                portal_domain=portal_domain, # type: ignore
                env=env,
            )
            self.existing_cognito_user_pool_id = None
            self.existing_cognito_app_client_id = None

        # Create CloudWatch stack
        self.cloudwatch_stack = CloudWatchStack(
            self.app,
            "cloudwatch",
            retention_days=params.get("log_retention_days", 365),
            env=env,
        )

    def create_build_infrastructure(self, env: cdk.Environment, params: dict, deploy_mode: str) -> None:
        """Create CodeBuild infrastructure."""
        # Create CodeBuild stack
        buildspec_path = params.get("portal_buildspec_path", "buildspec/portal.yml")
        if deploy_mode in ["incremental", "hybrid"]:
            buildspec_path = params.get("incremental_buildspec_path", "buildspec/incremental.yml")

        # Construct API domain
        domain_name = params.get("domain_name", "")
        api_subdomain = params.get("api_subdomain", "api")
        api_domain = f"{api_subdomain}.{domain_name}" if domain_name else ""

        self.codebuild_stack = CodeBuildStack(
            self.app,
            "codebuild",
            github_owner=params.get("github_owner", "robinje"),
            github_repo=params.get("github_repo", "eidolon-engine"),
            github_branch=params.get("github_branch", "main"),
            cognito_user_pool_id=( self.cognito_stack.user_pool.user_pool_id if self.cognito_stack else self.existing_cognito_user_pool_id), #type: ignore
            cognito_app_client_id=(self.cognito_stack.app_client.user_pool_client_id if self.cognito_stack else self.existing_cognito_app_client_id), #type: ignore
            portal_bucket=self.s3_stack.portal_bucket,
            lambda_bucket=self.s3_stack.lambda_bucket,
            api_domain=api_domain,
            buildspec_path=buildspec_path,
            cloudfront_distribution_id="",
            env=env,
        )
        if self.cognito_stack:
            self.codebuild_stack.add_dependency(self.cognito_stack)
        self.codebuild_stack.add_dependency(self.s3_stack)

    def create_application_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create application layer stacks (Lambda, API Gateway)."""
        # Get unified table names
        unified_tables: dict = self.get_unified_table_names(params)

        # Create base Lambda stack for common functions
        self.base_lambda_stack = BaseLambdaStack(
            self.app,
            "base-lambda",
            lambda_bucket=self.s3_stack.lambda_bucket,
            env=env,
        )
        self.base_lambda_stack.add_dependency(self.s3_stack)

        # Create unified Lambda stack with all API functions
        domain_name = params.get("domain_name", "")
        hosted_zone_id = params.get("hosted_zone_id", "")

        self.lambda_stack = LambdaStack(
            self.app,
            "lambda",
            config={
                "lambda_bucket": self.s3_stack.lambda_bucket.bucket_name,
                "players_table": unified_tables["Players"],
                "characters_table": unified_tables["Characters"],
                "archetypes_table": unified_tables["Archetypes"],
                "items_table": unified_tables.get("Items", ""),
                "cognito_user_pool_arn": (
                    self.cognito_stack.user_pool.user_pool_arn
                    if self.cognito_stack
                    else f"arn:aws:cognito-idp:{env.region}:{env.account}:userpool/{self.existing_cognito_user_pool_id}"
                ),
                "dependencies_layer_arn": self.base_lambda_stack.dependencies_layer.layer_version_arn,
                "domain_name": domain_name,
                "hosted_zone_id": hosted_zone_id,
                "api_subdomain": params.get("api_subdomain", "api"),
                "allowed_cors_origins": params.get("allowed_cors_origins", []),
                "lambda_execution_role_arn": self.iam_stack.lambda_execution_role.role_arn,
            },
            env=env,
        )
        self.lambda_stack.add_dependency(self.base_lambda_stack)
        self.lambda_stack.add_dependency(self.dynamodb_stack)
        self.lambda_stack.add_dependency(self.iam_stack)
        if self.cognito_stack:
            self.lambda_stack.add_dependency(self.cognito_stack)

    def create_distribution_layer(self, env: cdk.Environment, params: dict) -> None:
        """Create CloudFront distribution."""
        # Get CloudFront configuration
        cloudfront_config = self.config.get("CloudFront", {})
        portal_subdomain = cloudfront_config.get("Subdomain", "")

        self.cloudfront_stack = CloudFrontStack(
            self.app,
            "cloudfront",
            portal_bucket=self.s3_stack.portal_bucket,
            domain_name=params.get("domain_name", ""),
            portal_subdomain=portal_subdomain,
            hosted_zone_id=params.get("hosted_zone_id", ""),
            existing_distribution_id=params.get("cloudfront_distribution_id", ""),
            env=env,
        )
        self.cloudfront_stack.add_dependency(self.s3_stack)

    def get_unified_table_names(self, params: dict) -> dict:
        """Get unified table names for all deployment modes.

        Returns:
            Dictionary of table names used by all modes
        """

        tables: dict = {
            "Players": "players",
            "Characters": "characters",
            "Rooms": "rooms",
            "Exits": "exits",
            "Items": "items",
            "Prototypes": "prototypes",
            "Archetypes": "archetypes",
            "Motd": "motd",
            "Story": "story",
        }

        configured_tables = params.get("dynamodb_tables", {})
        tables.update(configured_tables)

        return tables

    def create_iam_stack(self, env: cdk.Environment, params: dict) -> None:
        """Create IAM stack with server execution role."""
        self.iam_stack = IAMStack(
            self.app,
            "iam",
            game_name=params.get("game_name", "eidolon-engine"),
            env=env,
        )

    def get_deployment_parameters(self) -> dict:
        """Get deployment parameters from config or state."""
        print("\nLoading deployment parameters...")

        # Start with defaults
        params: dict = {
            "game_name": "eidolon-engine",
            "contact_email": "contact@darkrelics.net",
            "github_owner": "robinje",
            "github_repo": "eidolon-engine",
            "github_branch": "develop",
            "log_retention_days": 365,
            "deployment_mode": "hybrid",
            "dynamodb_tables": {},
            "allowed_cors_origins": [],
        }
        print("   Loaded default parameters")

        stored_params: dict = self.state_manager.get_parameters()
        if stored_params:
            print(f"   Found {len(stored_params)} stored parameters")
            params.update(stored_params)

        self.load_game_config(params)
        self.load_deployment_config(params)
        self.load_dynamodb_config(params)
        self.load_cognito_config(params)
        self.load_codebuild_config(params)
        self.load_api_config(params)
        self.load_cors_config(params)
        self.load_github_config(params)

        self.load_context_overrides(params)

        print("\n   Parameter loading complete")
        return params

    def load_game_config(self, params: dict) -> None:
        """Load game configuration section."""
        game_config = self.config.get("Game", {})
        if game_config:
            print("   Loading Game configuration")
            params["game_name"] = game_config.get("name", params.get("game_name", "eidolon-engine"))

            # Check for existing bucket configurations
            if "PortalS3Bucket" in game_config:
                params["portal_bucket_name"] = game_config.get("PortalS3Bucket")
                print(f"     - Using existing portal bucket: {params['portal_bucket_name']}")
            if "ScriptsS3Bucket" in game_config:
                params["scripts_bucket_name"] = game_config.get("ScriptsS3Bucket")
                print(f"     - Using existing scripts bucket: {params['scripts_bucket_name']}")

    def load_deployment_config(self, params: dict) -> None:
        """Load deployment configuration section."""
        deploy_config = self.config.get("Deployment", {})
        if deploy_config:
            print("   Loading Deployment configuration")
            # Check for explicit mode
            if "Mode" in deploy_config:
                params["deployment_mode"] = deploy_config.get("Mode", "hybrid")
            elif self.app.node.try_get_context("deployment_mode") is None:
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

    def load_dynamodb_config(self, params: dict) -> None:
        """Load DynamoDB configuration section."""
        dynamodb_config = self.config.get("DynamoDB", {})
        if dynamodb_config:
            print("   Loading DynamoDB configuration")
            # Load unified tables
            if "Tables" in dynamodb_config:
                params["dynamodb_tables"] = dynamodb_config.get("Tables", {})
                print(f"     - Found {len(params['dynamodb_tables'])} unified tables")
            else:
                tables: dict = {}
                if "SharedTables" in dynamodb_config:
                    tables.update(dynamodb_config.get("SharedTables", {}))
                if "MUDTables" in dynamodb_config:
                    tables.update(dynamodb_config.get("MUDTables", {}))
                if "IncrementalTables" in dynamodb_config:
                    tables.update(dynamodb_config.get("IncrementalTables", {}))
                if tables:
                    params["dynamodb_tables"] = tables
                    print(f"     - Merged {len(tables)} tables from legacy configuration")

    def load_cognito_config(self, params: dict) -> None:
        """Load Cognito configuration section."""
        cognito_config = self.config.get("Cognito", {})
        if cognito_config:
            print("   Loading Cognito configuration")
            if "UserPoolId" in cognito_config and cognito_config.get("UserPoolId"):
                params["existing_user_pool_id"] = cognito_config.get("UserPoolId")
                print(f"     - Found existing user pool: {params['existing_user_pool_id']}")
            if "UserPoolClientId" in cognito_config and cognito_config.get("UserPoolClientId"):
                params["existing_app_client_id"] = cognito_config.get("UserPoolClientId")
                print(f"     - Found existing app client: {params['existing_app_client_id']}")
            if "UserPoolDomain" in cognito_config and cognito_config.get("UserPoolDomain"):
                params["existing_user_pool_domain"] = cognito_config.get("UserPoolDomain")
                print(f"     - Found existing domain: {params['existing_user_pool_domain']}")

    def load_codebuild_config(self, params: dict) -> None:
        """Load CodeBuild configuration section."""
        codebuild_config = self.config.get("CodeBuild", {})
        if codebuild_config:
            print("   Loading CodeBuild configuration")
            if "PortalBuildspecPath" in codebuild_config:
                params["portal_buildspec_path"] = codebuild_config.get("PortalBuildspecPath")
            if "IncrementalBuildspecPath" in codebuild_config:
                params["incremental_buildspec_path"] = codebuild_config.get("IncrementalBuildspecPath")

    def load_api_config(self, params: dict) -> None:
        """Load API configuration section."""
        api_config = self.config.get("API", {})
        if api_config:
            print("   Loading API configuration")
            params["domain_name"] = api_config.get("Domain", "")
            params["hosted_zone_id"] = api_config.get("HostedZoneId", "")
            params["api_subdomain"] = api_config.get("Subdomain", "api")

            print(f"     - Domain: {params['domain_name']}")
            print(f"     - Hosted Zone ID: {params['hosted_zone_id']}")
            print(f"     - API Subdomain: {params['api_subdomain']}")

    def load_cors_config(self, params: dict) -> None:
        """Load CORS configuration section."""
        # Derive CORS origins from CloudFront configuration
        allowed_origins = []

        # Add CloudFront custom domain if configured
        cloudfront_config = self.config.get("CloudFront", {})
        portal_subdomain = cloudfront_config.get("Subdomain", "")
        domain_name = params.get("domain_name", "")

        if portal_subdomain and domain_name:
            portal_origin = f"https://{portal_subdomain}.{domain_name}"
            allowed_origins.append(portal_origin)
            print("Deriving CORS configuration from CloudFront")
            print(f"     - Added portal origin: {portal_origin}")

        # Also add the CloudFront distribution URL if available
        cloudfront_url = cloudfront_config.get("portal_url", "")
        if cloudfront_url and cloudfront_url not in allowed_origins:
            allowed_origins.append(cloudfront_url)
            print(f"     - Added CloudFront distribution URL: {cloudfront_url}")

        # Check for legacy CORS configuration (for backward compatibility)
        cors_config = self.config.get("CORS", {})
        if cors_config:
            if "AllowedOrigins" in cors_config:
                legacy_origins = cors_config.get("AllowedOrigins", [])
                for origin in legacy_origins:
                    if origin not in allowed_origins:
                        allowed_origins.append(origin)
                if legacy_origins:
                    print(f"     - Added {len(legacy_origins)} legacy origins")

        params["allowed_cors_origins"] = allowed_origins
        if allowed_origins:
            print(f"     - Total allowed origins: {len(allowed_origins)}")

    def load_github_config(self, params: dict) -> None:
        """Load GitHub configuration section."""
        github_config = self.config.get("GitHub", {})
        if github_config:
            print("   Loading GitHub configuration")
            params["github_owner"] = github_config.get("Owner", params.get("github_owner", "robinje"))
            params["github_repo"] = github_config.get("Repo", params.get("github_repo", "eidolon-engine"))
            params["github_branch"] = github_config.get("Branch", params.get("github_branch", "develop"))
            print(f"     - Owner: {params['github_owner']}")
            print(f"     - Repo: {params['github_repo']}")
            print(f"     - Branch: {params['github_branch']}")

    def load_context_overrides(self, params: dict) -> None:
        """Override parameters with CDK context values."""
        # Check for context overrides
        github_branch = self.app.node.try_get_context("github_branch")
        if github_branch:
            params["github_branch"] = github_branch
            print(f"   Overriding GitHub branch from context: {github_branch}")

    def synth(self):
        """Synthesize the CDK app."""
        return self.app.synth()


def main() -> None:
    """Main entry point for CDK app."""
    app = EidolonEngineApp()
    app.synth()


if __name__ == "__main__":
    main()
