"""Character stack with Lambda functions for character management."""

import aws_cdk as cdk
from aws_cdk import CfnOutput, Duration, Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class CharacterStack(Stack):
    """Character management stack with Lambda functions."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        s3_bucket: str = "",
        client_fqdn: str = "",
        lambda_layer_arn: str = "",
        lambda_role_arn: str = "",
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
            lambda_layer_arn: ARN of shared Lambda layer from Lambda stack
            lambda_role_arn: ARN of shared Lambda execution role from Lambda stack
            dynamodb_tables: Dictionary of DynamoDB table names
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.client_fqdn = client_fqdn
        self.lambda_layer_arn = lambda_layer_arn
        self.lambda_role_arn = lambda_role_arn
        self.dynamodb_tables = dynamodb_tables or {}
        
        super().__init__(scope, stack_id, **kwargs)
        # Apply system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Import shared Lambda layer and role from Lambda stack
        self.lambda_layer = self._import_lambda_layer()
        self.lambda_role = self._import_lambda_role()

        # Deploy character Lambda functions
        self.functions = {}
        self._deploy_lambda_functions()

        # Add outputs for other stacks to use
        self._add_outputs()

    def _import_lambda_layer(self) -> lambda_.ILayerVersion:
        """Import shared Lambda layer from Lambda stack."""
        if self.lambda_layer_arn:
            return lambda_.LayerVersion.from_layer_version_arn(
                self, "ImportedLambdaLayer", self.lambda_layer_arn
            )
        else:
            # Try to import from CloudFormation export
            try:
                layer_arn = cdk.Fn.import_value("eidolon-lambda-layer-arn")
                return lambda_.LayerVersion.from_layer_version_arn(
                    self, "ImportedLambdaLayer", layer_arn
                )
            except Exception as e:
                print(f"  Warning: Failed to import Lambda layer from CloudFormation export: {e}")
                raise ValueError("Lambda layer ARN not provided and CloudFormation export not found")
    
    def _import_lambda_role(self) -> iam.IRole:
        """Import shared Lambda execution role from Lambda stack."""
        if self.lambda_role_arn:
            return iam.Role.from_role_arn(
                self, "ImportedLambdaRole", self.lambda_role_arn
            )
        else:
            # Try to import from CloudFormation export
            try:
                role_arn = cdk.Fn.import_value("eidolon-lambda-role-arn")
                return iam.Role.from_role_arn(
                    self, "ImportedLambdaRole", role_arn
                )
            except Exception as e:
                print(f"  Warning: Failed to import Lambda role from CloudFormation export: {e}")
                raise ValueError("Lambda role ARN not provided and CloudFormation export not found")

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
        
        # Export function ARNs for API Gateway
        for function_name, function in self.functions.items():
            CfnOutput(
                self,
                f"{function_name.replace('-', '')}Arn",
                value=function.function_arn,
                description=f"ARN of {function_name} Lambda function",
            )