"""AWS client factory for consistent client initialization across deployment modules."""

import boto3
from botocore.exceptions import ClientError


class AWSClientFactory:
    """Factory class for creating AWS service clients with consistent configuration."""

    def __init__(self, profile=None, region="us-east-1"):
        """Initialize the AWS client factory.

        Args:
            profile: AWS profile to use (optional)
            region: AWS region (default: us-east-1)
        """
        self.profile = profile
        self.region = region
        self._session = None
        self._clients = {}

    @property
    def session(self):
        """Get or create the boto3 session."""
        if self._session is None:
            session_args = {"region_name": self.region}
            if self.profile:
                session_args["profile_name"] = self.profile
            self._session = boto3.Session(**session_args)
        return self._session

    def get_client(self, service_name: str, **kwargs):
        """Get or create a client for the specified AWS service.

        Args:
            service_name: Name of the AWS service (e.g., 's3', 'cloudformation')
            **kwargs: Additional arguments to pass to the client constructor

        Returns:
            boto3 client for the specified service
        """
        # Create a cache key including any extra kwargs
        cache_key = f"{service_name}:{str(sorted(kwargs.items()))}"

        if cache_key not in self._clients:
            self._clients[cache_key] = self.session.client(service_name, **kwargs)

        return self._clients[cache_key]

    def get_resource(self, service_name: str, **kwargs):
        """Get a resource for the specified AWS service.

        Args:
            service_name: Name of the AWS service (e.g., 's3', 'dynamodb')
            **kwargs: Additional arguments to pass to the resource constructor

        Returns:
            boto3 resource for the specified service
        """
        return self.session.resource(service_name, **kwargs)

    def get_caller_identity(self) -> dict:
        """Get the caller identity information.

        Returns:
            Dictionary containing Account, Arn, and UserId

        Raises:
            ClientError: If unable to get caller identity
        """
        sts_client = self.get_client("sts")
        return sts_client.get_caller_identity()

    def get_account_id(self) -> str:
        """Get the AWS account ID.

        Returns:
            AWS account ID as string

        Raises:
            ClientError: If unable to get account ID
        """
        return self.get_caller_identity()["Account"]

    def validate_credentials(self) -> bool:
        """Validate that AWS credentials are properly configured.

        Returns:
            True if credentials are valid, False otherwise
        """
        try:
            self.get_caller_identity()
            return True
        except ClientError:
            return False
        except Exception:
            return False

    def clear_cache(self):
        """Clear the cached clients and session."""
        self._clients.clear()
        self._session = None
