"""CDK app for API stack deployment."""

import json
import os

import aws_cdk as cdk
from stacks.api_stack import ApiStack

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
deployment_mode = app.node.try_get_context("deployment_mode") or "hybrid"

# Get Lambda function ARNs if provided
lambda_arns_json = app.node.try_get_context("lambda_arns") or "{}"
lambda_arns = json.loads(lambda_arns_json)

# Get Cognito settings
cognito_user_pool_id = app.node.try_get_context("cognito_user_pool_id") or ""
cognito_client_id = app.node.try_get_context("cognito_client_id") or ""
cognito_user_pool_arn = app.node.try_get_context("cognito_user_pool_arn") or ""

# Create stack
api_stack = ApiStack(
    app,
    "api",
    env=cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=region),
    region_name=region,
    hosted_zone_id=hosted_zone_id,
    domain=domain,
    api_host=api_host,
    deployment_mode=deployment_mode,
    lambda_arns=lambda_arns,
    cognito_user_pool_id=cognito_user_pool_id,
    cognito_client_id=cognito_client_id,
    cognito_user_pool_arn=cognito_user_pool_arn,
)

app.synth()