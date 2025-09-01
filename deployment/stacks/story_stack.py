"""Story processing stack with Lambda functions, SSM, SQS, and EventBridge."""

import aws_cdk as cdk
from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, Tags
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_lambda_event_sources as lambda_event_sources
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class StoryStack(Stack):
    """Story processing stack for Eidolon Engine."""

    def __init__(
        self,
        scope: Construct,
        stack_id: str,
        region_name: str = "us-east-1",
        s3_bucket: str = "",
        client_fqdn: str = "",
        dynamodb_policy_arn: str = "",
        dynamodb_tables=None,
        lambda_layer_arn: str = "",
        lambda_role_arn: str = "",
        **kwargs,
    ) -> None:
        """Initialize Story stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            s3_bucket: S3 bucket containing Lambda artifacts
            client_fqdn: Client FQDN for CORS configuration
            dynamodb_policy_arn: ARN of DynamoDB policy to attach
            dynamodb_tables: Dictionary of DynamoDB table names
            lambda_layer_arn: ARN of shared Lambda layer from Character stack
            lambda_role_arn: ARN of shared Lambda execution role from Character stack
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.s3_bucket_name = s3_bucket
        self.client_fqdn = client_fqdn
        self.dynamodb_policy_arn = dynamodb_policy_arn
        self.dynamodb_tables = dynamodb_tables or {}
        self.lambda_layer_arn = lambda_layer_arn
        self.lambda_role_arn = lambda_role_arn

        super().__init__(scope, stack_id, **kwargs)
        # Apply system tag to all resources in this stack
        Tags.of(self).add("System", "Eidolon")

        # Create SSM Parameter for story configuration
        self.story_param = self._create_ssm_parameter()

        # Create SQS Queues
        self.processing_queue = self._create_processing_queue()
        self.advancement_queue = self._create_advancement_queue()

        # Create IAM Policy for Story operations
        self.story_policy = self._create_story_policy()

        # Import shared Lambda layer and role from Character stack
        self.lambda_layer = self._import_lambda_layer()
        self.lambda_role = self._import_lambda_role()

        # Deploy story Lambda functions
        self.functions = {}
        self._deploy_lambda_functions()

        # Configure SQS triggers for Lambda functions
        self._configure_sqs_triggers()

        # Create EventBridge rule for polling (starts disabled)
        self.polling_rule = self._create_polling_rule()

        # Add outputs
        self._add_outputs()

    def _create_ssm_parameter(self) -> ssm.StringParameter:
        """Create SSM Parameter for story configuration."""
        print("  Creating SSM Parameter: /eidolon/story/config")

        # Default story configuration
        default_config = '{"enabled": false, "polling_interval": 60}'

        return ssm.StringParameter(
            self,
            "StoryConfigParameter",
            parameter_name="/eidolon/story/config",
            string_value=default_config,
            description="Story processing configuration for Eidolon Engine",
            tier=ssm.ParameterTier.STANDARD,
        )

    def _create_processing_queue(self) -> sqs.Queue:
        """Create SQS queue for segment processing."""
        print("  Creating SQS Queue: eidolon-processing-queue")

        return sqs.Queue(
            self,
            "ProcessingQueue",
            queue_name="eidolon-processing-queue",
            visibility_timeout=Duration.seconds(90),  # 3x Lambda timeout
            retention_period=Duration.days(1),
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _create_advancement_queue(self) -> sqs.Queue:
        """Create SQS queue for story advancement."""
        print("  Creating SQS Queue: eidolon-advancement-queue")

        return sqs.Queue(
            self,
            "AdvancementQueue",
            queue_name="eidolon-advancement-queue",
            visibility_timeout=Duration.seconds(90),  # 3x Lambda timeout
            retention_period=Duration.days(1),
            removal_policy=RemovalPolicy.DESTROY,
        )

    def _create_story_policy(self) -> iam.ManagedPolicy:
        """Create IAM policy for story operations."""
        print("  Creating IAM Policy: eidolon-story-policy")

        return iam.ManagedPolicy(
            self,
            "StoryPolicy",
            managed_policy_name="eidolon-story-policy",
            description="Permissions for story processing operations",
            statements=[
                # SSM Parameter permissions
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["ssm:GetParameter", "ssm:GetParameters", "ssm:PutParameter"],
                    resources=[f"arn:aws:ssm:{self.region_name}:{self.account}:parameter/eidolon/story/*"],
                ),
                # SQS permissions
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "sqs:SendMessage",
                        "sqs:ReceiveMessage",
                        "sqs:DeleteMessage",
                        "sqs:GetQueueAttributes",
                        "sqs:GetQueueUrl",
                    ],
                    resources=[self.processing_queue.queue_arn, self.advancement_queue.queue_arn],
                ),
                # EventBridge permissions for enabling/disabling the polling rule
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=["events:EnableRule", "events:DisableRule"],
                    resources=[f"arn:aws:events:{self.region_name}:{self.account}:rule/eidolon-story-poller"],
                ),
            ],
        )

    def _import_lambda_layer(self) -> lambda_.ILayerVersion:
        """Import shared Lambda layer from Character stack."""
        if self.lambda_layer_arn:
            return lambda_.LayerVersion.from_layer_version_arn(self, "ImportedLambdaLayer", self.lambda_layer_arn)
        else:
            # Try to import from CloudFormation export
            try:
                layer_arn = cdk.Fn.import_value("eidolon-lambda-layer-arn")
                return lambda_.LayerVersion.from_layer_version_arn(self, "ImportedLambdaLayer", layer_arn)
            except Exception as e:
                print(f"  Warning: Failed to import Lambda layer from CloudFormation export: {e}")
                raise ValueError("Lambda layer ARN not provided and CloudFormation export not found")

    def _import_lambda_role(self) -> iam.IRole:
        """Import shared Lambda execution role from Character stack."""
        if self.lambda_role_arn:
            # Use unique logical ID to avoid conflict with _attach_policy_to_role
            return iam.Role.from_role_arn(self, "ImportedLambdaRoleForFunctions", self.lambda_role_arn)
        else:
            # Try to import from CloudFormation export
            try:
                role_arn = cdk.Fn.import_value("eidolon-lambda-role-arn")
                return iam.Role.from_role_arn(self, "ImportedLambdaRoleForFunctions", role_arn)
            except Exception as e:
                print(f"  Warning: Failed to import Lambda role from CloudFormation export: {e}")
                raise ValueError("Lambda role ARN not provided and CloudFormation export not found")

    def _deploy_lambda_functions(self) -> None:
        """Deploy story-related Lambda functions."""

        # Story Lambda functions
        lambda_configs = [
            # Story API functions
            ("api-story-start", "api_story_start.lambda_handler"),
            ("api-story-abandon", "api_story_abandon.lambda_handler"),
            ("api-segment-decision", "api_segment_decision.lambda_handler"),
            ("api-segment-history", "api_segment_history.lambda_handler"),
            ("api-segment-rest", "api_segment_rest.lambda_handler"),
            ("api-segment-status", "api_segment_status.lambda_handler"),
            # Operations functions
            ("ops-segment-poller", "ops_segment_poller.lambda_handler"),
            ("ops-segment-process", "ops_segment_process.lambda_handler"),
            ("ops-story-advance", "ops_story_advance.lambda_handler"),
        ]

        # Get common environment variables with queue URLs
        env_vars = self._get_environment_variables()

        bucket = s3.Bucket.from_bucket_name(self, "FunctionsBucket", self.s3_bucket_name)

        for function_name, handler in lambda_configs:
            print(f"  Deploying Lambda function: {function_name}")

            # Use fixed logical ID for each function
            logical_id = self._get_function_logical_id(function_name)

            self.functions[function_name] = lambda_.Function(
                self,
                logical_id,
                function_name=function_name,
                runtime=lambda_.Runtime.PYTHON_3_12,
                handler=handler,
                code=lambda_.Code.from_bucket(bucket, f"{function_name}.zip"),
                layers=[self.lambda_layer],
                role=self.lambda_role,
                timeout=Duration.seconds(30),
                memory_size=128,
                environment=env_vars,
                description=f"Eidolon Engine {function_name} function",
            )

    def _get_function_logical_id(self, function_name: str) -> str:
        """Get fixed logical ID for a Lambda function."""
        logical_id_map = {
            "api-story-start": "ApiStoryStartFunction",
            "api-story-abandon": "ApiStoryAbandonFunction",
            "api-segment-decision": "ApiSegmentDecisionFunction",
            "api-segment-history": "ApiSegmentHistoryFunction",
            "api-segment-rest": "ApiSegmentRestFunction",
            "api-segment-status": "ApiSegmentStatusFunction",
            "ops-segment-poller": "OpsSegmentPollerFunction",
            "ops-segment-process": "OpsSegmentProcessFunction",
            "ops-story-advance": "OpsStoryAdvanceFunction",
        }
        return logical_id_map.get(function_name, function_name.replace("-", "").title() + "Function")

    def _get_environment_variables(self) -> dict:
        """Get environment variables for Lambda functions."""
        # Use client FQDN for CORS origin
        cors_origin = f"https://{self.client_fqdn}" if self.client_fqdn else "*"

        env_vars = {
            "APPLICATION_NAME": "eidolon-engine",
            "LOG_LEVEL": "INFO",
            "ALLOWED_ORIGINS": cors_origin,
            "CORS_ALLOW_CREDENTIALS": "true",
            "CORS_ALLOW_HEADERS": "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token",
            "CORS_ALLOW_METHODS": "GET,POST,PUT,DELETE,OPTIONS",
            "CORS_MAX_AGE": "86400",
            # Add queue URLs
            "SEGMENT_QUEUE_URL": self.processing_queue.queue_url,
            "STORY_ADVANCEMENT_QUEUE_URL": self.advancement_queue.queue_url,
        }

        # Add DynamoDB table names
        table_mapping = {
            "story_table": "story",
            "segments_table": "segments",
            "active_segments_table": "active_segments",
            "story_history_table": "story_history",
            "segment_history_table": "segment_history",
            "characters_table": "characters",
            "opponents_table": "opponents",
        }

        for env_key, table_key in table_mapping.items():
            env_vars[env_key] = self.dynamodb_tables.get(table_key, table_key)

        return env_vars

    def _configure_sqs_triggers(self) -> None:
        """Configure SQS triggers for Lambda functions."""
        # Configure processing queue trigger for ops-segment-process
        if "ops-segment-process" in self.functions:
            print("  Configuring SQS trigger for ops-segment-process")
            process_function = self.functions["ops-segment-process"]
            process_function.add_event_source(
                lambda_event_sources.SqsEventSource(self.processing_queue, batch_size=10, max_batching_window=Duration.seconds(5))
            )

        # Configure advancement queue trigger for ops-story-advance
        if "ops-story-advance" in self.functions:
            print("  Configuring SQS trigger for ops-story-advance")
            advance_function = self.functions["ops-story-advance"]
            advance_function.add_event_source(
                lambda_event_sources.SqsEventSource(self.advancement_queue, batch_size=10, max_batching_window=Duration.seconds(5))
            )

    def _create_polling_rule(self) -> events.Rule:
        """Create EventBridge rule for polling (starts disabled)."""
        print("  Creating EventBridge Rule: eidolon-story-poller (disabled)")

        # Get the poller Lambda function we created
        if "ops-segment-poller" not in self.functions:
            raise ValueError("ops-segment-poller function not found")

        poller_function = self.functions["ops-segment-poller"]

        # Create the rule (starts disabled)
        rule = events.Rule(
            self,
            "PollingRule",
            rule_name="eidolon-story-poller",
            description="Polls for story segments to process",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            enabled=False,  # Starts disabled
        )

        # Add Lambda target with removal policy
        # The target will be automatically removed when the rule is deleted
        rule.add_target(
            targets.LambdaFunction(
                poller_function,
                retry_attempts=2,
                max_event_age=Duration.minutes(5),
            )  # type: ignore
        )

        # Grant EventBridge permission to invoke Lambda
        poller_function.add_permission(
            "EventBridgeInvokePermission",
            principal=iam.ServicePrincipal("events.amazonaws.com"),  # type: ignore
            source_arn=rule.rule_arn,
        )

        # Apply removal policy to ensure clean deletion
        rule.apply_removal_policy(RemovalPolicy.DESTROY)

        return rule

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(
            self,
            "SSMParameterName",
            value=self.story_param.parameter_name,
            description="SSM Parameter name for story configuration",
        )

        CfnOutput(
            self,
            "ProcessingQueueUrl",
            value=self.processing_queue.queue_url,
            description="URL of the processing queue",
            export_name="eidolon-processing-queue-url",
        )

        CfnOutput(
            self,
            "AdvancementQueueUrl",
            value=self.advancement_queue.queue_url,
            description="URL of the advancement queue",
            export_name="eidolon-advancement-queue-url",
        )

        CfnOutput(self, "ProcessingQueueArn", value=self.processing_queue.queue_arn, description="ARN of the processing queue")

        CfnOutput(self, "AdvancementQueueArn", value=self.advancement_queue.queue_arn, description="ARN of the advancement queue")

        if hasattr(self, "polling_rule"):
            CfnOutput(
                self, "EventBridgeRuleName", value=self.polling_rule.rule_name, description="Name of the EventBridge polling rule"
            )

            CfnOutput(
                self, "EventBridgeRuleArn", value=self.polling_rule.rule_arn, description="ARN of the EventBridge polling rule"
            )

        CfnOutput(self, "StoryPolicyArn", value=self.story_policy.managed_policy_arn, description="ARN of the story IAM policy")
