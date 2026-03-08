"""CDK app for Client stack deployment."""

import os

import aws_cdk as cdk
from stacks.client_stack import ClientStack

app = cdk.App()

# Get parameters from CDK context
region = app.node.try_get_context("region") or "us-east-1"
hosted_zone_id = app.node.try_get_context("hosted_zone_id")
domain = app.node.try_get_context("domain")

# Validate required parameters
if not hosted_zone_id:
    raise ValueError("hosted_zone_id is required but not provided")
if not domain:
    raise ValueError("domain is required but not provided")

api_host = app.node.try_get_context("api_host") or "api"
client_host = app.node.try_get_context("client_host") or "portal"
client_bucket = app.node.try_get_context("client_bucket") or ""
api_url = app.node.try_get_context("api_url") or f"https://{api_host}.{domain}"
deployment_mode = app.node.try_get_context("deployment_mode") or "hybrid"
github_owner = app.node.try_get_context("github_owner") or "darkrelics"
github_repo = app.node.try_get_context("github_repo") or "eidolon-engine"
github_branch = app.node.try_get_context("github_branch") or "develop"


def _ctx_bool(value, default: bool = False) -> bool:
    """Best-effort parse of CDK context booleans.

    Handles values coming from `-c name=true` (string) or cdk.json (bool).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


bucket_exists = _ctx_bool(app.node.try_get_context("bucket_exists"), False)

# Get Cognito settings
cognito_user_pool_id = app.node.try_get_context("cognito_user_pool_id") or ""
cognito_client_id = app.node.try_get_context("cognito_client_id") or ""

# Create stack
client_stack = ClientStack(
    app,
    "client",
    env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=region),
    region_name=region,
    hosted_zone_id=hosted_zone_id,
    domain=domain,
    api_host=api_host,
    client_host=client_host,
    client_bucket=client_bucket,
    api_url=api_url,
    deployment_mode=deployment_mode,
    github_owner=github_owner,
    github_repo=github_repo,
    github_branch=github_branch,
    cognito_user_pool_id=cognito_user_pool_id,
    cognito_client_id=cognito_client_id,
    bucket_exists=bucket_exists,
)

app.synth()
