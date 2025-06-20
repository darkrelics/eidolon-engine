"""AWS CloudWatch stack for logging and monitoring."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct


class CloudWatchStack(Stack):
    """CloudWatch stack for Eidolon Engine logging and metrics."""

    def __init__(
        self, scope: Construct, construct_id: str, game_name: str, dynamodb_policy_arn: str, retention_days: int = 365, **kwargs
    ) -> None:
        """Initialize CloudWatch stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            retention_days: Log retention period in days
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create Log Group
        self.log_group = logs.LogGroup(
            self,
            "logs",
            log_group_name="/aws/eidolon/server",
            retention=logs.RetentionDays(retention_days),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Create metrics namespace (this is just for documentation)
        self.metrics_namespace = "eidolon/metrics"

        # Create IAM policy for CloudWatch access
        self.cloudwatch_policy = iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"],
                    resources=[self.log_group.log_group_arn, f"{self.log_group.log_group_arn}:log-stream:*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["cloudwatch:PutMetricData"],
                    resources=["*"],
                    conditions={"StringEquals": {"cloudwatch:namespace": self.metrics_namespace}},
                ),
            ]
        )

        # Create managed policy
        self.access_policy = iam.ManagedPolicy(
            self,
            "cloudwatch-access",
            managed_policy_name="eidolon-cloudwatch-access",
            document=self.cloudwatch_policy,
            description="Policy for accessing Eidolon Engine CloudWatch resources",
        )

        # Output values
        CfnOutput(self, "LogGroupName", value=self.log_group.log_group_name, description="CloudWatch Log Group name")

        CfnOutput(self, "MetricsNamespace", value=self.metrics_namespace, description="CloudWatch Metrics namespace")

        CfnOutput(
            self,
            "CloudWatchAccessPolicyArn",
            value=self.access_policy.managed_policy_arn,
            description="ARN of the CloudWatch access policy",
        )
