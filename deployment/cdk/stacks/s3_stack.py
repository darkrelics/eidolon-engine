"""AWS S3 stack for Eidolon Engine storage needs."""

import boto3
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_s3 as s3
from aws_cdk.aws_s3 import IBucket
from botocore.exceptions import ClientError
from constructs import Construct


def check_bucket_exists(bucket_name: str, region: str) -> bool:
    """Check if an S3 bucket exists.

    Args:
        bucket_name: Name of the bucket to check
        region: AWS region to check in

    Returns:
        True if bucket exists, False otherwise
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code")
        if error_code in ["404", "NoSuchBucket"]:
            return False
        elif error_code == "403":
            # Bucket exists but we don't have access
            # Treat as existing to avoid trying to create it
            return True
        else:
            # Other errors - assume bucket doesn't exist
            return False


class S3Stack(Stack):
    """S3 stack for Eidolon Engine storage buckets."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        game_name: str = "eidolon",
        portal_bucket_name: str = "",
        scripts_bucket_name: str = "",
        lambda_bucket_name: str = "",
        **kwargs,
    ) -> None:
        """Initialize S3 stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            portal_bucket_name: Optional existing portal bucket name
            scripts_bucket_name: Optional existing scripts bucket name
            lambda_bucket_name: Optional existing lambda bucket name
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate configuration
        if not game_name:
            raise ValueError("game_name is required")

        # Handle portal bucket
        # Note: When using CloudFront, we don't need public read or website hosting
        self.portal_bucket = self.get_or_create_bucket(
            "portal-bucket",
            portal_bucket_name or "darkrelics-portal",
            website_config={},  # CloudFront will handle web serving
            public_read=False,  # CloudFront OAI will have access
        )

        # Handle scripts bucket
        self.scripts_bucket = self.get_or_create_bucket(
            "scripts-bucket",
            scripts_bucket_name or "darkrelics-scripts",
            public_read=True,
        )

        # Handle lambda bucket
        self.lambda_bucket = self.get_or_create_bucket(
            "lambda-bucket",
            lambda_bucket_name or f"{game_name}-lambda-{self.account}",
            public_read=False,
        )

        # Output values
        CfnOutput(
            self,
            "PortalBucketName",
            value=self.portal_bucket.bucket_name,
            description="S3 bucket name for web portal",
        )

        CfnOutput(
            self,
            "PortalWebsiteUrl",
            value=(
                self.portal_bucket.bucket_website_url
                if hasattr(self.portal_bucket, "bucket_website_url")
                else f"http://{self.portal_bucket.bucket_name}.s3-website-{self.region}.amazonaws.com"
            ),
            description="URL of the web portal",
        )

        CfnOutput(
            self,
            "ScriptsBucketName",
            value=self.scripts_bucket.bucket_name,
            description="S3 bucket name for game scripts",
        )

        CfnOutput(
            self,
            "LambdaBucketName",
            value=self.lambda_bucket.bucket_name,
            description="S3 bucket name for Lambda deployment packages",
        )

    def get_or_create_bucket(
        self,
        logical_id: str,
        bucket_name: str,
        website_config = None,
        public_read: bool = False,
    ) -> IBucket:
        """Get existing bucket or create a new one.

        Args:
            logical_id: Logical ID for the bucket in the stack
            bucket_name: Name of the bucket
            website_config: Optional website configuration
            public_read: Whether to enable public read access

        Returns:
            S3 bucket (existing or newly created)
        """

        if website_config is None:
            website_config = {}

        # Check if bucket exists
        if check_bucket_exists(bucket_name, self.region):
            # Import existing bucket
            bucket = s3.Bucket.from_bucket_name(self, logical_id, bucket_name)

            # Note: We cannot modify existing bucket configurations through CDK import
            # The bucket must already have the correct configuration
            print(f"Using existing S3 bucket: {bucket_name}")

            return bucket
        else:
            # Create new bucket with desired configuration
            bucket_props: dict = {
                "bucket_name": bucket_name,
                "removal_policy": RemovalPolicy.DESTROY,
                "auto_delete_objects": True,
            }

            if website_config:
                bucket_props["website_index_document"] = website_config.get("index_document", "index.html")
                bucket_props["website_error_document"] = website_config.get("error_document", "error.html")

            if public_read:
                bucket_props["public_read_access"] = True
                bucket_props["block_public_access"] = s3.BlockPublicAccess(
                    block_public_acls=False,
                    block_public_policy=False,
                    ignore_public_acls=False,
                    restrict_public_buckets=False,
                )

            bucket = s3.Bucket(self, logical_id, **bucket_props)
            print(f"Creating new S3 bucket: {bucket_name}")

            return bucket
