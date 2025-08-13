"""Player stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy


def get_lambda_function_arn(region: str) -> str:
    """Get cognito-player-new Lambda function ARN.
    
    Args:
        region: AWS region
        
    Returns:
        Lambda function ARN or empty string
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.get_function(FunctionName="cognito-player-new")
        return response["Configuration"]["FunctionArn"]
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            return ""
        print(f"Error getting Lambda ARN: {err}")
        return ""


def deploy_player_stack(params) -> dict:
    """Deploy the Player stack using CDK."""
    # Pass all parameters through context
    context_args = [
        f"-c region={params.region}",
        f"-c reply_email={params.reply_email}"
    ]
    
    # Get Lambda ARN if available
    lambda_arn = get_lambda_function_arn(params.region)
    if lambda_arn:
        context_args.append(f"-c lambda_function_arn={lambda_arn}")
    else:
        print("Warning: cognito-player-new Lambda not found")
        print("PostConfirmation trigger will not be configured")
    
    app_command = f"python3 app_player.py {' '.join(context_args)}"
    return run_cdk_deploy("player", params.region, app_command)


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
        response = cognito.list_user_pool_clients(
            UserPoolId=user_pool_id,
            MaxResults=10
        )
        
        clients = response.get("UserPoolClients", [])
        if clients:
            client_id = clients[0].get("ClientId", "")
            print(f"  [OK] User Pool Client: {client_id}")
            return True, client_id
        
        print(f"  [MISSING] User Pool Client")
        return False, ""
        
    except ClientError as err:
        print(f"  [ERROR] Could not validate client: {err}")
        return False, ""


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
        "success": user_pool_valid and client_valid
    }


def deploy_player(params, config: Config, state: CDKState,
                 config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Player stack."""
    print("\n" + "=" * 60)
    print("Phase 6: Player Stack")
    print("=" * 60)
    
    # Deploy stack
    result = deploy_player_stack(params)
    
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