"""DynamoDB stack for Eidolon Engine."""

import boto3
from aws_cdk import CfnDeletionPolicy, CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from botocore.exceptions import ClientError
from constructs import Construct

from core.dynamodb_tables import TABLE_CONFIGS


class DynamoDBStack(Stack):
    """Creates DynamoDB tables and access policy for Eidolon Engine."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """Initialize DynamoDB stack."""
        super().__init__(scope, construct_id, **kwargs)

        # Initialize existing tables from context
        self.existing_tables = {}
        self._load_existing_tables_from_context()

        # Store table ARNs for policy
        table_arns = []
        index_arns = []
        table_outputs = {}
        self.tables = {}

        # Create or import each table from configuration
        for config in TABLE_CONFIGS:
            table_name = config.get("name", "")

            # Check if we should use an existing table from context
            if table_name in self.existing_tables:
                existing_table_name = self.existing_tables[table_name]
                print(f"Importing existing DynamoDB table from context: {existing_table_name}")
                table = dynamodb.Table.from_table_name(self, f"{table_name}-imported", existing_table_name)
            elif self._table_exists(table_name):
                # Check if existing table has correct schema
                if self._validate_table_schema(table_name, config):
                    print(f"Found existing DynamoDB table: {table_name}, importing...")
                    table = dynamodb.Table.from_table_name(self, f"{table_name}-imported", table_name)
                else:
                    print(f"ERROR: Table {table_name} exists but has incorrect schema!")
                    print(f"Expected partition key: {config.get('partition_key', {}).get('name', '')}")
                    if "sort_key" in config:
                        print(f"Expected sort key: {config.get('sort_key', {}).get('name', '')}")
                    else:
                        print("Expected no sort key")
                    print("Please manually delete or migrate the table before deploying.")
                    raise ValueError(f"Table {table_name} has incorrect schema")
            else:
                # Create new table
                print(f"Creating new DynamoDB table: {table_name}")
                table = self.create_table(config)

            self.tables[table_name] = table
            table_arns.append(table.table_arn)
            table_outputs[config.get("name", "")] = table.table_name

            # Collect GSI ARNs if present
            if "gsi" in config:
                for gsi in config.get("gsi", []):
                    index_arns.append(f"{table.table_arn}/index/{gsi.get('name', '')}")

            # Create output for each table
            CfnOutput(
                self,
                f"{config.get('name', '').replace('_', '')}TableName",
                value=table.table_name,
                description=f"DynamoDB table name for {config.get('name', '')}"
            )

        # Create single IAM managed policy for DynamoDB access
        policy = iam.ManagedPolicy(
            self,
            "DynamoDBAccessPolicy",
            managed_policy_name="eidolon-dynamodb-policy",
            description="Policy for read/write access to Eidolon Engine DynamoDB tables",
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
                    resources=table_arns + index_arns
                )
            ]
        )

        # Output the policy ARN
        CfnOutput(
            self,
            "DynamoDBPolicyArn",
            value=policy.managed_policy_arn,
            description="ARN of the DynamoDB access policy"
        )

        # Store outputs for retrieval
        self.table_outputs = table_outputs
        self.policy_arn = policy.managed_policy_arn

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
            name=partition_key.get("name", ""),
            type=get_attribute_type(partition_key.get("type", ""))
        )

        # Add sort key if present
        if "sort_key" in config:
            sort_key = config.get("sort_key", {})
            table_props["sort_key"] = dynamodb.Attribute(
                name=sort_key.get("name", ""),
                type=get_attribute_type(sort_key.get("type", ""))
            )

        # Create the table
        table = dynamodb.Table(
            self,
            f"{config.get('name', '').replace('_', '')}Table",
            **table_props
        )

        # Set UpdateReplacePolicy to Retain to prevent data loss during updates
        cfn_table = table.node.default_child
        if cfn_table:
            cfn_table.cfn_options.update_replace_policy = CfnDeletionPolicy.RETAIN # type: ignore

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

    def _table_exists(self, table_name: str) -> bool:
        """Check if a DynamoDB table exists.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        try:
            if not table_name:
                return False

            dynamodb_client = boto3.client("dynamodb", region_name=self.region)
            dynamodb_client.describe_table(TableName=table_name)
            return True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "ResourceNotFoundException":
                return False
        return False

    def _validate_table_schema(self, table_name: str, config: dict) -> bool:
        """Validate that an existing table matches the expected schema.

        Args:
            table_name: Name of the table to validate
            config: Expected table configuration

        Returns:
            True if schema matches, False otherwise
        """
        try:
            dynamodb_client = boto3.client("dynamodb", region_name=self.region)
            response = dynamodb_client.describe_table(TableName=table_name)
            key_schema = response.get("Table", {}).get("KeySchema", [])

            # Check partition key
            pk_name = config.get("partition_key", {}).get("name", "")
            pk_found = False
            for key in key_schema:
                if key.get("KeyType") == "HASH" and key.get("AttributeName") == pk_name:
                    pk_found = True
                    break

            if not pk_found:
                print(f"WARNING: Table {table_name} has incorrect partition key. Expected: {pk_name}")
                return False

            # Check sort key
            if "sort_key" in config:
                sk_name = config.get("sort_key", {}).get("name", "")
                # Table should have a sort key
                sk_found = False
                for key in key_schema:
                    if key.get("KeyType") == "RANGE" and key.get("AttributeName") == sk_name:
                        sk_found = True
                        break
                if not sk_found:
                    print(f"WARNING: Table {table_name} has incorrect sort key. Expected: {sk_name}")
                    return False
            else:
                # Table should NOT have a sort key
                for key in key_schema:
                    if key.get("KeyType") == "RANGE":
                        print(f"WARNING: Table {table_name} has unexpected sort key: {key.get('AttributeName', '')}")
                        return False

            return True
        except Exception as err:
            print(f"Error validating table schema: {err}")
            return False


def add_gsi(table: dynamodb.Table, gsi_config: dict) -> None:
    """Add a Global Secondary Index to a table."""
    gsi_props = {
        "index_name": gsi_config.get("name", ""),
        "partition_key": dynamodb.Attribute(
            name=gsi_config.get("partition_key", {}).get("name", ""),
            type=get_attribute_type(gsi_config.get("partition_key", {}).get("type", ""))
        ),
    }

    # Add sort key if present
    if "sort_key" in gsi_config:
        gsi_props["sort_key"] = dynamodb.Attribute(
            name=gsi_config.get("sort_key", {}).get("name", ""),
            type=get_attribute_type(gsi_config.get("sort_key", {}).get("type", ""))
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
