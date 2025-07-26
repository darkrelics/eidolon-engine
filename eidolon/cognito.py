"""
Authentication utilities for Lambda functions.

Provides common authentication and authorization helpers for API Gateway
Lambda functions using Cognito user pools.
"""

from eidolon.logger import get_logger

logger = get_logger(__name__)


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


def extract_user_email(event: dict) -> str:
    """
    Extract user email from Cognito authorizer claims.

    Args:
        event: API Gateway Lambda event

    Returns:
        User email address
        
    Raises:
        ValueError: If no email found in claims
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    email = claims.get("email")
    
    if not email:
        logger.warning("No email found in authorization claims")
        raise ValueError("No email found in authorization claims")
        
    return email


def extract_username(event: dict) -> str:
    """
    Extract username from Cognito authorizer claims.

    Args:
        event: API Gateway Lambda event

    Returns:
        Username (cognito:username)
        
    Raises:
        ValueError: If no username found in claims
    """
    claims = event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
    username = claims.get("cognito:username")
    
    if not username:
        logger.warning("No username found in authorization claims")
        raise ValueError("No username found in authorization claims")
        
    return username


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
        
    Raises:
        ValueError: If user is not authenticated
    """
    # This will raise ValueError if not authenticated
    player_id = extract_player_id(event)
    
    # Placeholder implementation - always returns True for authenticated users
    logger.debug(
        "Permission check (placeholder always returns True)",
        extra={"player_id": player_id, "permission": permission}
    )
    
    return True


def get_authorization_claims(event: dict) -> dict:
    """
    Extract all authorization claims from the event.
    
    Args:
        event: API Gateway Lambda event
        
    Returns:
        Dict containing all claims. Empty dict if no claims found.
    """
    return event.get("requestContext", {}).get("authorizer", {}).get("claims", {})
