"""AWS CloudWatch stack for logging and monitoring."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct


class CloudWatchStack(Stack):
    """CloudWatch stack for Eidolon Engine logging and metrics."""

    def __init__(self, scope: Construct, construct_id: str, retention_days: int = 365, **kwargs) -> None:
        """Initialize CloudWatch stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            retention_days: Log retention period in days
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        if retention_days < 1:
            raise ValueError("retention_days must be at least 1")

        # Map retention days to valid enum values
        retention_mapping = {
            1: logs.RetentionDays.ONE_DAY,
            3: logs.RetentionDays.THREE_DAYS,
            5: logs.RetentionDays.FIVE_DAYS,
            7: logs.RetentionDays.ONE_WEEK,
            14: logs.RetentionDays.TWO_WEEKS,
            30: logs.RetentionDays.ONE_MONTH,
            60: logs.RetentionDays.TWO_MONTHS,
            90: logs.RetentionDays.THREE_MONTHS,
            120: logs.RetentionDays.FOUR_MONTHS,
            150: logs.RetentionDays.FIVE_MONTHS,
            180: logs.RetentionDays.SIX_MONTHS,
            365: logs.RetentionDays.ONE_YEAR,
            400: logs.RetentionDays.THIRTEEN_MONTHS,
            545: logs.RetentionDays.EIGHTEEN_MONTHS,
            731: logs.RetentionDays.TWO_YEARS,
            1827: logs.RetentionDays.FIVE_YEARS,
            3653: logs.RetentionDays.TEN_YEARS,
        }

        # Use the closest valid retention period
        retention_enum = retention_mapping.get(retention_days, logs.RetentionDays.ONE_YEAR)

        # Create Log Group
        self.log_group = logs.LogGroup(
            self,
            "logs",
            log_group_name="/aws/eidolon/server",
            retention=retention_enum,
            removal_policy=RemovalPolicy.DESTROY,
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
