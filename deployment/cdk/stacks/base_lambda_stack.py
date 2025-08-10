"""Base Lambda stack for common functions between applications.

This stack creates Lambda functions and layers that are used by
the MUD Portal and Incremental game applications.
"""

import aws_cdk as cdk
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class BaseLambdaStack(cdk.Stack):
    """Creates Lambda functions and layers for Eidolon Engine applications."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        lambda_bucket: s3.IBucket,
        **kwargs,
    ) -> None:
        """Initialize the base Lambda stack.

        Args:
            scope: CDK scope
            stack_id: Stack ID
            lambda_bucket: S3 bucket containing Lambda deployment packages
            **kwargs: Additional stack properties
        """
        # Validate required parameters before stack initialization
        if not lambda_bucket:
            raise ValueError("lambda_bucket is required")

        super().__init__(scope, stack_id, **kwargs)

        # Create Lambda layer for dependencies
        self.dependencies_layer = lambda_.LayerVersion(
            self,
            "lambda-dependencies",
            code=lambda_.Code.from_bucket(lambda_bucket, "lambda-layer/lambda-layer.zip"),
            compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
            description="Dependencies for Eidolon Engine Lambda functions",
        )

        # Output values

        cdk.CfnOutput(
            self,
            "DependenciesLayerArn",
            value=self.dependencies_layer.layer_version_arn,
            description="ARN of the Lambda dependencies layer",
            export_name="DependenciesLayerArn",
        )
