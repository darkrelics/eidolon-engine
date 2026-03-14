"""Deploy Eidolon infrastructure using CloudFormation templates."""

import sys
import time
from pathlib import Path

import boto3
import yaml
from botocore.exceptions import ClientError
from deployment.acm import certificate_exists, wait_for_certificate_validation
from deployment.apigateway import force_api_gateway_deployment
from deployment.cloudformation import deploy_stack, get_stack_output
from deployment.cloudfront import wait_for_cloudfront_operational
from deployment.codebuild import trigger_build
from deployment.config_update import update_config_from_stacks
from deployment.lambda_utils import cleanup_old_layer_versions, publish_layer_version, update_lambda_function_code
from deployment.s3 import set_bucket_policy_for_cloudfront, upload_scripts_to_s3
from deployment.tracker import DeploymentTracker
from deployment.validation import VALID_DEPLOYMENT_MODES, validate_config, validate_environment, validate_resources

tracker = DeploymentTracker()

# Deployment mode matrix: which stacks to deploy per mode
STACK_MODE_MATRIX = {
    "eidolon-roles": ["mud", "incremental", "hybrid"],
    "eidolon-dynamo": ["mud", "incremental", "hybrid"],
    "eidolon-certificate": ["mud", "incremental", "hybrid"],
    "eidolon-codebuild": ["mud", "incremental", "hybrid"],
    "eidolon-lambda-cognito": ["mud", "incremental", "hybrid"],
    "eidolon-cognito": ["mud", "incremental", "hybrid"],
    "eidolon-lambda-character": ["mud", "incremental", "hybrid"],
    "eidolon-lambda-story": ["incremental", "hybrid"],
    "eidolon-api-gateway": ["mud", "incremental", "hybrid"],
    "eidolon-portal-cloudfront": ["mud", "incremental", "hybrid"],
    "eidolon-codebuild-portal": ["mud", "incremental", "hybrid"],
    "eidolon-cloudwatch": ["mud", "hybrid"],
}


def should_deploy_stack(stack_name: str, deployment_mode: str) -> bool:
    """Check if a stack should be deployed for the given mode.

    Args:
        stack_name: CloudFormation stack name
        deployment_mode: Current deployment mode

    Returns:
        bool: True if stack should be deployed
    """
    modes = STACK_MODE_MATRIX.get(stack_name, [])
    return deployment_mode in modes


def print_deployment_plan(config: dict):
    """Print deployment plan summary.

    Args:
        config: Configuration dictionary
    """
    mode = config.get("deployment_mode", "")
    domain = config.get("domain", "")
    api_host = config.get("api_host", "")
    client_host = config.get("client_host", "")

    print(f"\n{'=' * 60}")
    print(f"Eidolon Deployment Plan [{mode}]")
    print(f"{'=' * 60}")
    print(f"  Region:          {config.get('region', '')}")
    print(f"  Mode:            {mode}")
    print(f"  API Domain:      {api_host}.{domain}")
    print(f"  Portal Domain:   {client_host}.{domain}")
    print(f"  S3 Lambda:       {config.get('s3_bucket', '')}")
    print(f"  S3 Client:       {config.get('client_bucket', '')}")
    scripts = config.get("scripts_bucket", "")
    if scripts:
        print(f"  S3 Scripts:      {scripts}")
    print(
        f"  GitHub:          {config.get('github_owner', '')}/{config.get('github_repo', '')} ({config.get('github_branch', '')})"
    )

    print("\n  Stacks to deploy:")
    for stack_name, modes in STACK_MODE_MATRIX.items():
        marker = "[YES]" if mode in modes else "[SKIP]"
        print(f"    {marker} {stack_name}")
    print()


def prompt_param(prompt: str, current: str, required: bool = False) -> str:
    """Prompt for a parameter value, showing the current value as default.

    Shows [current] and accepts Enter to keep it, or type a new value to override.

    Args:
        prompt: Description of the parameter
        current: Current value from config
        required: If True, loops until a value is provided

    Returns:
        The resolved parameter value
    """
    if current:
        user_input = input(f"  {prompt} [{current}]: ").strip()
        return user_input if user_input else current

    if required:
        value = ""
        while not value:
            value = input(f"  {prompt}: ").strip()
            if not value:
                print(f"    Value is required for {prompt}")
        return value

    return input(f"  {prompt}: ").strip()


def extract_deploy_config(full_config: dict) -> dict:
    """Extract flat deployment config from the unified config.yml structure.

    Args:
        full_config: Full config.yml dictionary

    Returns:
        Flat dictionary with deployment-specific keys
    """
    deployment = full_config.get("Deployment", {})
    github = full_config.get("GitHub", {})

    return {
        "region": full_config.get("AWS", {}).get("Region", ""),
        "deployment_mode": deployment.get("Mode", ""),
        "s3_bucket": deployment.get("S3Bucket", ""),
        "client_bucket": deployment.get("ClientBucket", ""),
        "scripts_bucket": deployment.get("ScriptsBucket", ""),
        "domain": deployment.get("Domain", ""),
        "route53_zone_id": deployment.get("Route53ZoneId", ""),
        "api_host": deployment.get("ApiHost", ""),
        "client_host": deployment.get("ClientHost", ""),
        "github_owner": github.get("Owner", ""),
        "github_repo": github.get("Repo", ""),
        "github_branch": github.get("Branch", ""),
    }


def collect_deployment_params(config: dict) -> dict:
    """Collect deployment parameters, prompting for overrides.

    Config values are shown as defaults. User can press Enter to accept
    or type a new value to override.

    Args:
        config: Flat config dictionary from extract_deploy_config

    Returns:
        Updated config dictionary with user overrides applied
    """
    print("\nDeployment Parameters:")

    config["deployment_mode"] = prompt_param(
        "Deployment Mode (mud/incremental/hybrid)", config.get("deployment_mode", ""), required=True
    )
    if config.get("deployment_mode", "") not in VALID_DEPLOYMENT_MODES:
        print(f"Error: Invalid deployment mode: {config.get('deployment_mode')}")
        print(f"  Valid modes: {', '.join(VALID_DEPLOYMENT_MODES)}")
        sys.exit(1)

    config["s3_bucket"] = prompt_param("S3 Lambda Bucket", config.get("s3_bucket", ""), required=True)
    config["client_bucket"] = prompt_param("S3 Client Bucket", config.get("client_bucket", ""), required=True)

    if config.get("deployment_mode", "") in ["mud", "hybrid"]:
        config["scripts_bucket"] = prompt_param("S3 Scripts Bucket", config.get("scripts_bucket", ""), required=True)

    config["github_branch"] = prompt_param("GitHub Branch", config.get("github_branch", ""), required=True)
    config["domain"] = prompt_param("Domain", config.get("domain", ""), required=True)
    config["route53_zone_id"] = prompt_param("Route53 Zone ID", config.get("route53_zone_id", ""), required=True)
    config["api_host"] = prompt_param("API Host", config.get("api_host", ""), required=True)
    config["client_host"] = prompt_param("Client Host", config.get("client_host", ""), required=True)

    return config


def main():
    base_dir = Path(__file__).resolve().parent.parent
    config_path = base_dir / "config.yml"

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as config_file:
        config = extract_deploy_config(yaml.safe_load(config_file))

    # Collect parameters interactively (config values shown as defaults)
    config = collect_deployment_params(config)

    # Step 1: Validate
    print("\n=== Step 1: Validating Configuration ===")
    tracker.start_step(1, "Validating Configuration")

    if not validate_config(config):
        sys.exit(1)
    print("  Config validated")

    deployment_mode = config.get("deployment_mode", "")
    account_id = validate_environment(str(base_dir), deployment_mode)
    if not account_id:
        sys.exit(1)
    print("  Environment validated")

    if not validate_resources(config):
        sys.exit(1)
    print("  Resources validated")

    tracker.complete_step()

    print_deployment_plan(config)

    response = input("Proceed with deployment? [Y/n]: ").strip().lower()
    if response == "n":
        print("Deployment cancelled")
        sys.exit(0)

    # Extract config values
    region = config.get("region", "")
    s3_bucket = config.get("s3_bucket", "")
    client_bucket = config.get("client_bucket", "")
    scripts_bucket = config.get("scripts_bucket", "")
    domain = config.get("domain", "")
    api_host = config.get("api_host", "")
    client_host = config.get("client_host", "")
    route53_zone_id = config.get("route53_zone_id", "")
    github_owner = config.get("github_owner", "")
    github_repo = config.get("github_repo", "")
    github_branch = config.get("github_branch", "")
    api_domain = f"{api_host}.{domain}"
    client_domain = f"{client_host}.{domain}"

    # Initialize AWS clients
    cf = boto3.client("cloudformation", region_name=region)
    cf_dir = base_dir / "cf"

    # Step 2: Deploy IAM Roles
    print("\n=== Step 2: Deploying IAM Roles ===")
    tracker.start_step(2, "Deploying IAM Roles")
    roles_params = {
        "S3BucketName": s3_bucket,
        "ClientBucketName": client_bucket,
        "ScriptsBucketName": scripts_bucket,
    }
    if not deploy_stack(cf, "eidolon-roles", cf_dir / "eidolon-roles.yml", roles_params, ["CAPABILITY_NAMED_IAM"]):
        print("Error: Failed to deploy IAM roles")
        tracker.print_summary()
        sys.exit(1)

    lambda_role_arn = get_stack_output(cf, "eidolon-roles", "LambdaExecutionRoleArn")
    codebuild_role_arn = get_stack_output(cf, "eidolon-roles", "CodeBuildRoleArn")
    if not lambda_role_arn or not codebuild_role_arn:
        print("Error: Could not retrieve role ARNs from stack outputs")
        tracker.print_summary()
        sys.exit(1)
    print(f"  Lambda Role: {lambda_role_arn}")
    print(f"  CodeBuild Role: {codebuild_role_arn}")

    print("  Waiting for IAM role propagation...")
    time.sleep(15)
    tracker.complete_step()

    # Step 3: Deploy DynamoDB Tables
    print("\n=== Step 3: Deploying DynamoDB Tables ===")
    tracker.start_step(3, "Deploying DynamoDB Tables")
    if not deploy_stack(cf, "eidolon-dynamo", cf_dir / "eidolon-dynamo.yml", {}):
        print("Error: Failed to deploy DynamoDB tables")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Step 4: Deploy ACM Certificates
    print("\n=== Step 4: Deploying ACM Certificates ===")
    tracker.start_step(4, "Deploying ACM Certificates")
    cert_params = {
        "ApiHostName": api_domain,
        "ClientHostName": client_domain,
        "Route53ZoneId": route53_zone_id,
    }
    if not deploy_stack(cf, "eidolon-certificate", cf_dir / "eidolon-certificate.yml", cert_params):
        print("Error: Failed to deploy ACM certificates")
        tracker.print_summary()
        sys.exit(1)

    api_cert_arn = get_stack_output(cf, "eidolon-certificate", "ApiCertificateArn")
    portal_cert_arn = get_stack_output(cf, "eidolon-certificate", "PortalCertificateArn")
    if not api_cert_arn or not portal_cert_arn:
        print("Error: Could not retrieve certificate ARNs from stack outputs")
        tracker.print_summary()
        sys.exit(1)

    # Wait for certificate validation
    certs_to_validate = [
        (api_domain, api_cert_arn, "API"),
        (client_domain, portal_cert_arn, "Portal"),
    ]
    for cert_domain, cert_arn, name in certs_to_validate:
        if certificate_exists(cert_domain, region):
            print(f"  {name} certificate already issued: {cert_domain}")
        else:
            if not wait_for_certificate_validation(cert_arn, region):
                print(f"Error: {name} certificate validation failed or timed out")
                tracker.print_summary()
                sys.exit(1)
            print(f"  {name} certificate validated")
    tracker.complete_step()

    # Step 5: Deploy CodeBuild Projects
    print("\n=== Step 5: Deploying CodeBuild Projects ===")
    tracker.start_step(5, "Deploying CodeBuild Projects")
    codebuild_params = {
        "S3BucketName": s3_bucket,
        "CodeBuildRoleArn": codebuild_role_arn,
        "GitHubOwner": github_owner,
        "GitHubRepo": github_repo,
        "GitHubBranch": github_branch,
    }
    if not deploy_stack(cf, "eidolon-codebuild", cf_dir / "eidolon-codebuild.yml", codebuild_params):
        print("Error: Failed to deploy CodeBuild projects")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Step 6: Build Lambda Layer
    print("\n=== Step 6: Building Lambda Layer ===")
    tracker.start_step(6, "Building Lambda Layer")
    if not trigger_build("eidolon-lambda-layer", region, github_branch):
        print("Error: Lambda layer build failed")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Step 7: Publish Lambda Layer Version
    print("\n=== Step 7: Publishing Lambda Layer ===")
    tracker.start_step(7, "Publishing Lambda Layer")
    lambda_client = boto3.client("lambda", region_name=region)
    layer_arn = publish_layer_version(
        lambda_client, "eidolon-dependencies", s3_bucket, "lambda-layer/lambda-layer.zip", "Eidolon Python Dependencies"
    )
    if not layer_arn:
        print("Error: Failed to publish Lambda layer")
        tracker.print_summary()
        sys.exit(1)
    print(f"  Layer ARN: {layer_arn}")
    cleanup_old_layer_versions(lambda_client, "eidolon-dependencies")
    tracker.complete_step()

    # Step 8: Build Lambda Functions
    print("\n=== Step 8: Building Lambda Functions ===")
    tracker.start_step(8, "Building Lambda Functions")
    if not trigger_build("eidolon-lambda-functions", region, github_branch):
        print("Error: Lambda functions build failed")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Common Lambda parameters
    allowed_origins = f"https://{client_domain}"
    lambda_params = {
        "S3BucketName": s3_bucket,
        "LambdaLayerArn": layer_arn,
        "LambdaExecutionRoleArn": lambda_role_arn,
        "AllowedOrigins": allowed_origins,
    }

    # Step 9: Deploy Cognito Lambda Functions
    print("\n=== Step 9: Deploying Cognito Lambda Functions ===")
    tracker.start_step(9, "Deploying Cognito Lambda Functions")
    if not deploy_stack(cf, "eidolon-lambda-cognito", cf_dir / "eidolon-lambda-cognito.yml", lambda_params):
        print("Error: Failed to deploy Cognito Lambda functions")
        tracker.print_summary()
        sys.exit(1)

    cognito_player_new_arn = get_stack_output(cf, "eidolon-lambda-cognito", "CognitoPlayerNewArn")
    if not cognito_player_new_arn:
        print("Error: Could not retrieve Cognito Lambda ARN from stack outputs")
        tracker.print_summary()
        sys.exit(1)
    print(f"  cognito-player-new: {cognito_player_new_arn}")

    # Update Cognito function code from S3
    cognito_functions = ["cognito-player-new", "cognito-player-delete"]
    for func_name in cognito_functions:
        if not update_lambda_function_code(lambda_client, func_name, s3_bucket, f"{func_name}.zip"):
            print(f"Error: Failed to update {func_name} code")
            tracker.print_summary()
            sys.exit(1)
    print("  Updated Cognito function code from S3")
    tracker.complete_step()

    # Step 10: Deploy Cognito User Pool
    print("\n=== Step 10: Deploying Cognito ===")
    tracker.start_step(10, "Deploying Cognito")
    cognito_params = {
        "PostConfirmationLambdaArn": cognito_player_new_arn,
        "AllowedOrigins": allowed_origins,
    }
    if not deploy_stack(cf, "eidolon-cognito", cf_dir / "eidolon-cognito.yml", cognito_params):
        print("Error: Failed to deploy Cognito")
        tracker.print_summary()
        sys.exit(1)

    user_pool_id = get_stack_output(cf, "eidolon-cognito", "UserPoolId")
    user_pool_arn = get_stack_output(cf, "eidolon-cognito", "UserPoolArn")
    user_pool_client_id = get_stack_output(cf, "eidolon-cognito", "UserPoolClientId")
    if not user_pool_id or not user_pool_arn or not user_pool_client_id:
        print("Error: Could not retrieve Cognito outputs from stack")
        tracker.print_summary()
        sys.exit(1)
    print(f"  User Pool ID: {user_pool_id}")
    print(f"  Client ID: {user_pool_client_id}")
    tracker.complete_step()

    # Step 11: Deploy Character Lambda Functions
    print("\n=== Step 11: Deploying Character Lambda Functions ===")
    tracker.start_step(11, "Deploying Character Lambda Functions")
    if not deploy_stack(cf, "eidolon-lambda-character", cf_dir / "eidolon-lambda-character.yml", lambda_params):
        print("Error: Failed to deploy Character Lambda functions")
        tracker.print_summary()
        sys.exit(1)

    # Update character function code from S3
    character_functions = [
        "api-character-add",
        "api-character-delete",
        "api-character-get",
        "api-character-list",
        "api-archetype-list",
        "api-item-brief",
        "api-item-prototype",
        "api-item-consume",
        "api-item-discard",
        "api-item-consolidate",
        "api-item-split",
        "api-store-list",
        "api-store-purchase",
    ]
    for func_name in character_functions:
        if not update_lambda_function_code(lambda_client, func_name, s3_bucket, f"{func_name}.zip"):
            print(f"Error: Failed to update {func_name} code")
            tracker.print_summary()
            sys.exit(1)
    print(f"  Deployed and updated {len(character_functions)} character functions")
    tracker.complete_step()

    # Step 12: Deploy Story Lambda Functions (conditional)
    if should_deploy_stack("eidolon-lambda-story", deployment_mode):
        print("\n=== Step 12: Deploying Story Lambda Functions ===")
        tracker.start_step(12, "Deploying Story Lambda Functions")
        if not deploy_stack(cf, "eidolon-lambda-story", cf_dir / "eidolon-lambda-story.yml", lambda_params):
            print("Error: Failed to deploy Story Lambda functions")
            tracker.print_summary()
            sys.exit(1)

        # Update story function code from S3
        story_functions = [
            "api-story-start",
            "api-story-abandon",
            "api-story-history",
            "api-segment-decision",
            "api-segment-history",
            "api-segment-status",
            "ops-segment-poller",
            "ops-segment-process",
            "ops-story-advance",
        ]
        for func_name in story_functions:
            if not update_lambda_function_code(lambda_client, func_name, s3_bucket, f"{func_name}.zip"):
                print(f"Error: Failed to update {func_name} code")
                tracker.print_summary()
                sys.exit(1)
        print(f"  Deployed and updated {len(story_functions)} story functions")
        tracker.complete_step()
    else:
        print("\n=== Step 12: Skipping Story Lambda Functions (not in mode) ===")

    # Step 13: Deploy API Gateway
    print("\n=== Step 13: Deploying API Gateway ===")
    tracker.start_step(13, "Deploying API Gateway")
    api_gw_params = {
        "UserPoolArn": user_pool_arn,
        "ApiCertificateArn": api_cert_arn,
        "Route53ZoneId": route53_zone_id,
        "ApiDomainName": api_domain,
        "AllowedOrigins": allowed_origins,
    }
    if not deploy_stack(cf, "eidolon-api-gateway", cf_dir / "eidolon-api-gateway.yml", api_gw_params):
        print("Error: Failed to deploy API Gateway")
        tracker.print_summary()
        sys.exit(1)

    rest_api_id = get_stack_output(cf, "eidolon-api-gateway", "RestApiId")
    if not rest_api_id:
        print("Error: Could not retrieve REST API ID from stack outputs")
        tracker.print_summary()
        sys.exit(1)
    print(f"  REST API ID: {rest_api_id}")

    # Force a fresh API Gateway deployment to capture all methods
    force_api_gateway_deployment(rest_api_id, "prod", region)
    print("  API Gateway deployment updated")
    tracker.complete_step()

    # Step 14: Deploy Portal CloudFront
    print("\n=== Step 14: Deploying Portal CloudFront ===")
    tracker.start_step(14, "Deploying Portal CloudFront")
    portal_params = {
        "ClientBucketName": client_bucket,
        "PortalCertificateArn": portal_cert_arn,
        "Route53ZoneId": route53_zone_id,
        "ClientDomainName": client_domain,
    }
    if not deploy_stack(cf, "eidolon-portal-cloudfront", cf_dir / "eidolon-portal-cloudfront.yml", portal_params):
        print("Error: Failed to deploy Portal CloudFront")
        tracker.print_summary()
        sys.exit(1)

    distribution_id = get_stack_output(cf, "eidolon-portal-cloudfront", "DistributionId")
    if not distribution_id:
        print("Error: Could not retrieve CloudFront distribution ID from stack outputs")
        tracker.print_summary()
        sys.exit(1)
    print(f"  Distribution ID: {distribution_id}")

    if not set_bucket_policy_for_cloudfront(client_bucket, distribution_id, region):
        print("Error: Failed to set bucket policy for CloudFront OAC")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Step 15: Deploy CodeBuild Portal Project
    print("\n=== Step 15: Deploying CodeBuild Portal ===")
    tracker.start_step(15, "Deploying CodeBuild Portal")
    portal_build_params = {
        "CodeBuildRoleArn": codebuild_role_arn,
        "ClientBucketName": client_bucket,
        "DistributionId": distribution_id,
        "CognitoUserPoolId": user_pool_id,
        "CognitoClientId": user_pool_client_id,
        "ApiDomain": api_domain,
        "GitHubOwner": github_owner,
        "GitHubRepo": github_repo,
        "GitHubBranch": github_branch,
        "DeploymentMode": deployment_mode,
    }
    if not deploy_stack(cf, "eidolon-codebuild-portal", cf_dir / "eidolon-codebuild-portal.yml", portal_build_params):
        print("Error: Failed to deploy CodeBuild Portal project")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Step 16: Build Portal
    print("\n=== Step 16: Building Portal ===")
    tracker.start_step(16, "Building Portal")
    if not trigger_build("eidolon-portal-build", region, github_branch):
        print("Error: Portal build failed")
        tracker.print_summary()
        sys.exit(1)
    tracker.complete_step()

    # Step 17: Upload Lua Scripts (conditional)
    if deployment_mode in ["mud", "hybrid"]:
        print("\n=== Step 17: Uploading Lua Scripts ===")
        tracker.start_step(17, "Uploading Lua Scripts")
        if not upload_scripts_to_s3(scripts_bucket, region, str(base_dir)):
            print("Error: Failed to upload Lua scripts")
            tracker.print_summary()
            sys.exit(1)
        tracker.complete_step()
    else:
        print("\n=== Step 17: Skipping Lua Scripts (not in mode) ===")

    # Step 18: Deploy CloudWatch (conditional)
    if should_deploy_stack("eidolon-cloudwatch", deployment_mode):
        print("\n=== Step 18: Deploying CloudWatch ===")
        tracker.start_step(18, "Deploying CloudWatch")

        # Check if log group exists outside CloudFormation management
        resources_to_import = None
        logs_client = boto3.client("logs", region_name=region)
        try:
            response = logs_client.describe_log_groups(logGroupNamePrefix="/eidolon/server", limit=1)
            log_groups = response.get("logGroups", [])
            if any(lg.get("logGroupName") == "/eidolon/server" for lg in log_groups):
                resources_to_import = [
                    {
                        "ResourceType": "AWS::Logs::LogGroup",
                        "LogicalResourceId": "ServerLogGroup",
                        "ResourceIdentifier": {"LogGroupName": "/eidolon/server"},
                    }
                ]
                print("  Log group /eidolon/server exists, will import into stack")
        except ClientError as err:
            print(f"  Warning: Could not check for existing log group: {err}")

        if not deploy_stack(
            cf, "eidolon-cloudwatch", cf_dir / "eidolon-cloudwatch.yml", {}, resources_to_import=resources_to_import
        ):
            print("Error: Failed to deploy CloudWatch")
            tracker.print_summary()
            sys.exit(1)
        tracker.complete_step()
    else:
        print("\n=== Step 18: Skipping CloudWatch (not in mode) ===")

    # Step 19: Update config.yml with stack outputs and deployment params
    print("\n=== Step 19: Updating config.yml ===")
    tracker.start_step(19, "Updating config.yml")
    update_config_from_stacks(cf, config_path, config)
    tracker.complete_step()

    # Step 20: Verify CloudFront operational
    print("\n=== Step 20: Verifying CloudFront ===")
    tracker.start_step(20, "Verifying CloudFront")
    if not wait_for_cloudfront_operational(client_domain):
        print("Warning: CloudFront not yet operational (may still be propagating)")
    else:
        print(f"  Portal accessible at https://{client_domain}")
    tracker.complete_step()

    tracker.print_summary(success=True)


if __name__ == "__main__":
    main()
