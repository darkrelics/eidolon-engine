"""Player stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from stacks import stack_utilities as utils
from utilities import extract_stack_outputs, run_cdk_deploy


def get_shared_resources(params, state: CDKState) -> dict:
    """Get shared Lambda resources from Lambda stack.

    Args:
        params: Deployment parameters with account_id and region
        state: CDK state containing infrastructure details

    Returns:
        Dict with Lambda layer and role ARNs
    """
    resources = {
        "lambda_layer_arn": "",
        "lambda_role_arn": "",
    }

    # Get ARNs from state (stored by Lambda stack deployment)
    if hasattr(state, "infrastructure") and state.infrastructure:
        # Use stored layer ARN if available
        if state.infrastructure.get("lambda_layer_arn"):
            resources["lambda_layer_arn"] = state.infrastructure.get("lambda_layer_arn")  # type: ignore
            print("  Using Lambda layer ARN from state")

        # Use stored role ARN if available
        if state.infrastructure.get("lambda_role_arn"):
            resources["lambda_role_arn"] = state.infrastructure.get("lambda_role_arn")  # type: ignore
            print("  Using Lambda role ARN from state")

    # If not in state, try to get from Lambda stack CloudFormation outputs
    if not resources["lambda_layer_arn"] or not resources["lambda_role_arn"]:
        try:
            lambda_outputs = extract_stack_outputs("lambda", params.region)

            if not resources["lambda_layer_arn"] and lambda_outputs.get("LambdaLayerArn"):
                resources["lambda_layer_arn"] = lambda_outputs["LambdaLayerArn"]
                print("  Using Lambda layer ARN from Lambda stack outputs")

            if not resources["lambda_role_arn"] and lambda_outputs.get("LambdaRoleArn"):
                resources["lambda_role_arn"] = lambda_outputs["LambdaRoleArn"]
                print("  Using Lambda role ARN from Lambda stack outputs")
        except Exception as e:
            print(f"  Warning: Could not get shared resources from Lambda stack: {e}")

    return resources


def get_cognito_player_new_arn(region: str) -> str:
    """Get cognito-player-new Lambda function ARN.

    Args:
        region: AWS region

    Returns:
        Lambda function ARN or empty string
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.get_function(FunctionName="cognito-player-new")
        arn = response["Configuration"]["FunctionArn"]
        return arn
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            return ""
        print(f"  [ERROR] Failed to get Lambda ARN: {err}")
        return ""


def check_existing_user_pool(region: str) -> tuple[bool, str]:
    """Check if the Cognito User Pool already exists."""
    user_pool_name = "eidolon-users"
    exists, pool_id = utils.check_cognito_user_pool_exists(user_pool_name, region)
    if exists:
        print(f"  Found existing user pool: {user_pool_name} ({pool_id})")
        return True, pool_id
    return False, ""


def deploy_player_stack(params, state: CDKState) -> dict:
    """Deploy the Player stack using CDK."""
    print("\nChecking for existing Cognito resources...")
    exists, user_pool_id = check_existing_user_pool(params.region)

    # Get shared resources from Lambda stack
    resources = get_shared_resources(params, state)

    # Get config for DynamoDB tables
    config_path = Path(__file__).parent.parent / "config.yml"
    config = Config.load(str(config_path))

    # Build client FQDN
    client_fqdn = f"{params.client_host}.{params.domain}"

    # Convert DynamoDB tables to JSON for context passing
    tables_json = json.dumps(config.dynamodb_tables)

    # Get DynamoDB policy ARN from state
    dynamodb_policy_arn = state.infrastructure.get("dynamodb_policy_arn", "")

    # Pass all parameters through context - each -c and key=value must be separate
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
        "-c",
        f"lambda_layer_arn={resources['lambda_layer_arn']}",
        "-c",
        f"lambda_role_arn={resources['lambda_role_arn']}",
        "-c",
        f"reply_email={params.reply_email}",
    ]

    # Add existing user pool ID to context if found
    if exists and user_pool_id:
        context_args.extend(["-c", f"existing_user_pool_id={user_pool_id}"])

    app_command = "python3 app_player.py"
    return run_cdk_deploy("player", params.region, app_command, context_args)


def validate_user_pool(user_pool_name: str, region: str) -> tuple[bool, str]:
    """Validate that Cognito User Pool exists.

    Args:
        user_pool_name: Name of the user pool to validate
        region: AWS region

    Returns:
        Tuple of (exists, user_pool_id)
    """
    try:
        cognito = boto3.client("cognito-idp", region_name=region)
        response = cognito.list_user_pools(MaxResults=60)

        for pool in response.get("UserPools", []):
            if pool.get("Name") == user_pool_name:
                pool_id = pool.get("Id", "")
                print(f"  [OK] User Pool: {user_pool_name} ({pool_id})")
                return True, pool_id

        print(f"  [MISSING] User Pool: {user_pool_name}")
        return False, ""

    except ClientError as err:
        print(f"  [ERROR] Could not validate user pool: {err}")
        return False, ""


def validate_user_pool_client(user_pool_id: str, region: str) -> tuple[bool, str]:
    """Validate that User Pool Client exists.

    Args:
        user_pool_id: ID of the user pool
        region: AWS region

    Returns:
        Tuple of (exists, client_id)
    """
    try:
        cognito = boto3.client("cognito-idp", region_name=region)
        response = cognito.list_user_pool_clients(UserPoolId=user_pool_id, MaxResults=10)

        clients = response.get("UserPoolClients", [])
        if clients:
            client_id = clients[0].get("ClientId", "")
            print(f"  [OK] User Pool Client: {client_id}")
            return True, client_id

        print("  [MISSING] User Pool Client")
        return False, ""

    except ClientError as err:
        print(f"  [ERROR] Could not validate client: {err}")
        return False, ""


def configure_user_pool_trigger(user_pool_id: str, lambda_arn: str, region: str) -> bool:
    """Check and configure PostConfirmation trigger on existing User Pool if needed.

    Args:
        user_pool_id: ID of the User Pool
        lambda_arn: ARN of the Lambda function
        region: AWS region

    Returns:
        True if trigger is configured (already was or newly configured)
    """

    try:
        cognito = boto3.client("cognito-idp", region_name=region)

        # STEP 1: CHECK - Get current user pool configuration
        print("  Checking current User Pool trigger configuration...")
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        current_config = response.get("UserPool", {})

        # Check if trigger is already configured
        lambda_config = current_config.get("LambdaConfig", {})
        current_trigger = lambda_config.get("PostConfirmation", "")

        trigger_needs_update = False

        if current_trigger == lambda_arn:
            print("  [OK] PostConfirmation trigger already configured correctly")
        elif current_trigger:
            print(f"  [WARNING] Different trigger configured: {current_trigger}")
            print(f"  [INFO] Will update to: {lambda_arn}")
            trigger_needs_update = True
        else:
            print("  [INFO] No PostConfirmation trigger currently configured")
            trigger_needs_update = True

        # STEP 2: APPLY - Update the Lambda configuration if needed
        if trigger_needs_update:
            print("  Applying PostConfirmation trigger configuration...")
            lambda_config["PostConfirmation"] = lambda_arn

            # Update the user pool with the new trigger
            cognito.update_user_pool(UserPoolId=user_pool_id, LambdaConfig=lambda_config)

            print("  [OK] PostConfirmation trigger configured successfully")

        # STEP 3: PERMISSIONS - Always ensure Lambda has permission to be invoked by Cognito
        # This is needed even if the trigger is already configured, as permissions can be lost
        # when Lambda functions are redeployed or recreated
        print("  Checking Lambda invoke permissions...")
        lambda_client = boto3.client("lambda", region_name=region)
        sts_client = boto3.client("sts")
        account_id = sts_client.get_caller_identity()["Account"]

        try:
            # First, try to remove any existing permission to avoid conflicts
            try:
                lambda_client.remove_permission(FunctionName="cognito-player-new", StatementId="CognitoInvokePermission")
                print("  [INFO] Removed existing Lambda permission")
            except ClientError:
                pass  # Permission doesn't exist, which is fine

            # Now add the correct permission
            lambda_client.add_permission(
                FunctionName="cognito-player-new",
                StatementId="CognitoInvokePermission",
                Action="lambda:InvokeFunction",
                Principal="cognito-idp.amazonaws.com",
                SourceArn=f"arn:aws:cognito-idp:{region}:{account_id}:userpool/{user_pool_id}",
            )
            print("  [OK] Lambda invoke permission granted to Cognito")
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            print(f"  [ERROR] Could not add Lambda permission: {err}")
            if error_code == "ResourceConflictException":
                print("  [INFO] Permission may already exist with a different configuration")

        return True

    except ClientError as err:
        print(f"  [ERROR] Failed to configure User Pool trigger: {err}")
        return False


def verify_player_deployment(params) -> dict:
    """Verify the Player deployment completed successfully."""
    print("\nVerifying Player deployment...")

    # Validate User Pool
    user_pool_valid, user_pool_id = validate_user_pool("eidolon-users", params.region)

    # Validate User Pool Client
    client_valid = False
    client_id = ""
    if user_pool_valid and user_pool_id:
        client_valid, client_id = validate_user_pool_client(user_pool_id, params.region)

    return {
        "user_pool": user_pool_valid,
        "user_pool_id": user_pool_id,
        "client": client_valid,
        "client_id": client_id,
        "success": user_pool_valid and client_valid,
    }


def deploy_player(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Player stack."""
    phase = get_stack_phase_number("player", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: Player Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_player_stack(params, state)

    if not result.get("success", False):
        print("\nPlayer deployment failed!")
        return False

    # Verify deployment
    validation = verify_player_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: Player deployment completed with issues")
        if not validation.get("user_pool", False):
            print("  - User Pool was not created")
        if not validation.get("client", False):
            print("  - User Pool Client was not created")

    # Configure Lambda trigger for existing User Pool (CDK can't do this for imported pools)
    if validation.get("user_pool_id"):
        lambda_arn = get_cognito_player_new_arn(params.region)
        if lambda_arn:
            print("\nConfiguring PostConfirmation trigger for User Pool...")
            trigger_configured = configure_user_pool_trigger(validation["user_pool_id"], lambda_arn, params.region)
            if not trigger_configured:
                print("  [ERROR] Failed to configure trigger")
        else:
            print("  [WARNING] cognito-player-new Lambda not found - trigger not configured")

    # Update configuration with Cognito settings
    if validation.get("user_pool", False) and validation.get("user_pool_id"):
        config.cognito_user_pool_id = validation.get("user_pool_id", "")
        # Use client ID from validation or stack outputs
        if validation.get("client_id"):
            config.cognito_client_id = validation.get("client_id", "")
        else:
            outputs = result.get("outputs", {})
            config.cognito_client_id = outputs.get("UserPoolClientId", "")
        config.save(str(config_path))

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("player", result.get("outputs", {}))
        state.save(str(state_path))

    return validation.get("success", False)
