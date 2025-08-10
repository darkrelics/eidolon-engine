"""Cognito trigger Lambda stack to avoid circular dependencies."""

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from constructs import Construct


class CognitoTriggerStack(cdk.Stack):
    """Creates Cognito trigger Lambda functions."""

    def __init__(
        self,
        scope: Construct,
        lambda_id,
        lambda_bucket: s3.IBucket,
        players_table: str,
        characters_table: str,
        items_table: str,
        active_segments_table: str,
        story_history_table: str,
        cognito_user_pool_arn: str,
        dependencies_layer: lambda_.ILayerVersion,
        allowed_cors_origins: list[str],
        **kwargs,
    ) -> None:
        """Initialize the Cognito trigger Lambda stack.

        Args:
            scope: CDK scope
            id: Stack ID
            lambda_bucket: S3 bucket containing Lambda deployment packages
            players_table: Name of the players DynamoDB table
            cognito_user_pool_arn: ARN of the Cognito user pool
            dependencies_layer: Lambda layer with dependencies
            allowed_cors_origins: List of allowed CORS origins
            **kwargs: Additional stack properties
        """
        super().__init__(scope, lambda_id, **kwargs)

        # Store table names
        self.characters_table = characters_table
        self.items_table = items_table
        self.active_segments_table = active_segments_table
        self.story_history_table = story_history_table

        # Store CORS origins for Lambda environment
        self.cors_origins_str = ",".join(allowed_cors_origins) if allowed_cors_origins else "*"

        # Create Lambda execution role
        cognito_lambda_role = iam.Role(
            self,
            "cognito-trigger-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),  # type: ignore
            description="Execution role for Cognito trigger Lambda function",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
            ],
        )

        # Grant DynamoDB access
        cognito_lambda_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:UpdateItem"],
                resources=[f"arn:aws:dynamodb:{self.region}:{self.account}:table/{players_table}"],
            )
        )

        # Create Cognito new player Lambda function
        self.cognito_new_player_function = lambda_.Function(
            self,
            "cognito-player-new",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="cognito_player_new.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "cognito-player-new.zip"),
            layers=[dependencies_layer],
            role=cognito_lambda_role,  # type: ignore
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            environment={
                "players_table": players_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            description="Creates new player records after Cognito user confirmation",
        )

        # Grant Cognito permission to invoke the Lambda function
        cognito_source_condition: dict = {"ArnLike": {"aws:SourceArn": cognito_user_pool_arn}}
        self.cognito_new_player_function.grant_invoke(
            iam.ServicePrincipal("cognito-idp.amazonaws.com", conditions=cognito_source_condition)
        )

        # Note: The trigger is added in the app.py after all stacks are created to avoid circular dependencies

        # Create CloudWatch log group with retention
        logs.LogGroup(
            self,
            "cognito-trigger-logs",
            log_group_name=f"/aws/lambda/{self.cognito_new_player_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Create Cognito delete player Lambda function
        self.cognito_delete_player_function = lambda_.Function(
            self,
            "cognito-player-delete",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="cognito_player_delete.lambda_handler",
            code=lambda_.Code.from_bucket(lambda_bucket, "cognito-player-delete.zip"),
            layers=[dependencies_layer],
            role=cognito_lambda_role,  # type: ignore
            timeout=cdk.Duration.seconds(30),
            memory_size=128,
            environment={
                "players_table": players_table,
                "characters_table": self.characters_table,
                "items_table": self.items_table,
                "active_segments_table": self.active_segments_table,
                "story_history_table": self.story_history_table,
                "ALLOWED_ORIGINS": self.cors_origins_str,
            },
            description="Deletes player data when Cognito user is deleted",
        )

        # Grant Cognito permission to invoke the delete Lambda function
        self.cognito_delete_player_function.grant_invoke(
            iam.ServicePrincipal("cognito-idp.amazonaws.com", conditions=cognito_source_condition)
        )

        # Create CloudWatch log group for delete function
        logs.LogGroup(
            self,
            "cognito-delete-trigger-logs",
            log_group_name=f"/aws/lambda/{self.cognito_delete_player_function.function_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # Output values
        cdk.CfnOutput(
            self,
            "CognitoTriggerLambdaFunctionArn",
            value=self.cognito_new_player_function.function_arn,
            description="ARN of the Cognito trigger Lambda function",
        )
