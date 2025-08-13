"""CDK application entry point for S3 stack."""

import argparse

import aws_cdk as cdk

from stacks.s3_stack import S3Stack

# Parse command line arguments
parser = argparse.ArgumentParser(description="Deploy S3 stack for Eidolon Engine")
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
parser.add_argument("--scripts-bucket", default="", help="S3 bucket for Lua scripts")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Deploy S3 stack with explicit parameters
if args.scripts_bucket:  # Only create if scripts bucket is provided
    s3_stack = S3Stack(
        app,
        "s3",
        description="S3 bucket and access policy for Lua scripts",
        region_name=args.region,
        scripts_bucket=args.scripts_bucket
    )
else:
    print("Error: Scripts bucket parameter is required for S3 stack")
    exit(1)

app.synth()