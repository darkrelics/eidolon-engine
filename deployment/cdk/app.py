"""AWS CDK application for Eidolon Engine infrastructure.

This application defines all AWS resources needed for the Eidolon Engine
game server using AWS CDK for infrastructure as code. Separates MUD
and Incremental deployments.
"""

import json
import os
import sys
from pathlib import Path

# Add parent directory to path to import shared modules
sys.path.insert(0, str(Path(__file__).parent.parent))

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
from stacks.sqs_stack import SQSStack
from stacks.ssm_stack import SSMStack
from state_manager import ConfigurationManager, DeploymentState


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
        file_path: Path to JSON file
        data: Data to save

    Returns:
        True if successful
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except IOError as err:
        print(f"Error saving {file_path}: {err}")
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
        file_path: Path to YAML file
        data: Data to save

    Returns:
        True if successful
    """
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        return True
    except IOError as err:
        print(f"Error saving {file_path}: {err}")
        return False


def deep_merge(base: dict, override: dict) -> None:
    """Deep merge override dict into base dict in-place.

    Args:
        base: Base dictionary to merge into
        override: Dictionary with values to override
    """
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            deep_merge(base[key], value)
        else:
            base[key] = value


def validate_required_config(config: dict) -> tuple:
    """Validate that all required configuration is present.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Required Game configuration
    game_config = config.get("Game", {})
    if not game_config.get("Name"):
        errors.append("Game.Name is required")

    # Required Deployment configuration
    deployment_config = config.get("Deployment", {})
    if not deployment_config.get("ContactEmail"):
        errors.append("Deployment.ContactEmail is required")
    if not deployment_config.get("DomainName"):
        errors.append("Deployment.DomainName is required")
    if not deployment_config.get("HostedZoneId"):
        errors.append("Deployment.HostedZoneId is required")

    # Required AWS configuration
    aws_config = config.get("AWS", {})
    if not aws_config.get("Region"):
        errors.append("AWS.Region is required")

    return len(errors) == 0, errors


def get_deployment_mode(app: cdk.App, params: dict) -> str:
    """Determine deployment mode from context or parameters.

    Args:
        app: CDK application
        params: Deployment parameters

    Returns:
        Deployment mode ('mud' or 'incremental')
    """
    # Check context first (command line argument)
    mode = app.node.try_get_context("deployment_mode")
    if mode:
        return mode

    # Check parameters
    if "deployment_mode" in params:
        return params["deployment_mode"]

    # Default to incremental
    return "incremental"


def validate_stack_specific_config(stack_name: str, config: dict) -> list:
    """Validate configuration for a specific stack.

    Args:
        stack_name: Name of the stack
        config: Configuration dictionary

    Returns:
        List of validation errors
    """
    errors = []

    # Stack-specific validation
    if stack_name == "cognito":
        # Cognito requires contact email
        if not config.get("contact_email"):
            errors.append("Contact email is required for Cognito stack")

    elif stack_name == "s3":
        # Validate S3 bucket names
        for bucket_type in ["portal_bucket_name", "scripts_bucket_name", "lambda_bucket_name"]:
            bucket_name = config.get(bucket_type)
            if bucket_name:
                if len(bucket_name) < 3 or len(bucket_name) > 63:
                    errors.append(f"S3 bucket name must be 3-63 characters: {bucket_name}")
                if ".." in bucket_name or bucket_name.startswith(".") or bucket_name.endswith("."):
                    errors.append(f"Invalid S3 bucket name format: {bucket_name}")

    elif stack_name == "cloudfront":
        # CloudFront requires domain name and hosted zone
        if not config.get("domain_name"):
            errors.append("Domain name is required for CloudFront")
        if not config.get("hosted_zone_id"):
            errors.append("Hosted zone ID is required for CloudFront")

    return errors


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
            env=env,
            game_name=params["game_name"],
            portal_bucket_name=params.get("portal_bucket_name", ""),
            scripts_bucket_name=params.get("scripts_bucket_name", ""),
            lambda_bucket_name=params.get("lambda_bucket_name", ""),
        )

        # Create DynamoDB stack (no dependencies)
        self.dynamodb_stack = DynamoDBStack(
            self.app,
            "dynamodb",
            env=env,
            game_name=params["game_name"],
            table_prefix=params.get("table_prefix", ""),
            existing_tables=params.get("dynamodb_tables", {}),
        )

        # Create Cognito stack (no dependencies for user pool)
        if params.get("create_cognito", True):
            self.cognito_stack = CognitoStack(
                self.app,
                "cognito",
                env=env,
                game_name=params["game_name"],
                user_pool_name=params.get("user_pool_name"),
                user_pool_id=params.get("user_pool_id"),
                app_client_id=params.get("app_client_id"),
                contact_email=params["contact_email"],
            )
        else:
            self.cognito_stack = None

        # Create CloudWatch stack (no dependencies)
        self.cloudwatch_stack = CloudWatchStack(
            self.app,
            "cloudwatch",
            env=env,
            retention_days=params.get("log_retention_days", 7),
        )

        # Create SSM parameter stack
        self.ssm_stack = SSMStack(self.app, "ssm", config=params, env=env)

        # Create SQS stack
        self.sqs_stack = SQSStack(self.app, "sqs", config=params, env=env)

    def create_build_infrastructure(self, env: cdk.Environment, params: dict, deploy_mode: str) -> None:
        """Create build infrastructure stacks."""
        # Create CodeBuild stack
        self.codebuild_stack = CodeBuildStack(
            self.app,
            "codebuild",
            env=env,
            github_owner=params.get("github_owner", ""),
            github_repo=params.get("github_repo", ""),
            github_branch=params.get("github_branch", "main"),
            portal_bucket=self.s3_stack.portal_bucket,
            lambda_bucket=self.s3_stack.lambda_bucket,
            buildspec_path=params.get("buildspec_path", "."),
            # Required Cognito parameters
            cognito_user_pool_id=params.get("user_pool_id", ""),
            cognito_app_client_id=params.get("app_client_id", ""),
            # Optional values for runtime updates
            api_domain=params.get("api_domain", ""),
            cloudfront_distribution_id=params.get("cloudfront_distribution_id", ""),
        )

        # Add dependency on S3 stack
        self.codebuild_stack.add_dependency(self.s3_stack)

    def create_application_stacks(self, env: cdk.Environment, params: dict) -> None:
        """Create application layer stacks."""
        # Create base Lambda stack with shared layer
        self.base_lambda_stack = BaseLambdaStack(
            self.app,
            "base-lambda",
            env=env,
            game_name=params["game_name"],
            lambda_bucket=self.s3_stack.lambda_bucket,
        )

        # Add dependency on S3 stack
        self.base_lambda_stack.add_dependency(self.s3_stack)

        # Create Lambda functions and API Gateway stack
        # Prepare config for LambdaStack
        lambda_config = {
            "game_name": params["game_name"],
            "domain_name": params["domain_name"],
            "hosted_zone_id": params["hosted_zone_id"],
            "lambda_bucket": self.s3_stack.lambda_bucket.bucket_name,
            "dependencies_layer_arn": getattr(self.base_lambda_stack, "lambda_layer_arn", ""),
            "cognito_user_pool_arn": self.cognito_stack.user_pool.user_pool_arn if self.cognito_stack else "",
            # Add DynamoDB tables
            "players_table": "players",
            "characters_table": "characters",
            "archetypes_table": "archetypes",
            "items_table": "items",
            "story_table": "story",
            "segments_table": "segments",
            "active_segments_table": "active_segments",
            "opponents_table": "opponents",
            "story_history_table": "story_history",
            "segment_history_table": "segment_history",
        }

        self.lambda_stack = LambdaStack(
            self.app,
            "lambda",
            config=lambda_config,
            env=env,
        )

        # Add dependencies
        self.lambda_stack.add_dependency(self.base_lambda_stack)
        self.lambda_stack.add_dependency(self.dynamodb_stack)
        self.lambda_stack.add_dependency(self.cloudwatch_stack)
        self.lambda_stack.add_dependency(self.sqs_stack)
        if self.cognito_stack:
            self.lambda_stack.add_dependency(self.cognito_stack)

    def create_distribution_layer(self, env: cdk.Environment, params: dict) -> None:
        """Create distribution layer stacks."""
        # Create CloudFront stack
        self.cloudfront_stack = CloudFrontStack(
            self.app,
            "cloudfront",
            env=env,
            game_name=params["game_name"],
            domain_name=params["domain_name"],
            hosted_zone_id=params["hosted_zone_id"],
            portal_bucket=self.s3_stack.portal_bucket,
            api_gateway_url=self.lambda_stack.api.url if hasattr(self.lambda_stack, "api") else "",
            distribution_id=params.get("cloudfront_distribution_id"),
        )

        # Add dependencies
        self.cloudfront_stack.add_dependency(self.s3_stack)
        self.cloudfront_stack.add_dependency(self.lambda_stack)

    def create_iam_stack(self, env: cdk.Environment, params: dict) -> None:
        """Create IAM stack."""
        self.iam_stack = IAMStack(
            self.app,
            "iam",
            env=env,
            game_name=params["game_name"],
        )

    def get_deployment_parameters(self) -> dict:
        """Get deployment parameters from configuration and state.

        Returns:
            Dictionary of deployment parameters
        """
        params: dict = {}

        # Get parameters from state if available
        stored_params = self.state_manager.state.get("parameters", {})
        if stored_params:
            params.update(stored_params)

        self.load_game_config(params)
        self.load_deployment_config(params)
        self.load_dynamodb_config(params)
        self.load_cognito_config(params)
        self.load_s3_config(params)
        self.load_cloudfront_config(params)
        self.load_codebuild_config(params)

        # Override with context values if provided
        for key in ["deployment_mode", "github_branch"]:
            context_value = self.app.node.try_get_context(key)
            if context_value:
                params[key] = context_value

        return params

    def load_game_config(self, params: dict) -> None:
        """Load game configuration section."""
        game_config = self.config.get("Game", {})
        if game_config:
            print("   Loading Game configuration")
            params["game_name"] = game_config.get("Name", params.get("game_name", "eidolon-engine"))
            params["default_health"] = game_config.get("StartingHealth", 10)
            params["default_essence"] = game_config.get("StartingEssence", 3)
            params["max_characters_per_player"] = game_config.get("MaxCharactersPerPlayer", 10)

    def load_deployment_config(self, params: dict) -> None:
        """Load deployment configuration section."""
        deployment_config = self.config.get("Deployment", {})
        if deployment_config:
            print("   Loading Deployment configuration")
            params["contact_email"] = deployment_config.get("ContactEmail", "")
            params["domain_name"] = deployment_config.get("DomainName", "")
            params["hosted_zone_id"] = deployment_config.get("HostedZoneId", "")
            params["log_retention_days"] = deployment_config.get("LogRetentionDays", 7)
            params["deployment_mode"] = deployment_config.get("Mode", "incremental")
            params["github_owner"] = deployment_config.get("GitHubOwner", "")
            params["github_repo"] = deployment_config.get("GitHubRepo", "")
            params["github_branch"] = deployment_config.get("GitHubBranch", "main")

    def load_dynamodb_config(self, params: dict) -> None:
        """Load DynamoDB configuration section."""
        dynamodb_config = self.config.get("DynamoDB", {})
        if dynamodb_config:
            print("   Loading DynamoDB configuration")
            tables = dynamodb_config.get("Tables", {})
            if tables:
                # Map configuration to expected parameter format
                params["dynamodb_tables"] = {
                    "Players": tables.get("Players", "players"),
                    "Characters": tables.get("Characters", "characters"),
                    "Archetypes": tables.get("Archetypes", "archetypes"),
                    "Rooms": tables.get("Rooms", "rooms"),
                    "Items": tables.get("Items", "items"),
                }

    def load_cognito_config(self, params: dict) -> None:
        """Load Cognito configuration section."""
        cognito_config = self.config.get("Cognito", {})
        if cognito_config:
            print("   Loading Cognito configuration")
            params["user_pool_id"] = cognito_config.get("UserPoolId", "")
            params["app_client_id"] = cognito_config.get("UserPoolClientId", "")
            params["user_pool_name"] = cognito_config.get("UserPoolName", "")
            # If we have existing Cognito resources, don't create new ones
            if params["user_pool_id"]:
                params["create_cognito"] = False

    def load_s3_config(self, params: dict) -> None:
        """Load S3 configuration section."""
        s3_config = self.config.get("S3", {})
        if s3_config:
            print("   Loading S3 configuration")
            params["portal_bucket_name"] = s3_config.get("PortalBucket", "")
            params["scripts_bucket_name"] = s3_config.get("ScriptsBucket", "")
            params["lambda_bucket_name"] = s3_config.get("ArtifactsBucket", "")

    def load_cloudfront_config(self, params: dict) -> None:
        """Load CloudFront configuration section."""
        cloudfront_config = self.config.get("CloudFront", {})
        if cloudfront_config:
            print("   Loading CloudFront configuration")
            params["cloudfront_distribution_id"] = cloudfront_config.get("DistributionId", "")
            # Calculate API domain from CloudFront domain if needed
            if not params.get("api_domain") and cloudfront_config.get("DomainName"):
                params["api_domain"] = f"api.{cloudfront_config['DomainName']}"

    def load_codebuild_config(self, params: dict) -> None:
        """Load CodeBuild configuration section."""
        codebuild_config = self.config.get("CodeBuild", {})
        if codebuild_config:
            print("   Loading CodeBuild configuration")
            params["buildspec_path"] = codebuild_config.get("BuildspecPath")


# Entry point for CDK app
app_instance = EidolonEngineApp()
app = app_instance.app
