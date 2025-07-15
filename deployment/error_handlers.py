"""Error handling utilities for deployment operations."""

import functools
import time
from botocore.exceptions import ClientError


def handle_client_errors(operation_name="operation", default_return=None):
    """Decorator for consistent AWS ClientError handling.

    Args:
        operation_name: Name of the operation for error messages
        default_return: Value to return on error (None if not specified)

    Returns:
        Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ClientError as err:
                error_code = err.response.get("Error", {}).get("Code", "Unknown")
                error_message = err.response.get("Error", {}).get("Message", str(err))
                
                # Handle common error codes
                if error_code == "NoSuchBucket":
                    print(f"[ERROR] {operation_name}: Bucket not found - {error_message}")
                elif error_code == "AccessDenied":
                    print(f"[ERROR] {operation_name}: Access denied - {error_message}")
                elif error_code == "ValidationError":
                    print(f"[ERROR] {operation_name}: Validation error - {error_message}")
                elif error_code == "ResourceNotFoundException":
                    print(f"[ERROR] {operation_name}: Resource not found - {error_message}")
                elif error_code == "404":
                    print(f"[ERROR] {operation_name}: Not found - {error_message}")
                else:
                    print(f"[ERROR] {operation_name}: {error_code} - {error_message}")
                
                return default_return
            except Exception as err:
                print(f"[ERROR] {operation_name}: Unexpected error - {str(err)}")
                return default_return
        
        return wrapper
    return decorator


def retry_on_throttle(max_retries=3, backoff_base=2.0):
    """Decorator to retry operations on throttling errors.

    Args:
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff

    Returns:
        Decorator function
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except ClientError as err:
                    error_code = err.response.get("Error", {}).get("Code", "")
                    if error_code in ["Throttling", "TooManyRequestsException", "RequestLimitExceeded"]:
                        if attempt < max_retries - 1:
                            wait_time = backoff_base ** attempt
                            print(f"[WARNING] Request throttled, retrying in {wait_time} seconds...")
                            time.sleep(wait_time)
                            continue
                    # Re-raise if not a throttling error or last attempt
                    raise
            
            # Should never reach here, but just in case
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


class DeploymentError(Exception):
    """Base exception for deployment errors."""
    pass


class StackOperationError(DeploymentError):
    """Exception for CloudFormation stack operation errors."""
    pass


class ResourceValidationError(DeploymentError):
    """Exception for resource validation errors."""
    pass


class ConfigurationError(DeploymentError):
    """Exception for configuration-related errors."""
    pass