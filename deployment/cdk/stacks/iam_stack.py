"""AWS IAM stack for server execution role."""

from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from constructs import Construct


def create_composite_principal():
    """Create a composite principal for EC2 and ECS services.

    Returns:
        CompositePrincipal that allows both EC2 and ECS to assume the role
    """
    return iam.CompositePrincipal(
        iam.ServicePrincipal("ec2.amazonaws.com"),  # type: ignore
        iam.ServicePrincipal("ecs-tasks.amazonaws.com"),  # type: ignore
    )


def create_execution_role(scope: Construct, role_id: str, game_name: str, principal: iam.CompositePrincipal) -> iam.Role:
    """Create an IAM execution role for the server.

    Args:
        scope: CDK construct scope
        role_id: Identifier for the role construct
        game_name: Name of the game for resource naming
        principal: Principal that can assume this role

    Returns:
        IAM Role for server execution
    """
    return iam.Role(
        scope,
        role_id,
        role_name=f"{game_name}-server-execution-role",
        assumed_by=principal,  # type: ignore
        description="Execution role for Eidolon Engine server on EC2 or Fargate",
    )


def attach_managed_policies(scope: Construct, role: iam.Role, cloudwatch_policy_arn: str, dynamodb_policy_arn: str) -> None:
    """Attach managed policies to the execution role.

    Args:
        scope: CDK construct scope
        role: IAM role to attach policies to
        cloudwatch_policy_arn: ARN of the CloudWatch access policy
        dynamodb_policy_arn: ARN of the DynamoDB access policy
    """
    # Validate ARNs early
    if not cloudwatch_policy_arn:
        raise ValueError("CloudWatch policy ARN is required")
    if not dynamodb_policy_arn:
        raise ValueError("DynamoDB policy ARN is required")

    # Import and attach CloudWatch policy
    cloudwatch_policy = iam.ManagedPolicy.from_managed_policy_arn(scope, "imported-cloudwatch-policy", cloudwatch_policy_arn)
    role.add_managed_policy(cloudwatch_policy)

    # Import and attach DynamoDB policy
    dynamodb_policy = iam.ManagedPolicy.from_managed_policy_arn(scope, "imported-dynamodb-policy", dynamodb_policy_arn)
    role.add_managed_policy(dynamodb_policy)


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
        # Fail-early validation
        if not game_name:
            raise ValueError("game_name is required")
        if not cloudwatch_policy_arn:
            raise ValueError("cloudwatch_policy_arn is required")
        if not dynamodb_policy_arn:
            raise ValueError("dynamodb_policy_arn is required")

        super().__init__(scope, construct_id, **kwargs)

        # Create composite principal for both EC2 and ECS
        composite_principal = create_composite_principal()

        # Create execution role with the composite principal
        self.execution_role = create_execution_role(self, "server-execution-role", game_name, composite_principal)

        # Attach managed policies
        attach_managed_policies(self, self.execution_role, cloudwatch_policy_arn, dynamodb_policy_arn)

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

        # Use getattr with sensible default for instance profile name
        instance_profile_name = getattr(self.instance_profile, "instance_profile_name", f"{game_name}-server-instance-profile")

        CfnOutput(
            self,
            "ServerInstanceProfileName",
            value=instance_profile_name,
            description="Name of the EC2 instance profile",
        )
