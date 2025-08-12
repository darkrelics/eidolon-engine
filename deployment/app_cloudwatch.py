"""CDK application entry point for CloudWatch stack."""

import argparse

import aws_cdk as cdk

from stacks.cloudwatch_stack import CloudWatchStack

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Deploy CloudWatch stack with explicit region
cloudwatch_stack = CloudWatchStack(
    app,
    "cloudwatch",
    description="CloudWatch logging and monitoring for Eidolon Engine",
    region_name=args.region
)

app.synth()