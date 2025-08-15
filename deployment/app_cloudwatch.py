"""CDK application entry point for CloudWatch stack."""

import aws_cdk as cdk
from stacks.cloudwatch_stack import CloudWatchStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
existing_log_group = app.node.try_get_context("existing_log_group") or ""

# Deploy CloudWatch stack with context parameters
cloudwatch_stack = CloudWatchStack(
    app, "cloudwatch", 
    description="CloudWatch logging and monitoring for Eidolon Engine", 
    region_name=region,
    existing_log_group=existing_log_group
)

app.synth()
