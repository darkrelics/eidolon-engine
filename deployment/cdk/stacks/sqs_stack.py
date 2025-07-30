"""SQS queue stack for Eidolon Engine."""

import aws_cdk as cdk
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class SQSStack(cdk.Stack):
    """Creates SQS queues for Eidolon Engine."""

    def __init__(self, scope: Construct, sqs_id: str, config: dict, **kwargs):
        super().__init__(scope, sqs_id, **kwargs)

        game_name = config.get("game_name", "eidolon")

        # Create segment processing queue without DLQ
        self.segment_queue = sqs.Queue(
            self,
            "segment-processing-queue",
            queue_name=f"{game_name}-segments",
            visibility_timeout=cdk.Duration.seconds(180),  # 3x Lambda timeout
            retention_period=cdk.Duration.days(4),
            receive_message_wait_time=cdk.Duration.seconds(20),  # Long polling
        )

        # Create story advancement queue for processing segments at end time
        self.story_advancement_queue = sqs.Queue(
            self,
            "story-advancement-queue",
            queue_name=f"{game_name}-story-advancement",
            visibility_timeout=cdk.Duration.seconds(180),  # 3x Lambda timeout
            retention_period=cdk.Duration.days(4),
            receive_message_wait_time=cdk.Duration.seconds(20),  # Long polling
            max_message_size_bytes=262144,  # 256KB for larger segment data
        )

        # Export queue details
        cdk.CfnOutput(
            self,
            "SegmentProcessingQueueUrl",
            value=self.segment_queue.queue_url,
            export_name=f"{self.stack_name}-SegmentProcessingQueueUrl",
        )

        cdk.CfnOutput(
            self,
            "SegmentProcessingQueueArn",
            value=self.segment_queue.queue_arn,
            export_name=f"{self.stack_name}-SegmentProcessingQueueArn",
        )

        cdk.CfnOutput(
            self,
            "SegmentProcessingQueueName",
            value=self.segment_queue.queue_name,
            export_name=f"{self.stack_name}-SegmentProcessingQueueName",
        )

        # Export story advancement queue details
        cdk.CfnOutput(
            self,
            "StoryAdvancementQueueUrl",
            value=self.story_advancement_queue.queue_url,
            export_name=f"{self.stack_name}-StoryAdvancementQueueUrl",
        )

        cdk.CfnOutput(
            self,
            "StoryAdvancementQueueArn",
            value=self.story_advancement_queue.queue_arn,
            export_name=f"{self.stack_name}-StoryAdvancementQueueArn",
        )

        cdk.CfnOutput(
            self,
            "StoryAdvancementQueueName",
            value=self.story_advancement_queue.queue_name,
            export_name=f"{self.stack_name}-StoryAdvancementQueueName",
        )