"""AWS CodeBuild stack for building and deploying the web portal."""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk.aws_s3 import IBucket
from constructs import Construct


class CodeBuildStack(Stack):
    """CodeBuild stack for building the Eidolon Engine web portal."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        github_owner: str,
        github_repo: str,
        github_branch: str,
        cognito_user_pool_id: str,
        cognito_app_client_id: str,
        portal_bucket: IBucket,
        buildspec_path: str = "buildspec/portal.yml",
        cloudfront_distribution_id: str = None,
        lambda_bucket: IBucket = None,
        **kwargs,
    ) -> None:
        """Initialize CodeBuild stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            github_owner: GitHub repository owner
            github_repo: GitHub repository name
            github_branch: GitHub branch to build from
            cognito_user_pool_id: Cognito User Pool ID
            cognito_app_client_id: Cognito App Client ID
            portal_bucket: S3 bucket for the web portal
            buildspec_path: Path to buildspec file relative to repository root
            cloudfront_distribution_id: CloudFront distribution ID for cache invalidation
            lambda_bucket: S3 bucket for Lambda deployment packages
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
                "S3_BUCKET_NAME": codebuild.BuildEnvironmentVariable(value=self.portal_bucket.bucket_name),
                "USER_POOL_ID": codebuild.BuildEnvironmentVariable(value=cognito_user_pool_id),
                "CLIENT_ID": codebuild.BuildEnvironmentVariable(value=cognito_app_client_id),
                "AWS_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                "CLOUDFRONT_DISTRIBUTION_ID": codebuild.BuildEnvironmentVariable(
                    value=cloudfront_distribution_id if cloudfront_distribution_id else ""
                ),
            },
            build_spec=codebuild.BuildSpec.from_source_filename(buildspec_path),
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

        # Create Lambda layer build project if lambda bucket is provided
        if lambda_bucket:
            self.lambda_bucket = lambda_bucket
            
            # Lambda layer build project
            self.lambda_layer_project = codebuild.Project(
                self,
                "lambda-layer-build",
                project_name="eidolon-lambda-layer-build",
                description="Build project for Eidolon Engine Lambda layer",
                source=codebuild.Source.git_hub(
                    owner=github_owner,
                    repo=github_repo,
                    branch_or_ref=github_branch,
                ),
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                    compute_type=codebuild.ComputeType.SMALL
                ),
                environment_variables={
                    "S3_BUCKET_NAME": codebuild.BuildEnvironmentVariable(value=self.lambda_bucket.bucket_name),
                },
                build_spec=codebuild.BuildSpec.from_source_filename("buildspec/lambda-layer.yml"),
                artifacts=codebuild.Artifacts.s3(
                    bucket=self.lambda_bucket,
                    include_build_id=False,
                    package_zip=False,
                    path="",
                    name="lambda-layer.zip",
                ),
            )
            
            # Lambda functions build project
            self.lambda_functions_project = codebuild.Project(
                self,
                "lambda-functions-build",
                project_name="eidolon-lambda-functions-build",
                description="Build project for Eidolon Engine Lambda functions",
                source=codebuild.Source.git_hub(
                    owner=github_owner,
                    repo=github_repo,
                    branch_or_ref=github_branch,
                ),
                environment=codebuild.BuildEnvironment(
                    build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                    compute_type=codebuild.ComputeType.SMALL
                ),
                environment_variables={
                    "S3_BUCKET_NAME": codebuild.BuildEnvironmentVariable(value=self.lambda_bucket.bucket_name),
                },
                build_spec=codebuild.BuildSpec.from_source_filename("buildspec/lambda-functions.yml"),
            )
            
            # Grant permissions to write to Lambda S3 bucket
            self.lambda_bucket.grant_read_write(self.lambda_layer_project)
            self.lambda_bucket.grant_read_write(self.lambda_functions_project)
            
            # Add Lambda functions build to upload individual zip files
            self.lambda_functions_project.add_to_role_policy(
                iam.PolicyStatement(
                    actions=["s3:PutObject"],
                    resources=[
                        f"{self.lambda_bucket.bucket_arn}/cognito_new_player.zip",
                        f"{self.lambda_bucket.bucket_arn}/get_player_archetypes.zip",
                        f"{self.lambda_bucket.bucket_arn}/save_character.zip",
                        f"{self.lambda_bucket.bucket_arn}/list_characters.zip",
                        f"{self.lambda_bucket.bucket_arn}/delete_character.zip",
                    ],
                )
            )

        # Output values
        CfnOutput(self, "CodeBuildProjectName", value=self.build_project.project_name, description="CodeBuild project name")
        
        if lambda_bucket:
            CfnOutput(self, "LambdaLayerProjectName", value=self.lambda_layer_project.project_name, description="Lambda layer build project name")
            CfnOutput(self, "LambdaFunctionsProjectName", value=self.lambda_functions_project.project_name, description="Lambda functions build project name")
