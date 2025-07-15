"""AWS CloudFront stack for Eidolon Engine portal distribution."""

import boto3
from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
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
        domain_name: str = "",
        portal_subdomain: str = "",
        hosted_zone_id: str = "",
        existing_distribution_id: str = "",
        **kwargs,
    ) -> None:
        """Initialize CloudFront stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            portal_bucket: S3 bucket containing the portal
            domain_name: Root domain name (e.g., darkrelics.net)
            portal_subdomain: Subdomain for portal
            hosted_zone_id: Route53 hosted zone ID
            existing_distribution_id: Optional existing CloudFront distribution ID to import
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate required configuration early
        if not portal_bucket:
            raise ValueError("portal_bucket is required")

        # Store parameters
        self.domain_name: str = domain_name
        self.portal_subdomain: str = portal_subdomain
        self.hosted_zone_id: str = hosted_zone_id

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

        # Output custom domain URL if configured, otherwise CloudFront domain
        if self.domain_name and self.portal_subdomain:
            portal_url: str = f"https://{self.portal_subdomain}.{self.domain_name}"
        else:
            portal_url: str = f"https://{self.distribution.distribution_domain_name}"

        CfnOutput(
            self,
            "PortalUrl",
            value=portal_url,
            description="Portal URL via CloudFront",
        )

    def create_distribution(self, portal_bucket: s3.IBucket) -> cloudfront.Distribution:
        """Create a new CloudFront distribution.

        Args:
            portal_bucket: S3 bucket containing the portal

        Returns:
            CloudFront distribution
        """
        # Configure custom domain if provided
        certificate = None
        domain_names = []

        if self.domain_name and self.portal_subdomain and self.hosted_zone_id:
            # Construct the full domain name
            portal_domain = f"{self.portal_subdomain}.{self.domain_name}"

            # Get the hosted zone
            hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "portal-hosted-zone",
                hosted_zone_id=self.hosted_zone_id,
                zone_name=self.domain_name,
            )

            # Create ACM certificate for the portal domain
            certificate = acm.Certificate(
                self,
                "portal-certificate",
                domain_name=portal_domain,
                validation=acm.CertificateValidation.from_dns(hosted_zone),
            )

            domain_names: list = [portal_domain]

        # Create the distribution
        distribution = cloudfront.Distribution(
            self,
            "eidolon-portal-distribution",
            default_root_object="index.html",
            certificate=certificate,
            domain_names=domain_names,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin(portal_bucket),
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
            comment="CloudFront distribution for Eidolon Engine portal",
            enabled=True,
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,  # US, Canada, Europe
        )

        # Note: S3 bucket policy will be updated post-deployment
        # CDK has issues updating existing bucket policies

        # Create Route53 record if custom domain is configured
        if self.domain_name and self.portal_subdomain and self.hosted_zone_id:
            hosted_zone = route53.HostedZone.from_hosted_zone_attributes(
                self,
                "portal-hosted-zone-for-record",
                hosted_zone_id=self.hosted_zone_id,
                zone_name=self.domain_name,
            )

            route53.ARecord(
                self,
                "portal-dns-record",
                zone=hosted_zone,
                record_name=self.portal_subdomain,
                target=route53.RecordTarget.from_alias(targets.CloudFrontTarget(distribution)), # type: ignore
            )

        return distribution

    def distribution_exists(self, distribution_id: str) -> bool:
        """Check if a CloudFront distribution exists.

        Args:
            distribution_id: ID of the distribution to check

        Returns:
            True if distribution exists, False otherwise
        """
        if not distribution_id:
            return False

        try:
            cf_client = boto3.client("cloudfront", region_name="us-east-1")
            cf_client.get_distribution(Id=distribution_id)
            return True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
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
        if not distribution_id:
            return f"{distribution_id}.cloudfront.net"

        try:
            cf_client = boto3.client("cloudfront", region_name="us-east-1")
            response = cf_client.get_distribution(Id=distribution_id)
            distribution_info = response.get("Distribution", {})
            return distribution_info.get("DomainName", f"{distribution_id}.cloudfront.net")
        except Exception:
            # Fallback to default CloudFront domain pattern
            return f"{distribution_id}.cloudfront.net"
