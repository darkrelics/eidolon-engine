"""
CORS handler module for Lambda functions.

Provides centralized CORS configuration and validation for API responses.
"""

import logging
import os

logger = logging.getLogger()


class CorsHandler:
    """Handles CORS configuration for Lambda functions."""

    def __init__(self):
        """Initialize CORS handler with environment configuration."""
        # Get allowed origins from environment variable
        origins_config = os.environ.get("ALLOWED_ORIGINS", "")
        self.allowed_origins = [origin.strip() for origin in origins_config.split(",") if origin.strip()]

        # Default to restrictive CORS if no origins specified
        if not self.allowed_origins:
            logger.warning("No ALLOWED_ORIGINS configured, CORS will be restrictive")
            self.allowed_origins = []

        # Whether to allow credentials
        self.allow_credentials = os.environ.get("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

        # Allowed headers
        self.allowed_headers = os.environ.get(
            "CORS_ALLOWED_HEADERS", "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token"
        )

        # Allowed methods
        self.allowed_methods = os.environ.get("CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS")

        # Max age for preflight cache
        self.max_age = os.environ.get("CORS_MAX_AGE", "86400")  # 24 hours default

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
            logger.warning(f"Origin '{origin}' not in allowed list. Allowed origins: {self.allowed_origins}")
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
