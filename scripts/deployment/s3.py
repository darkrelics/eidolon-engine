"""S3 bucket operations."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from deployment.aws_utils import retry_on_transient_error


def s3_bucket_exists(bucket_name: str, region: str) -> bool:
    """Check if S3 bucket exists.

    Args:
        bucket_name: S3 bucket name
        region: AWS region

    Returns:
        bool: True if bucket exists
    """
    s3_client = boto3.client("s3", region_name=region)
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ["404", "NoSuchBucket"]:
            return False
        raise err from err


def upload_scripts_to_s3(bucket_name: str, region: str, base_dir: str) -> bool:
    """Upload Lua scripts from scripts_lua directory to S3 bucket under scripts/.

    Args:
        bucket_name: Name of the S3 bucket
        region: AWS region
        base_dir: Project base directory

    Returns:
        bool: True if upload successful, False otherwise
    """
    scripts_path = Path(base_dir) / "scripts_lua"

    if not scripts_path.exists():
        print(f"  [WARNING] Scripts directory not found: {scripts_path}")
        return True

    s3_client = boto3.client("s3", region_name=region)
    uploaded = 0
    failed = 0

    print("Uploading Lua scripts to S3...")

    for script_file in scripts_path.glob("**/*"):
        if script_file.is_file():
            relative_path = script_file.relative_to(scripts_path)
            s3_key = f"scripts/{relative_path}"

            try:
                retry_on_transient_error(
                    lambda f=script_file, k=s3_key: s3_client.put_object(
                        Bucket=bucket_name, Key=k, Body=f.read_bytes()
                    )
                )
                print(f"  [UPLOADED] {s3_key}")
                uploaded += 1
            except ClientError as err:
                print(f"  [FAILED] {s3_key}: {err}")
                failed += 1

    print(f"Scripts upload summary: {uploaded} uploaded, {failed} failed")
    return failed == 0
