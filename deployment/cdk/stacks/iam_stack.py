"""AWS IAM stack for server execution role."""

import boto3
from aws_cdk import CfnOutput, Stack
from aws_cdk import aws_iam as iam
from botocore.exceptions import ClientError
from constructs import Construct


def check_policy_exists(policy_name: str, region: str) -> bool:
    """Check if an IAM policy already exists.
    
    Args:
        policy_name: Name of the policy to check
        region: AWS region
        
    Returns:
        True if policy exists, False otherwise
    """
    try:
        iam_client = boto3.client("iam", region_name=region)
        # List policies and check if our policy exists
        paginator = iam_client.get_paginator('list_policies')
        for page in paginator.paginate(Scope='Local'):
            for policy in page['Policies']:
                if policy['PolicyName'] == policy_name:
                    return True
        return False
    except ClientError:
        return False


def get_existing_policy_arn(policy_name: str, account: str) -> str:
    """Get ARN of existing policy.
    
    Args:
        policy_name: Name of the policy
        account: AWS account ID
        
    Returns:
        Policy ARN
    """
    return f"arn:aws:iam::{account}:policy/{policy_name}"


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


def create_cloudwatch_policy(scope: Construct, game_name: str) -> iam.ManagedPolicy:
    """Create CloudWatch access policy.

    Args:
        scope: CDK construct scope
        game_name: Name of the game for resource naming

    Returns:
        Managed policy for CloudWatch access
    """
    return iam.ManagedPolicy(
        scope,
        "cloudwatch-access",
        managed_policy_name=f"eidolon-{game_name}-cloudwatch-access",
        document=iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "logs:CreateLogGroup",
                        "logs:CreateLogStream",
                        "logs:PutLogEvents",
                        "logs:DescribeLogStreams",
                    ],
                    resources=[f"arn:aws:logs:{scope.region}:{scope.account}:log-group:/aws/eidolon/*"],
                ),
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "cloudwatch:PutMetricData",
                    ],
                    resources=["*"],
                ),
            ]
        ),
        description=f"Policy for accessing {game_name} CloudWatch logs and metrics",
    )




class IAMStack(Stack):
    """IAM stack for Eidolon Engine server execution role."""

    def __init__(
        self, scope: Construct, construct_id: str, game_name: str, **kwargs
    ) -> None:
        """Initialize IAM stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            **kwargs: Additional stack properties
        """
        # Fail-early validation
        if not game_name:
            raise ValueError("game_name is required")

        super().__init__(scope, construct_id, **kwargs)

        # Create composite principal for both EC2 and ECS
        composite_principal = create_composite_principal()

        # Create execution role with the composite principal
        self.execution_role = create_execution_role(self, "server-execution-role", game_name, composite_principal)

        # Check if CloudWatch policy already exists
        cloudwatch_policy_name = f"eidolon-{game_name}-cloudwatch-access"
        
        # Create or reference CloudWatch policy
        if check_policy_exists(cloudwatch_policy_name, self.region):
            print(f"  Using existing CloudWatch policy: {cloudwatch_policy_name}")
            # Reference existing policy
            cloudwatch_policy_arn = get_existing_policy_arn(cloudwatch_policy_name, self.account)
            self.cloudwatch_policy = iam.ManagedPolicy.from_managed_policy_arn(
                self, "cloudwatch-access-ref", cloudwatch_policy_arn
            )
        else:
            print(f"  Creating new CloudWatch policy: {cloudwatch_policy_name}")
            self.cloudwatch_policy = create_cloudwatch_policy(self, game_name)
        
        # Attach CloudWatch policy to role
        self.execution_role.add_managed_policy(self.cloudwatch_policy)
        
        # Note: Resource-specific policies are created by their respective stacks

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
        
        # Output policy ARNs
        CfnOutput(
            self,
            "CloudWatchPolicyArn",
            value=self.cloudwatch_policy.managed_policy_arn,
            description="ARN of the CloudWatch access policy",
        )
