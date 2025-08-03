"""
S3 utilities for Lambda functions and deployment scripts.

Provides centralized S3 bucket management and common operations.
"""

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import logger




def upload_file(bucket_name: str, file_path: str, object_name=None):
    """
    Upload a file to an S3 bucket.

    Args:
        bucket_name: Bucket to upload to
        file_path: Path to the file to upload
        object_name: S3 object name. If not specified, file_path is used

    Raises:
        ValueError: If bucket_name or file_path is empty
        RuntimeError: If S3 upload fails
    """
    if not bucket_name:
        raise ValueError("Bucket name cannot be empty")
    if not file_path:
        raise ValueError("File path cannot be empty")

    if object_name is None:
        object_name = file_path

    s3_client = boto3.client("s3")
    try:
        s3_client.upload_file(file_path, bucket_name, object_name)
    except ClientError as err:
        logger.error(
            "Failed to upload file to S3",
            extra={"file_path": file_path, "bucket_name": bucket_name, "object_name": object_name, "error": str(err)},
        )
        raise RuntimeError(f"Failed to upload file to S3: {str(err)}")

    logger.info(
        "Successfully uploaded file to S3", extra={"file_path": file_path, "bucket_name": bucket_name, "object_name": object_name}
    )


def download_file(bucket_name: str, object_name: str, file_path: str):
    """
    Download a file from an S3 bucket.

    Args:
        bucket_name: Bucket to download from
        object_name: S3 object name
        file_path: Path to save the downloaded file

    Raises:
        ValueError: If bucket_name, object_name, or file_path is empty
        RuntimeError: If S3 download fails
    """
    if not bucket_name:
        raise ValueError("Bucket name cannot be empty")
    if not object_name:
        raise ValueError("Object name cannot be empty")
    if not file_path:
        raise ValueError("File path cannot be empty")

    s3_client = boto3.client("s3")
    try:
        s3_client.download_file(bucket_name, object_name, file_path)
    except ClientError as err:
        logger.error(
            "Failed to download file from S3",
            extra={"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path, "error": str(err)},
        )
        raise RuntimeError(f"Failed to download file from S3: {str(err)}")

    logger.info(
        "Successfully downloaded file from S3",
        extra={"bucket_name": bucket_name, "object_name": object_name, "file_path": file_path},
    )


def list_files(bucket_name: str, prefix: str = "") -> list:
    """
    List files in an S3 bucket.

    Args:
        bucket_name: Bucket to list files from
        prefix: Prefix to filter by

    Returns:
        list: List of file keys. Empty list if no files found.

    Raises:
        ValueError: If bucket_name is empty
        RuntimeError: If S3 list operation fails
    """
    if not bucket_name:
        raise ValueError("Bucket name cannot be empty")

    s3_client = boto3.client("s3")
    try:
        response = s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    except ClientError as err:
        logger.error("Failed to list files in S3 bucket", extra={"bucket_name": bucket_name, "prefix": prefix, "error": str(err)})
        raise RuntimeError(f"Failed to list files in S3 bucket: {str(err)}")

    files = [item.get("Key") for item in response.get("Contents", [])]

    logger.info("Listed files in S3 bucket", extra={"bucket_name": bucket_name, "prefix": prefix, "file_count": len(files)})

    return files


def delete_file(bucket_name: str, s3_key: str):
    """
    Delete a file from an S3 bucket.

    Args:
        bucket_name: Bucket to delete from
        s3_key: S3 object key to delete

    Raises:
        ValueError: If bucket_name or s3_key is empty
        RuntimeError: If S3 delete operation fails
    """
    if not bucket_name:
        raise ValueError("Bucket name cannot be empty")
    if not s3_key:
        raise ValueError("S3 key cannot be empty")

    s3_client = boto3.client("s3")
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=s3_key)
    except ClientError as err:
        logger.error("Failed to delete file from S3", extra={"bucket_name": bucket_name, "s3_key": s3_key, "error": str(err)})
        raise RuntimeError(f"Failed to delete file from S3: {str(err)}")

    logger.info("Successfully deleted file from S3", extra={"bucket_name": bucket_name, "s3_key": s3_key})


def validate_s3_bucket(bucket_name: str):
    """
    Validate that an S3 bucket exists and is accessible.

    Args:
        bucket_name: Name of the bucket to validate

    Raises:
        ValueError: If bucket_name is empty or bucket does not exist
        RuntimeError: If access is denied or other S3 error occurs
    """
    if not bucket_name:
        raise ValueError("Bucket name cannot be empty")

    s3_client = boto3.client("s3")
    try:
        s3_client.get_bucket_location(Bucket=bucket_name)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")

        if error_code == "NoSuchBucket":
            logger.error("S3 bucket does not exist", extra={"bucket_name": bucket_name})
            raise ValueError(f"S3 bucket does not exist: {bucket_name}")
        elif error_code == "AccessDenied":
            logger.error("Access denied to S3 bucket", extra={"bucket_name": bucket_name})
            raise RuntimeError(f"Access denied to S3 bucket: {bucket_name}")
        else:
            logger.error(
                "Failed to validate S3 bucket", extra={"bucket_name": bucket_name, "error_code": error_code, "error": str(err)}
            )
            raise RuntimeError(f"Failed to validate S3 bucket: {str(err)}")

    logger.info("Successfully validated S3 bucket", extra={"bucket_name": bucket_name})
