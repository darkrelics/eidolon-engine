"""Story processing stack with SSM, SQS, and EventBridge."""

from aws_cdk import Stack, RemovalPolicy, CfnOutput, Duration
from aws_cdk import aws_ssm as ssm
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from constructs import Construct


class StoryStack(Stack):
    """Story processing stack for Eidolon Engine."""
    
    def __init__(self, scope: Construct, stack_id: str, 
                 region_name: str = "us-east-1",
                 lambda_role_arn: str = "",
                 poller_lambda_arn: str = "",
                 processor_lambda_arn: str = "",
                 advance_lambda_arn: str = "",
                 **kwargs) -> None:
        """Initialize Story stack.
        
        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            lambda_role_arn: ARN of Lambda execution role to attach policy to
            poller_lambda_arn: ARN of ops-segment-poller Lambda
            processor_lambda_arn: ARN of ops-segment-process Lambda
            advance_lambda_arn: ARN of ops-story-advance Lambda
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        self.lambda_role_arn = lambda_role_arn
        self.poller_lambda_arn = poller_lambda_arn
        self.processor_lambda_arn = processor_lambda_arn
        self.advance_lambda_arn = advance_lambda_arn
        
        
        super().__init__(scope, stack_id, **kwargs)
        
        # Create SSM Parameter for story configuration
        self.story_param = self._create_ssm_parameter()
        
        # Create SQS Queues
        self.processing_queue = self._create_processing_queue()
        self.advancement_queue = self._create_advancement_queue()
        
        # Create IAM Policy for Story operations
        self.story_policy = self._create_story_policy()
        
        # Attach policy to Lambda role if ARN provided
        if self.lambda_role_arn:
            self._attach_policy_to_role()
        
        # Configure SQS triggers for Lambda functions
        if self.processor_lambda_arn:
            self._configure_sqs_trigger(self.processing_queue, self.processor_lambda_arn, "ProcessorTrigger")
        
        if self.advance_lambda_arn:
            self._configure_sqs_trigger(self.advancement_queue, self.advance_lambda_arn, "AdvanceTrigger")
        
        # Create EventBridge rule for polling (starts disabled)
        if self.poller_lambda_arn:
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
            tier=ssm.ParameterTier.STANDARD
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
            removal_policy=RemovalPolicy.DESTROY
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
            removal_policy=RemovalPolicy.DESTROY
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
                    actions=[
                        "ssm:GetParameter",
                        "ssm:GetParameters",
                        "ssm:PutParameter"
                    ],
                    resources=[
                        f"arn:aws:ssm:{self.region_name}:{self.account}:parameter/eidolon/story/*"
                    ]
                ),
                # SQS permissions
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "sqs:SendMessage",
                        "sqs:ReceiveMessage", 
                        "sqs:DeleteMessage",
                        "sqs:GetQueueAttributes",
                        "sqs:GetQueueUrl"
                    ],
                    resources=[
                        self.processing_queue.queue_arn,
                        self.advancement_queue.queue_arn
                    ]
                )
            ]
        )
    
    def _attach_policy_to_role(self) -> None:
        """Attach story policy to Lambda execution role."""
        print("  Attaching story policy to Lambda role")
        
        # Import the Lambda role
        lambda_role = iam.Role.from_role_arn(
            self,
            "ImportedLambdaRole",
            self.lambda_role_arn
        )
        
        # Attach the policy
        lambda_role.add_managed_policy(self.story_policy)
    
    def _configure_sqs_trigger(self, queue: sqs.Queue, lambda_arn: str, trigger_id: str) -> None:
        """Configure SQS to trigger Lambda function."""
        print("  Configuring SQS trigger for Lambda")
        
        # Import the Lambda function with its role for proper permission grants
        # We need to use from_function_attributes to include the role
        lambda_function = lambda_.Function.from_function_attributes(
            self,
            f"Imported{trigger_id}",
            function_arn=lambda_arn,
            # Use the same role that was passed to the stack
            role=iam.Role.from_role_arn(
                self,
                f"ImportedRole{trigger_id}",
                self.lambda_role_arn
            ) if self.lambda_role_arn else None
        )
        
        # Add SQS event source
        lambda_function.add_event_source_mapping(
            f"{trigger_id}Mapping",
            event_source_arn=queue.queue_arn,
            batch_size=10
        )
        
        # Grant SQS permissions to Lambda execution role
        queue.grant_consume_messages(lambda_function)
    
    def _create_polling_rule(self) -> events.Rule:
        """Create EventBridge rule for polling (starts disabled)."""
        print("  Creating EventBridge Rule: eidolon-story-poller (disabled)")
        
        # Import the Lambda function
        poller_function = lambda_.Function.from_function_arn(
            self,
            "PollerFunction",
            self.poller_lambda_arn
        )
        
        # Create the rule (starts disabled)
        rule = events.Rule(
            self,
            "PollingRule",
            rule_name="eidolon-story-poller",
            description="Polls for story segments to process",
            schedule=events.Schedule.rate(Duration.minutes(1)),
            enabled=False  # Starts disabled
        )
        
        # Add Lambda target
        rule.add_target(targets.LambdaFunction(poller_function))  # type: ignore
        
        # Grant EventBridge permission to invoke Lambda
        poller_function.add_permission(
            "EventBridgeInvokePermission",
            principal=iam.ServicePrincipal("events.amazonaws.com"),  # type: ignore
            source_arn=rule.rule_arn
        )
        
        return rule
    
    def _add_outputs(self) -> None:
        """Add stack outputs."""
        CfnOutput(
            self,
            "SSMParameterName",
            value=self.story_param.parameter_name,
            description="SSM Parameter name for story configuration"
        )
        
        CfnOutput(
            self,
            "ProcessingQueueUrl",
            value=self.processing_queue.queue_url,
            description="URL of the processing queue"
        )
        
        CfnOutput(
            self,
            "AdvancementQueueUrl",
            value=self.advancement_queue.queue_url,
            description="URL of the advancement queue"
        )
        
        CfnOutput(
            self,
            "ProcessingQueueArn",
            value=self.processing_queue.queue_arn,
            description="ARN of the processing queue"
        )
        
        CfnOutput(
            self,
            "AdvancementQueueArn",
            value=self.advancement_queue.queue_arn,
            description="ARN of the advancement queue"
        )
        
        if hasattr(self, 'polling_rule'):
            CfnOutput(
                self,
                "EventBridgeRuleName",
                value=self.polling_rule.rule_name,
                description="Name of the EventBridge polling rule"
            )
            
            CfnOutput(
                self,
                "EventBridgeRuleArn",
                value=self.polling_rule.rule_arn,
                description="ARN of the EventBridge polling rule"
            )
        
        CfnOutput(
            self,
            "StoryPolicyArn",
            value=self.story_policy.managed_policy_arn,
            description="ARN of the story IAM policy"
        )
