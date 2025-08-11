"""CDK application entry point for Eidolon Engine infrastructure."""

import aws_cdk as cdk

from stacks.dynamodb_stack import DynamoDBStack

app = cdk.App()

# Deploy DynamoDB stack
dynamodb_stack = DynamoDBStack(
    app,
    "dynamodb",
    description="DynamoDB tables and access policy for Eidolon Engine"
)

app.synth()