"""DynamoDB stack for Eidolon Engine."""

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from constructs import Construct

from core.dynamodb_tables import TABLE_CONFIGS


class DynamoDBStack(Stack):
    """Creates DynamoDB tables and access policy for Eidolon Engine."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        """Initialize DynamoDB stack."""
        super().__init__(scope, construct_id, **kwargs)

        # Store table ARNs for policy
        table_arns = []
        index_arns = []
        table_outputs = {}

        # Create each table from configuration
        for config in TABLE_CONFIGS:
            table = self.create_table(config)
            table_arns.append(table.table_arn)
            table_outputs[config["name"]] = table.table_name
            
            # Collect GSI ARNs if present
            if "gsi" in config:
                for gsi in config["gsi"]:
                    index_arns.append(f"{table.table_arn}/index/{gsi['name']}")
            
            # Create output for each table
            CfnOutput(
                self,
                f"{config['name'].replace('_', '')}TableName",
                value=table.table_name,
                description=f"DynamoDB table name for {config['name']}"
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
            "table_name": config["name"],
            "billing_mode": dynamodb.BillingMode.PAY_PER_REQUEST,
            "removal_policy": RemovalPolicy.RETAIN,
            "point_in_time_recovery": False,  # Can be enabled if needed
        }

        # Add partition key
        partition_key = config["partition_key"]
        table_props["partition_key"] = dynamodb.Attribute(
            name=partition_key["name"],
            type=get_attribute_type(partition_key["type"])
        )

        # Add sort key if present
        if "sort_key" in config:
            sort_key = config["sort_key"]
            table_props["sort_key"] = dynamodb.Attribute(
                name=sort_key["name"],
                type=get_attribute_type(sort_key["type"])
            )

        # Create the table
        table = dynamodb.Table(
            self,
            f"{config['name'].replace('_', '')}Table",
            **table_props
        )

        # Add GSIs if present
        if "gsi" in config:
            for gsi_config in config["gsi"]:
                add_gsi(table, gsi_config)

        return table


def add_gsi(table: dynamodb.Table, gsi_config: dict) -> None:
    """Add a Global Secondary Index to a table."""
    gsi_props = {
        "index_name": gsi_config["name"],
        "partition_key": dynamodb.Attribute(
            name=gsi_config["partition_key"]["name"],
            type=get_attribute_type(gsi_config["partition_key"]["type"])
        ),
    }

    # Add sort key if present
    if "sort_key" in gsi_config:
        gsi_props["sort_key"] = dynamodb.Attribute(
            name=gsi_config["sort_key"]["name"],
            type=get_attribute_type(gsi_config["sort_key"]["type"])
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