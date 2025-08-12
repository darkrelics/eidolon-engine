"""CDK application entry point for Eidolon Engine infrastructure."""

import argparse

import aws_cdk as cdk

from stacks.dynamodb_stack import DynamoDBStack

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Deploy DynamoDB stack with explicit region
dynamodb_stack = DynamoDBStack(
    app,
    "dynamodb",
    description="DynamoDB tables and access policy for Eidolon Engine",
    region_name=args.region  # Pass region as explicit parameter
)

app.synth()