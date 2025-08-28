"""Character stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from codebuild import execute_lambda_builds, validate_build_artifacts
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from utilities import extract_stack_outputs, run_cdk_deploy


def deploy_character_stack(params) -> dict:
    """Deploy the Character stack using CDK."""
    # Get DynamoDB policy ARN from state
    state_path = Path(__file__).parent / ".cdk-state.json"
    state = CDKState.load(str(state_path))
    dynamodb_policy_arn = state.infrastructure.get("dynamodb_policy_arn", "")

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
        f"dynamodb_policy_arn={dynamodb_policy_arn}",
        "-c",
        f"dynamodb_tables={tables_json}",
    ]

    app_command = "python3 app_character.py"
    return run_cdk_deploy("character", params.region, app_command, context_args)


def validate_lambda_layer(layer_name: str, region: str) -> bool:
    """Validate that Lambda layer exists.

    Args:
        layer_name: Name of the Lambda layer
        region: AWS region

    Returns:
        True if layer exists, False otherwise
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.list_layer_versions(LayerName=layer_name, MaxItems=1)
        if response.get("LayerVersions"):
            print(f"  [OK] Lambda layer: {layer_name}")
            return True
        print(f"  [MISSING] Lambda layer: {layer_name}")
        return False
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            print(f"  [MISSING] Lambda layer: {layer_name}")
        else:
            print(f"  [ERROR] Lambda layer {layer_name}: {error_code}")
        return False


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

    # Check Lambda layer
    if not validate_lambda_layer("eidolon-dependencies", params.region):
        validation["success"] = False

    # Check Lambda execution role
    try:
        iam_client = boto3.client("iam", region_name=params.region)
        iam_client.get_role(RoleName="eidolon-lambda-execution-role")
        print(f"  [OK] Lambda execution role: eidolon-lambda-execution-role")
    except ClientError:
        print(f"  [MISSING] Lambda execution role: eidolon-lambda-execution-role")
        validation["success"] = False

    # Check Lambda functions
    functions_validation = validate_character_functions(params.region)
    if not functions_validation["success"]:
        validation["success"] = False

    return validation


def deploy_character(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
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
            print("✓ Lambda artifacts found")
    except ClientError:
        print(f"\nError: S3 bucket {params.s3_bucket} not accessible")
        print("Please ensure CodeBuild stack has been deployed")
        return False

    # Deploy stack
    result = deploy_character_stack(params)

    if not result.get("success", False):
        print("\nCharacter deployment failed!")
        return False

    # Extract outputs for other stacks
    outputs = extract_stack_outputs("character", params.region)
    
    # Store important outputs in state
    if outputs:
        state.infrastructure["lambda_layer_arn"] = outputs.get("LambdaLayerArn", "")
        state.infrastructure["lambda_role_arn"] = outputs.get("LambdaRoleArn", "")
        state.save(str(state_path))

    # Verify deployment
    validation = verify_character_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: Character deployment completed with issues")
        return False

    print("\n✓ Character Stack deployed successfully")
    return True