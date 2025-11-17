"""
Lambda handler decorator for consistent error handling and authentication.

Provides a decorator that handles common Lambda handler patterns:
- Request logging
- CORS preflight handling
- Authentication extraction
- Error handling and response formatting
"""

from functools import wraps

from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.logger import log_lambda_statistics, logger
from eidolon.responses import lambda_error, lambda_response


def authenticated_handler(business_logic_func):
    """
    Decorator for Lambda handlers that require authentication.

    This decorator handles:
    1. Request logging
    2. CORS preflight requests
    3. Authentication extraction from JWT
    4. Error handling and response formatting

    The decorated function receives (event, context, player_id) and should return
    a dict with 'status_code' and 'body' keys.

    Args:
        business_logic_func: Function that takes (event, context, player_id) and
                           returns dict with status_code and body

    Returns:
        Decorated function that handles all Lambda handler boilerplate

    Example:
        @authenticated_handler
        def lambda_handler(event: dict, context: object, player_id: str) -> dict:
            # Your business logic here
            return {
                'status_code': 200,
                'body': {'Message': 'Success'}
            }
    """

    @wraps(business_logic_func)
    def wrapper(event: dict, context: object) -> dict:
        # Log invocation statistics
        log_lambda_statistics(event, context)

        # Handle CORS preflight requests
        preflight_response: dict = cors_handler.handle_preflight(event)
        if preflight_response:
            return preflight_response

        # Extract and validate player authentication
        try:
            player_id: str = extract_player_id(event)
        except ValueError as err:
            logger.warning(f"Authentication failed: {err}", exc_info=False)
            return lambda_response(401, {"Error": "Unauthorized"}, event)
        except Exception as err:
            return lambda_error(event, err)

        # Execute business logic with error handling
        try:
            result = business_logic_func(event, context, player_id)
            status_code = result.get("status_code", 200)
            body = result.get("body", {})
            return lambda_response(status_code, body, event)
        except ValueError as err:
            # Business logic validation errors (400/403/404/409)
            logger.warning(f"Business logic validation error: {err}")
            # Allow business logic to specify status code via error message prefix
            # Format: "STATUS_CODE:Error message"
            error_msg = str(err)
            if ":" in error_msg and error_msg.split(":", 1)[0].isdigit():
                status_code = int(error_msg.split(":", 1)[0])
                error_text = error_msg.split(":", 1)[1].strip()
                return lambda_response(status_code, {"Error": error_text}, event)
            return lambda_response(400, {"Error": error_msg}, event)
        except RuntimeError as err:
            # System errors (500)
            logger.error(f"System error: {err}", exc_info=True)
            return lambda_response(500, {"Error": "Internal server error"}, event)
        except Exception as err:
            return lambda_error(event, err)

    return wrapper
