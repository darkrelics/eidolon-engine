"""S3 utilities for Lambda functions and deployment scripts.

Provides centralized S3 bucket management and common operations.
"""

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import get_logger

logger = get_logger(__name__)


def upload_file(bucket_name: str, file_path: str, object_name: str = None) -> bool:
    """Upload a file to an S3 bucket.

    Args:
        bucket_name: Bucket to upload to
        file_path: Path to the file to upload
        object_name: S3 object name. If not specified, file_path is used

    Returns:
        True if file was uploaded, else False
    """
    if object_name is None:
        object_name = file_path

    s3_client = boto3.client("s3")
    try:
        s3_client.upload_file(file_path, bucket_name, object_name)
        logger.info(f"Successfully uploaded {file_path} to s3://{bucket_name}/{object_name}")
        return True
    except ClientError as e:
        logger.error(f"Failed to upload {file_path} to s3://{bucket_name}/{object_name}", error=e)
        return False


def download_file(bucket_name: str, object_name: str, file_path: str) -> bool:
    """Download a file from an S3 bucket.

    Args:
        bucket_name: Bucket to download from
        object_name: S3 object name
        file_path: Path to save the downloaded file

    Returns:
        True if file was downloaded, else False
    """
    s3_client = boto3.client("s3")
    try:
        s3_client.download_file(bucket_name, object_name, file_path)
        logger.info(f"Successfully downloaded s3://{bucket_name}/{object_name} to {file_path}")
        return True
    except ClientError as e:
        logger.error(f"Failed to download s3://{bucket_name}/{object_name} to {file_path}", error=e)
        return False


def list_files(bucket_name: str, prefix: str = "") -> list:
    """List files in an S3 bucket.

    Args:
        bucket_name: Bucket to list files from
        prefix: Prefix to filter by

    Returns:
        List of file keys
    """
    s3_client = boto3.client("s3")
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        return [item["Key"] for item in response.get("Contents", [])]
    except ClientError as e:
        logger.error(f"Failed to list files in s3://{bucket_name}/{prefix}", error=e)
        return []
