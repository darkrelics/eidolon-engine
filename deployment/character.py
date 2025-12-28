"""Character stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from codebuild import execute_lambda_builds, validate_build_artifacts
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from utilities import run_cdk_deploy


def deploy_character_stack(params) -> dict:
    """Deploy the Character stack using CDK."""
    # Get state for Lambda stack resources
    state_path = Path(__file__).parent / ".cdk-state.json"
    state = CDKState.load(str(state_path))

    # Safely get Lambda resources from state
    lambda_layer_arn = ""
    lambda_role_arn = ""
    if hasattr(state, "infrastructure") and state.infrastructure:
        lambda_layer_arn = state.infrastructure.get("lambda_layer_arn", "")
        lambda_role_arn = state.infrastructure.get("lambda_role_arn", "")

    # Validate Lambda resources exist
    if not lambda_layer_arn:
        print("\nError: Lambda layer ARN not found in state. Please deploy Lambda stack first.")
        return {"success": False, "outputs": {}}
    if not lambda_role_arn:
        print("\nError: Lambda role ARN not found in state. Please deploy Lambda stack first.")
        return {"success": False, "outputs": {}}

    # Get config for DynamoDB tables
    config_path = Path(__file__).parent.parent / "config.yml"
    config = Config.load(str(config_path))

    # Build client FQDN
    client_fqdn = f"{params.client_host}.{params.domain}"

    # Convert DynamoDB tables to JSON for context passing
    tables_json = json.dumps(config.dynamodb_tables)

    # Pass parameters through context
    context_args = [
        "-c",
        f"region={params.region}",
        "-c",
        f"s3_bucket={params.s3_bucket}",
        "-c",
        f"client_fqdn={client_fqdn}",
        "-c",
        f"lambda_layer_arn={lambda_layer_arn}",
        "-c",
        f"lambda_role_arn={lambda_role_arn}",
        "-c",
        f"dynamodb_tables={tables_json}",
    ]

    app_command = "python3 app_character.py"
    return run_cdk_deploy("character", params.region, app_command, context_args)


def validate_character_functions(region: str) -> dict:
    """Validate character Lambda functions exist.

    Args:
        region: AWS region

    Returns:
        Dict with validation results
    """
    functions = [
        "api-character-add",
        "api-character-delete",
        "api-character-get",
        "api-character-list",
        "api-archetype-list",
        "api-item-brief",
        "api-item-prototype",
        "api-item-use",
        "api-item-discard",
        "api-item-consolidate",
        "api-item-split",
        "api-store-list",
        "api-store-purchase",
    ]

    lambda_client = boto3.client("lambda", region_name=region)
    results = {"success": True, "functions": {}}

    for function_name in functions:
        try:
            lambda_client.get_function(FunctionName=function_name)
            print(f"  [OK] Lambda function: {function_name}")
            results["functions"][function_name] = True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                print(f"  [MISSING] Lambda function: {function_name}")
            else:
                print(f"  [ERROR] Lambda function {function_name}: {error_code}")
            results["functions"][function_name] = False
            results["success"] = False

    return results


def verify_character_deployment(params) -> dict:
    """Verify Character stack deployment."""
    print("\nVerifying Character Stack...")
    validation = {"success": True}

    # Check Lambda functions
    functions_validation = validate_character_functions(params.region)
    if not functions_validation["success"]:
        validation["success"] = False

    return validation


def deploy_character(params, config: Config, _state: CDKState, config_path: Path, _state_path: Path) -> bool:
    """Deploy and verify Character stack."""
    phase = get_stack_phase_number("character", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: Character Stack")
    print("=" * 60)

    # Check if S3 bucket with artifacts exists
    try:
        s3 = boto3.client("s3", region_name=params.region)
        s3.head_bucket(Bucket=params.s3_bucket)

        # Check if Lambda artifacts exist
        print("\nChecking for Lambda artifacts...")
        artifacts_exist = validate_build_artifacts(params.s3_bucket, params.region)

        if not artifacts_exist:
            print("\nLambda artifacts missing. Running CodeBuild to create them...")
            build_success = execute_lambda_builds(params.region)

            if not build_success:
                print("\nError: Failed to build Lambda artifacts")
                return False

            # Verify artifacts were created
            artifacts_exist = validate_build_artifacts(params.s3_bucket, params.region)
            if not artifacts_exist:
                print("\nError: Build succeeded but artifacts still missing")
                return False
        else:
            print("Lambda artifacts found")
    except ClientError:
        print(f"\nError: S3 bucket {params.s3_bucket} not accessible")
        print("Please ensure CodeBuild stack has been deployed")
        return False

    # Deploy stack
    result = deploy_character_stack(params)

    if not result.get("success", False):
        print("\nCharacter deployment failed!")
        return False

    # Verify deployment
    validation = verify_character_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: Character deployment completed with issues")
        return False

    print("\nCharacter Stack deployed successfully")
    return True
