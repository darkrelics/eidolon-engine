"""CDK application entry point for Story stack."""

import aws_cdk as cdk
from stacks.story_stack import StoryStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
lambda_role_arn = app.node.try_get_context("lambda_role_arn") or ""
poller_lambda_arn = app.node.try_get_context("poller_lambda_arn") or ""
processor_lambda_arn = app.node.try_get_context("processor_lambda_arn") or ""
advance_lambda_arn = app.node.try_get_context("advance_lambda_arn") or ""


# Deploy Story stack with context parameters
story_stack = StoryStack(
    app,
    "story",
    description="Story processing stack for Eidolon Engine",
    region_name=region,
    lambda_role_arn=lambda_role_arn,
    poller_lambda_arn=poller_lambda_arn,
    processor_lambda_arn=processor_lambda_arn,
    advance_lambda_arn=advance_lambda_arn,
)

app.synth()
