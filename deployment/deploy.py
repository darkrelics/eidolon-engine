"""Main deployment script for Eidolon Engine infrastructure."""

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from core.config import Config
from core.state import CDKState
from utilities import get_aws_account_id, validate_region, verify_prerequisites
from dynamodb import deploy_dynamodb
from codebuild import deploy_codebuild
from s3 import deploy_s3


@dataclass
class DeploymentParams:
    """Parameters for deployment."""
    region: str = "us-east-1"
    account_id: str = ""
    s3_bucket: str = ""
    scripts_bucket: str = ""
    github_owner: str = "robinje"
    github_repo: str = "eidolon-engine"
    github_branch: str = "develop"


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
    
    # S3 Artifacts Bucket - priority: default → cdk.json → config.yml → user prompt
    s3_bucket = params.s3_bucket or cdk_context.get("s3_bucket", "") or getattr(config, "s3_artifacts_bucket", "")
    if s3_bucket:
        bucket_input = input(f"S3 Artifacts Bucket [{s3_bucket}]: ").strip()
        params.s3_bucket = bucket_input if bucket_input else s3_bucket
    else:
        while not params.s3_bucket:
            params.s3_bucket = input("S3 Artifacts Bucket: ").strip()
            if not params.s3_bucket:
                print("S3 bucket name is required")
    
    # S3 Scripts Bucket - priority: default → cdk.json → config.yml → user prompt
    scripts_bucket = params.scripts_bucket or cdk_context.get("scripts_bucket", "") or getattr(config, "s3_scripts_bucket", "")
    if scripts_bucket:
        scripts_input = input(f"S3 Scripts Bucket [{scripts_bucket}]: ").strip()
        params.scripts_bucket = scripts_input if scripts_input else scripts_bucket
    else:
        while not params.scripts_bucket:
            params.scripts_bucket = input("S3 Scripts Bucket: ").strip()
            if not params.scripts_bucket:
                print("S3 scripts bucket name is required")
    
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
    cdk_data["context"]["scripts_bucket"] = params.scripts_bucket
    cdk_data["context"]["github_owner"] = params.github_owner
    cdk_data["context"]["github_repo"] = params.github_repo
    cdk_data["context"]["github_branch"] = params.github_branch
    
    with open(cdk_json_path, "w") as f:
        json.dump(cdk_data, f, indent=2)
    
    return params


def main():
    """Main deployment entry point."""
    print("=" * 60)
    print("Eidolon Engine Infrastructure Deployment")
    print("=" * 60)

    # Load configuration
    config_path = Path(__file__).parent.parent / "config.yml"
    state_path = Path(__file__).parent / ".cdk-state.json"
    
    config = Config.load(str(config_path))
    state = CDKState.load(str(state_path))

    # Verify prerequisites
    if not verify_prerequisites():
        return 1

    # Collect user input
    try:
        params = collect_deployment_params(config)
    except ValueError as err:
        print(f"Error: {err}")
        return 1

    # Check CDK bootstrap
    from utilities import verify_cdk_bootstrap
    if not verify_cdk_bootstrap(params.region):
        response = input("\nCDK bootstrap not found. Continue anyway? [y/N]: ").strip().lower()
        if response != "y":
            print("Deployment cancelled")
            return 0

    # Single deployment confirmation after all input
    print("\n" + "=" * 60)
    print("Deployment Summary")
    print("=" * 60)
    print(f"  Account: {params.account_id}")
    print(f"  Region: {params.region}")
    print(f"  Stacks to deploy:")
    print(f"    - DynamoDB: 14 tables, 1 IAM policy")
    print(f"    - CodeBuild: 2 projects, 1 S3 bucket, 1 role, 2 policies")
    print(f"    - S3: 1 bucket, 1 IAM policy, Lua scripts upload")
    print(f"  S3 Artifacts: {params.s3_bucket}")
    print(f"  S3 Scripts: {params.scripts_bucket}")
    print(f"  GitHub: {params.github_owner}/{params.github_repo} ({params.github_branch})")
    print("=" * 60)
    
    response = input("\nProceed with deployment? [Y/n]: ").strip().lower()
    if response == "n":
        print("Deployment cancelled")
        return 0

    # Deploy stacks
    dynamodb_success = deploy_dynamodb(params, config, state, config_path, state_path)
    codebuild_success = deploy_codebuild(params, config, state, config_path, state_path)
    s3_success = deploy_s3(params, config, state, config_path, state_path)

    # Final summary
    print("\n" + "=" * 60)
    print("Deployment Summary")
    print("=" * 60)
    print(f"[{'OK' if dynamodb_success else 'WARNING'}] DynamoDB Stack")
    print(f"[{'OK' if codebuild_success else 'WARNING'}] CodeBuild Stack")
    print(f"[{'OK' if s3_success else 'WARNING'}] S3 Stack")
    print("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())