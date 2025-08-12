"""DynamoDB stack deployment functions."""

import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy, validate_policies


def deploy_dynamodb_stack(region: str) -> dict:
    """Deploy the DynamoDB stack using CDK."""
    app_command = f"python3 app.py --region {region}"
    return run_cdk_deploy("dynamodb", region, app_command)


def validate_tables(region: str) -> dict:
    """Validate that all tables were created and are active."""
    dynamodb = boto3.client("dynamodb", region_name=region)

    expected_tables = [
        "players", "characters", "rooms", "exits", "items", "prototypes",
        "archetypes", "motd", "story", "segments", "active_segments",
        "story_history", "segment_history", "opponents"
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
    print("\nVerifying deployment...")
    
    # Validate tables
    table_validation = validate_tables(params.region)
    
    # Validate IAM policies
    policy_validation = validate_policies(["eidolon-dynamodb-policy"])
    
    return {
        "tables": table_validation,
        "policies": policy_validation,
        "success": table_validation.get("success", False) and all(policy_validation.values())
    }


def update_dynamodb_configurations(config: Config, state: CDKState, params, 
                                  validation: dict, config_path: Path, state_path: Path) -> None:
    """Update config and state files with DynamoDB deployment results."""
    # Update configuration
    config.dynamodb_tables = validation.get("tables", {}).get("tables", {})
    config.region = params.region
    config.save(str(config_path))
    print(f"\nConfiguration saved to config.yml")
    
    # Update state
    state.mark_stack_deployed("dynamodb", {})
    state.infrastructure["dynamodb_policy_arn"] = f"arn:aws:iam::{params.account_id}:policy/eidolon-dynamodb-policy"
    state.save(str(state_path))
    print(f"State saved to .cdk-state.json")


def execute_dynamodb_deployment(params, state: CDKState) -> bool:
    """Execute the DynamoDB deployment with given parameters."""
    # Deploy the stack
    result = deploy_dynamodb_stack(params.region)
    return result.get("success", False)


def deploy_dynamodb(params, config: Config, state: CDKState, 
                   config_path: Path, state_path: Path) -> bool:
    """Deploy and verify DynamoDB stack."""
    print("\n" + "=" * 60)
    print("Phase 1: DynamoDB Stack")
    print("=" * 60)
    
    # Execute deployment
    if not execute_dynamodb_deployment(params, state):
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
    
    # Update configurations
    update_dynamodb_configurations(config, state, params, validation, config_path, state_path)
    
    return validation.get("success", False)