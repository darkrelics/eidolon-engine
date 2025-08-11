"""Main deployment script for Eidolon Engine infrastructure."""

import json
import subprocess
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState


def verify_aws_credentials() -> bool:
    """Verify AWS credentials are configured."""
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        print(f"AWS Account: {identity['Account']}")
        print(f"AWS User/Role: {identity['Arn']}")
        return True
    except Exception as err:
        print(f"Error: Unable to access AWS - {err}")
        return False


def verify_cdk_installed() -> bool:
    """Check if AWS CDK is installed."""
    try:
        result = subprocess.run(
            ["cdk", "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            print(f"CDK Version: {result.stdout.strip()}")
            return True
        else:
            print("Error: AWS CDK is not installed")
            print("Install it with: npm install -g aws-cdk")
            return False
    except FileNotFoundError:
        print("Error: AWS CDK is not installed")
        print("Install it with: npm install -g aws-cdk")
        return False


def deploy_dynamodb_stack(region: str) -> dict:
    """Deploy the DynamoDB stack using CDK."""
    print("\nDeploying DynamoDB stack...")
    
    # Run CDK deploy
    try:
        result = subprocess.run(
            [
                "cdk", "deploy", "dynamodb",
                "--require-approval", "never",
                "--region", region,
                "--app", "python app.py"
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            check=False
        )
        
        if result.returncode != 0:
            print(f"CDK deployment failed:")
            print(result.stderr)
            return {"success": False}
        
        print("Stack deployed successfully")
        
        # Extract outputs from CDK
        outputs = extract_stack_outputs("dynamodb", region)
        return {"success": True, "outputs": outputs}
        
    except Exception as err:
        print(f"Deployment error: {err}")
        return {"success": False}


def extract_stack_outputs(stack_name: str, region: str) -> dict:
    """Extract outputs from deployed CloudFormation stack."""
    cfn = boto3.client("cloudformation", region_name=region)
    
    try:
        response = cfn.describe_stacks(StackName=stack_name)
        stack = response["Stacks"][0]
        
        outputs = {}
        for output in stack.get("Outputs", []):
            outputs[output["OutputKey"]] = output["OutputValue"]
        
        return outputs
    except ClientError as err:
        print(f"Warning: Could not get stack outputs - {err}")
        return {}


def validate_tables(region: str) -> dict:
    """Validate that all tables were created."""
    dynamodb = boto3.client("dynamodb", region_name=region)
    
    expected_tables = [
        "players", "characters", "rooms", "exits", "items", "prototypes",
        "archetypes", "motd", "story", "segments", "active_segments",
        "story_history", "segment_history", "opponents"
    ]
    
    print("\nValidating DynamoDB tables...")
    
    try:
        response = dynamodb.list_tables()
        existing_tables = response.get("TableNames", [])
        
        results = {}
        all_present = True
        
        for table in expected_tables:
            if table in existing_tables:
                print(f"  [OK] {table}")
                results[table] = table
            else:
                print(f"  [MISSING] {table}")
                all_present = False
        
        return {"success": all_present, "tables": results}
        
    except ClientError as err:
        print(f"Error validating tables: {err}")
        return {"success": False, "tables": {}}


def validate_policy(region: str) -> bool:
    """Validate that the IAM policy was created."""
    iam = boto3.client("iam", region_name=region)
    
    try:
        response = iam.get_policy(
            PolicyArn=f"arn:aws:iam::{boto3.client('sts').get_caller_identity()['Account']}:policy/eidolon-dynamodb-policy"
        )
        print("[OK] IAM Policy: eidolon-dynamodb-policy")
        return True
    except ClientError:
        print("[MISSING] IAM Policy: eidolon-dynamodb-policy")
        return False


def main():
    """Main deployment entry point."""
    print("=" * 60)
    print("Eidolon Engine DynamoDB Deployment")
    print("=" * 60)
    
    # Load configuration
    config = Config.load("../config.yml")
    state = CDKState.load(".cdk-state.json")
    
    # Check if already deployed
    if "dynamodb" in state.stacks and state.stacks["dynamodb"].get("deployed"):
        print("\nDynamoDB stack already deployed")
        response = input("Redeploy? [y/N]: ").strip().lower()
        if response != "y":
            print("Deployment cancelled")
            return 0
    
    # Verify prerequisites
    print("\nChecking prerequisites...")
    if not verify_aws_credentials():
        return 1
    
    if not verify_cdk_installed():
        return 1
    
    # Get deployment parameters
    region = config.region
    print(f"\nDeployment Region: {region}")
    
    response = input("\nProceed with deployment? [Y/n]: ").strip().lower()
    if response == "n":
        print("Deployment cancelled")
        return 0
    
    # Deploy the stack
    result = deploy_dynamodb_stack(region)
    
    if not result["success"]:
        print("\nDeployment failed!")
        return 1
    
    # Validate deployment
    validation = validate_tables(region)
    
    if not validation["success"]:
        print("\nWarning: Some tables were not created")
    
    policy_valid = validate_policy(region)
    
    if not policy_valid:
        print("\nWarning: IAM policy was not created")
    
    # Update configuration
    config.dynamodb_tables = validation["tables"]
    config.save("../config.yml")
    print(f"\nConfiguration saved to config.yml")
    
    # Update state
    state.mark_stack_deployed("dynamodb", result.get("outputs", {}))
    state.infrastructure["dynamodb_policy_arn"] = f"arn:aws:iam::{boto3.client('sts').get_caller_identity()['Account']}:policy/eidolon-dynamodb-policy"
    state.save(".cdk-state.json")
    print(f"State saved to .cdk-state.json")
    
    print("\n" + "=" * 60)
    print("DynamoDB deployment completed successfully!")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())