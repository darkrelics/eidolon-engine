"""AWS Cognito stack for user authentication."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class CognitoStack(Stack):
    """Cognito stack for Eidolon Engine user authentication."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        contact_email: str = "",
        post_confirmation_lambda_arn = None,
        dev_mode: bool = False,
        portal_domain: str = "",
        **kwargs,
    ) -> None:
        """Initialize Cognito stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            contact_email: Administrator contact email (optional in dev mode)
            post_confirmation_lambda_arn: Optional Lambda function ARN for post-confirmation trigger
            dev_mode: If True, disables email sending and auto-verifies users
            portal_domain: Domain name for the portal (e.g., portal.darkrelics.net)
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Configure email settings based on mode
        if dev_mode:
            # In dev mode, use Cognito default email (no SES required)
            email_config = cognito.UserPoolEmail.with_cognito()
            auto_verify_attrs = None  # No auto-verification in dev mode
        else:
            # Production mode with SES
            if not contact_email:
                raise ValueError("contact_email is required when not in dev_mode")
            email_config = cognito.UserPoolEmail.with_ses(from_email=contact_email, reply_to=contact_email)
            auto_verify_attrs = cognito.AutoVerifiedAttrs(email=True)

        # Create User Pool
        self.user_pool = cognito.UserPool(
            self,
            "users",
            user_pool_name="eidolon-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True, username=False),
            auto_verify=auto_verify_attrs,
            password_policy=cognito.PasswordPolicy(
                min_length=8, require_lowercase=True, require_uppercase=True, require_digits=True, require_symbols=True
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.DESTROY,
            email=email_config,
        )

        # Create App Client
        # Configure OAuth settings if portal domain is provided
        oauth_config = None
        if portal_domain:
            portal_url: str = f"https://{portal_domain}"
            oauth_config = cognito.OAuthSettings(
                flows=cognito.OAuthFlows(
                    authorization_code_grant=True,
                    implicit_code_grant=True,
                ),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PHONE,
                    cognito.OAuthScope.PROFILE,
                    cognito.OAuthScope.COGNITO_ADMIN,
                ],
                callback_urls=[portal_url],
                logout_urls=[portal_url],
            )

        self.app_client = self.user_pool.add_client(
            "app-client",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False,
            prevent_user_existence_errors=True,
            o_auth=oauth_config,
            supported_identity_providers=[cognito.UserPoolClientIdentityProvider.COGNITO] if oauth_config else None,
        )

        # Create User Pool Domain
        # Simple domain prefix - will be unique per AWS account
        self.domain = self.user_pool.add_domain(
            "user-pool-domain",
            cognito_domain=cognito.CognitoDomainOptions(domain_prefix="eidolon-auth"),
        )

        # Output values
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id, description="Cognito User Pool ID")

        CfnOutput(self, "AppClientId", value=self.app_client.user_pool_client_id, description="Cognito App Client ID")

        CfnOutput(self, "UserPoolDomain", value=self.domain.domain_name, description="Cognito User Pool Domain")

        CfnOutput(self, "UserPoolArn", value=self.user_pool.user_pool_arn, description="Cognito User Pool ARN")

    def add_lambda_trigger(self, trigger_type: str, lambda_function: lambda_.IFunction) -> None:
        """Add a Lambda trigger to the user pool.

        Args:
            trigger_type: Type of trigger (e.g., 'PostConfirmation')
            lambda_function: Lambda function to trigger
        """
        if trigger_type == "PostConfirmation":
            self.user_pool.add_trigger(cognito.UserPoolOperation.POST_CONFIRMATION, lambda_function)
