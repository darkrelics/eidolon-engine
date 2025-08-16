"""S3 stack for Eidolon Engine scripts bucket."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class S3Stack(Stack):
    """S3 stack for Eidolon Engine scripts storage."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        scripts_bucket: str = "",
        bucket_exists: bool = False,
        **kwargs,
    ) -> None:
        """Initialize S3 stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            scripts_bucket: S3 bucket name for Lua scripts
            bucket_exists: Whether the S3 bucket already exists
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.scripts_bucket_name = scripts_bucket
        super().__init__(scope, stack_id, **kwargs)

        # Import existing bucket or create new one with fixed logical ID
        if bucket_exists:
            print(f"  Using existing S3 bucket: {self.scripts_bucket_name}")
            bucket = s3.Bucket.from_bucket_name(self, "ScriptsBucket", self.scripts_bucket_name)  # Fixed logical ID
        else:
            bucket = s3.Bucket(
                self,
                "ScriptsBucket",  # Fixed logical ID - won't change between deployments
                bucket_name=self.scripts_bucket_name,
                removal_policy=RemovalPolicy.RETAIN,
                auto_delete_objects=False,
                block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            )

        # Store bucket reference
        self.scripts_bucket = bucket

        # Create managed policy for S3 access
        self.s3_policy = iam.ManagedPolicy(
            self,
            "ScriptsS3Policy",
            managed_policy_name="eidolon-scripts-s3-policy",
            description="Policy for read/write access to scripts bucket",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"],
                    resources=[bucket.bucket_arn, f"{bucket.bucket_arn}/*"],
                )
            ],
        )

        # Add outputs
        self._add_outputs()

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "ScriptsBucketName", value=self.scripts_bucket.bucket_name, description="S3 bucket for Lua scripts")

        CfnOutput(
            self, "ScriptsS3PolicyArn", value=self.s3_policy.managed_policy_arn, description="ARN of the scripts S3 access policy"
        )
