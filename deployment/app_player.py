"""CDK application entry point for Player stack."""

import argparse

import aws_cdk as cdk

from stacks.player_stack import PlayerStack

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
parser.add_argument("--s3-bucket", default="", help="S3 bucket for Lambda artifacts")
parser.add_argument("--players-table", default="players", help="DynamoDB players table name")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Deploy Player stack with explicit parameters
if args.s3_bucket:  # Only create if S3 bucket is provided
    player_stack = PlayerStack(
        app,
        "player",
        description="Cognito User Pool and authentication Lambda for Eidolon Engine",
        region_name=args.region,
        s3_bucket=args.s3_bucket,
        players_table=args.players_table
    )
else:
    print("Error: S3 bucket parameter is required for Player stack")
    exit(1)

app.synth()