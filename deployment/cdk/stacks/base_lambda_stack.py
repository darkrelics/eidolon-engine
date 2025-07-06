"""Base Lambda stack for shared functions between applications.

This stack creates Lambda functions and layers that are shared between
the MUD Portal and Incremental game applications.
"""

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class BaseLambdaStack(cdk.Stack):
    """Creates shared Lambda functions and layers for Eidolon Engine applications."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        lambda_bucket: s3.IBucket,
        shared_players_table: str,
        cognito_user_pool_arn: str,
        allowed_cors_origins: list[str],
        **kwargs,
    ) -> None:
        """Initialize the base Lambda stack.

        Args:
            scope: CDK scope
            id: Stack ID
            lambda_bucket: S3 bucket containing Lambda deployment packages
            shared_players_table: Name of the shared players DynamoDB table
            cognito_user_pool_arn: ARN of the Cognito user pool
            allowed_cors_origins: List of allowed CORS origins
            **kwargs: Additional stack properties
        """
        # Validate required parameters before stack initialization
        if not lambda_bucket:
            raise ValueError("lambda_bucket is required")
        if not shared_players_table:
            raise ValueError("shared_players_table is required")
        if not cognito_user_pool_arn:
            raise ValueError("cognito_user_pool_arn is required")

        super().__init__(scope, id, **kwargs)

        # Store CORS origins for Lambda environment with default
        default_origins = ["https://portal.darkrelics.net"]
        origins = allowed_cors_origins if allowed_cors_origins else default_origins
        self.cors_origins_str = ",".join(origins)

        # Create Lambda layer for shared dependencies
        self.dependencies_layer = lambda_.LayerVersion(
            self,
            "shared-lambda-dependencies",
            code=lambda_.Code.from_bucket(lambda_bucket, "lambda-layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_11],
            description="Shared dependencies for Eidolon Engine Lambda functions",
        )

        # Create IAM role for Cognito Lambda
        cognito_lambda_role = iam.Role(
            self,
            "shared-cognito-lambda",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),  # type: ignore
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Add DynamoDB permissions for players table
        cognito_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:GetItem", "dynamodb:PutItem"],
                resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/{shared_players_table}"],
            )
        )

        # Create Cognito new player Lambda function (shared by all applications)
        self.cognito_new_player_function = lambda_.Function(
            self,
            "shared-cognito-new-player",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="cognito_new_player.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "cognito_new_player.zip"),
            layers=[self.dependencies_layer],
            role=cognito_lambda_role,  # type: ignore
            timeout=cdk.Duration.seconds(30),
            memory_size=256,
            environment={
                "players_table": shared_players_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            description="Creates new player records after Cognito user confirmation (shared)",
        )

        # Grant Cognito permission to invoke the Lambda function
        cognito_source_condition = {"ArnLike": {"aws:SourceArn": cognito_user_pool_arn}}
        self.cognito_new_player_function.grant_invoke(
            iam.ServicePrincipal("cognito-idp.amazonaws.com", conditions=cognito_source_condition)
        )

        # Create CloudWatch log group with retention
        logs.LogGroup(
            self,
            "shared-cognito-lambda-logs",
            log_group_name=f"/aws/lambda/{self.cognito_new_player_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Output values
        cdk.CfnOutput(
            self,
            "SharedCognitoLambdaFunctionArn",
            value=self.cognito_new_player_function.function_arn,
            description="ARN of the shared Cognito new player Lambda function",
            export_name="SharedCognitoLambdaFunctionArn",
        )

        cdk.CfnOutput(
            self,
            "SharedDependenciesLayerArn",
            value=self.dependencies_layer.layer_version_arn,
            description="ARN of the shared Lambda dependencies layer",
            export_name="SharedDependenciesLayerArn",
        )
