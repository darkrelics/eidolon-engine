"""
SSM Parameter Store utilities for Lambda functions.

Provides functions for reading and updating SSM parameters.
"""

import boto3
from botocore.exceptions import ClientError

from eidolon.logger import logger

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
            logger.error(f"Parameter not found for {parameter_name}")
            raise ValueError(f"Parameter {parameter_name} not found") from err

        logger.error(f"Failed to get parameter for {parameter_name} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get parameter: {err}") from err


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
        logger.info(f"Parameter updated successfully for {parameter_name}")
    except ClientError as err:
        logger.error(f"Failed to update parameter for {parameter_name} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update parameter: {err}") from err
