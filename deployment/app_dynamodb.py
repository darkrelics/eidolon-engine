"""CDK application entry point for DynamoDB stack."""

import aws_cdk as cdk
from stacks.dynamodb_stack import DynamoDBStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"

# Deploy DynamoDB stack with context parameters
dynamodb_stack = DynamoDBStack(
    app, "dynamodb", description="DynamoDB tables and access policy for Eidolon Engine", region_name=region
)

app.synth()
