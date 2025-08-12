"""Player stack for Cognito and authentication Lambda."""

import boto3
from aws_cdk import Stack, RemovalPolicy, CfnOutput, Duration
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from constructs import Construct
from botocore.exceptions import ClientError


class PlayerStack(Stack):
    """Player stack for Eidolon Engine authentication."""
    
    def __init__(self, scope: Construct, stack_id: str, 
                 region_name: str = "us-east-1",
                 s3_bucket: str = "",
                 players_table: str = "players",
                 **kwargs) -> None:
        """Initialize Player stack.
        
        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            s3_bucket: S3 bucket containing Lambda artifacts
            players_table: DynamoDB table name for players
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.players_table = players_table
        super().__init__(scope, stack_id, **kwargs)
        
        # Create Lambda dependencies layer
        self.dependencies_layer = self._create_dependencies_layer()
        
        # Create Cognito User Pool
        self.user_pool = self._create_user_pool()
        
        # Create User Pool Client
        self.app_client = self._create_app_client()
        
        # Create Lambda execution role
        self.lambda_role = self._create_lambda_role()
        
        # Create cognito-player-new Lambda function
        self.new_player_function = self._create_new_player_function()
        
        # Grant Cognito permission to invoke Lambda
        self._create_lambda_permission()
        
        # Configure Cognito trigger
        self._configure_cognito_trigger()
        
        # Add outputs
        self._add_outputs()
    
    def _create_dependencies_layer(self) -> lambda_.LayerVersion:
        """Create Lambda dependencies layer."""
        print(f"  Creating Lambda dependencies layer from {self.s3_bucket_name}")
        
        return lambda_.LayerVersion(
            self,
            "DependenciesLayer",
            code=lambda_.Code.from_bucket(
                lambda_.Bucket.from_bucket_name(self, "LambdaBucket", self.s3_bucket_name),
                "lambda-layer/lambda-layer.zip"
            ),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies for Eidolon Engine Lambda functions"
        )
    
    def _create_user_pool(self) -> cognito.UserPool:
        """Create Cognito User Pool."""
        user_pool_name = "eidolon-users"
        
        # Check if user pool exists
        if self._user_pool_exists(user_pool_name):
            print(f"  Importing existing user pool: {user_pool_name}")
            # Get the user pool ID
            user_pool_id = self._get_user_pool_id(user_pool_name)
            if user_pool_id:
                return cognito.UserPool.from_user_pool_id(
                    self,
                    "UserPool",
                    user_pool_id
                )
        
        print(f"  Creating new user pool: {user_pool_name}")
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
    
    def _user_pool_exists(self, user_pool_name: str) -> bool:
        """Check if a user pool exists."""
        try:
            cognito_client = boto3.client("cognito-idp", region_name=self.region_name)
            response = cognito_client.list_user_pools(MaxResults=60)
            
            for pool in response.get("UserPools", []):
                if pool.get("Name") == user_pool_name:
                    return True
            return False
        except ClientError:
            return False
    
    def _get_user_pool_id(self, user_pool_name: str) -> str:
        """Get user pool ID by name."""
        try:
            cognito_client = boto3.client("cognito-idp", region_name=self.region_name)
            response = cognito_client.list_user_pools(MaxResults=60)
            
            for pool in response.get("UserPools", []):
                if pool.get("Name") == user_pool_name:
                    return pool.get("Id", "")
            return ""
        except ClientError:
            return ""
    
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
    
    def _create_lambda_role(self) -> iam.Role:
        """Create Lambda execution role."""
        print("  Creating Lambda execution role")
        
        role = iam.Role(
            self,
            "LambdaExecutionRole",
            role_name="eidolon-player-lambda-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Execution role for Player Lambda functions"
        )
        
        # Attach basic Lambda execution policy
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        
        # Add inline policy for DynamoDB access instead of importing
        # This avoids dependency issues with the managed policy
        role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan"
                ],
                resources=[
                    f"arn:aws:dynamodb:{self.region_name}:*:table/{self.players_table}",
                    f"arn:aws:dynamodb:{self.region_name}:*:table/{self.players_table}/index/*"
                ]
            )
        )
        
        return role
    
    def _create_new_player_function(self) -> lambda_.Function:
        """Create cognito-player-new Lambda function."""
        print("  Creating cognito-player-new Lambda function")
        
        return lambda_.Function(
            self,
            "NewPlayerFunction",
            function_name="cognito-player-new",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="cognito-player-new.lambda_handler",
            code=lambda_.Code.from_bucket(
                lambda_.Bucket.from_bucket_name(self, "FunctionBucket", self.s3_bucket_name),
                "cognito-player-new.zip"
            ),
            layers=[self.dependencies_layer],
            role=self.lambda_role,
            timeout=Duration.seconds(30),
            memory_size=128,
            environment={
                "players_table": self.players_table
            },
            description="Creates new player records after Cognito user confirmation"
        )
    
    def _create_lambda_permission(self) -> None:
        """Grant Cognito permission to invoke Lambda."""
        print("  Creating Lambda permission for Cognito")
        
        self.new_player_function.add_permission(
            "CognitoInvokePermission",
            principal=iam.ServicePrincipal("cognito-idp.amazonaws.com"),
            source_arn=self.user_pool.user_pool_arn
        )
    
    def _configure_cognito_trigger(self) -> None:
        """Configure Cognito PostConfirmation trigger."""
        print("  Configuring Cognito PostConfirmation trigger")
        
        # Note: This is done through the cfn_user_pool property
        cfn_user_pool = self.user_pool.node.default_child
        cfn_user_pool.lambda_config = cognito.CfnUserPool.LambdaConfigProperty(
            post_confirmation=self.new_player_function.function_arn
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
            "LambdaFunctionArn",
            value=self.new_player_function.function_arn,
            description="cognito-player-new Lambda function ARN"
        )
        
        CfnOutput(
            self,
            "LambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="Lambda execution role ARN"
        )