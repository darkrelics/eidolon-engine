"""Configuration and environment validation for Eidolon deployment."""

import os
import re

import boto3
from botocore.exceptions import ClientError
from deployment.route53 import route53_zone_exists
from deployment.s3 import s3_bucket_exists

VALID_DEPLOYMENT_MODES = ["mud", "incremental", "hybrid"]

REQUIRED_TEMPLATES = [
    "cf/eidolon-roles.yml",
    "cf/eidolon-dynamo.yml",
    "cf/eidolon-certificate.yml",
    "cf/eidolon-codebuild.yml",
    "cf/eidolon-lambda-cognito.yml",
    "cf/eidolon-cognito.yml",
    "cf/eidolon-lambda-character.yml",
    "cf/eidolon-api-gateway.yml",
    "cf/eidolon-portal-cloudfront.yml",
    "cf/eidolon-codebuild-portal.yml",
]

CONDITIONAL_TEMPLATES = {
    "cf/eidolon-lambda-story.yml": ["incremental", "hybrid"],
    "cf/eidolon-s3-scripts.yml": ["mud", "hybrid"],
    "cf/eidolon-cloudwatch.yml": ["mud", "hybrid"],
}


def validate_domain(domain: str) -> bool:
    """Validate domain name format."""
    pattern = r"^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$"
    return bool(re.match(pattern, domain.lower()))


def validate_s3_bucket_name(bucket_name: str) -> bool:
    """Validate S3 bucket name format."""
    pattern = r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"
    return bool(re.match(pattern, bucket_name))


def validate_zone_id(zone_id: str) -> bool:
    """Validate Route53 hosted zone ID format."""
    pattern = r"^Z[A-Z0-9]{1,31}$"
    return bool(re.match(pattern, zone_id))


def validate_email(email: str) -> bool:
    """Validate email address format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_config(config: dict) -> bool:
    """Validate deployment configuration.

    Args:
        config: Configuration dictionary from deploy-config.yml

    Returns:
        bool: True if config is valid
    """
    required_fields = [
        "region",
        "deployment_mode",
        "s3_bucket",
        "client_bucket",
        "github_owner",
        "github_repo",
        "github_branch",
        "domain",
        "route53_zone_id",
        "api_host",
        "client_host",
        "reply_email",
    ]

    missing_fields = []
    for field in required_fields:
        if not config.get(field):
            missing_fields.append(field)

    if missing_fields:
        print("Error: Missing required config fields:")
        for field in missing_fields:
            print(f"  - {field}")
        return False

    deployment_mode = config.get("deployment_mode", "")
    if deployment_mode not in VALID_DEPLOYMENT_MODES:
        print(f"Error: Invalid deployment_mode: {deployment_mode}")
        print(f"  Valid modes: {', '.join(VALID_DEPLOYMENT_MODES)}")
        return False

    if not validate_s3_bucket_name(config.get("s3_bucket", "")):
        print(f"Error: Invalid S3 bucket name: {config.get('s3_bucket')}")
        return False

    if not validate_s3_bucket_name(config.get("client_bucket", "")):
        print(f"Error: Invalid client bucket name: {config.get('client_bucket')}")
        return False

    scripts_bucket = config.get("scripts_bucket", "")
    if scripts_bucket and not validate_s3_bucket_name(scripts_bucket):
        print(f"Error: Invalid scripts bucket name: {scripts_bucket}")
        return False

    domain = config.get("domain", "")
    if not validate_domain(domain):
        print(f"Error: Invalid domain: {domain}")
        return False

    api_host = config.get("api_host", "")
    api_domain = f"{api_host}.{domain}"
    if not validate_domain(api_domain):
        print(f"Error: Invalid API domain: {api_domain}")
        return False

    client_host = config.get("client_host", "")
    client_domain = f"{client_host}.{domain}"
    if not validate_domain(client_domain):
        print(f"Error: Invalid client domain: {client_domain}")
        return False

    if not validate_zone_id(config.get("route53_zone_id", "")):
        print(f"Error: Invalid Route53 zone ID: {config.get('route53_zone_id')}")
        return False

    if not validate_email(config.get("reply_email", "")):
        print(f"Error: Invalid reply email: {config.get('reply_email')}")
        return False

    return True


def validate_environment(base_dir: str, deployment_mode: str) -> str:
    """Validate environment before deployment.

    Args:
        base_dir: Project base directory
        deployment_mode: Current deployment mode

    Returns:
        str: AWS account ID if valid, empty string otherwise
    """
    try:
        sts_client = boto3.client("sts")
        identity = sts_client.get_caller_identity()
        account_id = identity.get("Account")
        if not account_id:
            print("Error: Failed to get AWS account ID")
            return ""
        print(f"AWS Account: {account_id}")
    except ClientError as err:
        print(f"Error: AWS credentials not configured: {err}")
        return ""

    missing_templates = []
    for template in REQUIRED_TEMPLATES:
        template_path = os.path.join(base_dir, template)
        if not os.path.exists(template_path):
            missing_templates.append(template)

    for template, modes in CONDITIONAL_TEMPLATES.items():
        if deployment_mode in modes:
            template_path = os.path.join(base_dir, template)
            if not os.path.exists(template_path):
                missing_templates.append(template)

    if missing_templates:
        print("Error: Missing required template files:")
        for template in missing_templates:
            print(f"  - {template}")
        return ""

    return account_id


def validate_resources(config: dict) -> bool:
    """Validate AWS resources exist before deployment.

    Args:
        config: Configuration dictionary

    Returns:
        bool: True if all resources exist
    """
    region = config.get("region", "")
    s3_bucket = config.get("s3_bucket", "")
    route53_zone_id = config.get("route53_zone_id", "")

    print("Validating AWS resources...")

    if not s3_bucket_exists(s3_bucket, region):
        print(f"Error: Lambda S3 bucket does not exist: {s3_bucket}")
        return False
    print(f"  Lambda S3 bucket: {s3_bucket}")

    if not route53_zone_exists(route53_zone_id):
        print(f"Error: Route53 hosted zone does not exist: {route53_zone_id}")
        return False
    print(f"  Route53 zone: {route53_zone_id}")

    return True
