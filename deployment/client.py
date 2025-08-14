"""Client stack deployment functions."""

import json
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
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


def check_cloudfront_exists(distribution_id: str) -> bool:
    """Check if a CloudFront distribution exists.

    Args:
        distribution_id: CloudFront distribution ID

    Returns:
        True if distribution exists, False otherwise
    """
    if not distribution_id:
        return False

    try:
        cf_client = boto3.client("cloudfront", region_name="us-east-1")
        cf_client.get_distribution(Id=distribution_id)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ["NoSuchDistribution", "DistributionNotFound"]:
            return False
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
    if state.stacks.get("api", {}).get("outputs", {}).get("ApiUrl"):
        api_url = state.stacks["api"]["outputs"]["ApiUrl"]
    else:
        # Fallback to default if API stack hasn't been deployed yet
        api_url = f"https://{params.api_host}.{params.domain}"

    # Build context arguments
    context_args = [
        "-c", f"region={params.region}",
        "-c", f"hosted_zone_id={params.hosted_zone_id}",
        "-c", f"domain={params.domain}",
        "-c", f"api_host={params.api_host}",
        "-c", f"client_host={params.client_host}",
        "-c", f"client_bucket={params.client_bucket}",
        "-c", f"deployment_mode={params.deployment_mode}",
        "-c", f"github_owner={params.github_owner}",
        "-c", f"github_repo={params.github_repo}",
        "-c", f"github_branch={params.github_branch}",
    ]

    # Add API URL
    context_args.extend(["-c", f"api_url={api_url}"])

    # Add Cognito settings from state
    if state.stacks.get("player", {}).get("outputs", {}).get("UserPoolId"):
        context_args.extend(["-c", f"cognito_user_pool_id={state.stacks['player']['outputs']['UserPoolId']}"])
        context_args.extend(["-c", f"cognito_client_id={state.stacks['player']['outputs']['UserPoolClientId']}"])
        context_args.extend(["-c", f"cognito_user_pool_arn={state.stacks['player']['outputs']['UserPoolArn']}"])

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
        
        build_id = response["build"]["id"]
        build_number = build_id.split(":")[-1]
        
        print(f"  [OK] Build started: #{build_number}")
        print(f"  Build ID: {build_id}")
        print(f"  You can monitor the build in the AWS Console or wait for completion...")
        
        # Optional: Wait for build to complete
        print("\nWaiting for build to complete (this may take a few minutes)...")
        
        waiter = codebuild.get_waiter("build_complete")
        try:
            waiter.wait(
                ids=[build_id],
                WaiterConfig={
                    "Delay": 10,
                    "MaxAttempts": 60  # Wait up to 10 minutes
                }
            )
            
            # Get final build status
            build_response = codebuild.batch_get_builds(ids=[build_id])
            build_status = build_response["builds"][0]["buildStatus"]
            
            if build_status == "SUCCEEDED":
                print(f"  [OK] Build completed successfully!")
                return True
            else:
                print(f"  [ERROR] Build failed with status: {build_status}")
                # Get last few log lines for context
                logs = build_response["builds"][0].get("logs", {})
                if logs.get("streamName"):
                    print(f"  Check logs at: {logs.get('deepLink', 'AWS Console')}")
                return False
                
        except Exception as e:
            print(f"  [WARNING] Timeout waiting for build. Check AWS Console for status.")
            print(f"  Build is still running in background: {build_id}")
            return True  # Return True since build started successfully
            
    except ClientError as err:
        print(f"  [ERROR] Failed to start CodeBuild project: {err}")
        return False


def update_bucket_policy_for_cloudfront(bucket_name: str, distribution_id: str, region: str) -> bool:
    """Update S3 bucket policy to allow CloudFront access.
    
    Args:
        bucket_name: Name of the S3 bucket
        distribution_id: CloudFront distribution ID
        region: AWS region
        
    Returns:
        True if policy was updated successfully
    """
    try:
        s3_client = boto3.client("s3", region_name=region)
        
        # Create bucket policy that allows CloudFront to read objects
        bucket_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowCloudFrontAccess",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "cloudfront.amazonaws.com"
                    },
                    "Action": "s3:GetObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*",
                    "Condition": {
                        "StringEquals": {
                            "AWS:SourceArn": f"arn:aws:cloudfront::{distribution_id}:distribution/{distribution_id}"
                        }
                    }
                }
            ]
        }
        
        # Apply the bucket policy
        s3_client.put_bucket_policy(
            Bucket=bucket_name,
            Policy=json.dumps(bucket_policy)
        )
        
        print(f"  [OK] Updated bucket policy for CloudFront access")
        return True
        
    except ClientError as err:
        print(f"  [ERROR] Failed to update bucket policy: {err}")
        return False


def verify_client_deployment(params, state: CDKState, outputs: dict) -> dict:
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


def deploy_client(params, config: Config, state: CDKState, config_path: Path, state_path: Path) -> bool:
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
    validation = verify_client_deployment(params, state, outputs)
    
    # Execute CodeBuild to deploy the portal/incremental app
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

    return validation.get("success", False)