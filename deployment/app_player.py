"""CDK application entry point for Player stack."""

import json

import aws_cdk as cdk
from stacks.player_stack import PlayerStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
s3_bucket = app.node.try_get_context("s3_bucket") or ""
client_fqdn = app.node.try_get_context("client_fqdn") or ""
dynamodb_policy_arn = app.node.try_get_context("dynamodb_policy_arn") or ""
dynamodb_tables_json = app.node.try_get_context("dynamodb_tables") or "{}"
lambda_layer_arn = app.node.try_get_context("lambda_layer_arn") or ""
lambda_role_arn = app.node.try_get_context("lambda_role_arn") or ""
reply_email = app.node.try_get_context("reply_email") or "contact@darkrelics.net"
existing_user_pool_id = app.node.try_get_context("existing_user_pool_id") or ""

# Parse DynamoDB tables from JSON string
try:
    dynamodb_tables = json.loads(dynamodb_tables_json) if dynamodb_tables_json else {}
except json.JSONDecodeError:
    print(f"Error: Invalid JSON for dynamodb_tables: {dynamodb_tables_json}")
    dynamodb_tables = {}

# Deploy Player stack with context parameters
if s3_bucket:  # Only create if S3 bucket is provided
    player_stack = PlayerStack(
        app,
        "player",
        description="Cognito User Pool and Lambda function for Eidolon Engine",
        region_name=region,
        s3_bucket=s3_bucket,
        client_fqdn=client_fqdn,
        dynamodb_policy_arn=dynamodb_policy_arn,
        dynamodb_tables=dynamodb_tables,
        lambda_layer_arn=lambda_layer_arn,
        lambda_role_arn=lambda_role_arn,
        reply_email=reply_email,
        existing_user_pool_id=existing_user_pool_id,
    )
else:
    print("Error: S3 bucket parameter is required for Player stack")
    exit(1)

app.synth()
