"""Player stack for Cognito User Pool and Lambda function."""

from pathlib import Path

import aws_cdk as cdk
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


def load_email_template(template_name: str) -> str:
    """Load email template from data directory.

    Args:
        template_name: Name of template file (e.g., 'cognito-verification-email.html')

    Returns:
        Template content as string, or empty string if file not found
    """
    # Get project root (parent of deployment directory)
    project_root = Path(__file__).parent.parent.parent
    template_path = project_root / "data" / template_name

    if not template_path.exists():
        print(f"  Warning: Email template not found: {template_path}")
        return ""

    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            content = f.read()
        print(f"  Loaded email template: {template_name} ({len(content)} bytes)")
        return content
    except Exception as e:
        print(f"  Error loading template {template_name}: {e}")
        return ""


class PlayerStack(Stack):
    """Player stack for Eidolon Engine authentication."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        s3_bucket: str = "",
        client_fqdn: str = "",
        dynamodb_policy_arn: str = "",
        dynamodb_tables=None,
        lambda_layer_arn: str = "",
        lambda_role_arn: str = "",
        reply_email: str = "contact@darkrelics.net",
        existing_user_pool_id: str = "",
        **kwargs,
    ) -> None:
        """Initialize Player stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            s3_bucket: S3 bucket containing Lambda artifacts
            client_fqdn: Client FQDN for CORS configuration
            dynamodb_policy_arn: ARN of DynamoDB policy to attach
            dynamodb_tables: Dictionary of DynamoDB table names
            lambda_layer_arn: ARN of shared Lambda layer from Character stack
            lambda_role_arn: ARN of shared Lambda execution role from Character stack
            reply_email: Email address for Cognito notifications
            existing_user_pool_id: ID of existing user pool to import (empty if none)
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.client_fqdn = client_fqdn
        self.dynamodb_policy_arn = dynamodb_policy_arn
        self.dynamodb_tables = dynamodb_tables or {}
        self.lambda_layer_arn = lambda_layer_arn
        self.lambda_role_arn = lambda_role_arn
        self.reply_email = reply_email
        self.existing_user_pool_id = existing_user_pool_id
        self.is_imported_pool = False  # Initialize flag
        super().__init__(scope, stack_id, **kwargs)
        # Apply system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Import shared Lambda layer and role from Character stack
        self.lambda_layer = self._import_lambda_layer()
        self.lambda_role = self._import_lambda_role()

        # Deploy cognito-player-new Lambda function
        self.lambda_function = self._deploy_lambda_function()

        # Create Cognito User Pool
        self.user_pool = self._create_user_pool()

        # Create User Pool Client
        self.app_client = self._create_app_client()

        # Configure Lambda trigger
        self._configure_lambda_trigger()

        # Add outputs
        self._add_outputs()

    def _create_user_pool(self):
        """Create Cognito User Pool with custom email template."""
        user_pool_name = "eidolon-users"

        # Check if we should import from context
        if self.existing_user_pool_id:
            print(f"  Using existing user pool from context: {self.existing_user_pool_id}")
            # Mark that this is an imported pool
            self.is_imported_pool = True
            return cognito.UserPool.from_user_pool_id(self, "UserPool", self.existing_user_pool_id)

        print(f"  Creating/updating user pool: {user_pool_name}")
        print(f"  Reply email: {self.reply_email}")

        # Load email template from data directory
        html_template = load_email_template("cognito-verification-email.html")

        # Prepare user verification config
        if html_template:
            # Use custom HTML template
            user_verification = cognito.UserVerificationConfig(
                email_subject="Verify your Eidolon Engine account",
                email_body=html_template,
                email_style=cognito.VerificationEmailStyle.CODE,
            )
        else:
            # Fallback to simple text template
            user_verification = cognito.UserVerificationConfig(
                email_subject="Verify your Eidolon Engine account",
                email_body="""Welcome to Eidolon Engine!

Please verify your email using one of these methods:

METHOD 1 - Click this link: {##Verify Email##}

METHOD 2 - Enter this code in the app: {####}

Code expires in 24 hours. Need a new code? Tap "Resend Code" in the app.""",
                email_style=cognito.VerificationEmailStyle.CODE,
            )

        self.is_imported_pool = False
        return cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=user_pool_name,
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8, require_lowercase=True, require_uppercase=True, require_digits=True, require_symbols=True
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
            email=cognito.UserPoolEmail.with_cognito(reply_to=self.reply_email),
            user_verification=user_verification,
        )

    def _create_app_client(self) -> cognito.UserPoolClient:
        """Create User Pool Client."""
        print("  Creating user pool client")

        return self.user_pool.add_client(
            "AppClient",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False,
            prevent_user_existence_errors=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30),
        )

    def _import_lambda_layer(self) -> lambda_.ILayerVersion:
        """Import shared Lambda layer from Character stack."""
        if self.lambda_layer_arn:
            return lambda_.LayerVersion.from_layer_version_arn(self, "ImportedLambdaLayer", self.lambda_layer_arn)
        else:
            # Try to import from CloudFormation export
            try:
                layer_arn = cdk.Fn.import_value("eidolon-lambda-layer-arn")
                return lambda_.LayerVersion.from_layer_version_arn(self, "ImportedLambdaLayer", layer_arn)
            except Exception as e:
                print(f"  Warning: Failed to import Lambda layer from CloudFormation export: {e}")
                raise ValueError("Lambda layer ARN not provided and CloudFormation export not found") from e

    def _import_lambda_role(self) -> iam.IRole:
        """Import shared Lambda execution role from Character stack."""
        if self.lambda_role_arn:
            return iam.Role.from_role_arn(self, "ImportedLambdaRole", self.lambda_role_arn)
        else:
            # Try to import from CloudFormation export
            try:
                role_arn = cdk.Fn.import_value("eidolon-lambda-role-arn")
                return iam.Role.from_role_arn(self, "ImportedLambdaRole", role_arn)
            except Exception as e:
                print(f"  Warning: Failed to import Lambda role from CloudFormation export: {e}")
                raise ValueError("Lambda role ARN not provided and CloudFormation export not found") from e

    def _deploy_lambda_function(self) -> lambda_.Function:
        """Deploy cognito-player-new Lambda function."""
        print("  Deploying Lambda function: cognito-player-new")

        bucket = s3.Bucket.from_bucket_name(self, "FunctionsBucket", self.s3_bucket_name)

        # Use client FQDN for CORS origin
        cors_origin = f"https://{self.client_fqdn}" if self.client_fqdn else "*"

        env_vars = {
            "APPLICATION_NAME": "eidolon-engine",
            "LOG_LEVEL": "INFO",
            "ALLOWED_ORIGINS": cors_origin,
            "CORS_ALLOW_CREDENTIALS": "true",
            "CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS",
            "CORS_MAX_AGE": "86400",
        }

        # Add DynamoDB table names
        table_mapping = {
            "players_table": "players",
            "characters_table": "characters",
        }

        for env_key, table_key in table_mapping.items():
            env_vars[env_key] = self.dynamodb_tables.get(table_key, table_key)

        return lambda_.Function(
            self,
            "CognitoPlayerNewFunction",
            function_name="cognito-player-new",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="cognito_player_new.lambda_handler",
            code=lambda_.Code.from_bucket(bucket, "cognito-player-new.zip"),
            layers=[self.lambda_layer],
            role=self.lambda_role,
            timeout=Duration.seconds(30),
            memory_size=128,
            environment=env_vars,
            description="Eidolon Engine Cognito post-confirmation trigger",
        )

    def _configure_lambda_trigger(self) -> None:
        """Configure Lambda trigger for user pool."""
        # Skip trigger configuration for imported pools
        if self.is_imported_pool:
            return

        print("  Configuring PostConfirmation trigger with Lambda function")

        # Add trigger to user pool (only works for created pools)
        self.user_pool.add_trigger(cognito.UserPoolOperation.POST_CONFIRMATION, self.lambda_function)  # type: ignore

        # Grant Cognito permission to invoke the Lambda
        self.lambda_function.add_permission(
            "CognitoInvokePermission",
            principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),  # type: ignore
            source_arn=self.user_pool.user_pool_arn,
        )

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id, description="Cognito User Pool ID")

        CfnOutput(self, "UserPoolClientId", value=self.app_client.user_pool_client_id, description="Cognito User Pool Client ID")

        CfnOutput(self, "UserPoolArn", value=self.user_pool.user_pool_arn, description="Cognito User Pool ARN")
