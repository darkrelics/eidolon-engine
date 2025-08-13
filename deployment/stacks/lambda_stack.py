"""Lambda stack for all Lambda functions and layer."""

from aws_cdk import Stack, CfnOutput, Duration
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class LambdaStack(Stack):
    """Lambda stack for Eidolon Engine functions."""
    
    def __init__(self, scope: Construct, stack_id: str,
                 region_name: str = "us-east-1",
                 s3_bucket: str = "",
                 client_fqdn: str = "",
                 dynamodb_policy_arn: str = "",
                 dynamodb_tables = None,
                 **kwargs) -> None:
        """Initialize Lambda stack.
        
        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            s3_bucket: S3 bucket containing Lambda artifacts
            client_fqdn: Client FQDN for CORS configuration
            dynamodb_policy_arn: ARN of DynamoDB policy to attach
            dynamodb_tables: Dictionary of DynamoDB table names
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.client_fqdn = client_fqdn
        self.dynamodb_policy_arn = dynamodb_policy_arn
        self.dynamodb_tables = dynamodb_tables or {}
        super().__init__(scope, stack_id, **kwargs)
        
        # Create Lambda layer
        self.lambda_layer = self._create_lambda_layer()
        
        # Create shared IAM execution role
        self.lambda_role = self._create_lambda_role()
        
        # Deploy Lambda functions in alphabetical order
        self.functions = {}
        self._deploy_lambda_functions()
        
        # Add outputs
        self._add_outputs()
    
    def _create_lambda_layer(self) -> lambda_.LayerVersion:
        """Create Lambda dependencies layer."""
        print(f"  Creating Lambda layer from {self.s3_bucket_name}/lambda-layer/lambda-layer.zip")
        
        bucket = s3.Bucket.from_bucket_name(self, "ArtifactsBucket", self.s3_bucket_name)
        
        return lambda_.LayerVersion(
            self,
            "DependenciesLayer",
            layer_version_name="eidolon-dependencies",
            code=lambda_.Code.from_bucket(bucket, "lambda-layer/lambda-layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared dependencies for Eidolon Engine Lambda functions"
        )
    
    def _create_lambda_role(self) -> iam.Role:
        """Create shared Lambda execution role."""
        print("  Creating shared Lambda execution role")
        
        role = iam.Role(
            self,
            "LambdaExecutionRole",
            role_name="eidolon-lambda-execution-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"), # type: ignore
            description="Shared execution role for Eidolon Engine Lambda functions"
        )
        
        # Attach basic Lambda execution policy
        role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "service-role/AWSLambdaBasicExecutionRole"
            )
        )
        
        # Create and attach CloudWatch Logs policy for dynamic log group creation
        logs_policy = iam.ManagedPolicy(
            self,
            "LambdaLogsPolicy",
            managed_policy_name="eidolon-lambda-logs-policy",
            description="CloudWatch Logs permissions for Lambda functions",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    resources=[f"arn:aws:logs:{self.region_name}:*:*"]
                )
            ]
        )
        role.add_managed_policy(logs_policy)
        
        # Attach DynamoDB policy if provided
        if self.dynamodb_policy_arn:
            print(f"  Attaching DynamoDB policy: {self.dynamodb_policy_arn}")
            dynamodb_policy = iam.ManagedPolicy.from_managed_policy_arn(
                self,
                "DynamoDBPolicy",
                self.dynamodb_policy_arn
            )
            role.add_managed_policy(dynamodb_policy)
        
        return role
    
    def _deploy_lambda_functions(self) -> None:
        """Deploy all Lambda functions in alphabetical order."""
        
        # Define all Lambda functions with their configurations
        lambda_configs = [
            # Character API functions
            ("api-archetype-list", "api_archetype_list.lambda_handler"),
            ("api-character-add", "api_character_add.lambda_handler"),
            ("api-character-delete", "api_character_delete.lambda_handler"),
            ("api-character-get", "api_character_get.lambda_handler"),
            ("api-character-list", "api_character_list.lambda_handler"),
            # Story API functions
            ("api-segment-decision", "api_segment_decision.lambda_handler"),
            ("api-segment-history", "api_segment_history.lambda_handler"),
            ("api-segment-outcome", "api_segment_outcome.lambda_handler"),
            ("api-segment-rest", "api_segment_rest.lambda_handler"),
            ("api-segment-status", "api_segment_status.lambda_handler"),
            ("api-story-abandon", "api_story_abandon.lambda_handler"),
            ("api-story-start", "api_story_start.lambda_handler"),
            # Player function
            ("cognito-player-new", "cognito_player_new.lambda_handler"),
            # Operations functions
            ("ops-segment-poller", "ops_segment_poller.lambda_handler"),
            ("ops-segment-process", "ops_segment_process.lambda_handler"),
            ("ops-story-advance", "ops_story_advance.lambda_handler")
        ]
        
        # Get common environment variables
        env_vars = self._get_environment_variables()
        
        bucket = s3.Bucket.from_bucket_name(self, "FunctionsBucket", self.s3_bucket_name)
        
        for function_name, handler in lambda_configs:
            print(f"  Deploying Lambda function: {function_name}")
            
            # Create resource ID from function name (remove hyphens for CDK)
            resource_id = function_name.replace("-", "").title()
            
            self.functions[function_name] = lambda_.Function(
                self,
                resource_id,
                function_name=function_name,
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler=handler,
                code=lambda_.Code.from_bucket(bucket, f"{function_name}.zip"),
                layers=[self.lambda_layer],
                role=self.lambda_role, # type: ignore
                timeout=Duration.seconds(30),
                memory_size=128,
                environment=self._get_function_environment(function_name, env_vars),
                description=f"Eidolon Engine {function_name} function"
            )
    
    def _get_environment_variables(self) -> dict:
        """Get common environment variables for all Lambda functions."""
        # Use client FQDN for CORS origin
        cors_origin = f"https://{self.client_fqdn}" if self.client_fqdn else "*"
        
        env_vars = {
            "APPLICATION_NAME": "eidolon-engine",
            "LOG_LEVEL": "20",
            "ALLOWED_ORIGINS": cors_origin,
            "CORS_ALLOW_CREDENTIALS": "true",
            "CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS",
            "CORS_MAX_AGE": "86400"
        }
        
        # Add DynamoDB table names
        table_mapping = {
            "players_table": "players",
            "characters_table": "characters",
            "rooms_table": "rooms",
            "exits_table": "exits",
            "items_table": "items",
            "prototypes_table": "prototypes",
            "archetypes_table": "archetypes",
            "motd_table": "motd",
            "story_table": "story",
            "segments_table": "segments",
            "active_segments_table": "active_segments",
            "story_history_table": "story_history",
            "segment_history_table": "segment_history",
            "opponents_table": "opponents"
        }
        
        for env_key, table_key in table_mapping.items():
            env_vars[env_key] = self.dynamodb_tables.get(table_key, table_key)
        
        return env_vars
    
    def _get_function_environment(self, function_name: str, base_env: dict) -> dict:
        """Get environment variables for a specific Lambda function."""
        env = base_env.copy()
        
        # Add function-specific environment variables
        if function_name == "ops-segment-process":
            env["SEGMENT_BATCH_SIZE"] = "10"
        elif function_name == "ops-segment-poller":
            env["POLLING_INTERVAL"] = "60"
        
        return env
    
    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(
            self,
            "LambdaLayerArn",
            value=self.lambda_layer.layer_version_arn,
            description="Lambda dependencies layer ARN"
        )
        
        CfnOutput(
            self,
            "LambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="Shared Lambda execution role ARN"
        )
        
        # Output each Lambda function ARN
        for function_name, function in self.functions.items():
            output_id = function_name.replace("-", "").title() + "Arn"
            CfnOutput(
                self,
                output_id,
                value=function.function_arn,
                description=f"{function_name} Lambda function ARN"
            )