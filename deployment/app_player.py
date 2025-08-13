"""CDK application entry point for Player stack."""

import aws_cdk as cdk

from stacks.player_stack import PlayerStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
lambda_function_arn = app.node.try_get_context("lambda_function_arn") or ""
reply_email = app.node.try_get_context("reply_email") or "contact@darkrelics.net"

# Deploy Player stack with context parameters
player_stack = PlayerStack(
    app,
    "player",
    description="Cognito User Pool for Eidolon Engine",
    region_name=region,
    lambda_function_arn=lambda_function_arn,
    reply_email=reply_email
)

app.synth()