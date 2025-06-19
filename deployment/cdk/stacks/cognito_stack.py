"""AWS Cognito stack for user authentication."""

from aws_cdk import Stack, aws_cognito as cognito, aws_iam as iam, CfnOutput, RemovalPolicy
from constructs import Construct


class CognitoStack(Stack):
    """Cognito stack for Eidolon Engine user authentication."""

    def __init__(self, scope: Construct, construct_id: str, game_name: str, contact_email: str, **kwargs) -> None:
        """Initialize Cognito stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            contact_email: Administrator contact email
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create User Pool
        self.user_pool = cognito.UserPool(
            self,
            "users",
            user_pool_name="eidolon-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8, require_lowercase=True, require_uppercase=True, require_digits=True, require_symbols=True
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
            email=cognito.UserPoolEmail.with_ses(from_email=contact_email, reply_to=contact_email),
        )

        # Create App Client
        self.app_client = self.user_pool.add_client(
            "app-client",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False,
            prevent_user_existence_errors=True,
        )

        # Create IAM role for authenticated users
        self.authenticated_role = iam.Role(
            self,
            "authenticated-role",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                conditions={
                    "StringEquals": {"cognito-identity.amazonaws.com:aud": self.user_pool.user_pool_id},
                    "ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "authenticated"},
                },
            ),
            description="Role for authenticated Eidolon Engine users",
        )

        # Output values
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id, description="Cognito User Pool ID")

        CfnOutput(self, "AppClientId", value=self.app_client.user_pool_client_id, description="Cognito App Client ID")

        CfnOutput(
            self, "AuthenticatedRoleArn", value=self.authenticated_role.role_arn, description="IAM role ARN for authenticated users"
        )
