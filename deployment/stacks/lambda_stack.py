"""Lambda stack with shared layer and execution role for all Lambda functions."""

from aws_cdk import CfnOutput, Stack, Tags
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class LambdaStack(Stack):
    """Lambda infrastructure stack with shared resources for all Lambda functions."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        s3_bucket: str = "",
        dynamodb_policy_arn: str = "",
        **kwargs,
    ) -> None:
        """Initialize Lambda stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            s3_bucket: S3 bucket containing Lambda layer artifact
            dynamodb_policy_arn: ARN of DynamoDB policy to attach
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.dynamodb_policy_arn = dynamodb_policy_arn

        super().__init__(scope, stack_id, description="Shared Lambda layer and execution role for Eidolon Engine", **kwargs)
        # Apply system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Create shared Lambda layer for all stacks
        self.lambda_layer = self._create_lambda_layer()

        # Create shared IAM execution role for all Lambda functions
        self.lambda_role = self._create_lambda_role()

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
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),  # type: ignore
            description="Shared execution role for all Eidolon Engine Lambda functions",
        )

        # Create and attach CloudWatch Logs policy
        logs_policy = iam.ManagedPolicy(
            self,
            "LambdaLogsPolicy",
            managed_policy_name="eidolon-lambda-logs-policy",
            description="CloudWatch Logs permissions for Lambda functions",
            statements=[
                # CreateLogGroup needs log-group ARN without :*
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogGroup"],
                    resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*"],
                ),
                # CreateLogStream and PutLogEvents need log-group ARN with :*
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[f"arn:aws:logs:{self.region_name}:{self.account}:log-group:/aws/lambda/*:*"],
                ),
            ],
        )
        role.add_managed_policy(logs_policy)

        # Attach DynamoDB policy if provided
        if self.dynamodb_policy_arn:
            print(f"  Attaching DynamoDB policy: {self.dynamodb_policy_arn}")
            dynamodb_policy = iam.ManagedPolicy.from_managed_policy_arn(self, "DynamoDBPolicy", self.dynamodb_policy_arn)
            role.add_managed_policy(dynamodb_policy)

        return role

    def _add_outputs(self) -> None:
        """Add stack outputs for other stacks to reference."""

        # Export Lambda layer ARN for other stacks
        CfnOutput(
            self,
            "LambdaLayerArn",
            value=self.lambda_layer.layer_version_arn,
            description="ARN of the shared Lambda layer",
            export_name="eidolon-lambda-layer-arn",
        )

        # Export Lambda role ARN for other stacks
        CfnOutput(
            self,
            "LambdaRoleArn",
            value=self.lambda_role.role_arn,
            description="ARN of the shared Lambda execution role",
            export_name="eidolon-lambda-role-arn",
        )

        # Export role name for boto3 operations
        CfnOutput(
            self,
            "LambdaRoleName",
            value=self.lambda_role.role_name,
            description="Name of the shared Lambda execution role",
        )
