"""AWS DynamoDB stack for game data storage."""

import boto3
from aws_cdk import CfnOutput, RemovalPolicy, Stack, CfnDeletionPolicy
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from botocore.exceptions import ClientError
from constructs import Construct


class DynamoDBStack(Stack):
    """DynamoDB stack for Eidolon Engine game data."""

    def __init__(self, scope: Construct, construct_id: str, game_name: str, table_names: dict[str, str] = {}, execution_role_arn: str = None, **kwargs) -> None:
        """Initialize DynamoDB stack.

        Args:
            scope: CDK app scope
            construct_id: Stack identifier
            game_name: Name of the game
            table_names: Optional dictionary of table type to table name mappings
            execution_role_arn: Optional ARN of IAM role to attach the DynamoDB policy to
            **kwargs: Additional stack properties
        """
        super().__init__(scope, construct_id, **kwargs)

        # Validate required parameters early
        if not game_name:
            raise ValueError("game_name is required")

        self.game_name = game_name
        self.custom_table_names = table_names or {}
        self.execution_role_arn = execution_role_arn

        # Define table types upfront
        self.table_types = ["players", "characters", "rooms", "exits", "items", "prototypes", "archetypes", "motd", "story"]

        # Initialize existing tables from context
        self.existing_tables: dict[str, str] = {}
        self._load_existing_tables_from_context()

        # Initialize tables dictionary - using ITable to support both created and imported tables
        self.tables: dict[str, dynamodb.ITable] = {}

        # Create or import tables
        self._create_or_import_tables()

        # Create IAM access policy
        self._create_access_policy()

    def _load_existing_tables_from_context(self) -> None:
        """Load existing table names from CDK context."""
        for table_type in self.table_types:
            context_key = f"dynamodb_{table_type}_table"
            existing_table_name = self.node.try_get_context(context_key)
            if existing_table_name:
                self.existing_tables[table_type] = existing_table_name

    def _get_table_configs(self) -> list[dict[str, str]]:
        """Get table configurations.

        Returns:
            List of table configuration dictionaries
        """
        return [
            {"name": "players", "pk": "player_id", "sk": ""},
            {"name": "characters", "pk": "player_id", "sk": "character_id"},
            {"name": "rooms", "pk": "room_id", "sk": ""},
            {"name": "exits", "pk": "room_id", "sk": "exit_id"},
            {"name": "items", "pk": "item_id", "sk": ""},
            {"name": "prototypes", "pk": "prototype_id", "sk": ""},
            {"name": "archetypes", "pk": "archetype_id", "sk": ""},
            {"name": "motd", "pk": "motd_id", "sk": ""},
            {"name": "story", "pk": "player_id", "sk": "story_id"},
        ]

    def _get_table_name(self, config_name: str) -> str:
        """Get the table name for a given configuration.

        Args:
            config_name: Name from the table configuration

        Returns:
            The resolved table name
        """
        # Check custom table names (try both capitalized and lowercase)
        capitalized_name = config_name.capitalize()

        if capitalized_name in self.custom_table_names:
            return self.custom_table_names[capitalized_name]
        elif config_name in self.custom_table_names:
            return self.custom_table_names[config_name]
        else:
            return config_name

    def _create_or_import_tables(self) -> None:
        """Create new tables or import existing ones."""
        table_configs = self._get_table_configs()

        for config in table_configs:
            table_name = self._get_table_name(config.get("name", ""))
            config_name = config.get("name", "")

            # Validate required config fields
            if not config_name:
                raise ValueError("Table configuration missing 'name' field")
            if not config.get("pk"):
                raise ValueError(f"Table configuration for '{config_name}' missing 'pk' field")

            # Check if we should use an existing table from context
            if config_name in self.existing_tables:
                existing_table_name = self.existing_tables[config_name]
                print(f"Importing existing DynamoDB table from context: {existing_table_name}")
                table = dynamodb.Table.from_table_name(self, f"{config_name}-imported", existing_table_name)
                self.tables[config_name] = table
            elif self._table_exists(table_name):
                # Import existing table found in AWS
                print(f"Found existing DynamoDB table: {table_name}, importing...")
                table = dynamodb.Table.from_table_name(self, f"{config_name}-imported", table_name)
                self.tables[config_name] = table
            else:
                # Create new table
                print(f"Creating new DynamoDB table: {table_name}")
                table = self._create_table(table_name, config)
                self.tables[config_name] = table

            # Output table name
            CfnOutput(
                self,
                f"{config_name.capitalize()}TableName",
                value=table.table_name,
                description=f"DynamoDB table name for {config_name}",
            )

    def _create_table(self, table_name: str, config: dict[str, str]) -> dynamodb.Table:
        """Create a new DynamoDB table.

        Args:
            table_name: Name for the table
            config: Table configuration dictionary

        Returns:
            The created DynamoDB table
        """
        # Define partition key
        partition_key = dynamodb.Attribute(name=config.get("pk", ""), type=dynamodb.AttributeType.STRING)

        # Base table properties
        table_props = {
            "table_name": table_name,
            "partition_key": partition_key,
            "billing_mode": dynamodb.BillingMode.PAY_PER_REQUEST,
            "removal_policy": RemovalPolicy.RETAIN,
        }

        # Add sort key if specified
        sort_key_name = config.get("sk", "")
        if sort_key_name:
            sort_key = dynamodb.Attribute(name=sort_key_name, type=dynamodb.AttributeType.STRING)
            table_props["sort_key"] = sort_key

        table = dynamodb.Table(self, table_name, **table_props)
        
        # Set UpdateReplacePolicy to Retain to prevent data loss during updates
        cfn_table = table.node.default_child
        cfn_table.cfn_options.update_replace_policy = CfnDeletionPolicy.RETAIN
        
        return table

    def _create_access_policy(self) -> None:
        """Create IAM policy for table access."""
        # Validate tables exist before creating policy
        if not self.tables:
            raise ValueError("No tables available to create access policy")

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
            "dynamodb-access",
            managed_policy_name=f"eidolon-{self.game_name}-dynamodb-access",
            document=self.table_access_policy,
            description=f"Policy for accessing {self.game_name} Eidolon Engine DynamoDB tables",
        )
        
        # Attach policy to execution role if ARN provided
        if self.execution_role_arn:
            # Import the role using its ARN
            execution_role = iam.Role.from_role_arn(
                self, "imported-execution-role", self.execution_role_arn
            )
            execution_role.add_managed_policy(self.access_policy)

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
            # Validate table name
            if not table_name:
                return False

            dynamodb_client = boto3.client("dynamodb", region_name=self.region)
            dynamodb_client.describe_table(TableName=table_name)
            return True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                return False
            else:
                # Log error but assume table doesn't exist
                print(f"Error checking table existence for {table_name}: {err}")
                return False
        except Exception as err:
            # Handle any other exceptions
            print(f"Unexpected error checking table {table_name}: {err}")
            return False
