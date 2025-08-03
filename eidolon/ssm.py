"""
SSM Parameter Store utilities for Lambda functions.

Provides functions for reading and updating SSM parameters.
"""

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import logger



# Initialize SSM client
ssm_client = boto3.client("ssm")


def get_parameter(parameter_name: str) -> str:
    """
    Get a parameter value from SSM Parameter Store.

    Args:
        parameter_name: Name of the parameter to retrieve

    Returns:
        Parameter value as string

    Raises:
        ValueError: If parameter not found
        RuntimeError: If SSM operation fails
    """
    try:
        response = ssm_client.get_parameter(Name=parameter_name)
        return response.get("Parameter", {}).get("Value")
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ParameterNotFound":
            logger.error("Parameter not found", extra={"parameter_name": parameter_name})
            raise ValueError(f"Parameter {parameter_name} not found")

        logger.error(
            "Failed to get parameter",
            extra={
                "parameter_name": parameter_name,
                "error": str(err),
                "error_code": error_code,
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get parameter: {str(err)}")


def put_parameter(parameter_name: str, value: str) -> None:
    """
    Update a parameter value in SSM Parameter Store.

    Args:
        parameter_name: Name of the parameter to update
        value: New value for the parameter

    Raises:
        RuntimeError: If SSM operation fails
    """
    try:
        ssm_client.put_parameter(
            Name=parameter_name,
            Value=value,
            Type="String",
            Overwrite=True,
        )
        logger.info(
            "Parameter updated successfully",
            extra={"parameter_name": parameter_name, "value": value},
        )
    except ClientError as err:
        logger.error(
            "Failed to update parameter",
            extra={
                "parameter_name": parameter_name,
                "value": value,
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update parameter: {str(err)}")
