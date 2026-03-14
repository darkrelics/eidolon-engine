"""Lambda function and layer operations."""

from botocore.exceptions import ClientError
from deployment.aws_utils import retry_on_transient_error


def update_lambda_function_code(lambda_client, function_name: str, s3_bucket: str, s3_key: str) -> bool:
    """Force update Lambda function code from S3.

    Args:
        lambda_client: boto3 Lambda client
        function_name: Name of the Lambda function
        s3_bucket: S3 bucket containing the code
        s3_key: S3 key of the zip file

    Returns:
        bool: True if update succeeded
    """
    try:
        retry_on_transient_error(
            lambda: lambda_client.update_function_code(
                FunctionName=function_name,
                S3Bucket=s3_bucket,
                S3Key=s3_key,
            )
        )
        return True
    except ClientError as err:
        print(f"    Error updating {function_name}: {err}")
        return False


def layer_exists(lambda_client, layer_name: str) -> bool:
    """Check if Lambda layer exists with at least one version.

    Args:
        lambda_client: boto3 Lambda client
        layer_name: Name of the Lambda layer

    Returns:
        bool: True if layer exists with at least one version
    """
    try:
        response = lambda_client.list_layer_versions(LayerName=layer_name)
        layer_versions = response.get("LayerVersions", [])
        return len(layer_versions) > 0
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            return False
        raise err from err


def get_latest_layer_version_arn(lambda_client, layer_name: str) -> str:
    """Get the latest version ARN for a Lambda layer.

    Args:
        lambda_client: boto3 Lambda client
        layer_name: Name of the Lambda layer

    Returns:
        str: Layer version ARN or empty string if not found
    """
    try:
        response = lambda_client.list_layer_versions(LayerName=layer_name, MaxItems=1)
        layer_versions = response.get("LayerVersions", [])
        if layer_versions:
            return layer_versions[0].get("LayerVersionArn", "")
        return ""
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            return ""
        raise err from err


def publish_layer_version(lambda_client, layer_name: str, s3_bucket: str, s3_key: str, description: str = "") -> str:
    """Publish a new Lambda layer version from S3.

    Args:
        lambda_client: boto3 Lambda client
        layer_name: Name of the Lambda layer
        s3_bucket: S3 bucket containing the layer zip
        s3_key: S3 key of the layer zip
        description: Layer description

    Returns:
        str: Layer version ARN or empty string on failure
    """
    try:
        response = retry_on_transient_error(
            lambda: lambda_client.publish_layer_version(
                LayerName=layer_name,
                Content={"S3Bucket": s3_bucket, "S3Key": s3_key},
                CompatibleRuntimes=["python3.12"],
                CompatibleArchitectures=["x86_64"],
                Description=description,
            )
        )
        return response.get("LayerVersionArn", "")
    except ClientError as err:
        print(f"    Error publishing {layer_name}: {err}")
        return ""


def cleanup_old_layer_versions(lambda_client, layer_name: str):
    """Delete old versions of a Lambda layer, keeping only the latest.

    Args:
        lambda_client: boto3 Lambda client
        layer_name: Name of the Lambda layer
    """
    print(f"Cleaning up old {layer_name} versions...")
    try:
        response = lambda_client.list_layer_versions(LayerName=layer_name)
        versions = response.get("LayerVersions", [])
        old_versions = versions[1:]
        if old_versions:
            for version_info in old_versions:
                version_number = version_info.get("Version")
                print(f"  Deleting {layer_name} version {version_number}")
                try:
                    lambda_client.delete_layer_version(LayerName=layer_name, VersionNumber=version_number)
                except ClientError as err:
                    print(f"  Warning: Could not delete version {version_number}: {err}")
            print(f"  Cleanup complete - deleted {len(old_versions)} old version(s)")
        else:
            print("  No old versions to clean up")
    except ClientError as err:
        print(f"  Warning: Could not clean up old versions: {err}")
