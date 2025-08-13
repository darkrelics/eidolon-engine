"""Story stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy, validate_policies


def get_lambda_arns(region: str) -> dict:
    """Get Lambda function ARNs for story processing.
    
    Args:
        region: AWS region
        
    Returns:
        Dict with Lambda ARNs
    """
    arns = {
        "lambda_role_arn": "",
        "poller_arn": "",
        "processor_arn": "",
        "advance_arn": ""
    }
    
    try:
        # Get Lambda role ARN from IAM
        iam_client = boto3.client("iam", region_name=region)
        try:
            response = iam_client.get_role(RoleName="eidolon-lambda-execution-role")
            arns["lambda_role_arn"] = response["Role"]["Arn"]
        except ClientError:
            print("Warning: Lambda execution role not found")
        
        # Get Lambda function ARNs
        lambda_client = boto3.client("lambda", region_name=region)
        
        functions = [
            ("ops-segment-poller", "poller_arn"),
            ("ops-segment-process", "processor_arn"),
            ("ops-story-advance", "advance_arn")
        ]
        
        for function_name, arn_key in functions:
            try:
                response = lambda_client.get_function(FunctionName=function_name)
                arns[arn_key] = response["Configuration"]["FunctionArn"]
            except ClientError:
                print(f"Warning: Lambda function {function_name} not found")
    
    except Exception as err:
        print(f"Error getting Lambda ARNs: {err}")
    
    return arns


def deploy_story_stack(params) -> dict:
    """Deploy the Story stack using CDK."""
    # Get Lambda ARNs
    arns = get_lambda_arns(params.region)
    
    # Pass all parameters through context
    context_args = [
        f"-c region={params.region}",
        f"-c lambda_role_arn={arns['lambda_role_arn']}",
        f"-c poller_lambda_arn={arns['poller_arn']}",
        f"-c processor_lambda_arn={arns['processor_arn']}",
        f"-c advance_lambda_arn={arns['advance_arn']}"
    ]
    
    app_command = f"python3 app_story.py {' '.join(context_args)}"
    return run_cdk_deploy("story", params.region, app_command)


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
        "EVENTBRIDGE_RULE_NAME": "eidolon-story-poller"
    }
    
    function_updates = [
        # API functions - all need all 4 environment variables
        ("api-story-start", story_env_vars),
        ("api-story-abandon", story_env_vars),
        ("api-segment-decision", story_env_vars),
        ("api-segment-history", story_env_vars),
        ("api-segment-outcome", story_env_vars),
        ("api-segment-rest", story_env_vars),
        ("api-segment-status", story_env_vars),
        # Operations functions
        ("ops-segment-poller", story_env_vars),
        ("ops-segment-process", story_env_vars),
        ("ops-story-advance", story_env_vars)
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
            lambda_client.update_function_configuration(
                FunctionName=function_name,
                Environment={"Variables": current_env}
            )
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
        "success": all([ssm_valid, processing_valid, advancement_valid, eventbridge_valid, policy_valid])
    }


def deploy_story(params, config: Config, state: CDKState,
                config_path: Path, state_path: Path) -> bool:
    """Deploy and verify Story stack."""
    print("\n" + "=" * 60)
    print("Phase 7: Story Stack")
    print("=" * 60)
    
    # Deploy stack
    result = deploy_story_stack(params)
    
    if not result.get("success", False):
        print("\nStory deployment failed!")
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
        update_lambda_environments(
            params,
            validation.get("processing_queue_url", ""),
            validation.get("advancement_queue_url", "")
        )
    
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