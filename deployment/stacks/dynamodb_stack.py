"""DynamoDB stack for Eidolon Engine."""

from aws_cdk import CfnDeletionPolicy, CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from constructs import Construct
from core.dynamodb_tables import TABLE_CONFIGS


class DynamoDBStack(Stack):
    """DynamoDB stack for Eidolon Engine data storage."""

    def __init__(self, scope: Construct, stack_id: str, region_name: str = "us-east-1", **kwargs) -> None:
        """Initialize DynamoDB stack.

        Args:
            scope: CDK construct scope
            stack_id: Stack identifier
            region_name: AWS region for resource operations
            **kwargs: Additional stack properties
        """
        self.region_name = region_name
        super().__init__(scope, stack_id, **kwargs)

        # Initialize existing tables from context
        self.existing_tables = {}
        self._load_existing_tables_from_context()

        # Store table ARNs for policy
        self.table_arns = []
        self.index_arns = []
        self.table_outputs = {}
        self.tables = {}

        # Create or import each table from configuration
        for config in TABLE_CONFIGS:
            table_name = config.get("name", "")

            # Check if we should use an existing table from context
            if table_name in self.existing_tables:
                existing_table_name = self.existing_tables.get(table_name, "")
                if existing_table_name:
                    print(f"  Using existing DynamoDB table from context: {existing_table_name}")
                    # Use fixed logical ID based on table name
                    logical_id = self._get_table_logical_id(table_name) + "Imported"
                    table = dynamodb.Table.from_table_name(self, logical_id, existing_table_name)
                else:
                    # Table was marked as non-existent in context, create new
                    print(f"  Creating new DynamoDB table: {table_name}")
                    table = self.create_table(config)
            else:
                # No context provided, always create (CDK will handle create vs update)
                print(f"  Creating/updating DynamoDB table: {table_name}")
                table = self.create_table(config)

            self.tables[table_name] = table
            self.table_arns.append(table.table_arn)
            self.table_outputs[config.get("name", "")] = table.table_name

            # Collect GSI ARNs if present
            if "gsi" in config:
                for gsi in config.get("gsi", []):
                    self.index_arns.append(f"{table.table_arn}/index/{gsi.get('name', '')}")

        # Create single IAM managed policy for DynamoDB access
        self.policy = iam.ManagedPolicy(
            self,
            "DynamoDBAccessPolicy",
            managed_policy_name="eidolon-dynamodb-policy",
            description="Policy for read/write access to Eidolon Engine DynamoDB tables",
            statements=[
                iam.PolicyStatement(
                    effect=iam.Effect.ALLOW,
                    actions=[
                        "dynamodb:DescribeTable",
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem",
                        "dynamodb:DeleteItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                        "dynamodb:BatchGetItem",
                        "dynamodb:BatchWriteItem",
                    ],
                    resources=self.table_arns + self.index_arns,
                )
            ],
        )

        # Store policy ARN for retrieval
        self.policy_arn = self.policy.managed_policy_arn

        # Add outputs
        self._add_outputs()

    def create_table(self, config: dict) -> dynamodb.Table:
        """Create a DynamoDB table from configuration."""
        # Base table properties
        table_props = {
            "table_name": config.get("name", ""),
            "billing_mode": dynamodb.BillingMode.PAY_PER_REQUEST,
            "removal_policy": RemovalPolicy.RETAIN,
            "point_in_time_recovery": False,  # Can be enabled if needed
        }

        # Add partition key
        partition_key = config.get("partition_key", {})
        table_props["partition_key"] = dynamodb.Attribute(
            name=partition_key.get("name", ""), type=get_attribute_type(partition_key.get("type", ""))
        )

        # Add sort key if present
        if "sort_key" in config:
            sort_key = config.get("sort_key", {})
            table_props["sort_key"] = dynamodb.Attribute(
                name=sort_key.get("name", ""), type=get_attribute_type(sort_key.get("type", ""))
            )

        # Create the table with fixed logical ID
        logical_id = self._get_table_logical_id(config.get('name', ''))
        table = dynamodb.Table(self, logical_id, **table_props)

        # Set UpdateReplacePolicy to Retain to prevent data loss during updates
        cfn_table = table.node.default_child
        if cfn_table:
            cfn_table.cfn_options.update_replace_policy = CfnDeletionPolicy.RETAIN  # type: ignore

        # Add GSIs if present
        if "gsi" in config:
            for gsi_config in config.get("gsi", []):
                add_gsi(table, gsi_config)

        return table

    def _load_existing_tables_from_context(self) -> None:
        """Load existing table names from CDK context."""
        for config in TABLE_CONFIGS:
            table_name = config.get("name", "")
            context_key = f"dynamodb_{table_name}_table"
            existing_table_name = self.node.try_get_context(context_key)
            if existing_table_name:
                self.existing_tables[table_name] = existing_table_name


    def _get_table_logical_id(self, table_name: str) -> str:
        """Get fixed logical ID for a table.
        
        This ensures consistent logical IDs across deployments.
        """
        # Define fixed mappings for all tables
        logical_id_map = {
            "players": "PlayersTable",
            "characters": "CharactersTable",
            "rooms": "RoomsTable",
            "exits": "ExitsTable",
            "items": "ItemsTable",
            "prototypes": "PrototypesTable",
            "archetypes": "ArchetypesTable",
            "motd": "MotdTable",
            "story": "StoryTable",
            "segments": "SegmentsTable",
            "active_segments": "ActiveSegmentsTable",
            "story_history": "StoryHistoryTable",
            "segment_history": "SegmentHistoryTable",
            "opponents": "OpponentsTable",
        }
        return logical_id_map.get(table_name, table_name.replace('_', '').title() + "Table")

    def _add_outputs(self) -> None:
        """Add stack outputs."""
        # Output each table name
        for table_name, table in self.tables.items():
            # Use fixed output ID
            output_id = self._get_table_logical_id(table_name) + "Name"
            CfnOutput(
                self,
                output_id,
                value=table.table_name,
                description=f"DynamoDB table name for {table_name}",
            )

        # Output the policy ARN
        CfnOutput(self, "DynamoDBPolicyArn", value=self.policy_arn, description="ARN of the DynamoDB access policy")


def add_gsi(table: dynamodb.Table, gsi_config: dict) -> None:
    """Add a Global Secondary Index to a table."""
    gsi_props = {
        "index_name": gsi_config.get("name", ""),
        "partition_key": dynamodb.Attribute(
            name=gsi_config.get("partition_key", {}).get("name", ""),
            type=get_attribute_type(gsi_config.get("partition_key", {}).get("type", "")),
        ),
    }

    # Add sort key if present
    if "sort_key" in gsi_config:
        gsi_props["sort_key"] = dynamodb.Attribute(
            name=gsi_config.get("sort_key", {}).get("name", ""),
            type=get_attribute_type(gsi_config.get("sort_key", {}).get("type", "")),
        )

    # Set projection type
    projection = gsi_config.get("projection", "ALL")
    if projection == "KEYS_ONLY":
        gsi_props["projection_type"] = dynamodb.ProjectionType.KEYS_ONLY
    elif projection == "ALL":
        gsi_props["projection_type"] = dynamodb.ProjectionType.ALL
    else:
        gsi_props["projection_type"] = dynamodb.ProjectionType.INCLUDE
        gsi_props["non_key_attributes"] = projection  # Should be a list of attributes

    table.add_global_secondary_index(**gsi_props)


def get_attribute_type(type_str: str) -> dynamodb.AttributeType:
    """Convert string type to CDK AttributeType."""
    if type_str == "S":
        return dynamodb.AttributeType.STRING
    elif type_str == "N":
        return dynamodb.AttributeType.NUMBER
    elif type_str == "B":
        return dynamodb.AttributeType.BINARY
    else:
        raise ValueError(f"Unknown attribute type: {type_str}")
