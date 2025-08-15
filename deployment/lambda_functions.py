"""Lambda stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
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

    app_command = "python3 app_lambda.py"
    return run_cdk_deploy("lambda", params.region, app_command, context_args)


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
        "ops-story-advance",
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
        "success": layer_valid and role_valid and functions_valid,
    }


def update_lambda_layer_from_s3(layer_name: str, s3_bucket: str, region: str) -> tuple[bool, str]:
    """Update Lambda layer with latest code from S3 and clean up old versions.
    
    Args:
        layer_name: Name of the Lambda layer
        s3_bucket: S3 bucket containing the layer code
        region: AWS region
        
    Returns:
        Tuple of (success status, layer version ARN)
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        
        print(f"\n  Updating Lambda layer '{layer_name}' from S3...")
        
        # Publish a new layer version with the latest code from S3
        response = lambda_client.publish_layer_version(
            LayerName=layer_name,
            Description=f"Updated from {s3_bucket}/lambda-layer/lambda-layer.zip",
            Content={
                'S3Bucket': s3_bucket,
                'S3Key': 'lambda-layer/lambda-layer.zip'
            },
            CompatibleRuntimes=['python3.12'],
            CompatibleArchitectures=['x86_64']  # Specify architecture for consistency
        )
        
        new_version = response.get('Version', 0)
        layer_arn = response.get('LayerVersionArn', '')
        print(f"    [OK] Layer updated to version {new_version}")
        
        # Delete the previous version to avoid accumulation (keep only latest)
        old_version = new_version - 1
        if old_version > 0:
            try:
                lambda_client.delete_layer_version(
                    LayerName=layer_name,
                    VersionNumber=old_version
                )
                print(f"    [CLEANUP] Deleted old layer version {old_version}")
            except ClientError as cleanup_err:
                # Don't fail if we can't delete old version
                print(f"    [WARNING] Could not delete old layer version {old_version}: {cleanup_err.response.get('Error', {}).get('Code', '')}")
        
        return True, layer_arn
        
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        print(f"    [ERROR] Failed to update layer: {error_code}")
        return False, ""


def update_lambda_function_from_s3(function_name: str, s3_bucket: str, region: str) -> bool:
    """Update Lambda function with latest code from S3.
    
    Args:
        function_name: Name of the Lambda function
        s3_bucket: S3 bucket containing the function code
        region: AWS region
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        
        # Update function code from S3
        lambda_client.update_function_code(
            FunctionName=function_name,
            S3Bucket=s3_bucket,
            S3Key=f"{function_name}.zip"
        )
        
        # Wait for update to complete
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)
        
        print(f"    [OK] {function_name} updated from S3")
        return True
        
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            print(f"    [SKIP] {function_name} not found (will be created by CDK)")
        else:
            print(f"    [ERROR] {function_name}: {error_code}")
        return False


def get_latest_layer_version_arn(layer_name: str, region: str) -> str:
    """Get the ARN of the latest version of a Lambda layer.
    
    Args:
        layer_name: Name of the Lambda layer
        region: AWS region
        
    Returns:
        ARN of the latest layer version, or empty string if not found
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.list_layer_versions(
            LayerName=layer_name,
            MaxItems=1
        )
        
        versions = response.get('LayerVersions', [])
        if versions:
            return versions[0]['LayerVersionArn']
        return ""
    except ClientError:
        return ""


def update_function_layer(function_name: str, layer_arn: str, region: str) -> bool:
    """Update a Lambda function to use the specified layer version.
    
    Args:
        function_name: Name of the Lambda function
        layer_arn: ARN of the layer version to use
        region: AWS region
        
    Returns:
        True if update successful, False otherwise
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        
        # Get current function configuration
        lambda_client.get_function_configuration(FunctionName=function_name)
        
        # Update function configuration with new layer
        lambda_client.update_function_configuration(
            FunctionName=function_name,
            Layers=[layer_arn] if layer_arn else []
        )
        
        # Wait for update to complete
        waiter = lambda_client.get_waiter('function_updated')
        waiter.wait(FunctionName=function_name)
        
        return True
    except ClientError:
        return False


def update_all_functions_with_layer(layer_name: str, new_layer_arn: str, region: str) -> dict:
    """Update all Lambda functions that use a specific layer to use the new version.
    
    Args:
        layer_name: Name of the layer (used for matching)
        new_layer_arn: ARN of the new layer version
        region: AWS region
        
    Returns:
        Dictionary with update results for each function
    """
    results = {}
    
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        
        # Get all functions (with pagination support)
        paginator = lambda_client.get_paginator('list_functions')
        
        for page in paginator.paginate():
            for function in page.get('Functions', []):
                function_name = function.get('FunctionName', '')
                current_layers = function.get('Layers', [])
                
                # Check if this function uses our layer
                uses_our_layer = False
                updated_layers = []
                
                for layer in current_layers:
                    layer_arn = layer.get('Arn', '')
                    # Check if this is our layer by name (ARN format: arn:aws:lambda:region:account:layer:name:version)
                    if f":layer:{layer_name}:" in layer_arn:
                        uses_our_layer = True
                        updated_layers.append(new_layer_arn)
                    else:
                        updated_layers.append(layer_arn)
                
                # Update function if it uses our layer
                if uses_our_layer:
                    try:
                        lambda_client.update_function_configuration(
                            FunctionName=function_name,
                            Layers=updated_layers
                        )
                        print(f"    [OK] Updated {function_name} to use new layer version")
                        results[function_name] = True
                    except ClientError as err:
                        print(f"    [ERROR] Failed to update {function_name}: {err.response.get('Error', {}).get('Code', '')}")
                        results[function_name] = False
                        
    except ClientError as err:
        print(f"    [ERROR] Failed to list functions: {err.response.get('Error', {}).get('Code', '')}")
        
    return results


def update_all_lambda_functions_from_s3(params) -> dict:
    """Update all Lambda functions and layer with latest code from S3.
    
    Args:
        params: Deployment parameters with S3 bucket and region
        
    Returns:
        Dictionary with update results
    """
    print("\n  Updating Lambda functions with latest code from S3...")
    
    # List of all Lambda functions we manage
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
        "ops-story-advance",
    ]
    
    # Update layer first and get the new ARN
    layer_updated, new_layer_arn = update_lambda_layer_from_s3("eidolon-dependencies", params.s3_bucket, params.region)
    
    # Update all functions that use this layer to the new version
    layer_update_results = {}
    if layer_updated and new_layer_arn:
        print(f"  New layer ARN: {new_layer_arn}")
        layer_update_results = update_all_functions_with_layer("eidolon-dependencies", new_layer_arn, params.region)
    
    # Update function code for our managed functions
    function_results = {}
    for function_name in expected_functions:
        # Update function code from S3
        result = update_lambda_function_from_s3(function_name, params.s3_bucket, params.region)
        function_results[function_name] = result
    
    successful_updates = sum(1 for v in function_results.values() if v)
    total_functions = len(expected_functions)
    
    print(f"\n  Lambda functions code updated: {successful_updates}/{total_functions}")
    
    if layer_update_results:
        layer_updates = sum(1 for v in layer_update_results.values() if v)
        print(f"  Functions updated with new layer: {layer_updates}/{len(layer_update_results)}")
    
    return {
        "layer_updated": layer_updated,
        "layer_arn": new_layer_arn,
        "functions_updated": function_results,
        "layer_updates": layer_update_results,
        "success": True  # We don't fail deployment if updates fail
    }


def deploy_lambda(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Lambda stack."""
    phase = get_stack_phase_number("lambda", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: Lambda Stack")
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

    # Update all Lambda functions and layer from S3 to ensure latest code
    update_all_lambda_functions_from_s3(params)

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
