"""Main deployment script for Eidolon Engine infrastructure."""

import argparse
import json
import os
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
from lambda_functions import deploy_lambda, update_lambda_functions_directly
from player import deploy_player
from s3 import deploy_s3
from story import deploy_story
from utilities import (
    get_aws_account_id,
    validate_lambda_artifacts,
    validate_region,
    validate_s3_bucket,
    verify_cdk_bootstrap,
    verify_prerequisites,
)


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


def is_interactive() -> bool:
    """Check if running in interactive mode (TTY available)."""
    return sys.stdin.isatty()


def get_param_value(
    env_var: str,
    config_value: str,
    cdk_value: str,
    default_value: str,
    prompt: str,
    required: bool = False,
) -> str:
    """
    Get parameter value with precedence: env var > config > cdk.json > prompt > default.

    Args:
        env_var: Environment variable name
        config_value: Value from config.yml
        cdk_value: Value from cdk.json context
        default_value: Default value to use
        prompt: Prompt text for interactive mode
        required: If True, will loop until value provided

    Returns:
        The resolved parameter value
    """
    # Check environment variable first
    env_value = os.environ.get(env_var, "").strip()
    if env_value:
        return env_value

    # Use config value if available
    if config_value:
        if is_interactive():
            user_input = input(f"{prompt} [{config_value}]: ").strip()
            return user_input if user_input else config_value
        return config_value

    # Use cdk.json value if available
    if cdk_value:
        if is_interactive():
            user_input = input(f"{prompt} [{cdk_value}]: ").strip()
            return user_input if user_input else cdk_value
        return cdk_value

    # Use default value if available
    if default_value:
        if is_interactive():
            user_input = input(f"{prompt} [{default_value}]: ").strip()
            return user_input if user_input else default_value
        return default_value

    # No defaults available, must prompt or error
    if is_interactive():
        if required:
            value = ""
            while not value:
                value = input(f"{prompt}: ").strip()
                if not value:
                    print(f"Value is required for {env_var}")
            return value
        else:
            return input(f"{prompt}: ").strip()
    else:
        # Non-interactive mode without value - error for required, empty for optional
        if required:
            raise ValueError(f"Required parameter {env_var} not set (set via environment variable or config file)")
        return ""


def collect_deployment_params(config: Config) -> DeploymentParams:
    """
    Collect deployment parameters from environment variables, config files, or user input.

    Parameter resolution order:
    1. Environment variables (AWS_REGION, EIDOLON_S3_BUCKET, etc.)
    2. config.yml values
    3. cdk.json context values
    4. Interactive prompts (if TTY available)
    5. Default values

    Raises:
        ValueError: If required parameters missing in non-interactive mode
    """
    print("\nConfiguration Parameters:")

    # Get account ID
    account_id = get_aws_account_id()
    if not account_id:
        raise ValueError("Unable to determine AWS account ID")
    print(f"AWS Account: {account_id}")

    # Get region from environment or config
    region_from_env = os.environ.get("AWS_REGION", "").strip()
    if region_from_env:
        validated_region = validate_region(region_from_env)
        if not validated_region:
            raise ValueError(f"Invalid AWS_REGION environment variable: {region_from_env}")
        print(f"Region (from AWS_REGION): {validated_region}")
    else:
        # Validate current config region
        validated_region = validate_region(config.region)
        if not validated_region:
            # Invalid config region - must prompt or error
            if is_interactive():
                while not validated_region:
                    region_input = input("Enter AWS Region (us-east-1, us-east-2, us-west-2): ").strip()
                    validated_region = validate_region(region_input)
                    if not validated_region:
                        print("Please enter a valid region")
            else:
                raise ValueError("Invalid region in config.yml and AWS_REGION not set")
        else:
            # Valid config region - allow override in interactive mode
            if is_interactive():
                region_input = input(f"AWS Region [{config.region}]: ").strip()
                if region_input:
                    new_region = validate_region(region_input)
                    if new_region:
                        validated_region = new_region
                    else:
                        print(f"Keeping current region: {config.region}")
            print(f"Region: {validated_region}")

    # Update config if region changed
    if validated_region != config.region:
        config.region = validated_region

    # Create params with defaults
    params = DeploymentParams(region=validated_region, account_id=account_id)

    # Load cdk.json context values if they exist
    cdk_json_path = Path(__file__).parent / "cdk.json"
    cdk_context = {}
    if cdk_json_path.exists():
        with open(cdk_json_path, "r", encoding="utf-8") as f:
            cdk_data = json.load(f)
            cdk_context = cdk_data.get("context", {})

    # Deployment Mode
    deployment_mode_value = get_param_value(
        env_var="EIDOLON_DEPLOYMENT_MODE",
        config_value=config.deployment_mode or "",
        cdk_value=cdk_context.get("deployment_mode", ""),
        default_value=params.deployment_mode,
        prompt="Deployment Mode (mud/incremental/hybrid)",
        required=False,
    )
    params.deployment_mode = validate_deployment_mode(deployment_mode_value)

    # S3 Artifacts Bucket
    params.s3_bucket = get_param_value(
        env_var="EIDOLON_S3_BUCKET",
        config_value=getattr(config, "s3_artifacts_bucket", ""),
        cdk_value=cdk_context.get("s3_bucket", ""),
        default_value="",
        prompt="S3 Artifacts Bucket",
        required=True,
    )

    # S3 Scripts Bucket - only needed for MUD and Hybrid modes
    if params.deployment_mode != "incremental":
        params.scripts_bucket = get_param_value(
            env_var="EIDOLON_SCRIPTS_BUCKET",
            config_value=getattr(config, "s3_scripts_bucket", ""),
            cdk_value=cdk_context.get("scripts_bucket", ""),
            default_value="",
            prompt="S3 Scripts Bucket",
            required=True,
        )

    # S3 Client Bucket (for portal static files)
    params.client_bucket = get_param_value(
        env_var="EIDOLON_CLIENT_BUCKET",
        config_value="",
        cdk_value=cdk_context.get("client_bucket", ""),
        default_value="",
        prompt="S3 Client Bucket",
        required=True,
    )

    # GitHub Owner
    params.github_owner = get_param_value(
        env_var="GITHUB_OWNER",
        config_value="",
        cdk_value=cdk_context.get("github_owner", ""),
        default_value=params.github_owner,
        prompt="GitHub Owner",
        required=False,
    )

    # GitHub Repository
    params.github_repo = get_param_value(
        env_var="GITHUB_REPO",
        config_value="",
        cdk_value=cdk_context.get("github_repo", ""),
        default_value=params.github_repo,
        prompt="GitHub Repository",
        required=False,
    )

    # GitHub Branch
    params.github_branch = get_param_value(
        env_var="GITHUB_BRANCH",
        config_value="",
        cdk_value=cdk_context.get("github_branch", ""),
        default_value=params.github_branch,
        prompt="GitHub Branch",
        required=False,
    )

    # Domain (base domain for all services)
    params.domain = get_param_value(
        env_var="EIDOLON_DOMAIN",
        config_value="",
        cdk_value=cdk_context.get("domain", ""),
        default_value=params.domain,
        prompt="Domain (e.g., darkrelics.net)",
        required=True,
    )

    # Route53 Hosted Zone ID
    params.hosted_zone_id = get_param_value(
        env_var="EIDOLON_HOSTED_ZONE_ID",
        config_value="",
        cdk_value=cdk_context.get("hosted_zone_id", ""),
        default_value="",
        prompt="Route53 Hosted Zone ID (e.g., Z1234567890ABC)",
        required=True,
    )

    # API Host (subdomain for API)
    params.api_host = get_param_value(
        env_var="EIDOLON_API_HOST",
        config_value="",
        cdk_value=cdk_context.get("api_host", ""),
        default_value=params.api_host,
        prompt="API Host (e.g., api)",
        required=True,
    )

    # Client Host (subdomain for portal)
    params.client_host = get_param_value(
        env_var="EIDOLON_CLIENT_HOST",
        config_value="",
        cdk_value=cdk_context.get("client_host", ""),
        default_value=params.client_host,
        prompt="Client Host (e.g., portal)",
        required=True,
    )

    # Reply Email (for Cognito)
    params.reply_email = get_param_value(
        env_var="EIDOLON_REPLY_EMAIL",
        config_value="",
        cdk_value=cdk_context.get("reply_email", ""),
        default_value=params.reply_email,
        prompt="Reply email for Cognito",
        required=False,
    )

    # Save user selections back to cdk.json
    cdk_data = {"app": "python3 app.py", "context": {}}
    if cdk_json_path.exists():
        with open(cdk_json_path, "r", encoding="utf-8") as f:
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

    with open(cdk_json_path, "w", encoding="utf-8") as f:
        json.dump(cdk_data, f, indent=2)

    return params


def validate_deployment_prerequisites(params) -> tuple:
    """Validate deployment prerequisites before starting.

    Checks:
    - S3 artifacts bucket exists and is accessible
    - Lambda artifacts exist in S3 (warns if missing, doesn't fail)

    Args:
        params: DeploymentParams object

    Returns:
        Tuple of (success: bool, warnings: list)
    """
    print("\n" + "=" * 60)
    print("Pre-deployment Validation")
    print("=" * 60)

    warnings = []
    errors = []

    # Validate S3 artifacts bucket exists
    print("\nValidating S3 buckets...")
    if not validate_s3_bucket(params.s3_bucket, params.region):
        errors.append(f"S3 artifacts bucket '{params.s3_bucket}' not accessible")

    # Validate S3 client bucket if specified
    if params.client_bucket:
        if not validate_s3_bucket(params.client_bucket, params.region):
            warnings.append(f"S3 client bucket '{params.client_bucket}' not accessible (will be created)")

    # Validate Lambda artifacts exist (warning only - CodeBuild may create them)
    print("\nValidating Lambda artifacts...")
    artifacts_ok, missing, present = validate_lambda_artifacts(
        params.s3_bucket, params.region, params.deployment_mode
    )
    if not artifacts_ok:
        warnings.append(
            f"{len(missing)} Lambda artifacts missing from S3. "
            "CodeBuild will create them during deployment."
        )

    # Report results
    print("\n" + "-" * 40)
    if errors:
        print("ERRORS (deployment cannot proceed):")
        for error in errors:
            print(f"  - {error}")

    if warnings:
        print("WARNINGS (deployment can proceed):")
        for warning in warnings:
            print(f"  - {warning}")

    if not errors and not warnings:
        print("All pre-deployment checks passed!")

    print("-" * 40)

    return len(errors) == 0, warnings


def update_lambdas_only():
    """Update Lambda functions only without full deployment."""
    print("=" * 60)
    print("Lambda Functions Update")
    print("=" * 60)

    # Load minimal configuration needed
    config_path = Path(__file__).parent.parent / "config.yml"
    config = Config.load(str(config_path))

    # Get account ID and region
    try:
        account_id = get_aws_account_id()
        if not account_id:
            print("Error: Unable to determine AWS account ID")
            return 1

        region = validate_region(config.region)
        if not region:
            print("Error: Invalid region in configuration")
            return 1

        # Get S3 bucket from environment, config, or user input
        s3_bucket = os.environ.get("EIDOLON_S3_BUCKET", "").strip()
        if not s3_bucket:
            s3_bucket = getattr(config, "s3_artifacts_bucket", "")
        if not s3_bucket:
            if is_interactive():
                s3_bucket = input("S3 Artifacts Bucket: ").strip()
            if not s3_bucket:
                print("Error: S3 bucket name is required (set EIDOLON_S3_BUCKET or config.yml)")
                return 1

        print(f"\nAccount: {account_id}")
        print(f"Region: {region}")
        print(f"S3 Bucket: {s3_bucket}")

        # Skip confirmation in non-interactive mode
        if is_interactive():
            response = input("\nProceed with Lambda updates? [Y/n]: ").strip().lower()
            if response == "n":
                print("Lambda update cancelled")
                return 0
        else:
            print("\nProceeding with Lambda updates (non-interactive mode)")

        # Create minimal params object
        class UpdateParams:
            def __init__(self, account_id, region):
                self.account_id = account_id
                self.region = region

        params = UpdateParams(account_id, region)

        # Run the Lambda update
        success = update_lambda_functions_directly(params, region, s3_bucket)

        if success:
            print("\nLambda functions updated successfully")
            return 0
        else:
            print("\nLambda function update failed")
            return 1

    except Exception as err:
        print(f"\nError during Lambda update: {err}")
        return 1


def main():
    """Main deployment entry point."""
    parser = argparse.ArgumentParser(description="Eidolon Engine Infrastructure Deployment")
    parser.add_argument(
        "--update-lambdas",
        action="store_true",
        help="Only update Lambda functions with latest artifacts (faster than full deployment)",
    )
    args = parser.parse_args()

    if args.update_lambdas:
        return update_lambdas_only()

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
        if is_interactive():
            response = input("\nCDK bootstrap not found. Continue anyway? [y/N]: ").strip().lower()
            if response != "y":
                print("Deployment cancelled")
                return 0
        else:
            print("\nWARNING: CDK bootstrap not found, proceeding anyway (non-interactive mode)")

    # Pre-deployment validation
    prereq_ok, prereq_warnings = validate_deployment_prerequisites(params)
    if not prereq_ok:
        print("\nDeployment cannot proceed due to prerequisite errors.")
        print("Please fix the errors above and try again.")
        return 1

    if prereq_warnings and is_interactive():
        print(f"\n{len(prereq_warnings)} warning(s) found during pre-deployment validation.")
        response = input("Continue with deployment? [Y/n]: ").strip().lower()
        if response == "n":
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

    # Skip confirmation in non-interactive mode
    if is_interactive():
        response = input("\nProceed with deployment? [Y/n]: ").strip().lower()
        if response == "n":
            print("Deployment cancelled")
            return 0
    else:
        print("\nProceeding with deployment (non-interactive mode)")

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
                result = deploy_func(params, config, state, config_path, state_path)

                # Special handling for client stack which returns a tuple
                if stack_name == "client" and isinstance(result, tuple):
                    infra_success, build_success = result
                    if infra_success and not build_success:
                        # Infrastructure OK but build failed - mark as warning
                        deployment_results[stack_name] = "warning"
                    else:
                        deployment_results[stack_name] = infra_success
                else:
                    deployment_results[stack_name] = result
                    if not result:
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

    # Phase 11: Lambda Function Updates
    # Check if all required stacks for Lambda updates were successful
    # Incremental mode does not require the S3 stack; only gate on CodeBuild and Lambda
    required_stacks = ["codebuild", "lambda"]
    overall_success = all(
        deployment_results.get(stack, False) and deployment_results.get(stack) != "warning" for stack in required_stacks
    )
    lambda_update_success = False
    if overall_success:
        lambda_update_success = update_lambda_functions_directly(params, params.region, params.s3_bucket)
        if not lambda_update_success:
            print("\nWARNING: Lambda function updates failed")
    else:
        print("\nSkipping Lambda function updates due to deployment issues")

    # Final summary
    print("\n" + "=" * 60)
    print("Deployment Summary")
    print("=" * 60)
    print(f"Mode: {params.deployment_mode.upper()}")
    for stack_name in deployment_order:
        if stack_name in deployment_results:
            result = deployment_results[stack_name]
            if result == "warning":
                status = "WARNING"
            elif result:
                status = "OK"
            else:
                status = "FAILED"
            print(f"[{status}] {stack_name.capitalize()} Stack")
        else:
            print(f"[SKIPPED] {stack_name.capitalize()} Stack")

    if overall_success:
        lambda_status = "OK" if lambda_update_success else "WARNING"
        print(f"[{lambda_status}] Lambda Function Updates")

    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
