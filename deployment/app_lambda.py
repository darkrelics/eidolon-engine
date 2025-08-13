"""CDK application entry point for Lambda stack."""

import argparse

import aws_cdk as cdk

from stacks.lambda_stack import LambdaStack

# Parse command line arguments
parser = argparse.ArgumentParser(description="Deploy Lambda stack for Eidolon Engine")
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
parser.add_argument("--s3-bucket", default="", help="S3 bucket containing Lambda artifacts")
parser.add_argument("--client-fqdn", default="", help="Client FQDN for CORS configuration")
parser.add_argument("--dynamodb-policy-arn", default="", help="ARN of DynamoDB policy to attach")
parser.add_argument("--dynamodb-tables", default="", help="Comma-separated list of table names")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Parse DynamoDB tables if provided
dynamodb_tables = {}
if args.dynamodb_tables:
    # Expected format: "players=players,characters=characters,..."
    for pair in args.dynamodb_tables.split(","):
        if "=" in pair:
            key, value = pair.split("=", 1)
            dynamodb_tables[key] = value

# Deploy Lambda stack with explicit parameters
if args.s3_bucket:  # Only create if S3 bucket is provided
    lambda_stack = LambdaStack(
        app,
        "lambda",
        description="Lambda functions and layer for Eidolon Engine",
        region_name=args.region,
        s3_bucket=args.s3_bucket,
        client_fqdn=args.client_fqdn,
        dynamodb_policy_arn=args.dynamodb_policy_arn,
        dynamodb_tables=dynamodb_tables
    )
else:
    print("Error: S3 bucket parameter is required for Lambda stack")
    exit(1)

app.synth()