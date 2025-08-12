"""Player stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy, validate_policies


def deploy_player_stack(params) -> dict:
    """Deploy the Player stack using CDK."""
    # Get the players table name from config if available
    config_path = Path(__file__).parent.parent / "config.yml"
    config = Config.load(str(config_path))
    players_table = config.dynamodb_tables.get("Players", "players")
    
    app_command = (
        f"python3 app_player.py --region {params.region} "
        f"--s3-bucket {params.s3_bucket} "
        f"--players-table {players_table}"
    )
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


def verify_player_deployment(params) -> dict:
    """Verify the Player deployment completed successfully."""
    print("\nVerifying Player deployment...")
    
    # Validate User Pool
    user_pool_valid, user_pool_id = validate_user_pool("eidolon-users", params.region)
    
    # Validate Lambda function
    lambda_valid = validate_lambda_function("cognito-player-new", params.region)
    
    # Validate IAM role (note: role might be from previous deployments)
    iam = boto3.client("iam", region_name=params.region)
    role_valid = False
    try:
        iam.get_role(RoleName="eidolon-player-lambda-role")
        print(f"  [OK] IAM Role: eidolon-player-lambda-role")
        role_valid = True
    except ClientError:
        print(f"  [MISSING] IAM Role: eidolon-player-lambda-role")
    
    # Check if Lambda is configured as Cognito trigger
    trigger_valid = False
    if user_pool_valid and user_pool_id:
        try:
            cognito = boto3.client("cognito-idp", region_name=params.region)
            response = cognito.describe_user_pool(UserPoolId=user_pool_id)
            lambda_config = response.get("UserPool", {}).get("LambdaConfig", {})
            post_confirmation = lambda_config.get("PostConfirmation", "")
            
            if "cognito-player-new" in post_confirmation:
                print(f"  [OK] PostConfirmation trigger configured")
                trigger_valid = True
            else:
                print(f"  [WARNING] PostConfirmation trigger not configured")
        except ClientError:
            print(f"  [ERROR] Could not verify trigger configuration")
    
    return {
        "user_pool": user_pool_valid,
        "user_pool_id": user_pool_id,
        "lambda": lambda_valid,
        "role": role_valid,
        "trigger": trigger_valid,
        "success": user_pool_valid and lambda_valid and role_valid
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
        if not validation.get("lambda", False):
            print("  - Lambda function was not created")
        if not validation.get("role", False):
            print("  - IAM role was not created")
        if not validation.get("trigger", False):
            print("  - Cognito trigger was not configured")
    
    # Update configuration with Cognito settings
    if validation.get("user_pool", False) and validation.get("user_pool_id"):
        config.cognito_user_pool_id = validation.get("user_pool_id", "")
        # Get client ID from stack outputs
        outputs = result.get("outputs", {})
        config.cognito_client_id = outputs.get("UserPoolClientId", "")
        config.save(str(config_path))
    
    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("player", result.get("outputs", {}))
        state.save(str(state_path))
    
    return validation.get("success", False)