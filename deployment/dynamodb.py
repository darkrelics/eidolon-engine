"""DynamoDB stack deployment functions."""

import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.dynamodb_tables import TABLE_CONFIGS
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from stacks import stack_utilities as utils
from utilities import run_cdk_deploy, validate_policies


def check_existing_tables(region: str) -> dict:
    """Check for existing DynamoDB tables and validate their schemas."""

    existing_tables = {}

    for config in TABLE_CONFIGS:
        table_name = config.get("name", "")
        if utils.check_dynamodb_table_exists(table_name, region):
            # Validate schema
            if utils.validate_dynamodb_table_schema(table_name, region, config):
                print(f"  Found existing table with correct schema: {table_name}")
                existing_tables[table_name] = table_name
            else:
                print(f"  WARNING: Table {table_name} exists but has incorrect schema!")
                print(f"    Expected partition key: {config.get('partition_key', {}).get('name', '')}")
                if "sort_key" in config:
                    print(f"    Expected sort key: {config.get('sort_key', {}).get('name', '')}")
                # Mark as empty string to indicate it should not be imported
                existing_tables[table_name] = ""
        else:
            # Mark as empty string to indicate it doesn't exist
            existing_tables[table_name] = ""

    return existing_tables


def check_dynamodb_table_exists(dynamodb_client, table_name: str) -> bool:
    """Check if a DynamoDB table physically exists.

    Returns True if the table exists or the check fails (assumes exists on error).
    Returns False only when the table is confirmed missing.
    """
    try:
        dynamodb_client.describe_table(TableName=table_name)
        return True
    except dynamodb_client.exceptions.ResourceNotFoundException:
        return False
    except ClientError:
        return True  # Assume exists on check errors


def remove_orphaned_stack_resources(region: str) -> bool:
    """Remove CloudFormation tracking for tables that no longer exist physically.

    When tables are manually deleted but CloudFormation still tracks them,
    this removes them from CloudFormation's state without deleting the stack.

    Returns True if orphaned resources were found and handled, False otherwise.
    """
    cfn = boto3.client("cloudformation", region_name=region)
    dynamodb_client = boto3.client("dynamodb", region_name=region)

    try:
        # Get stack status
        stack_response = cfn.describe_stacks(StackName="dynamodb")
        stacks = stack_response.get("Stacks", [])
        if not stacks:
            return False

        stack_status = stacks[0].get("StackStatus", "")

        # Get all resources in the DynamoDB stack
        response = cfn.describe_stack_resources(StackName="dynamodb")
        orphaned_resources = []

        for resource in response.get("StackResources", []):
            if resource.get("ResourceType") == "AWS::DynamoDB::Table":
                physical_id = resource.get("PhysicalResourceId", "")
                logical_id = resource.get("LogicalResourceId", "")

                if physical_id and not check_dynamodb_table_exists(dynamodb_client, physical_id):
                    print(f"  Found orphaned CloudFormation resource: {logical_id} -> {physical_id} (table doesn't exist)")
                    orphaned_resources.append(logical_id)

        if not orphaned_resources:
            return False

        print(f"\nFound {len(orphaned_resources)} orphaned table resources")
        print("Removing orphaned resources from CloudFormation tracking...")

        # If stack is in UPDATE_ROLLBACK_FAILED or similar, we may need to continue rollback first
        if "ROLLBACK" in stack_status and "COMPLETE" not in stack_status:
            print(f"  Stack is in {stack_status} state, continuing rollback and skipping orphaned resources...")
            cfn.continue_update_rollback(StackName="dynamodb", ResourcesToSkip=orphaned_resources)
            print("  Waiting for rollback to complete...")
            waiter = cfn.get_waiter("stack_update_rollback_complete")
            waiter.wait(StackName="dynamodb")
            print("  Rollback complete, orphaned resources removed from tracking\n")
            return True

        # For other states, delete and recreate the stack cleanly
        print("  Deleting CloudFormation stack to remove orphaned resource tracking...")
        print("  Note: Physical tables will be preserved (RemovalPolicy.RETAIN)")

        cfn.delete_stack(StackName="dynamodb")
        print("  Waiting for stack deletion...")
        waiter = cfn.get_waiter("stack_delete_complete")
        waiter.wait(StackName="dynamodb")
        print("  Stack deleted, orphaned resources removed from tracking\n")
        return True

    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ValidationError":
            if "does not exist" in str(err):
                # Stack doesn't exist, that's fine
                return False
        print(f"  Error handling orphaned resources: {err}")
        return False


def deploy_dynamodb_stack(params) -> dict:
    """Deploy the DynamoDB stack using CDK."""

    print("\nChecking for existing DynamoDB tables...")
    existing_tables = check_existing_tables(params.region)

    # Remove any orphaned CloudFormation resources
    remove_orphaned_stack_resources(params.region)

    # Pass parameters through context
    context_args = ["-c", f"region={params.region}"]

    # Add existing tables to context
    for table_name, actual_name in existing_tables.items():
        context_key = f"dynamodb_{table_name}_table"
        context_args.extend(["-c", f"{context_key}={actual_name}"])

    app_command = "python3 app_dynamodb.py"
    return run_cdk_deploy("dynamodb", params.region, app_command, context_args)


def validate_tables(region: str) -> dict:
    """Validate that all tables were created and are active."""
    dynamodb = boto3.client("dynamodb", region_name=region)

    expected_tables = [
        "players",
        "characters",
        "rooms",
        "exits",
        "items",
        "prototypes",
        "archetypes",
        "motd",
        "story",
        "segments",
        "active_segments",
        "story_history",
        "segment_history",
        "opponents",
    ]

    print("\nValidating DynamoDB tables...")

    try:
        # First check if tables exist
        response = dynamodb.list_tables()
        existing_tables = response.get("TableNames", [])

        results = {}
        all_present = True
        creating_tables = []

        for table in expected_tables:
            if table in existing_tables:
                # Check table status
                table_desc = dynamodb.describe_table(TableName=table)
                status = table_desc.get("Table", {}).get("TableStatus", "")

                if status == "ACTIVE":
                    print(f"  [OK] {table}")
                    results[table] = table
                elif status == "CREATING":
                    print(f"  [CREATING] {table}")
                    creating_tables.append(table)
                else:
                    print(f"  [STATUS: {status}] {table}")
                    all_present = False
            else:
                print(f"  [MISSING] {table}")
                all_present = False

        # If tables are still creating, wait and retry
        if creating_tables:
            print("\nWaiting for tables to become active...")
            time.sleep(10)

            # Check creating tables again
            for table in creating_tables:
                try:
                    table_desc = dynamodb.describe_table(TableName=table)
                    status = table_desc.get("Table", {}).get("TableStatus", "")

                    if status == "ACTIVE":
                        print(f"  [OK] {table}")
                        results[table] = table
                    else:
                        print(f"  [STILL {status}] {table}")
                        all_present = False
                except ClientError:
                    print(f"  [ERROR] {table} - Could not verify status")
                    all_present = False

        return {"success": all_present, "tables": results}

    except ClientError as err:
        print(f"Error validating tables: {err}")
        return {"success": False, "tables": {}}


def verify_dynamodb_deployment(params) -> dict:
    """Verify the DynamoDB deployment completed successfully."""
    print("\nVerifying DynamoDB deployment...")

    # Validate tables
    table_validation = validate_tables(params.region)

    # Validate IAM policies
    policy_validation = validate_policies(["eidolon-dynamodb-policy"])

    return {
        "tables": table_validation,
        "policies": policy_validation,
        "success": table_validation.get("success", False) and all(policy_validation.values()),
    }


def deploy_dynamodb(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify DynamoDB stack."""
    phase = get_stack_phase_number("dynamodb", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: DynamoDB Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_dynamodb_stack(params)

    if not result.get("success", False):
        print("\nDynamoDB deployment failed!")
        return False

    # Verify deployment
    validation = verify_dynamodb_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: DynamoDB deployment completed with issues")
        if not validation.get("tables", {}).get("success", False):
            print("  - Some tables were not created")
        if not all(validation.get("policies", {}).values()):
            print("  - Some IAM policies were not created")

    # Update configuration
    if validation.get("tables", {}).get("success", False):
        config.dynamodb_tables = validation.get("tables", {}).get("tables", {})
        config.region = params.region
        config.save(str(config_path))

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("dynamodb", result.get("outputs", {}))

        # Store infrastructure resources needed by other stacks
        if "infrastructure" not in state.__dict__:
            state.infrastructure = {}

        # Extract DynamoDB policy ARN from stack outputs
        dynamodb_policy_arn = result.get("outputs", {}).get("DynamoDBPolicyArn")
        if dynamodb_policy_arn:
            state.infrastructure["dynamodb_policy_arn"] = dynamodb_policy_arn
        else:
            # Fallback to constructed ARN if output not available (for backwards compatibility)
            print("  [WARNING] DynamoDB policy ARN not found in stack outputs, using constructed ARN")
            state.infrastructure["dynamodb_policy_arn"] = f"arn:aws:iam::{params.account_id}:policy/eidolon-dynamodb-policy"

        state.save(str(state_path))

    return validation.get("success", False)
