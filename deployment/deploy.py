"""Main deployment script for Eidolon Engine infrastructure."""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState


@dataclass
class DeploymentParams:
    """Parameters for deployment."""
    region: str = "us-east-1"
    account_id: str = ""
    s3_bucket: str = ""
    github_owner: str = "robinje"
    github_repo: str = "eidolon-engine"
    github_branch: str = "develop"


@cache
def get_aws_account_id() -> str:
    """Get AWS account ID (cached).
    
    Returns:
        AWS account ID string if successful, empty string if failed
    """
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        return identity.get('Account', '')
    except Exception as err:
        print(f"Error: Unable to get AWS account ID - {err}")
        return ""


def verify_aws_credentials() -> bool:
    """Verify AWS credentials are configured."""
    account_id = get_aws_account_id()
    if not account_id:
        print("Error: Unable to access AWS")
        return False
    
    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        print(f"AWS Account: {account_id}")
        print(f"AWS User/Role: {identity.get('Arn', '')}")
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


def verify_cdk_bootstrap(region: str) -> bool:
    """Check if CDK is bootstrapped in the target region."""
    # Validate region before attempting to check bootstrap
    if not validate_region(region):
        return False
    
    cfn = boto3.client("cloudformation", region_name=region)
    
    try:
        # CDK bootstrap creates a stack named CDKToolkit
        response = cfn.describe_stacks(StackName="CDKToolkit")
        if response.get("Stacks"):
            print(f"CDK Bootstrap: Found in {region}")
            return True
    except ClientError as err:
        if "does not exist" in str(err):
            print(f"Warning: CDK not bootstrapped in {region}")
            print(f"Run: cdk bootstrap aws://{get_aws_account_id()}/{region}")
            return False
        else:
            # Other errors - might be permissions
            print(f"Warning: Could not verify CDK bootstrap: {err}")
            return True  # Continue anyway
    
    return False


def deploy_dynamodb_stack(region: str) -> dict:
    """Deploy the DynamoDB stack using CDK."""
    print(f"\nDeploying DynamoDB stack in {region}...")

    # Run CDK deploy
    try:
        result = subprocess.run(
            [
                "cdk", "deploy", "dynamodb",
                "--require-approval", "never",
                "--region", region,
                "--app", f"python3 app.py --region {region}"
            ],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            check=False
        )

        if result.returncode != 0:
            print(f"\nCDK deployment failed with exit code {result.returncode}")
            if result.stdout:
                print("\nOutput:")
                print(result.stdout)
            if result.stderr:
                print("\nErrors:")
                print(result.stderr)
            return {"success": False}

        # Log CDK output for successful deployments too
        if result.stdout:
            print("\nCDK Output:")
            print(result.stdout)

        print("\nStack deployed successfully")

        # Extract outputs from CDK
        outputs = extract_stack_outputs("dynamodb", region)
        return {"success": True, "outputs": outputs}

    except Exception as err:
        print(f"\nDeployment error: {err}")
        return {"success": False}


def extract_stack_outputs(stack_name: str, region: str) -> dict:
    """Extract outputs from deployed CloudFormation stack."""
    cfn = boto3.client("cloudformation", region_name=region)

    try:
        response = cfn.describe_stacks(StackName=stack_name)
        stacks = response.get("Stacks", [])
        stack = stacks[0] if stacks else {}

        outputs = {}
        for output in stack.get("Outputs", []):
            output_key = output.get("OutputKey", "")
            output_value = output.get("OutputValue", "")
            if output_key:
                outputs[output_key] = output_value

        return outputs
    except ClientError as err:
        print(f"Warning: Could not get stack outputs - {err}")
        return {}


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


def validate_policies(policy_names: list[str]) -> dict:
    """Validate that IAM policies were created.
    
    Args:
        policy_names: List of policy names to check
        
    Returns:
        Dict with policy names as keys and bool status as values
    """
    iam = boto3.client("iam")
    account_id = get_aws_account_id()
    
    if not account_id:
        print("[ERROR] Cannot validate policies without AWS account ID")
        return {name: False for name in policy_names}
    
    results = {}
    for policy_name in policy_names:
        try:
            response = iam.get_policy(
                PolicyArn=f"arn:aws:iam::{account_id}:policy/{policy_name}"
            )
            print(f"[OK] IAM Policy: {policy_name}")
            results[policy_name] = True
        except ClientError:
            print(f"[MISSING] IAM Policy: {policy_name}")
            results[policy_name] = False
    
    return results


def validate_region(region: str) -> str:
    """Validate and sanitize AWS region.
    
    Args:
        region: AWS region to validate
        
    Returns:
        Sanitized region string if valid, empty string if invalid
    """
    # Sanitize input - strip whitespace and convert to lowercase
    sanitized_region = region.strip().lower()
    
    # Define supported regions
    supported_regions = ["us-east-1", "us-east-2", "us-west-2"]
    
    if sanitized_region in supported_regions:
        return sanitized_region
    
    # Invalid region - print error and return empty string
    print(f"\nError: Region '{region}' is not supported")
    print(f"Supported regions: {', '.join(supported_regions)}")
    print("To use a different region, please modify the validate_region function")
    
    return ""


def verify_prerequisites() -> bool:
    """Verify all prerequisites for deployment."""
    print("\nChecking prerequisites...")
    
    if not verify_aws_credentials():
        return False
    
    if not verify_cdk_installed():
        return False
    
    return True


def collect_deployment_params(config: Config) -> DeploymentParams:
    """Collect deployment parameters from user input."""
    print("\nConfiguration Parameters:")
    
    # Get account ID
    account_id = get_aws_account_id()
    if not account_id:
        raise ValueError("Unable to determine AWS account ID")
    print(f"AWS Account: {account_id}")
    
    # Get region with user input and validation
    print(f"Current region: {config.region}")
    
    # Validate current config region first
    validated_region = validate_region(config.region)
    if not validated_region:
        # Current config has invalid region, force user to enter valid one
        while not validated_region:
            region_input = input("Enter AWS Region (us-east-1, us-east-2, us-west-2): ").strip()
            validated_region = validate_region(region_input)
            if not validated_region:
                print("Please enter a valid region")
    else:
        # Current config region is valid, offer it as default
        region_input = input(f"AWS Region [{config.region}]: ").strip()
        if region_input:
            # User entered a new region, validate it
            new_region = validate_region(region_input)
            if new_region:
                validated_region = new_region
            else:
                print(f"Keeping current region: {config.region}")
                validated_region = config.region
    
    # Update config if region changed
    if validated_region != config.region:
        config.region = validated_region
        print(f"Updated region to: {validated_region}")
    
    # Create params with defaults
    params = DeploymentParams(region=validated_region, account_id=account_id)
    
    # Load cdk.json context values if they exist
    cdk_json_path = Path(__file__).parent / "cdk.json"
    cdk_context = {}
    if cdk_json_path.exists():
        with open(cdk_json_path, "r") as f:
            cdk_data = json.load(f)
            cdk_context = cdk_data.get("context", {})
    
    # S3 Bucket - priority: default → cdk.json → config.yml → user prompt
    s3_bucket = params.s3_bucket or cdk_context.get("s3_bucket", "") or getattr(config, "s3_artifacts_bucket", "")
    if s3_bucket:
        bucket_input = input(f"S3 Artifacts Bucket [{s3_bucket}]: ").strip()
        params.s3_bucket = bucket_input if bucket_input else s3_bucket
    else:
        while not params.s3_bucket:
            params.s3_bucket = input("S3 Artifacts Bucket: ").strip()
            if not params.s3_bucket:
                print("S3 bucket name is required")
    
    # GitHub Owner
    github_owner = cdk_context.get("github_owner", params.github_owner)
    owner_input = input(f"GitHub Owner [{github_owner}]: ").strip()
    params.github_owner = owner_input if owner_input else github_owner
    
    # GitHub Repository
    github_repo = cdk_context.get("github_repo", params.github_repo)
    repo_input = input(f"GitHub Repository [{github_repo}]: ").strip()
    params.github_repo = repo_input if repo_input else github_repo
    
    # GitHub Branch
    github_branch = cdk_context.get("github_branch", params.github_branch)
    branch_input = input(f"GitHub Branch [{github_branch}]: ").strip()
    params.github_branch = branch_input if branch_input else github_branch
    
    # Save user selections back to cdk.json
    cdk_data = {"app": "python3 app.py", "context": {}}
    if cdk_json_path.exists():
        with open(cdk_json_path, "r") as f:
            cdk_data = json.load(f)
    
    if "context" not in cdk_data:
        cdk_data["context"] = {}
    cdk_data["context"]["s3_bucket"] = params.s3_bucket
    cdk_data["context"]["github_owner"] = params.github_owner
    cdk_data["context"]["github_repo"] = params.github_repo
    cdk_data["context"]["github_branch"] = params.github_branch
    
    with open(cdk_json_path, "w") as f:
        json.dump(cdk_data, f, indent=2)
    
    return params


def execute_deployment(params: DeploymentParams, state: CDKState) -> bool:
    """Execute the deployment with given parameters."""
    # Check CDK bootstrap
    if not verify_cdk_bootstrap(params.region):
        response = input("\nCDK bootstrap not found. Continue anyway? [y/N]: ").strip().lower()
        if response != "y":
            print("Deployment cancelled")
            return False
    
    # Confirm deployment
    print("\nDeployment Summary:")
    print(f"  Account: {params.account_id}")
    print(f"  Region: {params.region}")
    print(f"  Stack: dynamodb")
    print(f"  Resources: 14 DynamoDB tables, 1 IAM policy")
    
    response = input("\nProceed with deployment? [Y/n]: ").strip().lower()
    if response == "n":
        print("Deployment cancelled")
        return False
    
    # Deploy the stack
    result = deploy_dynamodb_stack(params.region)
    return result.get("success", False)


def verify_deployment(params: DeploymentParams) -> dict:
    """Verify the deployment completed successfully."""
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


def update_configurations(config: Config, state: CDKState, params: DeploymentParams, 
                         validation: dict, config_path: Path, state_path: Path) -> None:
    """Update config and state files with deployment results."""
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


def main():
    """Main deployment entry point."""
    print("=" * 60)
    print("Eidolon Engine DynamoDB Deployment")
    print("=" * 60)

    # Load configuration
    config_path = Path(__file__).parent.parent / "config.yml"
    state_path = Path(__file__).parent / ".cdk-state.json"
    
    config = Config.load(str(config_path))
    state = CDKState.load(str(state_path))

    # Step 1: Verify prerequisites
    if not verify_prerequisites():
        return 1

    # Step 2: Collect user input
    try:
        params = collect_deployment_params(config)
    except ValueError as err:
        print(f"Error: {err}")
        return 1

    # Step 3: Execute deployment
    if not execute_deployment(params, state):
        print("\nDeployment failed!")
        return 1

    # Step 4: Verify deployment
    validation = verify_deployment(params)
    
    if not validation.get("success", False):
        print("\nWarning: Deployment completed with issues")
        if not validation.get("tables", {}).get("success", False):
            print("  - Some tables were not created")
        if not all(validation.get("policies", {}).values()):
            print("  - Some IAM policies were not created")

    # Step 5: Update configurations
    update_configurations(config, state, params, validation, config_path, state_path)

    # Final response
    print("\n" + "=" * 60)
    if validation.get("success", False):
        print("DynamoDB deployment completed successfully!")
    else:
        print("DynamoDB deployment completed with warnings")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
