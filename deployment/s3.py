"""S3 stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from stacks.stack_utilities import check_s3_bucket_exists
from utilities import run_cdk_deploy, validate_s3_bucket, validate_policies


def deploy_s3_stack(params) -> dict:
    """Deploy the S3 stack using CDK."""
    # Check if S3 bucket already exists
    bucket_exists = check_s3_bucket_exists(params.scripts_bucket, params.region)

    # Pass parameters through context
    context_args = [
        "-c",
        f"region={params.region}",
        "-c",
        f"scripts_bucket={params.scripts_bucket}",
        "-c",
        f"bucket_exists={'true' if bucket_exists else 'false'}",
    ]

    app_command = "python3 app_s3.py"
    return run_cdk_deploy("s3", params.region, app_command, context_args)


def verify_s3_deployment(params) -> dict:
    """Verify the S3 deployment completed successfully."""
    print("\nVerifying S3 deployment...")

    # Validate S3 bucket
    bucket_valid = validate_s3_bucket(params.scripts_bucket, params.region)

    # Validate IAM policy
    policy_validation = validate_policies(["eidolon-scripts-s3-policy"])

    return {"bucket": bucket_valid, "policies": policy_validation, "success": bucket_valid and all(policy_validation.values())}


def upload_scripts(bucket_name: str, region: str) -> bool:
    """Upload Lua scripts from scripts_lua directory to S3 bucket under scripts/.

    Args:
        bucket_name: Name of the S3 bucket
        region: AWS region

    Returns:
        True if upload successful, False otherwise
    """
    scripts_path = Path(__file__).parent.parent / "scripts_lua"

    if not scripts_path.exists():
        print(f"  [WARNING] Scripts directory not found: {scripts_path}")
        return True  # Not an error if directory doesn't exist

    s3 = boto3.client("s3", region_name=region)
    uploaded = 0
    failed = 0

    print("\nUploading Lua scripts to S3...")

    for script_file in scripts_path.glob("**/*"):
        if script_file.is_file():
            # Get relative path for S3 key, prefix with 'scripts/'
            relative_path = script_file.relative_to(scripts_path)
            s3_key = f"scripts/{relative_path}"

            try:
                with open(script_file, "rb") as f:
                    s3.put_object(Bucket=bucket_name, Key=s3_key, Body=f)
                print(f"  [UPLOADED] {s3_key}")
                uploaded += 1
            except ClientError as err:
                print(f"  [FAILED] {s3_key}: {err}")
                failed += 1

    print(f"\nScripts upload summary: {uploaded} uploaded, {failed} failed")
    return failed == 0


def deploy_s3(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify S3 stack."""
    phase = get_stack_phase_number("s3", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: S3 Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_s3_stack(params)

    if not result.get("success", False):
        print("\nS3 deployment failed!")
        return False

    # Verify deployment
    validation = verify_s3_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: S3 deployment completed with issues")
        if not validation.get("bucket", False):
            print("  - S3 bucket was not created or is not accessible")
        if not all(validation.get("policies", {}).values()):
            print("  - IAM policy was not created")

    # Upload scripts to bucket if validation passed
    if validation.get("bucket", False):
        upload_success = upload_scripts(params.scripts_bucket, params.region)
        if not upload_success:
            print("\nWarning: Some scripts failed to upload")

    # Update configuration with scripts bucket
    if validation.get("bucket", False):
        config.s3_scripts_bucket = params.scripts_bucket
        config.save(str(config_path))

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("s3", result.get("outputs", {}))

        # No infrastructure resources needed by other stacks from S3

        state.save(str(state_path))

    return validation.get("success", False)
