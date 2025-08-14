"""CDK application entry point for Lambda stack."""

import json

import aws_cdk as cdk

from stacks.lambda_stack import LambdaStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
s3_bucket = app.node.try_get_context("s3_bucket") or ""
client_fqdn = app.node.try_get_context("client_fqdn") or ""
dynamodb_policy_arn = app.node.try_get_context("dynamodb_policy_arn") or ""
dynamodb_tables_json = app.node.try_get_context("dynamodb_tables") or "{}"

# Parse DynamoDB tables from JSON string
try:
    dynamodb_tables = json.loads(dynamodb_tables_json) if dynamodb_tables_json else {}
except json.JSONDecodeError:
    print(f"Error: Invalid JSON for dynamodb_tables: {dynamodb_tables_json}")
    dynamodb_tables = {}

# Deploy Lambda stack with context parameters
if s3_bucket:  # Only create if S3 bucket is provided
    lambda_stack = LambdaStack(
        app,
        "lambda",
        description="Lambda functions and layer for Eidolon Engine",
        region_name=region,
        s3_bucket=s3_bucket,
        client_fqdn=client_fqdn,
        dynamodb_policy_arn=dynamodb_policy_arn,
        dynamodb_tables=dynamodb_tables
    )
else:
    print("Error: S3 bucket parameter is required for Lambda stack")
    exit(1)

app.synth()