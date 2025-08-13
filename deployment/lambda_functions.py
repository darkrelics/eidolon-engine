"""Lambda stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy


def deploy_lambda_stack(params) -> dict:
    """Deploy the Lambda stack using CDK."""
    # Get DynamoDB policy ARN from state
    state_path = Path(__file__).parent / ".cdk-state.json"
    state = CDKState.load(str(state_path))
    dynamodb_policy_arn = state.infrastructure.get("dynamodb_policy_arn", "")
    
    # Get config for DynamoDB tables
    config_path = Path(__file__).parent.parent / "config.yml"
    config = Config.load(str(config_path))
    
    # Build client FQDN
    client_fqdn = f"{params.client_host}.{params.domain}"
    
    # Build DynamoDB tables parameter
    tables_list = []
    for key, value in config.dynamodb_tables.items():
        tables_list.append(f"{key}={value}")
    tables_param = ",".join(tables_list)
    
    app_command = (
        f"python3 app_lambda.py --region {params.region} "
        f"--s3-bucket {params.s3_bucket} "
        f"--client-fqdn {client_fqdn} "
        f"--dynamodb-policy-arn {dynamodb_policy_arn} "
        f"--dynamodb-tables '{tables_param}'"
    )
    return run_cdk_deploy("lambda", params.region, app_command)


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
        response = lambda_client.list_layer_versions(
            LayerName=layer_name,
            MaxItems=1
        )
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


def validate_lambda_function(function_name: str, region: str) -> bool:
    """Validate that Lambda function exists.
    
    Args:
        function_name: Name of the Lambda function
        region: AWS region
        
    Returns:
        True if function exists, False otherwise
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        lambda_client.get_function(FunctionName=function_name)
        print(f"  [OK] Lambda function: {function_name}")
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            print(f"  [MISSING] Lambda function: {function_name}")
        else:
            print(f"  [ERROR] Lambda function {function_name}: {error_code}")
        return False


def validate_lambda_role(role_name: str, region: str) -> bool:
    """Validate that IAM role exists.
    
    Args:
        role_name: Name of the IAM role
        region: AWS region
        
    Returns:
        True if role exists, False otherwise
    """
    try:
        iam = boto3.client("iam", region_name=region)
        iam.get_role(RoleName=role_name)
        print(f"  [OK] IAM role: {role_name}")
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "NoSuchEntity":
            print(f"  [MISSING] IAM role: {role_name}")
        else:
            print(f"  [ERROR] IAM role {role_name}: {error_code}")
        return False


def verify_lambda_deployment(params) -> dict:
    """Verify the Lambda deployment completed successfully."""
    print("\nVerifying Lambda deployment...")
    
    # List of expected Lambda functions in alphabetical order
    expected_functions = [
        "api-archetype-list",
        "api-character-add",
        "api-character-delete",
        "api-character-get",
        "api-character-list",
        "api-segment-decision",
        "api-segment-history",
        "api-segment-outcome",
        "api-segment-rest",
        "api-segment-status",
        "api-story-abandon",
        "api-story-start",
        "cognito-player-new",
        "ops-segment-poller",
        "ops-segment-process",
        "ops-story-advance"
    ]
    
    # Validate Lambda layer
    layer_valid = validate_lambda_layer("eidolon-dependencies", params.region)
    
    # Validate IAM role
    role_valid = validate_lambda_role("eidolon-lambda-execution-role", params.region)
    
    # Validate all Lambda functions
    functions_valid = True
    function_results = {}
    for function_name in expected_functions:
        result = validate_lambda_function(function_name, params.region)
        function_results[function_name] = result
        if not result:
            functions_valid = False
    
    # Count successful deployments
    successful_functions = sum(1 for v in function_results.values() if v)
    total_functions = len(expected_functions)
    
    print(f"\nLambda functions deployed: {successful_functions}/{total_functions}")
    
    return {
        "layer": layer_valid,
        "role": role_valid,
        "functions": functions_valid,
        "function_results": function_results,
        "success": layer_valid and role_valid and functions_valid
    }


def deploy_lambda(params, config: Config, state: CDKState,
                 config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Lambda stack."""
    print("\n" + "=" * 60)
    print("Phase 5: Lambda Stack")
    print("=" * 60)
    
    # Check if S3 bucket with artifacts exists
    try:
        s3 = boto3.client("s3", region_name=params.region)
        s3.head_bucket(Bucket=params.s3_bucket)
    except ClientError:
        print(f"\nError: S3 bucket {params.s3_bucket} not accessible")
        print("Please ensure CodeBuild has run and created Lambda artifacts")
        return False
    
    # Deploy stack
    result = deploy_lambda_stack(params)
    
    if not result.get("success", False):
        print("\nLambda deployment failed!")
        return False
    
    # Verify deployment
    validation = verify_lambda_deployment(params)
    
    if not validation.get("success", False):
        print("\nWarning: Lambda deployment completed with issues")
        if not validation.get("layer", False):
            print("  - Lambda layer was not created")
        if not validation.get("role", False):
            print("  - IAM role was not created")
        if not validation.get("functions", False):
            failed_functions = [k for k, v in validation.get("function_results", {}).items() if not v]
            print(f"  - Failed functions: {', '.join(failed_functions)}")
    
    # Update state with Lambda ARNs
    if validation.get("success", False):
        state.mark_stack_deployed("lambda", result.get("outputs", {}))
        
        # Store Lambda function ARNs in infrastructure
        if "infrastructure" not in state.__dict__:
            state.infrastructure = {}
        
        # Store role ARN
        state.infrastructure["lambda_role_arn"] = result.get("outputs", {}).get("LambdaRoleArn", "")
        
        # Store function ARNs
        lambda_arns = {}
        for function_name in validation.get("function_results", {}).keys():
            arn_key = function_name.replace("-", "").title() + "Arn"
            arn_value = result.get("outputs", {}).get(arn_key, "")
            if arn_value:
                lambda_arns[function_name] = arn_value
        
        state.infrastructure["lambda_function_arns"] = lambda_arns
        state.save(str(state_path))
    
    return validation.get("success", False)