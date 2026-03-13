"""AWS utility functions for retry logic and error handling."""

import time

from botocore.exceptions import ClientError

TRANSIENT_ERROR_CODES = [
    "Throttling",
    "ThrottlingException",
    "RequestLimitExceeded",
    "ServiceUnavailable",
    "InternalError",
    "InternalServiceError",
    "ResourceConflictException",
]


def retry_on_transient_error(func, max_retries: int = 3, base_delay: float = 2.0):
    """Wrapper to retry a function on transient AWS errors.

    Args:
        func: Function to call (should be a lambda or callable)
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds (doubles with each retry)

    Returns:
        Result of the function call

    Raises:
        ClientError: If all retries exhausted or non-transient error
    """
    for attempt in range(max_retries + 1):
        try:
            return func()
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code in TRANSIENT_ERROR_CODES and attempt < max_retries:
                delay = base_delay * (2**attempt)
                print(f"    Transient error ({error_code}), retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                raise err from err
    raise ClientError({"Error": {"Code": "RetriesExhausted", "Message": "All retries exhausted"}}, "Unknown")
