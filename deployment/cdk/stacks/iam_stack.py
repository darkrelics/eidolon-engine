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


def create_dynamodb_policy(scope: Construct, game_name: str) -> iam.ManagedPolicy:
    """Create DynamoDB access policy.

    Args:
        scope: CDK construct scope
        game_name: Name of the game for resource naming

    Returns:
        Managed policy for DynamoDB access
    """
    # Table names that will be created
    table_names = ["players", "characters", "rooms", "exits", "items", "prototypes", "archetypes", "motd", "story"]
    table_arns = [f"arn:aws:dynamodb:{scope.region}:{scope.account}:table/{name}" for name in table_names]
    
    return iam.ManagedPolicy(
        scope,
        "dynamodb-access",
        managed_policy_name=f"eidolon-{game_name}-dynamodb-access",
        document=iam.PolicyDocument(
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                        "dynamodb:BatchGetItem",
                        "dynamodb:BatchWriteItem",
                    ],
                    resources=table_arns,
                )
            ]
        ),
        description=f"Policy for accessing {game_name} DynamoDB tables",
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

        # Create and attach policies
        self.cloudwatch_policy = create_cloudwatch_policy(self, game_name)
        self.dynamodb_policy = create_dynamodb_policy(self, game_name)
        
        # Attach policies to role
        self.execution_role.add_managed_policy(self.cloudwatch_policy)
        self.execution_role.add_managed_policy(self.dynamodb_policy)

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
        
        CfnOutput(
            self,
            "CloudWatchPolicyArn",
            value=self.cloudwatch_policy.managed_policy_arn,
            description="ARN of the CloudWatch access policy",
        )
        
        CfnOutput(
            self,
            "DynamoDBPolicyArn",
            value=self.dynamodb_policy.managed_policy_arn,
            description="ARN of the DynamoDB access policy",
        )
