"""Player stack for Cognito User Pool."""

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class PlayerStack(Stack):
    """Player stack for Eidolon Engine authentication."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        lambda_function_arn: str = "",
        reply_email: str = "contact@darkrelics.net",
        existing_user_pool_id: str = "",
        **kwargs,
    ) -> None:
        """Initialize Player stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            lambda_function_arn: ARN of cognito-player-new Lambda function
            reply_email: Email address for Cognito notifications
            existing_user_pool_id: ID of existing user pool to import (empty if none)
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.lambda_function_arn = lambda_function_arn
        self.reply_email = reply_email
        self.existing_user_pool_id = existing_user_pool_id
        self.is_imported_pool = False  # Initialize flag
        super().__init__(scope, stack_id, **kwargs)
        # Apply system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Create Cognito User Pool
        self.user_pool = self._create_user_pool()

        # Create User Pool Client
        self.app_client = self._create_app_client()

        # Configure Lambda trigger if ARN provided
        if self.lambda_function_arn:
            self._configure_lambda_trigger()

        # Add outputs
        self._add_outputs()

    def _create_user_pool(self):
        """Create Cognito User Pool."""
        user_pool_name = "eidolon-users"

        # Check if we should import from context
        if self.existing_user_pool_id:
            print(f"  Using existing user pool from context: {self.existing_user_pool_id}")
            # Mark that this is an imported pool
            self.is_imported_pool = True
            return cognito.UserPool.from_user_pool_id(self, "UserPool", self.existing_user_pool_id)

        print(f"  Creating/updating user pool: {user_pool_name}")
        print(f"  Reply email: {self.reply_email}")
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

    def _configure_lambda_trigger(self) -> None:
        """Configure Lambda trigger for user pool."""
        # Skip trigger configuration for imported pools
        if self.is_imported_pool:
            return

        print("  Configuring PostConfirmation trigger with Lambda ARN")

        # Import the Lambda function
        lambda_function = lambda_.Function.from_function_arn(self, "CognitoPlayerNewFunction", self.lambda_function_arn)

        # Add trigger to user pool (only works for created pools)
        self.user_pool.add_trigger(cognito.UserPoolOperation.POST_CONFIRMATION, lambda_function)  # type: ignore

        # Grant Cognito permission to invoke the Lambda
        lambda_function.add_permission(
            "CognitoInvokePermission",
            principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),  # type: ignore
            source_arn=self.user_pool.user_pool_arn,
        )

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id, description="Cognito User Pool ID")

        CfnOutput(self, "UserPoolClientId", value=self.app_client.user_pool_client_id, description="Cognito User Pool Client ID")

        CfnOutput(self, "UserPoolArn", value=self.user_pool.user_pool_arn, description="Cognito User Pool ARN")
