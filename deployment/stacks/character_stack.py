"""Character stack with Lambda functions for character management."""

import aws_cdk as cdk
from aws_cdk import CfnOutput, Duration, Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class CharacterStack(Stack):
    """Character management stack with shared Lambda resources."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        s3_bucket: str = "",
        client_fqdn: str = "",
        dynamodb_policy_arn: str = "",
        dynamodb_tables=None,
        **kwargs,
    ) -> None:
        """Initialize Character stack.

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
        # Apply system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Create shared Lambda layer for all stacks
        self.lambda_layer = self._create_lambda_layer()

        # Create shared IAM execution role for all Lambda functions
        self.lambda_role = self._create_lambda_role()

        # Deploy character Lambda functions
        self.functions = {}
        self._deploy_lambda_functions()

        # Add outputs for other stacks to use
        self._add_outputs()

    def _create_lambda_layer(self) -> lambda_.LayerVersion:
        """Create Lambda dependencies layer shared by all stacks."""
        layer_name = "eidolon-dependencies"

        print(f"  Creating Lambda layer from {self.s3_bucket_name}/lambda-layer/lambda-layer.zip")

        bucket = s3.Bucket.from_bucket_name(self, "ArtifactsBucket", self.s3_bucket_name)

        return lambda_.LayerVersion(
            self,
            "DependenciesLayer",
            layer_version_name=layer_name,
            code=lambda_.Code.from_bucket(bucket, "lambda-layer/lambda-layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Shared dependencies for Eidolon Engine Lambda functions",
        )

    def _create_lambda_role(self) -> iam.Role:
        """Create shared IAM execution role for all Lambda functions."""
        role_name = "eidolon-lambda-execution-role"
        
        print(f"  Creating Lambda execution role: {role_name}")

        role = iam.Role(
            self,
            "LambdaExecutionRole",
            role_name=role_name,
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Shared execution role for all Eidolon Engine Lambda functions",
        )

        # Create and attach CloudWatch Logs policy
        logs_policy = iam.ManagedPolicy(
            self,
            "LambdaLogsPolicy",
            managed_policy_name="eidolon-lambda-logs-policy",
            description="CloudWatch Logs permissions for Lambda functions",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[f"arn:aws:logs:{self.region_name}:*:*"],
                )
            ],
        )
        role.add_managed_policy(logs_policy)

        # Attach DynamoDB policy if provided
        if self.dynamodb_policy_arn:
            print(f"  Attaching DynamoDB policy: {self.dynamodb_policy_arn}")
            dynamodb_policy = iam.ManagedPolicy.from_managed_policy_arn(self, "DynamoDBPolicy", self.dynamodb_policy_arn)
            role.add_managed_policy(dynamodb_policy)

        return role

    def _deploy_lambda_functions(self) -> None:
        """Deploy character-related Lambda functions."""
        
        # Character API functions
        lambda_configs = [
            ("api-character-add", "api_character_add.lambda_handler"),
            ("api-character-delete", "api_character_delete.lambda_handler"),
            ("api-character-get", "api_character_get.lambda_handler"),
            ("api-character-list", "api_character_list.lambda_handler"),
            ("api-archetype-list", "api_archetype_list.lambda_handler"),
        ]

        # Get common environment variables
        env_vars = self._get_environment_variables()

        bucket = s3.Bucket.from_bucket_name(self, "FunctionsBucket", self.s3_bucket_name)

        for function_name, handler in lambda_configs:
            print(f"  Deploying Lambda function: {function_name}")

            # Use fixed logical ID for each function
            logical_id = self._get_function_logical_id(function_name)

            self.functions[function_name] = lambda_.Function(
                self,
                logical_id,
                function_name=function_name,
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler=handler,
                code=lambda_.Code.from_bucket(bucket, f"{function_name}.zip"),
                layers=[self.lambda_layer],
                role=self.lambda_role,
                timeout=Duration.seconds(30),
                memory_size=128,
                environment=env_vars,
                description=f"Eidolon Engine {function_name} function",
            )

    def _get_function_logical_id(self, function_name: str) -> str:
        """Get fixed logical ID for a Lambda function."""
        logical_id_map = {
            "api-character-add": "ApiCharacterAddFunction",
            "api-character-delete": "ApiCharacterDeleteFunction",
            "api-character-get": "ApiCharacterGetFunction",
            "api-character-list": "ApiCharacterListFunction",
            "api-archetype-list": "ApiArchetypeListFunction",
        }
        return logical_id_map.get(function_name, function_name.replace("-", "").title() + "Function")

    def _get_environment_variables(self) -> dict:
        """Get common environment variables for all Lambda functions."""
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
            "archetypes_table": "archetypes",
            "items_table": "items",
            "prototypes_table": "prototypes",
        }

        for env_key, table_key in table_mapping.items():
            env_vars[env_key] = self.dynamodb_tables.get(table_key, table_key)

        return env_vars

    def _add_outputs(self) -> None:
        """Add stack outputs for other stacks to reference."""
        
        # Export Lambda layer ARN for other stacks
        CfnOutput(
            self,
            "LambdaLayerArn",
            value=self.lambda_layer.layer_version_arn,
            description="ARN of the shared Lambda dependencies layer",
            export_name="eidolon-lambda-layer-arn"
        )

        # Export Lambda execution role ARN for other stacks
        CfnOutput(
            self,
            "LambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="ARN of the shared Lambda execution role",
            export_name="eidolon-lambda-role-arn"
        )

        # Export function ARNs for API Gateway
        for function_name, function in self.functions.items():
            CfnOutput(
                self,
                f"{function_name.replace('-', '')}Arn",
                value=function.function_arn,
                description=f"ARN of {function_name} Lambda function",
            )