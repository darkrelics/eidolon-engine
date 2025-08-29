"""Story stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from lambda_functions import attach_story_policy_to_lambda_role
from utilities import run_cdk_deploy, validate_policies


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
            from utilities import extract_stack_outputs
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


def deploy_story_stack(params, state: CDKState) -> dict:
    """Deploy the Story stack using CDK."""
    # Get shared resources from Character stack
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
    ]

    # App command is just the Python script, context goes to CDK
    app_command = "python3 app_story.py"
    return run_cdk_deploy("story", params.region, app_command, context_args)


def validate_ssm_parameter(parameter_name: str, region: str) -> bool:
    """Validate that SSM parameter exists.

    Args:
        parameter_name: Name of the SSM parameter
        region: AWS region

    Returns:
        bool: True if parameter exists
    """
    try:
        ssm = boto3.client("ssm", region_name=region)
        response = ssm.get_parameter(Name=parameter_name)

        if response.get("Parameter"):
            print(f"  [OK] SSM Parameter: {parameter_name}")
            return True

        print(f"  [MISSING] SSM Parameter: {parameter_name}")
        return False

    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ParameterNotFound":
            print(f"  [MISSING] SSM Parameter: {parameter_name}")
        else:
            print(f"  [ERROR] Could not validate SSM parameter: {err}")
        return False


def validate_sqs_queue(queue_name: str, region: str) -> tuple[bool, str]:
    """Validate that SQS queue exists.

    Args:
        queue_name: Name of the SQS queue
        region: AWS region

    Returns:
        Tuple of (exists, queue_url)
    """
    try:
        sqs = boto3.client("sqs", region_name=region)
        response = sqs.get_queue_url(QueueName=queue_name)

        queue_url = response.get("QueueUrl", "")
        if queue_url:
            print(f"  [OK] SQS Queue: {queue_name}")
            return True, queue_url

        print(f"  [MISSING] SQS Queue: {queue_name}")
        return False, ""

    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "AWS.SimpleQueueService.NonExistentQueue":
            print(f"  [MISSING] SQS Queue: {queue_name}")
        else:
            print(f"  [ERROR] Could not validate SQS queue: {err}")
        return False, ""


def validate_eventbridge_rule(rule_name: str, region: str) -> bool:
    """Validate that EventBridge rule exists.

    Args:
        rule_name: Name of the EventBridge rule
        region: AWS region

    Returns:
        bool: True if rule exists
    """
    try:
        events = boto3.client("events", region_name=region)
        response = events.describe_rule(Name=rule_name)

        if response.get("Name"):
            state = response.get("State", "")
            print(f"  [OK] EventBridge Rule: {rule_name} (State: {state})")
            return True

        print(f"  [MISSING] EventBridge Rule: {rule_name}")
        return False

    except ClientError as err:
        if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            print(f"  [MISSING] EventBridge Rule: {rule_name}")
        else:
            print(f"  [ERROR] Could not validate EventBridge rule: {err}")
        return False


def fix_eventbridge_lambda_permission(params) -> bool:
    """Fix EventBridge permission to invoke ops-segment-poller Lambda.

    This addresses the issue where CDK's add_permission() doesn't work
    when importing Lambda functions from ARNs.

    Args:
        params: Deployment parameters with region

    Returns:
        bool: True if permission was successfully added or already exists
    """
    print("\nFixing EventBridge Lambda invocation permission...")

    lambda_client = boto3.client("lambda", region_name=params.region)
    events_client = boto3.client("events", region_name=params.region)

    function_name = "ops-segment-poller"
    rule_name = "eidolon-story-poller"
    statement_id = "EventBridgeInvokePermission"

    try:
        # First check if the permission already exists
        try:
            response = lambda_client.get_policy(FunctionName=function_name)
            policy = json.loads(response["Policy"])

            # Check if EventBridge permission already exists
            for stmt in policy.get("Statement", []):
                if stmt.get("Sid") == statement_id:
                    print(f"  [OK] Permission '{statement_id}' already exists")

                    # Verify the target is configured
                    targets_response = events_client.list_targets_by_rule(Rule=rule_name)
                    targets = targets_response.get("Targets", [])
                    if targets:
                        print(f"  [OK] EventBridge rule has {len(targets)} target(s)")
                        return True
                    else:
                        print(f"  [WARNING] EventBridge rule has no targets")
                        # Continue to add the target
                        break
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise
            # No policy exists yet, continue to add permission

        # Get the rule ARN
        rule_response = events_client.describe_rule(Name=rule_name)
        rule_arn = rule_response["Arn"]

        # Remove any existing permission with the same statement ID
        try:
            lambda_client.remove_permission(FunctionName=function_name, StatementId=statement_id)
            print(f"  Removed existing permission '{statement_id}'")
        except ClientError as e:
            if e.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        # Add the permission
        lambda_client.add_permission(
            FunctionName=function_name,
            StatementId=statement_id,
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn,
        )
        print(f"  [OK] Added permission for EventBridge to invoke {function_name}")

        # Always update/ensure the target is properly configured
        # Get the Lambda function ARN
        function_response = lambda_client.get_function(FunctionName=function_name)
        function_arn = function_response["Configuration"]["FunctionArn"]

        # Check existing targets
        targets_response = events_client.list_targets_by_rule(Rule=rule_name)
        existing_targets = targets_response.get("Targets", [])

        # Remove any existing targets (to ensure clean configuration)
        if existing_targets:
            target_ids = [t["Id"] for t in existing_targets]
            events_client.remove_targets(Rule=rule_name, Ids=target_ids)
            print(f"  Removed {len(target_ids)} existing target(s)")

        # Add the target with proper configuration
        # Note: EventBridge uses the Lambda resource-based policy for permissions,
        # not an execution role
        events_client.put_targets(
            Rule=rule_name,
            Targets=[
                {
                    "Id": "1",
                    "Arn": function_arn,
                    # EventBridge will use the resource-based policy we added above
                    # No RoleArn needed for Lambda targets
                }
            ],
        )
        print(f"  [OK] Configured Lambda target for EventBridge rule")

        # Final verification
        print("  Verifying configuration...")

        # Check the permission is set
        response = lambda_client.get_policy(FunctionName=function_name)
        policy = json.loads(response["Policy"])
        has_permission = any(
            stmt.get("Sid") == statement_id and stmt.get("Principal", {}).get("Service") == "events.amazonaws.com"
            for stmt in policy.get("Statement", [])
        )

        # Check the target is set
        targets_response = events_client.list_targets_by_rule(Rule=rule_name)
        has_target = len(targets_response.get("Targets", [])) > 0

        # Check the rule state
        rule_response = events_client.describe_rule(Name=rule_name)
        rule_state = rule_response.get("State", "UNKNOWN")

        print(f"    Permission configured: {has_permission}")
        print(f"    Target configured: {has_target}")
        print(f"    Rule state: {rule_state}")

        if has_permission and has_target:
            print(f"  [OK] EventBridge->Lambda integration fully configured")
            if rule_state == "DISABLED":
                print(f"  [INFO] Rule is currently DISABLED (will be enabled when a story starts)")
            return True
        else:
            print(f"  [ERROR] EventBridge->Lambda integration not properly configured")
            return False

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ResourceNotFoundException":
            print(f"  [ERROR] Lambda function '{function_name}' or rule '{rule_name}' not found")
        else:
            print(f"  [ERROR] Failed to fix EventBridge permission: {error_code} - {err}")
        return False
    except Exception as err:
        print(f"  [ERROR] Unexpected error fixing EventBridge permission: {err}")
        return False


def update_lambda_environments(params, processing_queue_url: str, advancement_queue_url: str) -> bool:
    """Update Lambda function environment variables with Story stack resources.

    Args:
        params: Deployment parameters with region
        processing_queue_url: URL of the processing queue
        advancement_queue_url: URL of the advancement queue

    Returns:
        bool: True if all updates successful
    """
    print("\nUpdating Lambda environment variables...")

    lambda_client = boto3.client("lambda", region_name=params.region)

    # Define which functions need which environment variables
    # All story-related environment variables for consistency
    story_env_vars = {
        "SEGMENT_QUEUE_URL": processing_queue_url,
        "STORY_ADVANCEMENT_QUEUE_URL": advancement_queue_url,
        "SSM_POLLER_STATE_PARAMETER": "/eidolon/story/config",
        "EVENTBRIDGE_RULE_NAME": "eidolon-story-poller",
    }

    function_updates = [
        # API functions - all need all 4 environment variables
        ("api-story-start", story_env_vars),
        ("api-story-abandon", story_env_vars),
        ("api-segment-decision", story_env_vars),
        ("api-segment-history", story_env_vars),
        ("api-segment-rest", story_env_vars),
        ("api-segment-status", story_env_vars),
        # Operations functions
        ("ops-segment-poller", story_env_vars),
        ("ops-segment-process", story_env_vars),
        ("ops-story-advance", story_env_vars),
    ]

    all_success = True
    for function_name, env_updates in function_updates:
        try:
            # Get current configuration
            response = lambda_client.get_function_configuration(FunctionName=function_name)
            current_env = response.get("Environment", {}).get("Variables", {})

            # Merge with new variables
            current_env.update(env_updates)

            # Update function configuration
            lambda_client.update_function_configuration(FunctionName=function_name, Environment={"Variables": current_env})
            print(f"  [OK] Updated environment for {function_name}")

        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                print(f"  [WARNING] Lambda function {function_name} not found")
            else:
                print(f"  [ERROR] Failed to update {function_name}: {err}")
                all_success = False

    return all_success


def verify_story_deployment(params) -> dict:
    """Verify the Story deployment completed successfully."""
    print("\nVerifying Story deployment...")

    # Validate SSM Parameter
    ssm_valid = validate_ssm_parameter("/eidolon/story/config", params.region)

    # Validate SQS Queues
    processing_valid, processing_url = validate_sqs_queue("eidolon-processing-queue", params.region)
    advancement_valid, advancement_url = validate_sqs_queue("eidolon-advancement-queue", params.region)

    # Validate EventBridge Rule
    eventbridge_valid = validate_eventbridge_rule("eidolon-story-poller", params.region)

    # Validate IAM Policy using utilities function
    policy_validation = validate_policies(["eidolon-story-policy"])
    policy_valid = policy_validation.get("eidolon-story-policy", False)

    return {
        "ssm": ssm_valid,
        "processing_queue": processing_valid,
        "processing_queue_url": processing_url,
        "advancement_queue": advancement_valid,
        "advancement_queue_url": advancement_url,
        "eventbridge": eventbridge_valid,
        "policy": policy_valid,
        "success": all([ssm_valid, processing_valid, advancement_valid, eventbridge_valid, policy_valid]),
    }


def deploy_story(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Story stack."""
    phase = get_stack_phase_number("story", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: Story Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_story_stack(params, state)

    if not result.get("success", False):
        print("\nStory deployment failed!")
        return False

    # Attach Story policy to Lambda execution role (CDK can't do this with imported roles)
    if not attach_story_policy_to_lambda_role(params, state):
        print("\nError: Failed to attach Story policy to Lambda role")
        return False

    # Verify deployment
    validation = verify_story_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: Story deployment completed with issues")
        if not validation.get("ssm", False):
            print("  - SSM Parameter was not created")
        if not validation.get("processing_queue", False):
            print("  - Processing queue was not created")
        if not validation.get("advancement_queue", False):
            print("  - Advancement queue was not created")
        if not validation.get("eventbridge", False):
            print("  - EventBridge rule was not created")
        if not validation.get("policy", False):
            print("  - IAM policy was not created")

    # Update Lambda function environment variables if queues were created
    if validation.get("processing_queue_url") and validation.get("advancement_queue_url"):
        update_lambda_environments(params, validation.get("processing_queue_url", ""), validation.get("advancement_queue_url", ""))

    # Fix EventBridge Lambda permission (CDK doesn't set this correctly when importing Lambda ARNs)
    if validation.get("eventbridge", False):
        fix_eventbridge_lambda_permission(params)

    # Update configuration with queue URLs if available
    if validation.get("processing_queue_url"):
        config.sqs_processing_queue_url = validation.get("processing_queue_url", "")  # type: ignore
    if validation.get("advancement_queue_url"):
        config.sqs_advancement_queue_url = validation.get("advancement_queue_url", "")  # type: ignore

    # Always save SSM parameter name
    config.ssm_story_parameter = "/eidolon/story/config"  # type: ignore
    config.save(str(config_path))

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("story", result.get("outputs", {}))
        state.save(str(state_path))

    return validation.get("success", False)
