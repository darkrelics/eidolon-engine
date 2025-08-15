"""API stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from utilities import run_cdk_deploy


def validate_api_gateway(api_name: str, region: str) -> tuple[bool, str]:
    """Validate that API Gateway exists.

    Args:
        api_name: Name of the API Gateway
        region: AWS region

    Returns:
        Tuple of (exists, api_id)
    """
    try:
        api_client = boto3.client("apigateway", region_name=region)
        response = api_client.get_rest_apis(limit=500)

        for api in response.get("items", []):
            if api.get("name") == api_name:
                api_id = api.get("id", "")
                print(f"  [OK] API Gateway: {api_name} ({api_id})")
                return True, api_id

        print(f"  [MISSING] API Gateway: {api_name}")
        return False, ""

    except ClientError as err:
        print(f"  [ERROR] Could not validate API Gateway: {err}")
        return False, ""


def get_lambda_function_arns(region: str) -> dict:
    """Get Lambda function ARNs for API integrations.

    Args:
        region: AWS region

    Returns:
        Dictionary of function names to ARNs
    """
    lambda_client = boto3.client("lambda", region_name=region)
    function_arns = {}

    # List of Lambda functions needed for API
    api_functions = [
        "api-archetype-get",
        "api-character-add",
        "api-character-get",
        "api-character-delete",
        "api-character-list",
        "api-story-start",
        "api-story-abandon",
        "api-segment-decision",
        "api-segment-outcome",
        "api-segment-status",
        "api-segment-history",
        "api-character-rest",
    ]

    for function_name in api_functions:
        try:
            response = lambda_client.get_function(FunctionName=function_name)
            function_arns[function_name] = response["Configuration"]["FunctionArn"]
        except ClientError:
            # Function doesn't exist yet - that's ok
            pass

    return function_arns


def deploy_api_stack(params, state: CDKState) -> dict:
    """Deploy the API stack using CDK."""
    print("\nPreparing API Gateway deployment...")

    # Get Lambda function ARNs
    print("  Discovering Lambda functions for API integration...")
    lambda_arns = get_lambda_function_arns(params.region)
    if not lambda_arns:
        print("  [ERROR] No Lambda functions found")
        return {"success": False, "outputs": {}}

    print(f"  Found {len(lambda_arns)} Lambda functions to integrate:")
    for func in lambda_arns:
        print(f"    - {func}")

    # Build context arguments
    context_args = [
        "-c",
        f"region={params.region}",
        "-c",
        f"hosted_zone_id={params.hosted_zone_id}",
        "-c",
        f"domain={params.domain}",
        "-c",
        f"api_host={params.api_host}",
        "-c",
        f"deployment_mode={params.deployment_mode}",
    ]

    # Add Lambda ARNs as JSON
    if lambda_arns:
        context_args.extend(["-c", f"lambda_arns={json.dumps(lambda_arns)}"])

    # Add Cognito settings from state
    if state.stacks.get("player", {}).get("outputs", {}).get("UserPoolId"):
        context_args.extend(["-c", f"cognito_user_pool_id={state.stacks['player']['outputs']['UserPoolId']}"])
        context_args.extend(["-c", f"cognito_client_id={state.stacks['player']['outputs']['UserPoolClientId']}"])
        context_args.extend(["-c", f"cognito_user_pool_arn={state.stacks['player']['outputs']['UserPoolArn']}"])

    app_command = "python3 app_api.py"
    return run_cdk_deploy("api", params.region, app_command, context_args)


def verify_api_deployment(params, state: CDKState) -> dict:
    """Verify the API deployment completed successfully."""
    print("\nVerifying API deployment...")

    # Validate API Gateway
    api_valid, api_id = validate_api_gateway("eidolon-api", params.region)

    # Check custom domain
    custom_domain_valid = False
    try:
        api_client = boto3.client("apigateway", region_name=params.region)
        domain_name = f"{params.api_host}.{params.domain}"
        response = api_client.get_domain_name(domainName=domain_name)
        if response:
            print(f"  [OK] Custom domain: {domain_name}")
            custom_domain_valid = True
    except ClientError:
        print(f"  [MISSING] Custom domain: {params.api_host}.{params.domain}")

    return {
        "api_gateway": api_valid,
        "api_id": api_id,
        "custom_domain": custom_domain_valid,
        "success": api_valid and custom_domain_valid,
    }


def deploy_api(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify API stack."""
    phase = get_stack_phase_number("api", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: API Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_api_stack(params, state)

    if not result.get("success", False):
        print("\nAPI deployment failed!")
        return False

    # Verify deployment
    validation = verify_api_deployment(params, state)

    if not validation.get("success", False):
        print("\nWarning: API deployment completed with issues")
        if not validation.get("api_gateway", False):
            print("  - API Gateway was not created")
        if not validation.get("custom_domain", False):
            print("  - Custom domain was not configured")

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("api", result.get("outputs", {}))
        state.save(str(state_path))

    return validation.get("success", False)
