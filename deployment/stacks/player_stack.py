"""Player stack for Cognito User Pool."""

from aws_cdk import Stack, RemovalPolicy, CfnOutput, Duration
from aws_cdk import aws_cognito as cognito
from constructs import Construct


class PlayerStack(Stack):
    """Player stack for Eidolon Engine authentication."""
    
    def __init__(self, scope: Construct, stack_id: str, 
                 region_name: str = "us-east-1",
                 **kwargs) -> None:
        """Initialize Player stack.
        
        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        super().__init__(scope, stack_id, **kwargs)
        
        # Create Cognito User Pool
        self.user_pool = self._create_user_pool()
        
        # Create User Pool Client
        self.app_client = self._create_app_client()
        
        # Add outputs
        self._add_outputs()
    
    def _create_user_pool(self):
        """Create Cognito User Pool."""
        user_pool_name = "eidolon-users"
        
        print(f"  Creating/updating user pool: {user_pool_name}")
        return cognito.UserPool(
            self,
            "UserPool",
            user_pool_name=user_pool_name,
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(
                email=True,
                username=False
            ),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True
            ),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=RemovalPolicy.RETAIN,
            email=cognito.UserPoolEmail.with_cognito()
        )
    
    def _create_app_client(self) -> cognito.UserPoolClient:
        """Create User Pool Client."""
        print("  Creating user pool client")
        
        return self.user_pool.add_client(
            "AppClient",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True
            ),
            generate_secret=False,
            prevent_user_existence_errors=True,
            access_token_validity=Duration.hours(1),
            id_token_validity=Duration.hours(1),
            refresh_token_validity=Duration.days(30)
        )
    
    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(
            self,
            "UserPoolId",
            value=self.user_pool.user_pool_id,
            description="Cognito User Pool ID"
        )
        
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.app_client.user_pool_client_id,
            description="Cognito User Pool Client ID"
        )
        
        CfnOutput(
            self,
            "UserPoolArn",
            value=self.user_pool.user_pool_arn,
            description="Cognito User Pool ARN"
        )