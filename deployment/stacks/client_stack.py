"""Client stack for portal deployment with CloudFront and CodeBuild."""

from aws_cdk import Stack, CfnOutput, Duration, RemovalPolicy
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_certificatemanager as acm
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_route53 as route53
from aws_cdk import aws_route53_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_codebuild as codebuild
from constructs import Construct

from . import stack_utilities as utils


class ClientStack(Stack):
    """Client stack for Eidolon Engine portal."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str,
        hosted_zone_id: str,
        domain: str,
        api_host: str = "api",
        client_host: str = "portal",
        client_bucket: str = "",
        api_url: str = "",
        deployment_mode: str = "hybrid",
        github_owner: str = "",
        github_repo: str = "",
        github_branch: str = "",
        cognito_user_pool_id: str = "",
        cognito_client_id: str = "",
        **kwargs,
    ) -> None:
        """Initialize Client stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region
            hosted_zone_id: Route53 Hosted Zone ID
            domain: Base domain name
            api_host: Subdomain for API (default: api)
            client_host: Subdomain for portal (default: portal)
            client_bucket: S3 bucket name for portal static files
            api_url: Full URL of the API Gateway
            deployment_mode: Deployment mode (mud/incremental/hybrid)
            github_owner: GitHub repository owner
            github_repo: GitHub repository name
            github_branch: GitHub branch
            cognito_user_pool_id: Cognito User Pool ID
            cognito_client_id: Cognito Client ID
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.hosted_zone_id = hosted_zone_id
        self.domain = domain
        self.api_host = api_host
        self.client_host = client_host
        self.client_bucket = client_bucket
        self.api_url = api_url
        self.deployment_mode = deployment_mode
        self.github_owner = github_owner
        self.github_repo = github_repo
        self.github_branch = github_branch
        self.cognito_user_pool_id = cognito_user_pool_id
        self.cognito_client_id = cognito_client_id

        super().__init__(scope, stack_id, description="Portal S3 bucket, CloudFront CDN, and CodeBuild deployment", **kwargs)

        # Create portal S3 bucket
        self.portal_bucket = self._create_portal_bucket()

        # Create CloudFront distribution
        self.distribution = self._create_cloudfront_distribution()

        # Create CodeBuild project for portal deployment
        self.build_project = self._create_codebuild_project()

        # Add outputs
        self._add_outputs()

    def _create_portal_bucket(self) -> s3.IBucket:
        """Create S3 bucket for portal."""
        # Use provided bucket name or generate one
        bucket_name = self.client_bucket or f"{self.client_host}-{self.domain.replace('.', '-')}"
        
        # Create bucket with fixed logical ID
        return s3.Bucket(
            self,
            "PortalBucket",  # Fixed logical ID
            bucket_name=bucket_name,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

    def _create_cloudfront_distribution(self) -> cloudfront.Distribution:
        """Create CloudFront distribution for portal."""
        print("  Setting up CloudFront distribution")

        # Configure custom domain
        portal_domain = f"{self.client_host}.{self.domain}"
        hosted_zone = utils.get_hosted_zone_by_id(self, self.hosted_zone_id, self.domain)
        
        if not hosted_zone:
            raise ValueError(f"Could not find hosted zone {self.hosted_zone_id} for domain {self.domain}")
        
        # Create certificate with fixed logical ID
        certificate = acm.Certificate(
            self,
            "PortalCertificate",  # Fixed logical ID
            domain_name=portal_domain,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )
        domain_names = [portal_domain]

        # Create distribution with fixed logical ID
        distribution = cloudfront.Distribution(
            self,
            "PortalDistribution",  # Fixed logical ID
            default_root_object="index.html",
            certificate=certificate,
            domain_names=domain_names,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(self.portal_bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
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
        )

        # Create Route53 record
        route53.ARecord(
            self,
            "PortalDnsRecord",
            zone=hosted_zone,
            record_name=self.client_host,
            target=route53.RecordTarget.from_alias(targets.CloudFrontTarget(distribution)), # type: ignore
        )

        return distribution

    def _create_codebuild_project(self) -> codebuild.Project:
        """Create CodeBuild project for portal deployment."""
        print("  Creating CodeBuild project")

        # Determine buildspec file based on deployment mode
        buildspec_file = "buildspec/portal.yml" if self.deployment_mode == "mud" else "buildspec/incremental.yml"
        
        # Use the provided API URL

        # Create CodeBuild project
        project = codebuild.Project(
            self,
            "PortalBuildProject",
            project_name="eidolon-portal-build",
            description="Build project for Eidolon Engine portal",
            source=codebuild.Source.git_hub(
                owner=self.github_owner,
                repo=self.github_repo,
                branch_or_ref=self.github_branch,
                webhook=False,
                report_build_status=False,
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            environment_variables={
                "S3_BUCKET": codebuild.BuildEnvironmentVariable(value=self.portal_bucket.bucket_name),
                "USER_POOL_ID": codebuild.BuildEnvironmentVariable(value=self.cognito_user_pool_id),
                "CLIENT_ID": codebuild.BuildEnvironmentVariable(value=self.cognito_client_id),
                "API_DOMAIN": codebuild.BuildEnvironmentVariable(value=self.api_url),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region_name),
                "CLOUDFRONT_DISTRIBUTION_ID": codebuild.BuildEnvironmentVariable(value=self.distribution.distribution_id),
            },
            build_spec=codebuild.BuildSpec.from_source_filename(buildspec_file),
        )

        # Grant permissions
        self.portal_bucket.grant_read_write(project)
        
        project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudfront:CreateInvalidation"],
                resources=[f"arn:aws:cloudfront::{self.account}:distribution/{self.distribution.distribution_id}"],
            )
        )

        return project


    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "PortalBucketName", value=self.portal_bucket.bucket_name, description="Portal S3 bucket name")
        
        CfnOutput(self, "CloudFrontDistributionId", value=self.distribution.distribution_id, description="CloudFront distribution ID")
        
        CfnOutput(self, "CloudFrontUrl", value=f"https://{self.distribution.distribution_domain_name}", description="CloudFront URL")
        
        CfnOutput(self, "PortalUrl", value=f"https://{self.client_host}.{self.domain}", description="Portal custom domain URL")
        
        CfnOutput(self, "CodeBuildProjectName", value=self.build_project.project_name, description="CodeBuild project name")