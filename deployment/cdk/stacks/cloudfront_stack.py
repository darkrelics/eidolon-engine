"""AWS CloudFront stack for Eidolon Engine portal distribution."""

import boto3
from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from botocore.exceptions import ClientError
from constructs import Construct


class CloudFrontStack(Stack):
    """CloudFront stack for Eidolon Engine portal distribution."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        portal_bucket: s3.IBucket,
        existing_distribution_id: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize CloudFront stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            portal_bucket: S3 bucket containing the portal
            existing_distribution_id: Optional existing CloudFront distribution ID to import
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Check if we should import an existing distribution
        if existing_distribution_id and self.distribution_exists(existing_distribution_id):
            # Import existing distribution
            self.distribution = cloudfront.Distribution.from_distribution_attributes(
                self,
                "portal-distribution",
                distribution_id=existing_distribution_id,
                domain_name=self.get_distribution_domain(existing_distribution_id),
            )
            print(f"Using existing CloudFront distribution: {existing_distribution_id}")
        else:
            # Create new distribution
            self.distribution = self.create_distribution(portal_bucket)
            print("Creating new CloudFront distribution")

        # Output values
        CfnOutput(
            self,
            "DistributionId",
            value=self.distribution.distribution_id,
            description="CloudFront distribution ID",
        )

        CfnOutput(
            self,
            "DistributionDomainName",
            value=self.distribution.distribution_domain_name,
            description="CloudFront distribution domain name",
        )

        CfnOutput(
            self,
            "PortalUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
            description="Portal URL via CloudFront",
        )

    def create_distribution(self, portal_bucket: s3.IBucket) -> cloudfront.Distribution:
        """Create a new CloudFront distribution.

        Args:
            portal_bucket: S3 bucket containing the portal

        Returns:
            CloudFront distribution
        """
        # Create Origin Access Identity for secure S3 access
        oai = cloudfront.OriginAccessIdentity(
            self,
            "portal-oai",
            comment="OAI for portal bucket",
        )

        # Grant CloudFront read access to the bucket
        portal_bucket.grant_read(oai)

        # Create the distribution
        distribution = cloudfront.Distribution(
            self,
            "eidolon-portal-distribution",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    portal_bucket,
                    origin_access_identity=oai,
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                compress=True,
            ),
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.minutes(5),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_page_path="/index.html",
                    response_http_status=200,
                    ttl=Duration.minutes(5),
                ),
            ],
            comment="CloudFront distribution for portal",
            enabled=True,
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # US, Canada, Europe
        )

        return distribution

    def distribution_exists(self, distribution_id: str) -> bool:
        """Check if a CloudFront distribution exists.

        Args:
            distribution_id: ID of the distribution to check

        Returns:
            True if distribution exists, False otherwise
        """
        try:
            cf_client = boto3.client("cloudfront", region_name="us-east-1")
            cf_client.get_distribution(Id=distribution_id)
            return True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code")
            if error_code in ["NoSuchDistribution", "DistributionNotFound"]:
                return False
            else:
                # Other errors - assume distribution doesn't exist
                return False

    def get_distribution_domain(self, distribution_id: str) -> str:
        """Get the domain name of an existing distribution.

        Args:
            distribution_id: ID of the distribution

        Returns:
            Domain name of the distribution
        """
        try:
            cf_client = boto3.client("cloudfront", region_name="us-east-1")
            response = cf_client.get_distribution(Id=distribution_id)
            return response["Distribution"]["DomainName"]
        except Exception:
            # Fallback to default CloudFront domain pattern
            return f"{distribution_id}.cloudfront.net"
