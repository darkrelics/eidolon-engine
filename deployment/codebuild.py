"""CodeBuild stack deployment functions."""

from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from core.config import Config
from core.state import CDKState
from utilities import run_cdk_deploy, validate_policies


def deploy_codebuild_stack(params) -> dict:
    """Deploy the CodeBuild stack using CDK."""
    app_command = (
        f"python3 app.py --region {params.region} --s3-bucket {params.s3_bucket} "
        f"--github-owner {params.github_owner} --github-repo {params.github_repo} "
        f"--github-branch {params.github_branch}"
    )
    return run_cdk_deploy("codebuild", params.region, app_command)


def validate_s3_bucket(bucket_name: str, region: str) -> bool:
    """Validate that S3 bucket exists and is accessible.
    
    Args:
        bucket_name: Name of the S3 bucket to validate
        region: AWS region
        
    Returns:
        True if bucket exists and is accessible, False otherwise
    """
    try:
        s3 = boto3.client("s3", region_name=region)
        s3.head_bucket(Bucket=bucket_name)
        print(f"  [OK] S3 bucket: {bucket_name}")
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "404":
            print(f"  [MISSING] S3 bucket: {bucket_name}")
        elif error_code == "403":
            print(f"  [FORBIDDEN] S3 bucket: {bucket_name} - insufficient permissions")
        else:
            print(f"  [ERROR] S3 bucket: {bucket_name} - {error_code}")
        return False


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
    policy_validation = validate_policies([
        "eidolon-codebuild-logs-policy",
        "eidolon-codebuild-s3-policy"
    ])
    
    return {
        "bucket": bucket_valid,
        "projects": projects_validation,
        "policies": policy_validation,
        "success": bucket_valid and all(projects_validation.values()) and all(policy_validation.values())
    }


def deploy_codebuild(params, config: Config, state: CDKState,
                    config_path: Path, state_path: Path) -> bool:
    """Deploy and verify CodeBuild stack."""
    print("\n" + "=" * 60)
    print("Phase 2: CodeBuild Stack")
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
        state.save(str(state_path))
    
    return validation.get("success", False)