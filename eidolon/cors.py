"""
CORS handler module for Lambda functions.

Provides centralized CORS configuration and validation for API responses.
"""

from eidolon.environment import ALLOWED_ORIGINS, CORS_ALLOW_CREDENTIALS, CORS_ALLOWED_HEADERS, CORS_ALLOWED_METHODS, CORS_MAX_AGE
from eidolon.logger import logger


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

    def extract_origin(self, event: dict) -> str:
        """
        Extract origin from request headers.

        Args:
            event: Lambda event containing request headers

        Returns:
            Origin string or empty string if not found
        """
        headers = event.get("headers", {})
        return headers.get("origin") or headers.get("Origin", "")

    def get_base_cors_headers(self) -> dict:
        """
        Get base CORS headers that are always included.

        Returns:
            Dictionary with base CORS headers
        """
        return {
            "Access-Control-Allow-Headers": self.allowed_headers,
            "Access-Control-Allow-Methods": self.allowed_methods,
            "Access-Control-Max-Age": self.max_age,
        }

    def is_origin_allowed(self, origin: str) -> bool:
        """
        Check if an origin is in the allowed list.

        Args:
            origin: Origin to check

        Returns:
            True if origin is allowed, False otherwise
        """
        return bool(origin and origin in self.allowed_origins)

    def get_allowed_origin_header(self, origin: str) -> tuple:
        """
        Determine the Access-Control-Allow-Origin header value.

        Args:
            origin: Request origin

        Returns:
            Tuple of (origin_header_value, should_allow_credentials)
        """
        # No origins configured - use wildcard without credentials
        if not self.allowed_origins:
            return "*", False

        # Origin is in allowed list
        if self.is_origin_allowed(origin):
            return origin, self.allow_credentials

        # Single origin configured - use as default
        if len(self.allowed_origins) == 1:
            return self.allowed_origins[0], self.allow_credentials

        # Multiple origins configured but request origin not allowed
        logger.warning(f"Origin not in allowed list for {origin}")
        return None, False

    def get_cors_headers(self, event: dict) -> dict:
        """
        Get CORS headers based on the request origin.

        Args:
            event: Lambda event containing request headers

        Returns:
            Dictionary of CORS headers
        """
        # Start with base headers
        cors_headers = self.get_base_cors_headers()

        # Extract and validate origin
        origin = self.extract_origin(event)
        allowed_origin, allow_credentials = self.get_allowed_origin_header(origin)

        # Set origin header if allowed
        if allowed_origin:
            cors_headers["Access-Control-Allow-Origin"] = allowed_origin
            if allow_credentials:
                cors_headers["Access-Control-Allow-Credentials"] = "true"

        return cors_headers

    def handle_preflight(self, event: dict) -> dict:
        """
        Handle OPTIONS preflight requests.

        Args:
            event: Lambda event

        Returns:
            Lambda response for preflight request
        """
        if event.get("httpMethod") == "OPTIONS":
            return {"statusCode": 200, "headers": self.get_cors_headers(event), "body": ""}

        return {}

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
