"""
CORS handler module for Lambda functions.

Provides centralized CORS configuration and validation for API responses.
"""

from eidolon.environment import (
    ALLOWED_ORIGINS,
    CORS_ALLOW_CREDENTIALS,
    CORS_ALLOWED_HEADERS,
    CORS_ALLOWED_METHODS,
    CORS_MAX_AGE,
)
from eidolon.logger import get_logger

logger = get_logger(__name__)


class CorsHandler:
    """Handles CORS configuration for Lambda functions."""

    def __init__(self):
        """Initialize CORS handler with environment configuration."""
        # Get allowed origins from environment variable
        self.allowed_origins = [origin.strip() for origin in ALLOWED_ORIGINS.split(",") if origin.strip()]

        # Default to restrictive CORS if no origins specified
        if not self.allowed_origins:
            logger.warning("No ALLOWED_ORIGINS configured, CORS will be restrictive")
            self.allowed_origins = []

        # Whether to allow credentials
        self.allow_credentials = CORS_ALLOW_CREDENTIALS.lower() == "true"

        # Allowed headers
        self.allowed_headers = CORS_ALLOWED_HEADERS

        # Allowed methods
        self.allowed_methods = CORS_ALLOWED_METHODS

        # Max age for preflight cache
        self.max_age = CORS_MAX_AGE

    def get_cors_headers(self, event: dict) -> dict:
        """
        Get CORS headers based on the request origin.

        Args:
            event: Lambda event containing request headers

        Returns:
            Dictionary of CORS headers
        """
        # Extract origin from request headers
        headers = event.get("headers", {})
        origin = headers.get("origin") or headers.get("Origin", "")

        cors_headers = {
            "Access-Control-Allow-Headers": self.allowed_headers,
            "Access-Control-Allow-Methods": self.allowed_methods,
            "Access-Control-Max-Age": self.max_age,
        }

        # Validate origin
        if not self.allowed_origins:
            # No origins configured, use wildcard but don't allow credentials
            cors_headers["Access-Control-Allow-Origin"] = "*"
            # Don't set credentials header when using wildcard
        elif origin and origin in self.allowed_origins:
            cors_headers["Access-Control-Allow-Origin"] = origin
            if self.allow_credentials:
                cors_headers["Access-Control-Allow-Credentials"] = "true"
        elif len(self.allowed_origins) == 1:
            # If only one origin is allowed, use it as default
            cors_headers["Access-Control-Allow-Origin"] = self.allowed_origins[0]
            if self.allow_credentials:
                cors_headers["Access-Control-Allow-Credentials"] = "true"
        else:
            # No valid origin found, reject the request
            logger.warning("Origin not in allowed list", extra={"origin": origin, "allowed_origins": self.allowed_origins})
            # Don't set Access-Control-Allow-Origin header for unauthorized origins
            # This will cause the browser to block the request

        return cors_headers

    def handle_preflight(self, event: dict) -> dict:
        """
        Handle OPTIONS preflight requests.

        Args:
            event: Lambda event

        Returns:
            Lambda response for preflight request
        """
        return {"statusCode": 200, "headers": self.get_cors_headers(event), "body": ""}

    def add_cors_headers(self, response: dict, event: dict) -> dict:
        """
        Add CORS headers to an existing response.

        Args:
            response: Lambda response dictionary
            event: Lambda event containing request headers

        Returns:
            Response with CORS headers added
        """
        if "headers" not in response:
            response["headers"] = {}

        response["headers"].update(self.get_cors_headers(event))
        return response


# Global instance for easy import
cors_handler = CorsHandler()
