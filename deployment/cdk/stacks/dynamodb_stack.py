"""AWS DynamoDB stack for game data storage."""

from aws_cdk import Stack, aws_dynamodb as dynamodb, aws_iam as iam, CfnOutput, RemovalPolicy
from constructs import Construct
import boto3
from botocore.exceptions import ClientError


class DynamoDBStack(Stack):
    """DynamoDB stack for Eidolon Engine game data."""

    def __init__(self, scope: Construct, construct_id: str, game_name: str, **kwargs) -> None:
        """Initialize DynamoDB stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)
        
        # Check for existing tables from context (passed from deploy.py)
        self.existing_tables = {}
        for i in range(8):  # We have 8 table types
            table_types = ["players", "characters", "rooms", "exits", "items", "prototypes", "archetypes", "motd"]
            if i < len(table_types):
                table_type = table_types[i]
                context_key = f"dynamodb_{table_type}_table"
                existing_table_name = self.node.try_get_context(context_key)
                if existing_table_name:
                    self.existing_tables[table_type] = existing_table_name

        # Define table configurations
        table_configs = [
            {"name": "players", "pk": "player_id", "sk": None},
            {"name": "characters", "pk": "player_id", "sk": "character_id"},
            {"name": "rooms", "pk": "room_id", "sk": None},
            {"name": "exits", "pk": "room_id", "sk": "exit_id"},
            {"name": "items", "pk": "item_id", "sk": None},
            {"name": "prototypes", "pk": "prototype_id", "sk": None},
            {"name": "archetypes", "pk": "archetype_id", "sk": None},
            {"name": "motd", "pk": "motd_id", "sk": None},
        ]

        self.tables = {}

        # Create or import DynamoDB tables
        for config in table_configs:
            table_name = f"{game_name}-{config['name']}"
            
            # Check if we should use an existing table
            if config["name"] in self.existing_tables:
                # Import existing table
                existing_table_name = self.existing_tables[config["name"]]
                print(f"Importing existing DynamoDB table: {existing_table_name}")
                
                table = dynamodb.Table.from_table_name(
                    self,
                    f"{game_name}-{config['name']}-imported",
                    existing_table_name
                )
                self.tables[config["name"]] = table
            else:
                # Check if table already exists
                if self._table_exists(table_name):
                    # Import the table
                    print(f"Found existing DynamoDB table: {table_name}, importing...")
                    table = dynamodb.Table.from_table_name(
                        self,
                        f"{game_name}-{config['name']}-imported",
                        table_name
                    )
                    self.tables[config["name"]] = table
                else:
                    # Create new table
                    print(f"Creating new DynamoDB table: {table_name}")
                    
                    # Define partition key
                    partition_key = dynamodb.Attribute(name=config["pk"], type=dynamodb.AttributeType.STRING)

                    # Create table with or without sort key
                    if config["sk"]:
                        sort_key = dynamodb.Attribute(name=config["sk"], type=dynamodb.AttributeType.STRING)
                        table = dynamodb.Table(
                            self,
                            table_name,
                            table_name=table_name,
                            partition_key=partition_key,
                            sort_key=sort_key,
                            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                            removal_policy=RemovalPolicy.RETAIN,
                            point_in_time_recovery=True,
                        )
                    else:
                        table = dynamodb.Table(
                            self,
                            table_name,
                            table_name=table_name,
                            partition_key=partition_key,
                            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
                            removal_policy=RemovalPolicy.RETAIN,
                            point_in_time_recovery=True,
                        )

                    self.tables[config["name"]] = table

            # Output table name
            CfnOutput(
                self,
                f"{config['name'].capitalize()}TableName",
                value=table.table_name,
                description=f"DynamoDB table name for {config['name']}",
            )

        # Create IAM policy for table access
        self.table_access_policy = iam.PolicyDocument(
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
                    resources=[table.table_arn for table in self.tables.values()],
                )
            ]
        )

        # Create managed policy
        self.access_policy = iam.ManagedPolicy(
            self,
            f"{game_name}-dynamodb-access",
            managed_policy_name=f"{game_name}-dynamodb-access",
            document=self.table_access_policy,
            description="Policy for accessing Eidolon Engine DynamoDB tables",
        )

        CfnOutput(
            self,
            "DynamoDBAccessPolicyArn",
            value=self.access_policy.managed_policy_arn,
            description="ARN of the DynamoDB access policy",
        )

    def _table_exists(self, table_name: str) -> bool:
        """Check if a DynamoDB table exists.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        try:
            dynamodb_client = boto3.client("dynamodb", region_name=self.region)
            dynamodb_client.describe_table(TableName=table_name)
            return True
        except ClientError as err:
            if err.response["Error"]["Code"] == "ResourceNotFoundException":
                return False
            else:
                # Assume table doesn't exist on other errors
                return False
