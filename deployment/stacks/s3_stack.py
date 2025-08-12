"""S3 stack for Eidolon Engine scripts bucket."""

import boto3
from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from botocore.exceptions import ClientError
from constructs import Construct


class S3Stack(Stack):
    """Creates S3 bucket and access policy for Eidolon Engine scripts."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        scripts_bucket: str = "",
        **kwargs
    ) -> None:
        """Initialize S3 stack."""
        self.region_name = region_name
        self.scripts_bucket_name = scripts_bucket
        super().__init__(scope, stack_id, **kwargs)

        # Create or import S3 bucket for scripts
        if self._bucket_exists(self.scripts_bucket_name):
            print(f"Importing existing S3 bucket: {self.scripts_bucket_name}")
            bucket = s3.Bucket.from_bucket_name(
                self, "ScriptsBucket", self.scripts_bucket_name
            )
        else:
            print(f"Creating new S3 bucket: {self.scripts_bucket_name}")
            bucket = s3.Bucket(
                self,
                "ScriptsBucket",
                bucket_name=self.scripts_bucket_name,
                removal_policy=RemovalPolicy.RETAIN,
                versioned=True,
            )

        # Store bucket reference
        self.scripts_bucket = bucket

        # Create managed policy for S3 access
        s3_policy = iam.ManagedPolicy(
            self,
            "ScriptsS3Policy",
            managed_policy_name="eidolon-scripts-s3-policy",
            description="Policy for read/write access to scripts bucket",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "s3:GetObject",
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket"
                    ],
                    resources=[
                        bucket.bucket_arn,
                        f"{bucket.bucket_arn}/*"
                    ]
                )
            ]
        )

        # Create outputs
        CfnOutput(
            self,
            "ScriptsBucketName",
            value=bucket.bucket_name,
            description="S3 bucket for Lua scripts"
        )

        CfnOutput(
            self,
            "ScriptsS3PolicyArn",
            value=s3_policy.managed_policy_arn,
            description="ARN of the scripts S3 access policy"
        )

    def _bucket_exists(self, bucket_name: str) -> bool:
        """Check if S3 bucket exists.
        
        Args:
            bucket_name: Name of the bucket to check
            
        Returns:
            True if bucket exists, False otherwise
        """
        if not bucket_name:
            return False
            
        try:
            s3_client = boto3.client("s3", region_name=self.region_name)
            s3_client.head_bucket(Bucket=bucket_name)
            return True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code in ["404", "NoSuchBucket"]:
                return False
            # If it's a permission error, assume bucket exists
            if error_code == "403":
                print(f"Warning: Cannot verify bucket {bucket_name} - permission denied, assuming it exists")
                return True
        return False