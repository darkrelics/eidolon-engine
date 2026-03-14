"""API Gateway operations."""

import boto3
from botocore.exceptions import ClientError
from deployment.aws_utils import retry_on_transient_error


def force_api_gateway_deployment(api_id: str, stage_name: str, region: str) -> bool:
    """Force a new API Gateway deployment to the specified stage.

    Args:
        api_id: API Gateway REST API ID
        stage_name: Stage name to deploy to
        region: AWS region

    Returns:
        bool: True if deployment succeeded
    """
    apigateway = boto3.client("apigateway", region_name=region)
    try:
        retry_on_transient_error(
            lambda: apigateway.create_deployment(
                restApiId=api_id,
                stageName=stage_name,
                description="Forced deployment from eidolon_deployment.py",
            )
        )
        return True
    except ClientError as err:
        print(f"    Error creating API Gateway deployment: {err}")
        return False
