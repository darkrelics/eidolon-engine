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


def load_email_template(template_name: str) -> str:
    """Load email template from data directory.

    Args:
        template_name: Name of template file (e.g., 'cognito-verification-email.html')

    Returns:
        Template content as string, or empty string if file not found
    """
    project_root = Path(__file__).parent.parent
    template_path = project_root / "data" / template_name

    if not template_path.exists():
        print(f"  [WARNING] Email template not found: {template_path}")
        return ""

    try:
        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"  Loaded email template: {template_name} ({len(content)} bytes)")
        return content
    except Exception as e:
        print(f"  [ERROR] Failed to load template {template_name}: {e}")
        return ""


def configure_user_pool_settings(user_pool_id: str, lambda_arn: str, region: str) -> bool:
    """Configure all User Pool settings in a single update to prevent AWS from resetting values.

    Args:
        user_pool_id: ID of the User Pool
        lambda_arn: ARN of the cognito-player-new Lambda function
        region: AWS region

    Returns:
        True if all settings configured successfully
    """
    try:
        cognito = boto3.client("cognito-idp", region_name=region)

        # Load email template
        html_template = load_email_template("cognito-verification-email.html")

        # Build update parameters
        update_params = {
            "UserPoolId": user_pool_id,
            "AutoVerifiedAttributes": ["email"],
            "LambdaConfig": {"PostConfirmation": lambda_arn},
        }

        # Add email template if available
        if html_template:
            update_params["VerificationMessageTemplate"] = {
                "DefaultEmailOption": "CONFIRM_WITH_CODE",
                "EmailMessage": html_template,
                "EmailSubject": "Verify your Eidolon Engine account",
            }
            print("  Configuring User Pool with all settings (including custom email template)...")
        else:
            update_params["VerificationMessageTemplate"] = {"DefaultEmailOption": "CONFIRM_WITH_CODE"}
            print("  Configuring User Pool with all settings (using default email template)...")

        # Apply all settings in a single update
        cognito.update_user_pool(**update_params)

        print("  [OK] User Pool settings configured successfully")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        error_msg = err.response.get("Error", {}).get("Message", "")
        print(f"  [ERROR] Failed to configure User Pool settings: {error_code} - {error_msg}")
        return False


def configure_user_pool_auto_verify(user_pool_id: str, region: str) -> bool:
    """Configure auto-verified attributes for User Pool.

    Args:
        user_pool_id: ID of the User Pool
        region: AWS region

    Returns:
        True if auto-verify is configured successfully
    """
    try:
        cognito = boto3.client("cognito-idp", region_name=region)

        # Get current user pool configuration
        print("  Checking auto-verified attributes...")
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        current_config = response.get("UserPool", {})

        # Check current auto-verified attributes (handle null/None)
        current_auto_verify = current_config.get("AutoVerifiedAttributes") or []

        # Ensure email is in auto-verified attributes
        if "email" in current_auto_verify:
            print("  [OK] Email auto-verification already enabled")
            return True

        print("  Enabling email auto-verification...")

        # Update the user pool to enable email auto-verification
        cognito.update_user_pool(UserPoolId=user_pool_id, AutoVerifiedAttributes=["email"])

        print("  [OK] Email auto-verification enabled successfully")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        error_msg = err.response.get("Error", {}).get("Message", "")
        print(f"  [ERROR] Failed to enable auto-verification: {error_code} - {error_msg}")
        return False


def configure_user_pool_email_template(user_pool_id: str, region: str) -> bool:
    """Configure email verification template for User Pool.

    Args:
        user_pool_id: ID of the User Pool
        region: AWS region

    Returns:
        True if template is configured successfully
    """
    try:
        cognito = boto3.client("cognito-idp", region_name=region)

        # Load email template from data directory
        html_template = load_email_template("cognito-verification-email.html")

        if not html_template:
            print("  [INFO] No custom email template found, using Cognito default")
            return True  # Not a failure - just use default

        # Get current user pool configuration
        print("  Checking current email verification template...")
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        current_config = response.get("UserPool", {})

        # Check current verification template (handle null/None)
        current_template = current_config.get("VerificationMessageTemplate", {})
        current_email = current_template.get("EmailMessage") or ""

        # Check if update is needed
        template_needs_update = current_email != html_template

        if not template_needs_update:
            print("  [OK] Email verification template already up to date")
            return True

        print("  Updating email verification template...")

        # Update the user pool with new email template
        cognito.update_user_pool(
            UserPoolId=user_pool_id,
            VerificationMessageTemplate={
                "DefaultEmailOption": "CONFIRM_WITH_CODE",
                "EmailMessage": html_template,
                "EmailSubject": "Verify your Eidolon Engine account",
            },
        )

        print("  [OK] Email verification template updated successfully")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        error_msg = err.response.get("Error", {}).get("Message", "")
        print(f"  [ERROR] Failed to update email template: {error_code} - {error_msg}")
        return False


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


def verify_user_pool_trigger_configuration(user_pool_id: str, expected_lambda_arn: str, region: str) -> tuple[bool, bool]:
    """Verify User Pool trigger and Lambda permissions are correctly configured.

    Args:
        user_pool_id: ID of the User Pool
        expected_lambda_arn: Expected ARN of the Lambda function
        region: AWS region

    Returns:
        Tuple of (trigger_configured, permissions_configured)
    """
    trigger_ok = False
    permissions_ok = False

    try:
        # Check trigger configuration
        cognito = boto3.client("cognito-idp", region_name=region)
        response = cognito.describe_user_pool(UserPoolId=user_pool_id)
        lambda_config = response.get("UserPool", {}).get("LambdaConfig", {})
        current_trigger = lambda_config.get("PostConfirmation", "")

        if current_trigger == expected_lambda_arn:
            trigger_ok = True
        else:
            print(f"  [ERROR] Trigger verification failed - Expected: {expected_lambda_arn}, Got: {current_trigger}")

        # Check Lambda permissions
        lambda_client = boto3.client("lambda", region_name=region)
        try:
            policy_response = lambda_client.get_policy(FunctionName="cognito-player-new")
            policy_str = policy_response.get("Policy", "{}")
            policy = json.loads(policy_str)
            statements = policy.get("Statement", [])

            # Look for Cognito invoke permission
            for statement in statements:
                if (
                    statement.get("Effect") == "Allow"
                    and statement.get("Action") == "lambda:InvokeFunction"
                    and statement.get("Principal", {}).get("Service") == "cognito-idp.amazonaws.com"
                ):
                    source_arn = statement.get("Condition", {}).get("ArnLike", {}).get("AWS:SourceArn", "")
                    if user_pool_id in source_arn:
                        permissions_ok = True
                        break

            if not permissions_ok:
                print("  [ERROR] Permission verification failed - Cognito invoke permission not found")

        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                print("  [ERROR] Permission verification failed - No policy found on Lambda function")

    except ClientError as err:
        print(f"  [ERROR] Verification failed: {err}")

    return trigger_ok, permissions_ok


def configure_lambda_permissions_and_verify(user_pool_id: str, lambda_arn: str, region: str) -> bool:
    """Configure Lambda permissions and verify User Pool trigger configuration.

    NOTE: This function does NOT update the User Pool trigger - that must be done by
    configure_user_pool_settings() to avoid resetting other User Pool settings.

    Args:
        user_pool_id: ID of the User Pool
        lambda_arn: ARN of the Lambda function
        region: AWS region

    Returns:
        True if permissions configured and trigger verified successfully
    """
    try:
        # STEP 1: PERMISSIONS - Ensure Lambda has permission to be invoked by Cognito
        # This is needed even if the trigger is already configured, as permissions can be lost
        # when Lambda functions are redeployed or recreated
        print("  Configuring Lambda invoke permissions...")
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
            if error_code == "ResourceConflictException":
                print("  [INFO] Permission already exists")
            else:
                print(f"  [ERROR] Could not add Lambda permission: {err}")
                return False

        # STEP 2: VERIFY - Confirm trigger and permissions are configured correctly
        print("  Verifying trigger and permission configuration...")
        trigger_ok, permissions_ok = verify_user_pool_trigger_configuration(user_pool_id, lambda_arn, region)

        if trigger_ok and permissions_ok:
            print("  [OK] Trigger and permissions verified successfully")
            return True

        if not trigger_ok:
            print("  [ERROR] Trigger verification failed")
        if not permissions_ok:
            print("  [ERROR] Permissions verification failed")

        return False

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

    # Configure User Pool settings (trigger, auto-verify, email template)
    # This must run on every deployment to ensure all settings are properly configured
    # (CDK cannot do this for imported pools, and AWS can reset settings when updating individual parameters)
    trigger_configured = False
    if validation.get("user_pool_id"):
        lambda_arn = get_cognito_player_new_arn(params.region)
        if lambda_arn:
            print("\nConfiguring User Pool settings (trigger, auto-verify, email template)...")

            # Configure all settings together to prevent AWS from resetting values
            settings_configured = configure_user_pool_settings(validation["user_pool_id"], lambda_arn, params.region)

            if settings_configured:
                # Configure Lambda permissions and verify settings
                trigger_configured = configure_lambda_permissions_and_verify(
                    validation["user_pool_id"], lambda_arn, params.region
                )
                if not trigger_configured:
                    print("  [ERROR] Failed to configure permissions or verify trigger - new user registration may not work")
                    print("  [ERROR] Deployment continuing with errors")
            else:
                print("  [ERROR] Failed to configure User Pool settings")
                print("  [ERROR] New user registration will not work until this is fixed")
        else:
            print("  [ERROR] cognito-player-new Lambda not found - User Pool cannot be configured")
            print("  [ERROR] New user registration will not work until this is fixed")
    else:
        print("  [ERROR] User Pool ID not found - cannot configure settings")
        print("  [ERROR] New user registration will not work until this is fixed")

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
