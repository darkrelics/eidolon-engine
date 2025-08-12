"""CloudWatch stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy, validate_policies


def deploy_cloudwatch_stack(params) -> dict:
    """Deploy the CloudWatch stack using CDK."""
    app_command = f"python3 app_cloudwatch.py --region {params.region}"
    return run_cdk_deploy("cloudwatch", params.region, app_command)


def validate_log_group(log_group_name: str, region: str) -> bool:
    """Validate that CloudWatch log group exists.
    
    Args:
        log_group_name: Name of the log group to validate
        region: AWS region
        
    Returns:
        True if log group exists, False otherwise
    """
    try:
        cloudwatch = boto3.client("logs", region_name=region)
        response = cloudwatch.describe_log_groups(
            logGroupNamePrefix=log_group_name,
            limit=1
        )
        
        for group in response.get("logGroups", []):
            if group.get("logGroupName") == log_group_name:
                print(f"  [OK] Log group: {log_group_name}")
                return True
        
        print(f"  [MISSING] Log group: {log_group_name}")
        return False
        
    except ClientError as err:
        print(f"  [ERROR] Could not validate log group: {err}")
        return False


def verify_cloudwatch_deployment(params) -> dict:
    """Verify the CloudWatch deployment completed successfully."""
    print("\nVerifying CloudWatch deployment...")
    
    # Validate log group
    log_group_valid = validate_log_group("/eidolon/server", params.region)
    
    # Validate IAM policy
    policy_validation = validate_policies(["eidolon-cloudwatch-policy"])
    
    return {
        "log_group": log_group_valid,
        "policies": policy_validation,
        "success": log_group_valid and all(policy_validation.values())
    }


def deploy_cloudwatch(params, config: Config, state: CDKState,
                     config_path: Path, state_path: Path) -> bool:
    """Deploy and verify CloudWatch stack."""
    print("\n" + "=" * 60)
    print("Phase 4: CloudWatch Stack")
    print("=" * 60)
    
    # Deploy stack
    result = deploy_cloudwatch_stack(params)
    
    if not result.get("success", False):
        print("\nCloudWatch deployment failed!")
        return False
    
    # Verify deployment
    validation = verify_cloudwatch_deployment(params)
    
    if not validation.get("success", False):
        print("\nWarning: CloudWatch deployment completed with issues")
        if not validation.get("log_group", False):
            print("  - Log group was not created")
        if not all(validation.get("policies", {}).values()):
            print("  - IAM policy was not created")
    
    # Update configuration with CloudWatch settings
    if validation.get("log_group", False):
        config.cloudwatch_log_group = "/eidolon/server"
        config.cloudwatch_metrics_namespace = "eidolon/metrics"
        config.save(str(config_path))
    
    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("cloudwatch", result.get("outputs", {}))
        state.save(str(state_path))
    
    return validation.get("success", False)