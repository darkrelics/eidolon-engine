"""CDK application entry point for Lambda stack."""

import aws_cdk as cdk
from stacks.lambda_stack import LambdaStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
s3_bucket = app.node.try_get_context("s3_bucket") or ""
dynamodb_policy_arn = app.node.try_get_context("dynamodb_policy_arn") or ""

# Deploy Lambda stack with context parameters
if s3_bucket:  # Only create if S3 bucket is provided
    lambda_stack = LambdaStack(
        app,
        "lambda",
        region_name=region,
        s3_bucket=s3_bucket,
        dynamodb_policy_arn=dynamodb_policy_arn,
    )
else:
    print("Error: S3 bucket parameter is required for Lambda stack")
    exit(1)

app.synth()
