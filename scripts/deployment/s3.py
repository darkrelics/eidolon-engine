"""S3 bucket operations."""

import json
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


def set_bucket_policy_for_cloudfront(bucket_name: str, distribution_id: str, region: str) -> bool:
    """Set S3 bucket policy to allow CloudFront OAC read access.

    Merges the OAC statement into any existing bucket policy rather than
    replacing it, which avoids conflicts with policies set outside CloudFormation.

    Args:
        bucket_name: S3 bucket name
        distribution_id: CloudFront distribution ID
        region: AWS region

    Returns:
        bool: True if policy was set successfully
    """
    s3_client = boto3.client("s3", region_name=region)
    sts_client = boto3.client("sts", region_name=region)

    try:
        account_id = retry_on_transient_error(lambda: sts_client.get_caller_identity()).get("Account", "")
    except ClientError as err:
        print(f"  [ERROR] Failed to get account ID: {err}")
        return False

    sid = f"AllowCloudFrontServicePrincipal-{distribution_id}"
    oac_statement = {
        "Sid": sid,
        "Effect": "Allow",
        "Principal": {"Service": "cloudfront.amazonaws.com"},
        "Action": "s3:GetObject",
        "Resource": f"arn:aws:s3:::{bucket_name}/*",
        "Condition": {"StringEquals": {"AWS:SourceArn": f"arn:aws:cloudfront::{account_id}:distribution/{distribution_id}"}},
    }

    try:
        existing = s3_client.get_bucket_policy(Bucket=bucket_name)
        policy = json.loads(existing.get("Policy", "{}"))
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ["NoSuchBucketPolicy", "NoSuchBucket"]:
            policy = {"Version": "2012-10-17", "Statement": []}
        else:
            print(f"  [ERROR] Failed to read bucket policy: {err}")
            return False

    statements = policy.get("Statement", [])
    cleaned = []
    for stmt in statements:
        principal = stmt.get("Principal", {})
        if isinstance(principal, dict):
            if "CanonicalUser" in principal:
                continue
            aws_principal = principal.get("AWS", "")
            if isinstance(aws_principal, str) and not aws_principal.startswith("arn:"):
                # Bare IAM unique ID — stale reference to a deleted principal
                continue
            if isinstance(aws_principal, str) and "cloudfront" in aws_principal:
                continue
            service = principal.get("Service", "")
            if service == "cloudfront.amazonaws.com":
                continue
        cleaned.append(stmt)
    cleaned.append(oac_statement)
    policy["Statement"] = cleaned

    policy_json = json.dumps(policy, indent=2)
    try:
        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=policy_json)
        print(f"  [OK] Bucket policy updated for CloudFront OAC access on {bucket_name}")
        return True
    except ClientError as err:
        print(f"  [ERROR] Failed to set bucket policy: {err}")
        print(f"  [DEBUG] Policy submitted:\n{policy_json}")
        return False


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
