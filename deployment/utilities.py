"""Utility functions for deployment scripts."""

import subprocess
import traceback
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
        return identity.get("Account", "")
    except ClientError as err:
        print(f"Error: AWS API error while getting account ID - {err}")
        return ""
    except Exception as err:
        print(f"Error: Unexpected error getting AWS account ID - {err}")
        print("Stack trace:")
        print(traceback.format_exc())
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
    except ClientError as err:
        print(f"Error: AWS API error during credential verification - {err}")
        return False
    except Exception as err:
        print(f"Error: Unexpected error accessing AWS - {err}")
        print("Stack trace:")
        print(traceback.format_exc())
        return False


def verify_cdk_installed() -> bool:
    """Check if AWS CDK is installed."""
    try:
        result = subprocess.run(["cdk", "--version"], capture_output=True, text=True, check=False)
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
    validated_region = validate_region(region)
    if not validated_region:
        return False

    cfn = boto3.client("cloudformation", region_name=validated_region)

    try:
        # CDK bootstrap creates a stack named CDKToolkit
        response = cfn.describe_stacks(StackName="CDKToolkit")
        if response.get("Stacks"):
            print(f"CDK Bootstrap: Found in {validated_region}")
            return True
    except ClientError as err:
        if "does not exist" in str(err):
            print(f"Warning: CDK not bootstrapped in {validated_region}")
            print(f"Run: cdk bootstrap aws://{get_aws_account_id()}/{validated_region}")
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
            iam.get_policy(PolicyArn=f"arn:aws:iam::{account_id}:policy/{policy_name}")
            print(f"  [OK] IAM Policy: {policy_name}")
            results[policy_name] = True
        except ClientError:
            print(f"  [MISSING] IAM Policy: {policy_name}")
            results[policy_name] = False

    return results


def validate_s3_bucket(bucket_name: str, region: str) -> bool:
    """Validate that S3 bucket exists and is accessible.

    Args:
        bucket_name: Name of the S3 bucket to validate
        region: AWS region

    Returns:
        True if bucket exists and is accessible, False otherwise
    """
    try:
        s3 = boto3.client("s3", region_name=region)
        s3.head_bucket(Bucket=bucket_name)
        print(f"  [OK] S3 bucket: {bucket_name}")
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "404":
            print(f"  [MISSING] S3 bucket: {bucket_name}")
        elif error_code == "403":
            print(f"  [FORBIDDEN] S3 bucket: {bucket_name} - insufficient permissions")
        else:
            print(f"  [ERROR] S3 bucket: {bucket_name} - {error_code}")
        return False


def validate_s3_artifacts(bucket_name: str, region: str, required_artifacts: list) -> dict:
    """Validate that required Lambda artifacts exist in S3 bucket.

    Args:
        bucket_name: Name of the S3 bucket
        region: AWS region
        required_artifacts: List of artifact keys to check (e.g., ['lambda/api-character-add.zip'])

    Returns:
        Dict with artifact keys as keys and bool status as values
    """
    results = {}

    try:
        s3 = boto3.client("s3", region_name=region)

        for artifact_key in required_artifacts:
            try:
                s3.head_object(Bucket=bucket_name, Key=artifact_key)
                results[artifact_key] = True
            except ClientError as err:
                error_code = err.response.get("Error", {}).get("Code", "")
                if error_code == "404":
                    results[artifact_key] = False
                else:
                    print(f"  [ERROR] Cannot check artifact {artifact_key}: {error_code}")
                    results[artifact_key] = False

    except ClientError as err:
        print(f"  [ERROR] Cannot access S3 bucket {bucket_name}: {err}")
        return {key: False for key in required_artifacts}

    return results


def validate_lambda_artifacts(bucket_name: str, region: str, deployment_mode: str) -> tuple:
    """Validate that Lambda function artifacts exist in S3.

    Args:
        bucket_name: S3 bucket containing Lambda artifacts
        region: AWS region
        deployment_mode: Deployment mode (mud/incremental/hybrid)

    Returns:
        Tuple of (all_present: bool, missing: list, present: list)
    """
    # Core Lambda artifacts needed for all modes
    core_artifacts = [
        "lambda/cognito-player-new.zip",
        "lambda-layer/lambda-layer.zip",
    ]

    # Character/Item Lambda artifacts
    character_artifacts = [
        "lambda/api-archetype-list.zip",
        "lambda/api-character-add.zip",
        "lambda/api-character-get.zip",
        "lambda/api-character-delete.zip",
        "lambda/api-character-list.zip",
        "lambda/api-item-brief.zip",
        "lambda/api-item-prototype.zip",
        "lambda/api-item-consume.zip",
        "lambda/api-item-discard.zip",
        "lambda/api-item-consolidate.zip",
        "lambda/api-item-split.zip",
        "lambda/api-store-list.zip",
        "lambda/api-store-purchase.zip",
    ]

    # Story Lambda artifacts (incremental and hybrid modes only)
    story_artifacts = [
        "lambda/api-story-start.zip",
        "lambda/api-story-abandon.zip",
        "lambda/api-story-history.zip",
        "lambda/api-segment-decision.zip",
        "lambda/api-segment-status.zip",
        "lambda/api-segment-history.zip",
        "lambda/ops-segment-poller.zip",
        "lambda/ops-segment-process.zip",
        "lambda/ops-story-advance.zip",
    ]

    # Build required artifacts list based on deployment mode
    required_artifacts = core_artifacts + character_artifacts
    if deployment_mode in ("incremental", "hybrid"):
        required_artifacts.extend(story_artifacts)

    print(f"\n  Validating {len(required_artifacts)} Lambda artifacts in S3...")

    results = validate_s3_artifacts(bucket_name, region, required_artifacts)

    present = [k for k, v in results.items() if v]
    missing = [k for k, v in results.items() if not v]

    if missing:
        print(f"  [WARNING] {len(missing)} artifacts missing:")
        for artifact in missing[:5]:  # Show first 5
            print(f"    - {artifact}")
        if len(missing) > 5:
            print(f"    ... and {len(missing) - 5} more")
    else:
        print(f"  [OK] All {len(present)} Lambda artifacts present")

    return len(missing) == 0, missing, present


def run_cdk_deploy(stack_name: str, region: str, app_command: str, context_args=None) -> dict:
    """Run CDK deploy for a specific stack with context arguments.

    Args:
        stack_name: Name of the CDK stack to deploy
        region: AWS region
        app_command: Full app command with parameters
        context_args: List of context arguments to pass to CDK

    Returns:
        Dict with success status and outputs
    """
    print(f"\nDeploying {stack_name} stack in {region}...")

    context_args = context_args or []

    # Build CDK command with context arguments
    cdk_command = ["cdk", "deploy", stack_name, "--require-approval", "never", "--region", region, "--app", app_command]

    # Add context arguments
    cdk_command.extend(context_args)

    # Run CDK deploy
    try:
        result = subprocess.run(cdk_command, capture_output=True, text=True, cwd=Path(__file__).parent, check=False)

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
