"""Utility functions for deployment scripts."""

import json
import subprocess
from functools import cache
from pathlib import Path

import boto3
from botocore.exceptions import ClientError


@cache
def get_aws_account_id() -> str:
    """Get AWS account ID (cached).
    
    Returns:
        AWS account ID string if successful, empty string if failed
    """
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        return identity.get('Account', '')
    except Exception as err:
        print(f"Error: Unable to get AWS account ID - {err}")
        return ""


def verify_aws_credentials() -> bool:
    """Verify AWS credentials are configured."""
    account_id = get_aws_account_id()
    if not account_id:
        print("Error: Unable to access AWS")
        return False
    
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        print(f"AWS Account: {account_id}")
        print(f"AWS User/Role: {identity.get('Arn', '')}")
        return True
    except Exception as err:
        print(f"Error: Unable to access AWS - {err}")
        return False


def verify_cdk_installed() -> bool:
    """Check if AWS CDK is installed."""
    try:
        result = subprocess.run(
            ["cdk", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print(f"CDK Version: {result.stdout.strip()}")
            return True
        else:
            print("Error: AWS CDK is not installed")
            print("Install it with: npm install -g aws-cdk")
            return False
    except FileNotFoundError:
        print("Error: AWS CDK is not installed")
        print("Install it with: npm install -g aws-cdk")
        return False


def verify_cdk_bootstrap(region: str) -> bool:
    """Check if CDK is bootstrapped in the target region."""
    # Validate region before attempting to check bootstrap
    if not validate_region(region):
        return False
    
    cfn = boto3.client("cloudformation", region_name=region)
    
    try:
        # CDK bootstrap creates a stack named CDKToolkit
        response = cfn.describe_stacks(StackName="CDKToolkit")
        if response.get("Stacks"):
            print(f"CDK Bootstrap: Found in {region}")
            return True
    except ClientError as err:
        if "does not exist" in str(err):
            print(f"Warning: CDK not bootstrapped in {region}")
            print(f"Run: cdk bootstrap aws://{get_aws_account_id()}/{region}")
            return False
        else:
            # Other errors - might be permissions
            print(f"Warning: Could not verify CDK bootstrap: {err}")
            return True  # Continue anyway
    
    return False


def validate_region(region: str) -> str:
    """Validate and sanitize AWS region.
    
    Args:
        region: AWS region to validate
        
    Returns:
        Sanitized region string if valid, empty string if invalid
    """
    # Sanitize input - strip whitespace and convert to lowercase
    sanitized_region = region.strip().lower()
    
    # Define supported regions
    supported_regions = ["us-east-1", "us-east-2", "us-west-2"]
    
    if sanitized_region in supported_regions:
        return sanitized_region
    
    # Invalid region - print error and return empty string
    print(f"\nError: Region '{region}' is not supported")
    print(f"Supported regions: {', '.join(supported_regions)}")
    print("To use a different region, please modify the validate_region function")
    
    return ""


def verify_prerequisites() -> bool:
    """Verify all prerequisites for deployment."""
    print("\nChecking prerequisites...")
    
    if not verify_aws_credentials():
        return False
    
    if not verify_cdk_installed():
        return False
    
    return True


def extract_stack_outputs(stack_name: str, region: str) -> dict:
    """Extract outputs from deployed CloudFormation stack."""
    cfn = boto3.client("cloudformation", region_name=region)

    try:
        response = cfn.describe_stacks(StackName=stack_name)
        stacks = response.get("Stacks", [])
        stack = stacks[0] if stacks else {}

        outputs = {}
        for output in stack.get("Outputs", []):
            output_key = output.get("OutputKey", "")
            output_value = output.get("OutputValue", "")
            if output_key:
                outputs[output_key] = output_value

        return outputs
    except ClientError as err:
        print(f"Warning: Could not get stack outputs - {err}")
        return {}


def validate_policies(policy_names: list[str]) -> dict:
    """Validate that IAM policies were created.
    
    Args:
        policy_names: List of policy names to check
        
    Returns:
        Dict with policy names as keys and bool status as values
    """
    iam = boto3.client("iam")
    account_id = get_aws_account_id()
    
    if not account_id:
        print("[ERROR] Cannot validate policies without AWS account ID")
        return {name: False for name in policy_names}
    
    results = {}
    for policy_name in policy_names:
        try:
            response = iam.get_policy(
                PolicyArn=f"arn:aws:iam::{account_id}:policy/{policy_name}"
            )
            print(f"  [OK] IAM Policy: {policy_name}")
            results[policy_name] = True
        except ClientError:
            print(f"  [MISSING] IAM Policy: {policy_name}")
            results[policy_name] = False
    
    return results


def run_cdk_deploy(stack_name: str, region: str, app_command: str) -> dict:
    """Run CDK deploy for a specific stack.
    
    Args:
        stack_name: Name of the CDK stack to deploy
        region: AWS region
        app_command: Full app command with parameters
        
    Returns:
        Dict with success status and outputs
    """
    print(f"\nDeploying {stack_name} stack in {region}...")

    # Run CDK deploy
    try:
        result = subprocess.run(
            [
                "cdk", "deploy", stack_name,
                "--require-approval", "never",
                "--region", region,
                "--app", app_command
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            check=False
        )

        if result.returncode != 0:
            print(f"\nCDK deployment failed with exit code {result.returncode}")
            if result.stdout:
                print("\nOutput:")
                print(result.stdout)
            if result.stderr:
                print("\nErrors:")
                print(result.stderr)
            return {"success": False}

        # Log CDK output for successful deployments too
        if result.stdout:
            print("\nCDK Output:")
            print(result.stdout)

        print("\nStack deployed successfully")

        # Extract outputs from CDK
        outputs = extract_stack_outputs(stack_name, region)
        return {"success": True, "outputs": outputs}

    except Exception as err:
        print(f"\nDeployment error: {err}")
        return {"success": False}