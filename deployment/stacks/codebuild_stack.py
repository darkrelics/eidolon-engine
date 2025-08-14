"""CodeBuild stack for Eidolon Engine Lambda builds."""

from aws_cdk import CfnOutput, Stack, RemovalPolicy
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_iam as iam
from constructs import Construct

from . import stack_utilities as utils


class CodeBuildStack(Stack):
    """CodeBuild stack for Eidolon Engine Lambda builds."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        s3_bucket: str = "",
        github_owner: str = "robinje",
        github_repo: str = "eidolon-engine",
        github_branch: str = "develop",
        **kwargs,
    ) -> None:
        """Initialize CodeBuild stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            s3_bucket: S3 bucket name for Lambda artifacts
            github_owner: GitHub repository owner
            github_repo: GitHub repository name
            github_branch: GitHub branch to build from
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.github_owner = github_owner
        self.github_repo = github_repo
        self.github_branch = github_branch
        super().__init__(scope, stack_id, **kwargs)

        # Create S3 bucket for artifacts with fixed logical ID
        bucket = s3.Bucket(
            self,
            "ArtifactsBucket",  # Fixed logical ID - won't change between deployments
            bucket_name=self.s3_bucket_name,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        )

        # Store bucket reference
        self.artifacts_bucket = bucket

        # Create shared IAM role for CodeBuild projects
        self.codebuild_role = self._create_codebuild_role()

        # Create CodeBuild projects
        self.lambda_layer_project = self._create_lambda_layer_project()
        self.lambda_functions_project = self._create_lambda_functions_project()

        # Add outputs
        self._add_outputs()


    def _create_codebuild_role(self) -> iam.Role:
        """Create shared IAM role for CodeBuild projects."""
        # Create custom managed policy for CloudWatch Logs
        logs_policy = iam.ManagedPolicy(
            self,
            "CodeBuildLogsPolicy",
            managed_policy_name="eidolon-codebuild-logs-policy",
            description="Policy for CodeBuild to write logs to CloudWatch",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
                    resources=[f"arn:aws:logs:{self.region_name}:*:log-group:/aws/codebuild/*"],
                )
            ],
        )

        # Create custom managed policy for S3 access
        s3_policy = iam.ManagedPolicy(
            self,
            "CodeBuildS3Policy",
            managed_policy_name="eidolon-codebuild-s3-policy",
            description="Policy for CodeBuild to access artifacts bucket",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                    resources=[self.artifacts_bucket.bucket_arn, f"{self.artifacts_bucket.bucket_arn}/*"],
                )
            ],
        )

        # Create the role with both managed policies
        role = iam.Role(
            self,
            "LambdaCodeBuildRole",
            role_name="eidolon-lambda-codebuild-role",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),  # type: ignore
            managed_policies=[logs_policy, s3_policy],
        )

        return role

    def _create_lambda_layer_project(self):
        """Create CodeBuild project for Lambda layer."""
        project_name = "eidolon-lambda-layer"

        # Check if project exists (CDK will update if it exists)
        if utils.check_codebuild_project_exists(project_name, self.region_name):
            print(f"CodeBuild project {project_name} already exists, will be updated")
        else:
            print(f"  Creating new CodeBuild project: {project_name}")

        # Create the project
        project = codebuild.Project(
            self,
            "LambdaLayerProject",
            project_name=project_name,
            description="Build Lambda layer with Python dependencies",
            role=self.codebuild_role,  # type: ignore
            source=codebuild.Source.git_hub(
                owner=self.github_owner,
                repo=self.github_repo,
                branch_or_ref=self.github_branch,
                webhook=False,
                clone_depth=1,
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            environment_variables={
                "S3_BUCKET": codebuild.BuildEnvironmentVariable(value=self.artifacts_bucket.bucket_name),
                "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=self.region_name),
            },
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec/lambda-layer.yml"),
            artifacts=codebuild.Artifacts.s3(
                bucket=self.artifacts_bucket,
                include_build_id=False,
                package_zip=False,
                path="lambda-layer",
                name="lambda-layer.zip",
            ),
        )

        # Set removal policy
        project.apply_removal_policy(RemovalPolicy.DESTROY)

        return project

    def _create_lambda_functions_project(self):
        """Create CodeBuild project for Lambda functions."""
        project_name = "eidolon-lambda-functions"

        # Check if project exists (CDK will update if it exists)
        if utils.check_codebuild_project_exists(project_name, self.region_name):
            print(f"CodeBuild project {project_name} already exists, will be updated")
        else:
            print(f"  Creating new CodeBuild project: {project_name}")

        # Create the project
        project = codebuild.Project(
            self,
            "LambdaFunctionsProject",
            project_name=project_name,
            description="Build Lambda function deployment packages",
            role=self.codebuild_role,  # type: ignore
            source=codebuild.Source.git_hub(
                owner=self.github_owner,
                repo=self.github_repo,
                branch_or_ref=self.github_branch,
                webhook=False,
                clone_depth=1,
            ),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            environment_variables={
                "S3_BUCKET": codebuild.BuildEnvironmentVariable(value=self.artifacts_bucket.bucket_name),
                "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=self.region_name),
            },
            build_spec=codebuild.BuildSpec.from_source_filename("buildspec/lambda-functions.yml"),
            artifacts=codebuild.Artifacts.s3(
                bucket=self.artifacts_bucket,
                include_build_id=False,
                package_zip=False,
                path="lambda-functions",
            ),
        )

        # Set removal policy
        project.apply_removal_policy(RemovalPolicy.DESTROY)

        return project

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "S3BucketName", value=self.artifacts_bucket.bucket_name, description="S3 bucket for Lambda artifacts")

        CfnOutput(self, "CodeBuildRoleArn", value=self.codebuild_role.role_arn, description="ARN of the shared CodeBuild IAM role")

        CfnOutput(
            self,
            "LambdaLayerProjectName",
            value=self.lambda_layer_project.project_name,
            description="CodeBuild project for Lambda layer",
        )

        CfnOutput(
            self,
            "LambdaFunctionsProjectName",
            value=self.lambda_functions_project.project_name,
            description="CodeBuild project for Lambda functions",
        )
