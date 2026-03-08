"""CodeBuild stack deployment functions."""

import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from core.config import Config
from core.state import CDKState
from deploy_mode import get_stack_phase_number
from stacks.stack_utilities import check_s3_bucket_exists
from utilities import run_cdk_deploy, validate_policies, validate_s3_bucket


def deploy_codebuild_stack(params) -> dict:
    """Deploy the CodeBuild stack using CDK."""
    # Check if S3 bucket already exists

    bucket_exists = check_s3_bucket_exists(params.s3_bucket, params.region)

    # Pass parameters through context
    context_args = [
        "-c",
        f"region={params.region}",
        "-c",
        f"s3_bucket={params.s3_bucket}",
        "-c",
        f"github_owner={params.github_owner}",
        "-c",
        f"github_repo={params.github_repo}",
        "-c",
        f"github_branch={params.github_branch}",
        "-c",
        f"bucket_exists={'true' if bucket_exists else 'false'}",
    ]

    app_command = "python3 app_codebuild.py"
    return run_cdk_deploy("codebuild", params.region, app_command, context_args)


def validate_codebuild_projects(project_names: list[str], region: str) -> dict:
    """Validate that CodeBuild projects were created.

    Args:
        project_names: List of project names to check
        region: AWS region

    Returns:
        Dict with project names as keys and bool status as values
    """
    codebuild = boto3.client("codebuild", region_name=region)

    results = {}
    try:
        response = codebuild.batch_get_projects(names=project_names)
        existing_projects = {p["name"] for p in response.get("projects", [])}

        for project_name in project_names:
            if project_name in existing_projects:
                print(f"  [OK] CodeBuild project: {project_name}")
                results[project_name] = True
            else:
                print(f"  [MISSING] CodeBuild project: {project_name}")
                results[project_name] = False

    except ClientError as err:
        print(f"  [ERROR] Could not validate CodeBuild projects: {err}")
        for project_name in project_names:
            results[project_name] = False

    return results


def verify_codebuild_deployment(params) -> dict:
    """Verify the CodeBuild deployment completed successfully."""
    print("\nVerifying CodeBuild deployment...")

    # Validate S3 bucket
    bucket_valid = validate_s3_bucket(params.s3_bucket, params.region)

    # Validate CodeBuild projects
    projects = ["eidolon-lambda-layer", "eidolon-lambda-functions"]
    projects_validation = validate_codebuild_projects(projects, params.region)

    # Validate IAM policies
    policy_validation = validate_policies(["eidolon-codebuild-logs-policy", "eidolon-codebuild-s3-policy"])

    return {
        "bucket": bucket_valid,
        "projects": projects_validation,
        "policies": policy_validation,
        "success": bucket_valid and all(projects_validation.values()) and all(policy_validation.values()),
    }


def start_build(project_name: str, region: str) -> str:
    """Start a CodeBuild project build.

    Args:
        project_name: Name of the CodeBuild project
        region: AWS region

    Returns:
        Build ID if successful, empty string if failed
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)
        print(f"  Starting build: {project_name}")
        response = codebuild.start_build(projectName=project_name)
        build_id = response["build"]["id"]
        print(f"  Build started: {build_id}")
        return build_id
    except ClientError as err:
        print(f"  [ERROR] Failed to start build for {project_name}: {err}")
        return ""


def monitor_build(build_id: str, region: str, timeout_minutes: int = 30) -> bool:
    """Monitor a build until completion.

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
            if not response["builds"]:
                print(f"  [ERROR] Build not found: {build_id}")
                return False

            build = response["builds"][0]
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
                print_build_logs(build_id, region)
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


def print_build_logs(build_id: str, region: str, tail_lines: int = 50) -> None:
    """Print the last N lines of build logs.

    Args:
        build_id: Build ID to get logs for
        region: AWS region
        tail_lines: Number of lines to print
    """
    try:
        codebuild = boto3.client("codebuild", region_name=region)
        response = codebuild.batch_get_builds(ids=[build_id])

        if not response["builds"]:
            return

        build = response["builds"][0]
        log_info = build.get("logs", {})

        if not log_info.get("streamName"):
            print("  No log stream available")
            return

        # Get logs from CloudWatch
        logs = boto3.client("logs", region_name=region)
        group_name = log_info.get("groupName", "/aws/codebuild/eidolon")
        stream_name = log_info["streamName"]

        print(f"\n  Last {tail_lines} lines of build logs:")
        print("  " + "-" * 56)

        response = logs.get_log_events(logGroupName=group_name, logStreamName=stream_name, limit=tail_lines, startFromHead=False)

        events = response.get("events", [])
        for event in events[-tail_lines:]:
            print(f"  {event['message'].rstrip()}")

        print("  " + "-" * 56)

    except ClientError:
        print("  Could not retrieve build logs")


def execute_lambda_builds(region: str) -> bool:
    """Execute Lambda layer and functions builds sequentially.

    Args:
        region: AWS region

    Returns:
        True if both builds succeeded, False otherwise
    """
    # Build Lambda layer first
    layer_build_id = start_build("eidolon-lambda-layer", region)
    if not layer_build_id:
        return False

    if not monitor_build(layer_build_id, region):
        print("Lambda layer build failed")
        return False

    # Build Lambda functions after layer is ready
    functions_build_id = start_build("eidolon-lambda-functions", region)
    if not functions_build_id:
        return False

    if not monitor_build(functions_build_id, region):
        print("Lambda functions build failed")
        return False

    print("\nAll builds completed successfully")
    return True


def validate_build_artifacts(bucket_name: str, region: str) -> bool:
    """Validate that build artifacts were created in S3.

    Args:
        bucket_name: S3 bucket name
        region: AWS region

    Returns:
        True if all expected artifacts exist, False otherwise
    """
    print("\nValidating build artifacts...")
    s3 = boto3.client("s3", region_name=region)

    # Expected artifacts
    expected_artifacts = [
        "lambda-layer/lambda-layer.zip",
        # Player Lambda functions
        "cognito-player-new.zip",
        "cognito-player-delete.zip",
        # Character Lambda functions
        "api-archetype-list.zip",
        "api-character-add.zip",
        "api-character-delete.zip",
        "api-character-get.zip",
        "api-character-list.zip",
        "api-item-brief.zip",
        "api-item-prototype.zip",
        "api-item-consume.zip",
        "api-item-discard.zip",
        "api-item-consolidate.zip",
        "api-item-split.zip",
        # Store Lambda functions
        "api-store-list.zip",
        "api-store-purchase.zip",
        # Story Lambda functions
        "api-segment-decision.zip",
        "api-segment-history.zip",
        "api-segment-status.zip",
        "api-story-abandon.zip",
        "api-story-history.zip",
        "api-story-start.zip",
        "ops-segment-poller.zip",
        "ops-segment-process.zip",
        "ops-story-advance.zip",
    ]

    all_valid = True
    for artifact in expected_artifacts:
        try:
            response = s3.head_object(Bucket=bucket_name, Key=artifact)
            size = response.get("ContentLength", 0)
            if size > 0:
                print(f"  [OK] {artifact} ({size:,} bytes)")
            else:
                print(f"  [WARNING] {artifact} (empty file)")
                all_valid = False
        except ClientError:
            print(f"  [MISSING] {artifact}")
            all_valid = False

    return all_valid


def deploy_codebuild(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
    """Deploy and verify CodeBuild stack."""
    phase = get_stack_phase_number("codebuild", params.deployment_mode)
    print("\n" + "=" * 60)
    print(f"Phase {phase}: CodeBuild Stack")
    print("=" * 60)

    # Deploy stack
    result = deploy_codebuild_stack(params)

    if not result.get("success", False):
        print("\nCodeBuild deployment failed!")
        return False

    # Verify deployment
    validation = verify_codebuild_deployment(params)

    if not validation.get("success", False):
        print("\nWarning: CodeBuild deployment completed with issues")
        if not validation.get("bucket", False):
            print("  - S3 bucket was not created or is not accessible")
        if not all(validation.get("projects", {}).values()):
            print("  - Some CodeBuild projects were not created")
        if not all(validation.get("policies", {}).values()):
            print("  - Some IAM policies were not created")

    # Update configuration with S3 bucket
    if validation.get("bucket", False):
        config.s3_artifacts_bucket = params.s3_bucket
        config.save(str(config_path))

    # Update state
    if validation.get("success", False):
        state.mark_stack_deployed("codebuild", result.get("outputs", {}))

        # Store infrastructure resources needed by other stacks
        if "infrastructure" not in state.__dict__:
            state.infrastructure = {}
        # Store S3 bucket name for Lambda stack
        s3_bucket_name = result.get("outputs", {}).get("S3BucketName", "")
        if s3_bucket_name:
            state.infrastructure["artifacts_bucket"] = s3_bucket_name

        state.save(str(state_path))

    # Execute builds if stack deployment was successful
    if validation.get("success", False):
        print("\nExecuting Lambda builds...")

        builds_success = execute_lambda_builds(params.region)

        if builds_success:
            artifacts_valid = validate_build_artifacts(params.s3_bucket, params.region)
            if not artifacts_valid:
                print("\nWarning: Some build artifacts are missing or invalid")
                return False
        else:
            print("\nWarning: Build execution failed")
            return False

    return validation.get("success", False)
