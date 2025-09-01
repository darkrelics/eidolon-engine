"""Main deployment script for Eidolon Engine infrastructure."""

import json
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

from api import deploy_api
from character import deploy_character
from client import deploy_client
from cloudwatch import deploy_cloudwatch
from codebuild import deploy_codebuild
from core.config import Config
from core.state import CDKState
from deploy_mode import display_mode_summary, get_deployment_order, validate_deployment_mode
from dynamodb import deploy_dynamodb
from lambda_functions import deploy_lambda
from player import deploy_player
from s3 import deploy_s3
from story import deploy_story
from utilities import get_aws_account_id, validate_region, verify_cdk_bootstrap, verify_prerequisites


@dataclass
class DeploymentParams:
    """Parameters for deployment."""

    region: str = "us-east-1"
    account_id: str = ""
    deployment_mode: str = "hybrid"
    s3_bucket: str = ""
    scripts_bucket: str = ""
    client_bucket: str = ""
    github_owner: str = "robinje"
    github_repo: str = "eidolon-engine"
    github_branch: str = "develop"
    domain: str = "darkrelics.net"
    hosted_zone_id: str = ""
    api_host: str = "api"
    client_host: str = "portal"
    reply_email: str = "contact@darkrelics.net"


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

    # Deployment Mode - priority: config.yml → cdk.json → default
    deployment_mode = config.deployment_mode or cdk_context.get("deployment_mode", params.deployment_mode)
    mode_input = input(f"Deployment Mode (mud/incremental/hybrid) [{deployment_mode}]: ").strip()
    if mode_input:
        params.deployment_mode = validate_deployment_mode(mode_input)
    else:
        params.deployment_mode = validate_deployment_mode(deployment_mode)

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

    # S3 Scripts Bucket - only needed for MUD and Hybrid modes
    if params.deployment_mode != "incremental":
        scripts_bucket = params.scripts_bucket or cdk_context.get("scripts_bucket", "") or getattr(config, "s3_scripts_bucket", "")
        if scripts_bucket:
            scripts_input = input(f"S3 Scripts Bucket [{scripts_bucket}]: ").strip()
            params.scripts_bucket = scripts_input if scripts_input else scripts_bucket
        else:
            while not params.scripts_bucket:
                params.scripts_bucket = input("S3 Scripts Bucket: ").strip()
                if not params.scripts_bucket:
                    print("S3 scripts bucket name is required")

    # S3 Client Bucket (for portal static files)
    client_bucket = cdk_context.get("client_bucket", params.client_bucket)
    if not client_bucket:
        # Generate default based on domain and client host
        if params.domain and params.client_host:
            client_bucket = f"{params.client_host}-{params.domain.replace('.', '-')}"
    if client_bucket:
        client_input = input(f"S3 Client Bucket [{client_bucket}]: ").strip()
        params.client_bucket = client_input if client_input else client_bucket
    else:
        while not params.client_bucket:
            params.client_bucket = input("S3 Client Bucket: ").strip()
            if not params.client_bucket:
                print("S3 client bucket name is required")

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

    # Domain and Hosting Configuration
    # Domain (base domain for all services)
    domain = cdk_context.get("domain", params.domain)
    if domain:
        domain_input = input(f"Domain (e.g., darkrelics.net) [{domain}]: ").strip()
        params.domain = domain_input if domain_input else domain
    else:
        while not params.domain:
            params.domain = input("Domain (e.g., darkrelics.net): ").strip()
            if not params.domain:
                print("Domain is required for deployment")

    # Route53 Hosted Zone ID
    hosted_zone_id = cdk_context.get("hosted_zone_id", params.hosted_zone_id)
    if hosted_zone_id:
        zone_input = input(f"Route53 Hosted Zone ID [{hosted_zone_id}]: ").strip()
        params.hosted_zone_id = zone_input if zone_input else hosted_zone_id
    else:
        while not params.hosted_zone_id:
            params.hosted_zone_id = input("Route53 Hosted Zone ID (e.g., Z1234567890ABC): ").strip()
            if not params.hosted_zone_id:
                print("Hosted Zone ID is required for DNS configuration")

    # API Host (subdomain for API)
    api_host = cdk_context.get("api_host", params.api_host)
    if api_host:
        api_input = input(f"API Host (e.g., api) [{api_host}]: ").strip()
        params.api_host = api_input if api_input else api_host
    else:
        while not params.api_host:
            params.api_host = input("API Host (e.g., api): ").strip()
            if not params.api_host:
                print("API host is required for API configuration")

    # Client Host (subdomain for portal)
    client_host = cdk_context.get("client_host", params.client_host)
    if client_host:
        host_input = input(f"Client Host (e.g., portal) [{client_host}]: ").strip()
        params.client_host = host_input if host_input else client_host
    else:
        while not params.client_host:
            params.client_host = input("Client Host (e.g., portal): ").strip()
            if not params.client_host:
                print("Client host is required for portal configuration")

    # Reply Email (for Cognito)
    reply_email = cdk_context.get("reply_email", params.reply_email)
    email_input = input(f"Reply email for Cognito [{reply_email}]: ").strip()
    params.reply_email = email_input if email_input else reply_email

    # Save user selections back to cdk.json
    cdk_data = {"app": "python3 app.py", "context": {}}
    if cdk_json_path.exists():
        with open(cdk_json_path, "r") as f:
            cdk_data = json.load(f)

    if "context" not in cdk_data:
        cdk_data["context"] = {}
    cdk_data["context"]["deployment_mode"] = params.deployment_mode
    cdk_data["context"]["s3_bucket"] = params.s3_bucket
    cdk_data["context"]["scripts_bucket"] = params.scripts_bucket
    cdk_data["context"]["client_bucket"] = params.client_bucket
    cdk_data["context"]["github_owner"] = params.github_owner
    cdk_data["context"]["github_repo"] = params.github_repo
    cdk_data["context"]["github_branch"] = params.github_branch
    cdk_data["context"]["domain"] = params.domain
    cdk_data["context"]["hosted_zone_id"] = params.hosted_zone_id
    cdk_data["context"]["api_host"] = params.api_host
    cdk_data["context"]["client_host"] = params.client_host
    cdk_data["context"]["reply_email"] = params.reply_email

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
        print(f"\nError during parameter collection: {err}")
        return 1
    except Exception as err:
        print("\nUnexpected error during parameter collection")
        print(f"Error: {err}")
        print("\nFull stack trace:")
        print(traceback.format_exc())
        return 1

    # Check CDK bootstrap
    if not verify_cdk_bootstrap(params.region):
        response = input("\nCDK bootstrap not found. Continue anyway? [y/N]: ").strip().lower()
        if response != "y":
            print("Deployment cancelled")
            return 0

    # Display deployment summary based on mode
    print("\n" + "=" * 60)
    print("Deployment Summary")
    print("=" * 60)
    print(f"  Account: {params.account_id}")
    print(f"  Region: {params.region}")
    display_mode_summary(params.deployment_mode)
    print(f"  S3 Artifacts: {params.s3_bucket}")
    print(f"  S3 Scripts: {params.scripts_bucket}")
    print(f"  S3 Client: {params.client_bucket}")
    print(f"  GitHub: {params.github_owner}/{params.github_repo} ({params.github_branch})")
    print(f"  API URL: {params.api_host}.{params.domain}")
    print(f"  Client URL: {params.client_host}.{params.domain}")
    print("=" * 60)

    response = input("\nProceed with deployment? [Y/n]: ").strip().lower()
    if response == "n":
        print("Deployment cancelled")
        return 0

    # Update config with deployment mode
    config.deployment_mode = params.deployment_mode
    config.save(str(config_path))

    # Get deployment order based on mode
    deployment_order = get_deployment_order(params.deployment_mode)

    # Map stack names to deployment functions
    deployment_functions = {
        "codebuild": deploy_codebuild,
        "dynamodb": deploy_dynamodb,
        "lambda": deploy_lambda,
        "character": deploy_character,
        "player": deploy_player,
        "story": deploy_story,
        "s3": deploy_s3,
        "cloudwatch": deploy_cloudwatch,
        "api": deploy_api,
        "client": deploy_client,
    }

    # Deploy stacks in order
    deployment_results = {}
    for stack_name in deployment_order:
        if stack_name in deployment_functions:
            print(f"\nDeploying {stack_name} stack...")
            deploy_func = deployment_functions[stack_name]
            try:
                success = deploy_func(params, config, state, config_path, state_path)
                deployment_results[stack_name] = success
                if not success:
                    print(f"WARNING: {stack_name} deployment had issues")
            except Exception as e:
                print(f"\n{'='*60}")
                print(f"ERROR deploying {stack_name} stack")
                print(f"{'='*60}")
                print(f"Error: {e}")
                print("\nFull stack trace:")
                print(traceback.format_exc())
                print(f"{'='*60}")
                deployment_results[stack_name] = False
        else:
            print(f"\nSkipping {stack_name} stack (not yet implemented)")
            deployment_results[stack_name] = False

    # Final summary
    print("\n" + "=" * 60)
    print("Deployment Summary")
    print("=" * 60)
    print(f"Mode: {params.deployment_mode.upper()}")
    for stack_name in deployment_order:
        if stack_name in deployment_results:
            status = "OK" if deployment_results[stack_name] else "WARNING"
            print(f"[{status}] {stack_name.capitalize()} Stack")
        else:
            print(f"[SKIPPED] {stack_name.capitalize()} Stack")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
