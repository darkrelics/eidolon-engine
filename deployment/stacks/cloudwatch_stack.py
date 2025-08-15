"""CloudWatch stack for logging and monitoring."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct


class CloudWatchStack(Stack):
    """CloudWatch stack for Eidolon Engine logging and metrics."""

    def __init__(self, scope: Construct, stack_id: str, region_name: str = "us-east-1", 
                 existing_log_group: str = "", **kwargs) -> None:
        """Initialize CloudWatch stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            existing_log_group: Name of existing log group to import (empty if none)
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.existing_log_group = existing_log_group
        super().__init__(scope, stack_id, **kwargs)

        # Create or import log group
        self.log_group = self._create_log_group()

        # Define metrics namespace
        self.metrics_namespace = "eidolon/metrics"

        # Create managed policy for CloudWatch access
        self.cloudwatch_policy = self._create_cloudwatch_policy()

        # Add outputs
        self._add_outputs()

    def _create_log_group(self) -> logs.ILogGroup:
        """Create or import the server log group."""
        log_group_name = "/eidolon/server"

        # Check if we should import from context
        if self.existing_log_group:
            print(f"  Using existing log group from context: {self.existing_log_group}")
            return logs.LogGroup.from_log_group_name(self, "ServerLogGroup", self.existing_log_group)

        print(f"  Creating/updating log group: {log_group_name}")
        return logs.LogGroup(
            self,
            "ServerLogGroup",
            log_group_name=log_group_name,
            retention=logs.RetentionDays.ONE_YEAR,
            removal_policy=RemovalPolicy.RETAIN,
        )

    def _create_cloudwatch_policy(self) -> iam.ManagedPolicy:
        """Create managed policy for CloudWatch access."""
        policy_name = "eidolon-cloudwatch-policy"

        print(f"  Creating managed policy: {policy_name}")
        return iam.ManagedPolicy(
            self,
            "CloudWatchPolicy",
            managed_policy_name=policy_name,
            description="Policy for Eidolon Engine CloudWatch access",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
                    resources=[self.log_group.log_group_arn, f"{self.log_group.log_group_arn}:*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["cloudwatch:PutMetricData"],
                    resources=["*"],
                    conditions={"StringEquals": {"cloudwatch:namespace": self.metrics_namespace}},
                ),
            ],
        )

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(self, "LogGroupName", value=self.log_group.log_group_name, description="CloudWatch Log Group name")

        CfnOutput(self, "MetricsNamespace", value=self.metrics_namespace, description="CloudWatch Metrics namespace")

        CfnOutput(
            self,
            "CloudWatchPolicyArn",
            value=self.cloudwatch_policy.managed_policy_arn,
            description="ARN of the CloudWatch access policy",
        )
