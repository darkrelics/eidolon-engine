"""CDK application entry point for CodeBuild stack."""

import argparse

import aws_cdk as cdk

from stacks.codebuild_stack import CodeBuildStack

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--region", default="us-east-1", help="AWS region for deployment")
parser.add_argument("--s3-bucket", default="", help="S3 bucket for Lambda artifacts")
parser.add_argument("--github-owner", default="robinje", help="GitHub repository owner")
parser.add_argument("--github-repo", default="eidolon-engine", help="GitHub repository name")
parser.add_argument("--github-branch", default="develop", help="GitHub branch to build from")
args, unknown = parser.parse_known_args()  # Use parse_known_args to ignore CDK's other args

app = cdk.App()

# Deploy CodeBuild stack with explicit parameters
if args.s3_bucket:  # Only create if S3 bucket is provided
    codebuild_stack = CodeBuildStack(
        app,
        "codebuild",
        description="CodeBuild projects and S3 bucket for Lambda builds",
        region_name=args.region,
        s3_bucket=args.s3_bucket,
        github_owner=args.github_owner,
        github_repo=args.github_repo,
        github_branch=args.github_branch
    )
else:
    print("Error: S3 bucket parameter is required for CodeBuild stack")
    exit(1)

app.synth()