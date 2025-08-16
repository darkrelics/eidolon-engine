"""CDK application entry point for CodeBuild stack."""

import aws_cdk as cdk
from stacks.codebuild_stack import CodeBuildStack

app = cdk.App()

# Get parameters from context
region = app.node.try_get_context("region") or "us-east-1"
s3_bucket = app.node.try_get_context("s3_bucket") or ""
github_owner = app.node.try_get_context("github_owner") or "robinje"
github_repo = app.node.try_get_context("github_repo") or "eidolon-engine"
github_branch = app.node.try_get_context("github_branch") or "develop"
bucket_exists = app.node.try_get_context("bucket_exists") == "true"

# Deploy CodeBuild stack with context parameters
if s3_bucket:  # Only create if S3 bucket is provided
    codebuild_stack = CodeBuildStack(
        app,
        "codebuild",
        description="CodeBuild projects and S3 bucket for Lambda builds",
        region_name=region,
        s3_bucket=s3_bucket,
        github_owner=github_owner,
        github_repo=github_repo,
        github_branch=github_branch,
        bucket_exists=bucket_exists,
    )
else:
    print("Error: S3 bucket parameter is required for CodeBuild stack")
    exit(1)

app.synth()
