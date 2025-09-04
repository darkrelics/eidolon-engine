"""Lambda stack deployment functions."""

import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from codebuild import execute_lambda_builds
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from utilities import extract_stack_outputs, run_cdk_deploy


def deploy_lambda_stack(params) -> dict:
    """Deploy the Lambda stack using CDK."""
    # Get DynamoDB policy ARN from state
    state_path = Path(__file__).parent / ".cdk-state.json"
    state = CDKState.load(str(state_path))
    dynamodb_policy_arn = ""
    if hasattr(state, "infrastructure") and state.infrastructure:
        dynamodb_policy_arn = state.infrastructure.get("dynamodb_policy_arn", "")

    # Pass parameters through context
    context_args = [
        "-c",
        f"region={params.region}",
        "-c",
        f"s3_bucket={params.s3_bucket}",
        "-c",
        f"dynamodb_policy_arn={dynamodb_policy_arn}",
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


def verify_lambda_deployment(params) -> dict:
    """Verify Lambda stack deployment."""
    print("\nVerifying Lambda Stack...")
    validation = {"success": True}

    # Check Lambda layer
    if not validate_lambda_layer("eidolon-dependencies", params.region):
        validation["success"] = False

    # Check Lambda execution role
    try:
        iam_client = boto3.client("iam", region_name=params.region)
        iam_client.get_role(RoleName="eidolon-lambda-execution-role")
        print("  [OK] Lambda execution role: eidolon-lambda-execution-role")
    except ClientError:
        print("  [MISSING] Lambda execution role: eidolon-lambda-execution-role")
        validation["success"] = False

    return validation


def attach_story_policy_to_lambda_role(params, state: CDKState) -> bool:
    """Attach Story policy to shared Lambda execution role using boto3.

    This is done post-Story deployment because CDK cannot modify imported resources.

    Args:
        params: Deployment parameters with region
        state: CDK state containing policy information

    Returns:
        bool: True if policy was successfully attached
    """
    print("\nAttaching Story policy to Lambda execution role...")

    # Get the Lambda role ARN from state
    if not hasattr(state, "infrastructure") or not state.infrastructure:
        print("  [ERROR] State infrastructure not initialized")
        return False

    lambda_role_arn = state.infrastructure.get("lambda_role_arn", "")
    if not lambda_role_arn:
        print("  [ERROR] Lambda role ARN not found in state")
        return False

    # Extract role name from ARN
    role_name = lambda_role_arn.split("/")[-1]

    try:
        iam_client = boto3.client("iam", region_name=params.region)

        # Check if story policy exists
        try:
            iam_client.get_policy(PolicyArn=f"arn:aws:iam::{params.account_id}:policy/eidolon-story-policy")
        except ClientError:
            print("  [INFO] Story policy not yet created, skipping attachment")
            return True

        # Get current attached policies
        response = iam_client.list_attached_role_policies(RoleName=role_name)
        attached_policies = [p["PolicyArn"] for p in response.get("AttachedManagedPolicies", [])]

        story_policy_arn = f"arn:aws:iam::{params.account_id}:policy/eidolon-story-policy"
        if story_policy_arn in attached_policies:
            print(f"  [OK] Story policy already attached to {role_name}")
            return True

        # Attach the story policy to the role
        iam_client.attach_role_policy(RoleName=role_name, PolicyArn=story_policy_arn)
        print(f"  [OK] Attached eidolon-story-policy to {role_name}")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        print(f"  [ERROR] Failed to attach policy: {error_code} - {err}")
        return False
    except Exception as err:
        print(f"  [ERROR] Unexpected error: {err}")
        return False


def deploy_lambda(params, _config: Config, state: CDKState, _config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Lambda stack."""
    phase = get_stack_phase_number("lambda", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: Lambda Stack")
    print("=" * 60)

    # Check if S3 bucket with artifacts exists
    try:
        s3 = boto3.client("s3", region_name=params.region)
        s3.head_bucket(Bucket=params.s3_bucket)

        # Check if Lambda layer artifact exists
        print("\nChecking for Lambda layer artifact...")
        artifacts_exist = False
        try:
            s3.head_object(Bucket=params.s3_bucket, Key="lambda-layer/lambda-layer.zip")
            print("✓ Lambda layer artifact found")
            artifacts_exist = True
        except ClientError:
            print("Lambda layer artifact missing")

        if not artifacts_exist:
            print("\nLambda layer artifact missing. Running CodeBuild to create it...")
            build_success = execute_lambda_builds(params.region)

            if not build_success:
                print("\nError: Failed to build Lambda artifacts")
                return False

            # Verify artifact was created
            try:
                s3.head_object(Bucket=params.s3_bucket, Key="lambda-layer/lambda-layer.zip")
                print("✓ Lambda layer artifact created")
            except ClientError:
                print("\nError: Build succeeded but layer artifact still missing")
                return False
    except ClientError:
        print(f"\nError: S3 bucket {params.s3_bucket} not accessible")
        print("Please ensure CodeBuild stack has been deployed")
        return False

    # Deploy stack
    result = deploy_lambda_stack(params)

    if not result.get("success", False):
        print("\nLambda deployment failed!")
        return False

    # Extract outputs for other stacks
    outputs = extract_stack_outputs("lambda", params.region)

    # Store important outputs in state
    if outputs:
        # Ensure infrastructure dict exists
        if not hasattr(state, "infrastructure"):
            state.infrastructure = {}
        state.infrastructure["lambda_layer_arn"] = outputs.get("LambdaLayerArn", "")
        state.infrastructure["lambda_role_arn"] = outputs.get("LambdaRoleArn", "")
        state.infrastructure["lambda_role_name"] = outputs.get("LambdaRoleName", "")
        state.save(str(state_path))

    # Verify deployment
    validation = verify_lambda_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: Lambda deployment completed with issues")
        return False

    print("\n✓ Lambda Stack deployed successfully")
    return True


def update_lambda_functions_directly(params, region: str, s3_bucket: str) -> bool:
    """Phase 11: Update Lambda function code from S3 artifacts.
    
    This function updates all Lambda functions with the latest code from S3.
    The Lambda layer and infrastructure were already deployed in Phase 3.
    
    Args:
        params: Deployment parameters
        region: AWS region
        s3_bucket: S3 bucket containing Lambda artifacts
        
    Returns:
        bool: True if all updates successful
    """
    print("\n" + "=" * 60)
    print("Phase 11: Lambda Function Code Updates")
    print("=" * 60)
    
    lambda_client = boto3.client("lambda", region_name=region)
    
    # Get the current layer version ARN from the existing layer
    print("\n1. Getting current Lambda layer version...")
    try:
        response = lambda_client.list_layer_versions(
            LayerName="eidolon-dependencies",
            MaxItems=1
        )
        if not response.get('LayerVersions'):
            print("  [ERROR] No layer versions found for eidolon-dependencies")
            return False
        new_layer_arn = response['LayerVersions'][0]['LayerVersionArn']
        print(f"  [OK] Using layer version: {new_layer_arn}")
    except ClientError as err:
        print(f"  [ERROR] Failed to get layer version: {err}")
        return False
    
    # Define all Lambda functions to update
    lambda_functions = [
        # Character functions
        "api-character-add",
        "api-character-delete", 
        "api-character-get",
        "api-character-list",
        "api-archetype-list",
        # Player functions  
        "cognito-player-new",
        # Story functions
        "api-story-start",
        "api-story-abandon", 
        "api-segment-decision",
        "api-segment-history",
        "api-segment-rest",
        "api-segment-status",
        "ops-segment-poller",
        "ops-segment-process",
        "ops-story-advance"
    ]
    
    print(f"\n2. Updating {len(lambda_functions)} Lambda functions...")
    
    update_results = {}
    wait_time = 60  # Wait 60 seconds between attempts
    max_attempts = 10  # Try for up to 10 minutes
    
    # Try to update all functions, with retries if they're locked
    for attempt in range(max_attempts):
        failed_functions = []
        
        for function_name in lambda_functions:
            # Skip functions we already updated successfully
            if function_name in update_results and update_results[function_name] is True:
                continue
                
            print(f"  Updating {function_name}...")
            
            try:
                # Get current configuration first to check layer
                current_config = lambda_client.get_function_configuration(FunctionName=function_name)
                current_layers = current_config.get('Layers', [])
                needs_layer_update = True
                
                for layer in current_layers:
                    if layer.get('Arn') == new_layer_arn:
                        needs_layer_update = False
                        break
                
                # Update function code (no waiting, just like the GUI)
                lambda_client.update_function_code(
                    FunctionName=function_name,
                    S3Bucket=s3_bucket,
                    S3Key=f"{function_name}.zip"
                )
                
                # Only update configuration if layer is outdated
                # This might fail if the code update is still processing, but that's OK
                if needs_layer_update:
                    try:
                        lambda_client.update_function_configuration(
                            FunctionName=function_name,
                            Layers=[new_layer_arn]
                        )
                        print(f"    [OK] Updated {function_name} code and layer")
                    except ClientError as config_err:
                        if config_err.response.get('Error', {}).get('Code') == 'ResourceConflictException':
                            print(f"    [OK] Updated {function_name} code (layer update pending)")
                        else:
                            raise
                else:
                    print(f"    [OK] Updated {function_name} code (layer already current)")
                    
                update_results[function_name] = True
                
            except ClientError as err:
                error_code = err.response.get('Error', {}).get('Code', '')
                if error_code == 'ResourceNotFoundException':
                    print(f"    [SKIP] Function {function_name} doesn't exist yet")
                    update_results[function_name] = None  # Skip, not an error
                elif error_code == 'ResourceConflictException':
                    print(f"    [LOCKED] Function {function_name} is still updating")
                    failed_functions.append(function_name)
                else:
                    print(f"    [ERROR] Failed to update {function_name}: {err}")
                    update_results[function_name] = False
        
        # If no functions failed due to locks, we're done
        if not failed_functions:
            break
            
        # If we still have locked functions and more attempts, wait and retry
        if attempt < max_attempts - 1:
            print(f"  {len(failed_functions)} functions still locked, waiting {wait_time} seconds... (attempt {attempt + 1}/{max_attempts})")
            time.sleep(wait_time)
        else:
            print(f"  [ERROR] {len(failed_functions)} functions still locked after {max_attempts} attempts")
            for func in failed_functions:
                update_results[func] = False
    
    # Summary
    updated_count = sum(1 for result in update_results.values() if result is True)
    skipped_count = sum(1 for result in update_results.values() if result is None) 
    failed_count = sum(1 for result in update_results.values() if result is False)
    
    print(f"\n3. Update Summary:")
    print(f"  [OK] Updated: {updated_count} functions")
    if skipped_count > 0:
        print(f"  [SKIP] Not deployed yet: {skipped_count} functions")
    if failed_count > 0:
        print(f"  [ERROR] Failed: {failed_count} functions")
        return False
    
    print("\n✓ Lambda function updates completed successfully")
    return True
