"""Client stack deployment functions."""

import json
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from utilities import run_cdk_deploy


def check_bucket_exists(bucket_name: str, region: str) -> bool:
    """Check if an S3 bucket exists.

    Args:
        bucket_name: Name of the bucket to check
        region: AWS region

    Returns:
        True if bucket exists, False otherwise
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        s3_client.head_bucket(Bucket=bucket_name)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code")
        if error_code in ["404", "NoSuchBucket"]:
            return False
        elif error_code == "403":
            # Bucket exists but we don't have access
            return True
        else:
            return False


def validate_codebuild_project(project_name: str, region: str) -> bool:
    """Validate that CodeBuild project exists.

    Args:
        project_name: Name of the CodeBuild project
        region: AWS region

    Returns:
        True if project exists, False otherwise
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)
        response = codebuild.batch_get_projects(names=[project_name])

        if response.get("projects"):
            print(f"  [OK] CodeBuild project: {project_name}")
            return True

        print(f"  [MISSING] CodeBuild project: {project_name}")
        return False

    except ClientError as err:
        print(f"  [ERROR] Could not validate CodeBuild project: {err}")
        return False


def deploy_client_stack(params, state: CDKState) -> dict:
    """Deploy the Client stack using CDK."""
    # Get API URL from API stack outputs
    api_url = ""
    api_outputs = state.stacks.get("api", {}).get("outputs", {})
    if api_outputs.get("ApiUrl"):
        api_url = api_outputs.get("ApiUrl", "")
    else:
        # Fallback to default if API stack hasn't been deployed yet
        api_url = f"https://{params.api_host}.{params.domain}"

    # Check if client bucket already exists
    bucket_exists = check_bucket_exists(params.client_bucket, params.region)

    # Build context arguments
    context_args = [
        "-c",
        f"region={params.region}",
        "-c",
        f"hosted_zone_id={params.hosted_zone_id}",
        "-c",
        f"domain={params.domain}",
        "-c",
        f"api_host={params.api_host}",
        "-c",
        f"client_host={params.client_host}",
        "-c",
        f"client_bucket={params.client_bucket}",
        "-c",
        f"deployment_mode={params.deployment_mode}",
        "-c",
        f"github_owner={params.github_owner}",
        "-c",
        f"github_repo={params.github_repo}",
        "-c",
        f"github_branch={params.github_branch}",
        "-c",
        f"bucket_exists={'true' if bucket_exists else 'false'}",
    ]

    # Add API URL
    context_args.extend(["-c", f"api_url={api_url}"])

    # Add Cognito settings from state
    player_outputs = state.stacks.get("player", {}).get("outputs", {})
    if player_outputs.get("UserPoolId"):
        context_args.extend(["-c", f"cognito_user_pool_id={player_outputs.get('UserPoolId', '')}"])
        context_args.extend(["-c", f"cognito_client_id={player_outputs.get('UserPoolClientId', '')}"])
        context_args.extend(["-c", f"cognito_user_pool_arn={player_outputs.get('UserPoolArn', '')}"])

    app_command = "python3 app_client.py"
    return run_cdk_deploy("client", params.region, app_command, context_args)


def execute_codebuild_project(project_name: str, region: str) -> bool:
    """Execute CodeBuild project to deploy the portal.

    Args:
        project_name: Name of the CodeBuild project
        region: AWS region

    Returns:
        True if build started successfully
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)

        print(f"\nStarting CodeBuild project: {project_name}")
        response = codebuild.start_build(projectName=project_name)

        build_id = response.get("build", {}).get("id", "")
        build_number = build_id.split(":")[-1]

        print(f"  [OK] Build started: #{build_number}")
        print(f"  Build ID: {build_id}")
        print("  You can monitor the build in the AWS Console or wait for completion...")

        # Wait for build to complete using polling
        print("\nWaiting for build to complete (this may take a few minutes)...")

        start_time = time.time()
        timeout_seconds = 600  # 10 minutes timeout
        last_phase = ""

        while True:
            try:
                response = codebuild.batch_get_builds(ids=[build_id])
                builds = response.get("builds", [])
                if not builds:
                    print(f"  [ERROR] Build not found: {build_id}")
                    return False

                build = builds[0]
                status = build.get("buildStatus", "UNKNOWN")
                phase = build.get("currentPhase", "UNKNOWN")

                # Print phase changes
                if phase != last_phase and phase != "UNKNOWN":
                    print(f"    Phase: {phase}")
                    last_phase = phase

                # Check terminal states
                if status == "SUCCEEDED":
                    print("  [OK] Build completed successfully!")
                    return True
                elif status in ["FAILED", "FAULT", "TIMED_OUT", "STOPPED"]:
                    print(f"  [ERROR] Build failed with status: {status}")
                    # Get last few log lines for context
                    logs = build.get("logs", {})
                    if logs.get("deepLink"):
                        print(f"  Check logs at: {logs.get('deepLink')}")
                    return False

                # Check timeout
                if time.time() - start_time > timeout_seconds:
                    print(f"  [WARNING] Build timed out after {timeout_seconds/60:.0f} minutes")
                    print(f"  Build is still running in background: {build_id}")
                    return True  # Build started successfully even if we timed out waiting

                # Wait before next check
                time.sleep(10)

            except ClientError as err:
                print(f"  [ERROR] Failed to get build status: {err}")
                return False

    except ClientError as err:
        print(f"  [ERROR] Failed to start CodeBuild project: {err}")
        return False


def get_cloudfront_oai_id(distribution_id: str, bucket_name: str) -> str:
    """Get the OAI ID from a CloudFront distribution for the given S3 bucket.

    Returns:
        OAI ID string, or empty string if not found or on error.
    """
    try:
        cloudfront_client = boto3.client("cloudfront", region_name="us-east-1")  # CloudFront is global
        dist_response = cloudfront_client.get_distribution(Id=distribution_id)
        origins = dist_response.get("Distribution", {}).get("DistributionConfig", {}).get("Origins", {}).get("Items", [])

        for origin in origins:
            if bucket_name in origin.get("DomainName", ""):
                s3_origin_config = origin.get("S3OriginConfig", {})
                oai = s3_origin_config.get("OriginAccessIdentity", "")
                if oai:
                    oai_id = oai.split("/")[-1] if "/" in oai else oai
                    return oai_id
        return ""
    except ClientError as err:
        print(f"  [ERROR] Failed to get distribution details: {err}")
        return ""


def load_existing_bucket_policy(s3_client, bucket_name: str) -> dict:
    """Load existing S3 bucket policy. Returns empty policy structure if none exists.

    Raises ClientError for unexpected S3 errors.
    """
    try:
        existing_policy = s3_client.get_bucket_policy(Bucket=bucket_name)
        if existing_policy.get("Policy"):
            return json.loads(existing_policy.get("Policy", "{}"))
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code")
        if error_code not in {"NoSuchBucketPolicy", "NoSuchBucket"}:
            raise
    return {"Version": "2012-10-17", "Statement": []}


def update_bucket_policy_for_cloudfront(bucket_name: str, distribution_id: str, region: str) -> bool:
    """Update S3 bucket policy to allow CloudFront access.

    Args:
        bucket_name: Name of the S3 bucket
        distribution_id: CloudFront distribution ID
        region: AWS region

    Returns:
        True if policy was updated successfully
    """
    oai_id = get_cloudfront_oai_id(distribution_id, bucket_name)
    if not oai_id:
        print(f"  [WARNING] No OAI found for distribution {distribution_id}")
        print("  CloudFront may be using OAC or public access")
        return False

    # Desired statements for CloudFront access
    desired_statements = [
        {
            "Sid": "AllowCloudFrontOAIAccess",
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity {oai_id}"},
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket_name}/*",
        },
        {
            "Sid": "AllowCloudFrontOAIListBucket",
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::cloudfront:user/CloudFront Origin Access Identity {oai_id}"},
            "Action": "s3:ListBucket",
            "Resource": f"arn:aws:s3:::{bucket_name}",
        },
    ]

    try:
        s3_client = boto3.client("s3", region_name=region)

        bucket_policy = load_existing_bucket_policy(s3_client, bucket_name)

        # Normalise statements to a list before mutation
        statements = bucket_policy.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]
        elif not isinstance(statements, list):
            statements = []

        bucket_policy["Version"] = bucket_policy.get("Version", "2012-10-17")

        replacement_sids = {stmt.get("Sid") for stmt in desired_statements}

        # Drop old versions of the CloudFront statements so we can replace them cleanly
        statements = [stmt for stmt in statements if stmt.get("Sid") not in replacement_sids]

        # Append / merge the desired statements
        statements.extend(desired_statements)

        bucket_policy["Statement"] = statements

        # Apply the merged bucket policy
        s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(bucket_policy))

        print("  [OK] Updated bucket policy for CloudFront OAI access")
        print(f"  OAI ID: {oai_id}")
        return True

    except ClientError as err:
        print(f"  [ERROR] Failed to update bucket policy: {err}")
        return False


def verify_client_deployment(params, outputs: dict) -> dict:
    """Verify the Client deployment completed successfully."""
    print("\nVerifying Client deployment...")

    # Get portal bucket name from deployment outputs first, then from params
    portal_bucket_name = outputs.get("PortalBucketName", "")
    if not portal_bucket_name:
        # Use the bucket name that was actually provided during deployment
        portal_bucket_name = params.client_bucket

    # Validate portal bucket
    portal_bucket_valid = False
    if portal_bucket_name:
        portal_bucket_valid = check_bucket_exists(portal_bucket_name, params.region)
        if portal_bucket_valid:
            print(f"  [OK] Portal bucket: {portal_bucket_name}")
        else:
            print(f"  [MISSING] Portal bucket: {portal_bucket_name}")
    else:
        print("  [ERROR] No portal bucket name available for verification")

    # Validate CodeBuild project
    codebuild_valid = validate_codebuild_project("eidolon-portal-build", params.region)

    return {
        "portal_bucket": portal_bucket_valid,
        "portal_bucket_name": portal_bucket_name,
        "codebuild_project": codebuild_valid,
        "success": portal_bucket_valid and codebuild_valid,
    }


def deploy_client(params, config, state: CDKState, config_path, state_path: Path):
    """Deploy and verify Client stack."""
    phase = get_stack_phase_number("client", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: Client Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_client_stack(params, state)

    if not result.get("success", False):
        print("\nClient deployment failed!")
        return False

    # Update bucket policy for CloudFront access
    outputs = result.get("outputs", {})
    bucket_name = outputs.get("PortalBucketName", "") or params.client_bucket
    distribution_id = outputs.get("CloudFrontDistributionId", "")

    if bucket_name and distribution_id:
        print("\nUpdating bucket policy for CloudFront access...")
        update_bucket_policy_for_cloudfront(bucket_name, distribution_id, params.region)

    # Verify deployment
    validation = verify_client_deployment(params, outputs)

    # Execute CodeBuild to deploy the portal/incremental app
    build_success = False
    if validation.get("codebuild_project", False):
        print("\n" + "=" * 60)
        print("Portal Build Phase")
        print("=" * 60)
        build_success = execute_codebuild_project("eidolon-portal-build", params.region)
        if build_success:
            print("\n  Portal deployment completed successfully!")
            portal_url = outputs.get("PortalUrl", f"https://{params.client_host}.{params.domain}")
            print(f"  Portal URL: {portal_url}")
        else:
            print("\n  Warning: Portal build encountered issues")
    else:
        print("\n  Skipping portal build - CodeBuild project not available")
        build_success = True  # Not a failure if we're skipping

    if not validation.get("success", False):
        print("\nWarning: Client deployment completed with issues")
        if not validation.get("portal_bucket", False):
            print("  - Portal bucket was not created")
        if not validation.get("codebuild_project", False):
            print("  - CodeBuild project was not created")

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("client", result.get("outputs", {}))
        state.save(str(state_path))

    # Return a tuple: (infrastructure_success, build_success)
    # This allows the caller to distinguish between infrastructure and build issues
    return (validation.get("success", False), build_success)


def start_portal_build(region: str) -> str:
    """Start the portal CodeBuild project build.

    Args:
        region: AWS region

    Returns:
        Build ID if successful, empty string if failed
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)
        project_name = "eidolon-portal-build"
        print(f"\n  Starting portal build: {project_name}")
        response = codebuild.start_build(projectName=project_name)
        build_id = response.get("build", {}).get("id", "")
        print(f"  Build started: {build_id}")
        return build_id
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        print(f"  [ERROR] Failed to start portal build: {error_code}")
        if error_code == "ResourceNotFoundException":
            print("  Portal build project not found. Ensure Client stack deployed successfully.")
        return ""


def monitor_portal_build(build_id: str, region: str, timeout_minutes: int = 30) -> bool:
    """Monitor the portal build until completion.

    Args:
        build_id: Build ID to monitor
        region: AWS region
        timeout_minutes: Maximum time to wait

    Returns:
        True if build succeeded, False otherwise
    """
    codebuild = boto3.client("codebuild", region_name=region)
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    last_phase = ""

    print(f"  Monitoring build (timeout: {timeout_minutes} minutes)")

    while True:
        try:
            response = codebuild.batch_get_builds(ids=[build_id])
            builds = response.get("builds", [])
            if not builds:
                print(f"  [ERROR] Build not found: {build_id}")
                return False

            build = builds[0]
            status = build.get("buildStatus", "UNKNOWN")
            phase = build.get("currentPhase", "UNKNOWN")

            # Print phase changes
            if phase != last_phase:
                print(f"    Phase: {phase}")
                last_phase = phase

            # Check terminal states
            if status == "SUCCEEDED":
                print("  Build completed successfully")
                return True
            elif status in ["FAILED", "FAULT", "TIMED_OUT", "STOPPED"]:
                print(f"  Build failed with status: {status}")
                print_portal_build_logs(build_id, region)
                return False

            # Check timeout
            if time.time() - start_time > timeout_seconds:
                print(f"  Build timed out after {timeout_minutes} minutes")
                return False

            # Wait before next check
            time.sleep(10)

        except ClientError as err:
            print(f"  [ERROR] Failed to get build status: {err}")
            return False


def print_portal_build_logs(build_id: str, region: str, tail_lines: int = 50) -> None:
    """Print the last N lines of portal build logs.

    Args:
        build_id: Build ID to get logs for
        region: AWS region
        tail_lines: Number of lines to print
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)
        response = codebuild.batch_get_builds(ids=[build_id])

        builds = response.get("builds", [])
        if not builds:
            return

        build = builds[0]
        log_info = build.get("logs", {})

        if not log_info.get("streamName"):
            print("  No log stream available")
            return

        # Get logs from CloudWatch
        logs = boto3.client("logs", region_name=region)
        group_name = log_info.get("groupName", "/aws/codebuild/eidolon-portal-build")
        stream_name = log_info.get("streamName", "")

        print(f"\n  Last {tail_lines} lines of build logs:")
        print("  " + "-" * 56)

        response = logs.get_log_events(logGroupName=group_name, logStreamName=stream_name, limit=tail_lines, startFromHead=False)

        events = response.get("events", [])
        for event in events[-tail_lines:]:
            print(f"  {event.get('message', '').rstrip()}")

        print("  " + "-" * 56)

    except ClientError:
        print("  Could not retrieve build logs")


def execute_portal_build(params) -> bool:
    """Execute the portal build and deployment.

    Args:
        params: Deployment parameters with region and mode

    Returns:
        True if build succeeded, False otherwise
    """
    print(f"\nExecuting portal build for {params.deployment_mode} mode")

    # The buildspec was configured during stack creation based on deployment mode
    # MUD mode: buildspec/portal.yml - Traditional MUD interface
    # Incremental/Hybrid: buildspec/incremental.yml - Story-driven interface
    if params.deployment_mode == "mud":
        print("  Buildspec: /buildspec/portal.yml (Traditional MUD interface)")
        print("  Features: Character management, room exploration, combat")
    else:
        print("  Buildspec: /buildspec/incremental.yml (Story-driven interface)")
        print("  Features: Narrative progression, dynamic segments, story mode")

    # Start the build
    build_id = start_portal_build(params.region)
    if not build_id:
        return False

    # Monitor until completion
    if not monitor_portal_build(build_id, params.region):
        print("\nPortal build failed")
        print("Check the build logs in AWS CodeBuild console for details")
        return False

    print("\nPortal build completed successfully!")
    print("  [OK] Frontend application built and uploaded to S3")
    print("  [OK] CloudFront distribution updated")
    print("  [OK] Cache invalidation triggered automatically")
    print("\nDeployment Complete!")
    print(f"  Portal URL: https://{params.client_host}.{params.domain}")
    print("  Note: DNS propagation may take 5-10 minutes")

    return True
