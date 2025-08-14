"""CDK application entry point for S3 stack."""

import aws_cdk as cdk

from stacks.s3_stack import S3Stack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
scripts_bucket = app.node.try_get_context("scripts_bucket") or ""

# Deploy S3 stack with context parameters
if scripts_bucket:  # Only create if scripts bucket is provided
    s3_stack = S3Stack(
        app, "s3", description="S3 bucket and access policy for Lua scripts", region_name=region, scripts_bucket=scripts_bucket
    )
else:
    print("Error: Scripts bucket parameter is required for S3 stack")
    exit(1)

app.synth()
