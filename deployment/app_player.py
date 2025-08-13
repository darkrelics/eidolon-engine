"""CDK application entry point for Player stack."""

import argparse

import aws_cdk as cdk

from stacks.player_stack import PlayerStack

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Deploy Player stack with explicit parameters
player_stack = PlayerStack(
    app,
    "player",
    description="Cognito User Pool for Eidolon Engine",
    region_name=args.region
)

app.synth()