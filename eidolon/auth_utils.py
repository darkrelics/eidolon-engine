"""
Authentication utilities for Lambda functions.

Provides common authentication and authorization helpers for API Gateway
Lambda functions using Cognito user pools.
"""

import json


def extract_player_id(event: dict) -> str | None:
    """
    Extract player ID from Cognito authorizer claims.

    Args:
        event: API Gateway Lambda event

    Returns:
        Player ID (Cognito sub) or None if not found
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    return claims.get("sub")


def require_auth(event: dict) -> tuple[str | None, dict | None]:
    """
    Validate authentication and return player_id or error response.

    Args:
        event: API Gateway Lambda event

    Returns:
        Tuple of (player_id, error_response)
        - If authenticated: (player_id, None)
        - If not authenticated: (None, error_response_dict)
    """
    player_id = extract_player_id(event)

    if not player_id:
        error_response = {
            "statusCode": 401,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Unauthorized"}),
        }
        return None, error_response

    return player_id, None


def extract_user_email(event: dict) -> str | None:
    """
    Extract user email from Cognito authorizer claims.

    Args:
        event: API Gateway Lambda event

    Returns:
        User email or None if not found
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    return claims.get("email")


def extract_username(event: dict) -> str | None:
    """
    Extract username from Cognito authorizer claims.

    Args:
        event: API Gateway Lambda event

    Returns:
        Username (cognito:username) or None if not found
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    return claims.get("cognito:username")


def has_permission(event: dict, permission: str) -> bool:
    """
    Check if user has a specific permission.

    This is a placeholder for future permission system implementation.
    Currently returns True for all authenticated users.

    Args:
        event: API Gateway Lambda event
        permission: Permission string to check

    Returns:
        True if user has permission, False otherwise
    """
    player_id = extract_player_id(event)
    if not player_id:
        return False

    # TODO: Implement actual permission checking
    # For now, all authenticated users have all permissions
    return True
