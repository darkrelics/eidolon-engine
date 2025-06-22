"""AWS IAM stack for server execution role."""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


class IAMStack(Stack):
    """IAM stack for Eidolon Engine server execution role."""

    def __init__(
        self, scope: Construct, construct_id: str, game_name: str, cloudwatch_policy_arn: str, dynamodb_policy_arn: str, **kwargs
    ) -> None:
        """Initialize IAM stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            cloudwatch_policy_arn: ARN of the CloudWatch access policy
            dynamodb_policy_arn: ARN of the DynamoDB access policy
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Create principals for EC2 and Fargate
        ec2_principal = iam.ServicePrincipal("ec2.amazonaws.com")
        ecs_principal = iam.ServicePrincipal("ecs-tasks.amazonaws.com")
        
        # Create execution role with trust policy for EC2 and Fargate
        self.execution_role = iam.Role(
            self,
            "server-execution-role",
            role_name=f"{game_name}-server-execution-role",
            assumed_by=iam.CompositePrincipal(ec2_principal, ecs_principal),
            description="Execution role for Eidolon Engine server on EC2 or Fargate",
        )

        # Attach the CloudWatch managed policy
        cloudwatch_policy = iam.ManagedPolicy.from_managed_policy_arn(self, "imported-cloudwatch-policy", cloudwatch_policy_arn)
        self.execution_role.add_managed_policy(cloudwatch_policy)

        # Attach the DynamoDB managed policy
        dynamodb_policy = iam.ManagedPolicy.from_managed_policy_arn(self, "imported-dynamodb-policy", dynamodb_policy_arn)
        self.execution_role.add_managed_policy(dynamodb_policy)

        # Create instance profile for EC2 use
        self.instance_profile = iam.CfnInstanceProfile(
            self,
            "server-instance-profile",
            instance_profile_name=f"{game_name}-server-instance-profile",
            roles=[self.execution_role.role_name],
        )

        # Output values
        CfnOutput(
            self,
            "ServerExecutionRoleArn",
            value=self.execution_role.role_arn,
            description="ARN of the server execution role",
        )

        CfnOutput(
            self,
            "ServerInstanceProfileName",
            value=self.instance_profile.instance_profile_name or f"{game_name}-server-instance-profile",
            description="Name of the EC2 instance profile",
        )
