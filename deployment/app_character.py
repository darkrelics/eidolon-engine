"""CDK application entry point for Character stack."""

import json

import aws_cdk as cdk
from stacks.character_stack import CharacterStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
s3_bucket = app.node.try_get_context("s3_bucket") or ""
client_fqdn = app.node.try_get_context("client_fqdn") or ""
lambda_layer_arn = app.node.try_get_context("lambda_layer_arn") or ""
lambda_role_arn = app.node.try_get_context("lambda_role_arn") or ""
dynamodb_tables_json = app.node.try_get_context("dynamodb_tables") or "{}"

# Parse DynamoDB tables from JSON string
try:
    dynamodb_tables = json.loads(dynamodb_tables_json) if dynamodb_tables_json else {}
except json.JSONDecodeError:
    print(f"Error: Invalid JSON for dynamodb_tables: {dynamodb_tables_json}")
    dynamodb_tables = {}

# Deploy Character stack with context parameters
if s3_bucket:  # Only create if S3 bucket is provided
    character_stack = CharacterStack(
        app,
        "character",
        description="Character management Lambda functions for Eidolon Engine",
        region_name=region,
        s3_bucket=s3_bucket,
        client_fqdn=client_fqdn,
        lambda_layer_arn=lambda_layer_arn,
        lambda_role_arn=lambda_role_arn,
        dynamodb_tables=dynamodb_tables,
    )
else:
    print("Error: S3 bucket parameter is required for Character stack")
    exit(1)

app.synth()