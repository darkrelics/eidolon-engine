"""AWS CodeBuild stack for building and deploying the web portal."""

from aws_cdk import Stack, aws_codebuild as codebuild, aws_s3 as s3, aws_iam as iam, CfnOutput
from aws_cdk.aws_s3 import IBucket
from constructs import Construct


class CodeBuildStack(Stack):
    """CodeBuild stack for building the Eidolon Engine web portal."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        game_name: str,
        github_owner: str,
        github_repo: str,
        github_branch: str,
        cognito_user_pool_id: str,
        cognito_app_client_id: str,
        portal_bucket: IBucket,
        cloudfront_distribution_id: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize CodeBuild stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            github_owner: GitHub repository owner
            github_repo: GitHub repository name
            github_branch: GitHub branch to build from
            cognito_user_pool_id: Cognito User Pool ID
            cognito_app_client_id: Cognito App Client ID
            portal_bucket: S3 bucket for the web portal
            cloudfront_distribution_id: CloudFront distribution ID for cache invalidation
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Use provided S3 bucket
        self.portal_bucket = portal_bucket

        # Create CodeBuild project
        self.build_project = codebuild.Project(
            self,
            "portal-build",
            project_name="eidolon-portal-build",
            description="Build project for Eidolon Engine web portal",
            source=codebuild.Source.git_hub(
                owner=github_owner,
                repo=github_repo,
                branch_or_ref=github_branch,
                webhook=True,
                webhook_filters=[
                    codebuild.FilterGroup.in_event_of(
                        codebuild.EventAction.PUSH, codebuild.EventAction.PULL_REQUEST_MERGED
                    ).and_branch_is(github_branch)
                ],
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0, compute_type=codebuild.ComputeType.MEDIUM
            ),
            environment_variables={
                "PORTAL_BUCKET": codebuild.BuildEnvironmentVariable(value=self.portal_bucket.bucket_name),
                "COGNITO_USER_POOL_ID": codebuild.BuildEnvironmentVariable(value=cognito_user_pool_id),
                "COGNITO_APP_CLIENT_ID": codebuild.BuildEnvironmentVariable(value=cognito_app_client_id),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                "CLOUDFRONT_DISTRIBUTION_ID": codebuild.BuildEnvironmentVariable(
                    value=cloudfront_distribution_id if cloudfront_distribution_id else ""
                ),
            },
            build_spec=codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "runtime-versions": {"nodejs": "18"},
                            "commands": [
                                "cd portal",
                                "curl -fsSL https://flutter.dev/release/stable/linux | tar xJ -C /opt",
                                'export PATH="$PATH:/opt/flutter/bin"',
                                "flutter doctor",
                            ],
                        },
                        "pre_build": {
                            "commands": [
                                "flutter pub get",
                                "echo 'const String cognitoUserPoolId = \"$COGNITO_USER_POOL_ID\";' > lib/config.dart",
                                "echo 'const String cognitoAppClientId = \"$COGNITO_APP_CLIENT_ID\";' >> lib/config.dart",
                                "echo 'const String awsRegion = \"$AWS_REGION\";' >> lib/config.dart",
                            ]
                        },
                        "build": {"commands": ["flutter build web --release"]},
                        "post_build": {
                            "commands": [
                                "aws s3 sync build/web/ s3://$PORTAL_BUCKET/ --delete",
                                "aws s3 cp build/web/index.html s3://$PORTAL_BUCKET/index.html --cache-control max-age=0",
                                'if [ ! -z "$CLOUDFRONT_DISTRIBUTION_ID" ]; then echo "Invalidating CloudFront cache..."; aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths "/*"; fi',
                            ]
                        },
                    },
                }
            ),
        )

        # Grant CodeBuild permissions to write to S3
        self.portal_bucket.grant_read_write(self.build_project)

        # Grant CodeBuild permissions to create CloudFront invalidations if distribution ID is provided
        if cloudfront_distribution_id:
            self.build_project.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["cloudfront:CreateInvalidation"],
                    resources=[f"arn:aws:cloudfront::{self.account}:distribution/{cloudfront_distribution_id}"],
                )
            )

        # Output values
        CfnOutput(self, "CodeBuildProjectName", value=self.build_project.project_name, description="CodeBuild project name")
