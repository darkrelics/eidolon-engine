"""SSM Parameter Store stack for Eidolon Engine."""

import aws_cdk as cdk
from aws_cdk import aws_ssm as ssm
from constructs import Construct


class SSMStack(cdk.Stack):
    """Creates SSM parameters for Eidolon Engine."""

    def __init__(self, scope: Construct, ssm_id: str, config: dict, **kwargs):
        super().__init__(scope, ssm_id, **kwargs)

        game_name = config.get("game_name", "eidolon-engine")

        # Create segment poller state parameter
        self.segment_poller_state = ssm.StringParameter(
            self,
            "segment-poller-state",
            parameter_name=f"/{game_name}/segment-poller-state",
            string_value="stop",
            description="Controls the segment polling state (run/stop)",
            tier=ssm.ParameterTier.STANDARD,
        )

        # Export parameter name for use in other stacks
        cdk.CfnOutput(
            self,
            "SegmentPollerStateParameterName",
            value=self.segment_poller_state.parameter_name,
            export_name=f"{self.stack_name}-SegmentPollerStateParameterName",
        )
