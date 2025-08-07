"""
Authentication utilities for Lambda functions.

Provides common authentication and authorization helpers for API Gateway
Lambda functions using Cognito user pools.
"""

from eidolon.logger import logger


def extract_player_id(event: dict) -> str:
    """
    Extract player ID from Cognito authorizer claims.

    Args:
        event: API Gateway Lambda event

    Returns:
        Player ID (Cognito sub)

    Raises:
        ValueError: If no player ID found in claims
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    player_id = claims.get("sub")

    if not player_id:
        logger.warning("No player ID found in authorization claims")
        raise ValueError("No player ID found in authorization claims")

    return player_id


def require_auth(event: dict) -> str:
    """
    Validate authentication and return player_id.

    Args:
        event: API Gateway Lambda event

    Returns:
        Player ID string

    Raises:
        ValueError: If not authenticated
    """
    return extract_player_id(event)
