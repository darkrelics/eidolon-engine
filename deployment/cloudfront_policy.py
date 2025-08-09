"""Shared helper for ensuring S3 bucket policy grants CloudFront OAI access.

This module centralizes the logic to:
- Resolve the OAI used by a CloudFront distribution.
- Ensure the target S3 bucket policy contains an Allow statement for that OAI to GetObject on bucket/*.

It is safe to call repeatedly; it will only update the policy when required.
"""

from __future__ import annotations

import json
from typing import Optional

import boto3
from botocore.exceptions import ClientError


def _get_distribution_config(cf_client, distribution_id: str) -> tuple[dict, str]:
    resp = cf_client.get_distribution(Id=distribution_id)
    return resp["Distribution"]["DistributionConfig"], resp["ETag"]


def _extract_oai_id_from_distribution_config(dist_config: dict) -> Optional[str]:
    origins = dist_config.get("Origins", {}).get("Items", [])
    if not origins:
        return None
    # Use first origin with S3OriginConfig
    for origin in origins:
        s3cfg = origin.get("S3OriginConfig", {})
        oai_path = s3cfg.get("OriginAccessIdentity", "")
        if oai_path:
            return oai_path.split("/")[-1]
    return None


def ensure_bucket_policy_for_cloudfront(
    *,
    bucket_name: str,
    distribution_id: str,
    session: Optional[boto3.session.Session] = None,
    region: Optional[str] = None,
) -> bool:
    """Ensure the S3 bucket policy allows the CloudFront distribution's OAI to read objects.

    Args:
        bucket_name: Name of the S3 bucket to update.
        distribution_id: CloudFront distribution ID.
        session: Optional boto3 session; when omitted, a default session is used.
        region: Optional S3 region override; defaults to session / environment region.

    Returns:
        True if policy is correctly configured (updated or already correct). False if a non-fatal issue occurred.
    """
    try:
        sess = session or boto3.session.Session()
        cf_client = sess.client("cloudfront", region_name="us-east-1")
        s3_client = sess.client("s3", region_name=region)

        # Get distribution config and try to find existing OAI id
        dist_config, _etag = _get_distribution_config(cf_client, distribution_id)
        oai_id = _extract_oai_id_from_distribution_config(dist_config)
        if not oai_id:
            # No OAI on the distribution; cannot safely author a policy
            print("    Warning: Distribution has no OAI; skipping bucket policy update")
            return False

        oai_arn = f"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity {oai_id}"

        # Fetch current bucket policy (or initialize)
        try:
            policy_response = s3_client.get_bucket_policy(Bucket=bucket_name)
            current_policy = json.loads(policy_response["Policy"])  # type: ignore[arg-type]
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchBucketPolicy":
                current_policy = {"Version": "2012-10-17", "Statement": []}
            else:
                raise

        # Detect if correct statement already exists
        for stmt in current_policy.get("Statement", []):
            if (
                stmt.get("Effect") == "Allow"
                and stmt.get("Action") == "s3:GetObject"
                and stmt.get("Principal", {}).get("AWS") == oai_arn
                and stmt.get("Resource") == f"arn:aws:s3:::{bucket_name}/*"
            ):
                # Already configured
                print("    Bucket policy already allows CloudFront OAI access")
                return True

        # Remove any prior CloudFront-related statements to avoid duplicates
        filtered = []
        for stmt in current_policy.get("Statement", []):
            principal = stmt.get("Principal", {})
            principal_str = json.dumps(principal)
            if "cloudfront:user/CloudFront" in principal_str or stmt.get("Sid", "").startswith("AllowCloudFront"):
                continue
            filtered.append(stmt)

        new_statement = {
            "Sid": "AllowCloudFrontOAI",
            "Effect": "Allow",
            "Principal": {"AWS": oai_arn},
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket_name}/*",
        }
        current_policy["Statement"] = filtered + [new_statement]

        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(current_policy))
        print(f"    Updated bucket policy for OAI: {oai_id}")
        return True

    except ClientError as err:
        code = err.response.get("Error", {}).get("Code", "")
        if code == "NoSuchBucket":
            print(f"    Bucket {bucket_name} not found")
            return False
        print(f"    AWS error updating bucket policy: {err}")
        return False
    except Exception as e:
        print(f"    Error ensuring bucket policy: {e}")
        return False
