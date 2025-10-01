"""Utilities for CDK stack resource management and preservation."""

import boto3
from aws_cdk import aws_route53 as route53
from botocore.exceptions import ClientError
from constructs import Construct


def check_s3_bucket_exists(bucket_name: str, region: str) -> bool:
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


def check_dynamodb_table_exists(table_name: str, region: str) -> bool:
    """Check if a DynamoDB table exists.

    Args:
        table_name: Name of the table
        region: AWS region

    Returns:
        True if table exists, False otherwise
    """
    if not table_name:
        return False

    try:
        dynamodb_client = boto3.client("dynamodb", region_name=region)
        dynamodb_client.describe_table(TableName=table_name)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code")
        if error_code == "ResourceNotFoundException":
            return False
        return False


def validate_dynamodb_table_schema(table_name: str, region: str, expected_config: dict) -> bool:
    """Validate that a DynamoDB table has the expected schema.

    Args:
        table_name: Name of the table
        region: AWS region
        expected_config: Expected table configuration with partition_key and optional sort_key

    Returns:
        True if schema matches, False otherwise
    """
    try:
        dynamodb_client = boto3.client("dynamodb", region_name=region)
        response = dynamodb_client.describe_table(TableName=table_name)
        key_schema = response.get("Table", {}).get("KeySchema", [])

        # Check partition key
        partition_key = expected_config.get("partition_key", {})
        partition_match = any(key["AttributeName"] == partition_key.get("name") and key["KeyType"] == "HASH" for key in key_schema)

        # Check sort key if specified
        sort_key = expected_config.get("sort_key", {})
        if sort_key:
            sort_match = any(key["AttributeName"] == sort_key.get("name") and key["KeyType"] == "RANGE" for key in key_schema)
            return partition_match and sort_match

        return partition_match
    except ClientError:
        return False


def check_cognito_user_pool_exists(pool_name: str, region: str) -> tuple[bool, str]:
    """Check if a Cognito User Pool exists.

    Args:
        pool_name: Name of the user pool
        region: AWS region

    Returns:
        Tuple of (exists, pool_id)
    """
    try:
        cognito_client = boto3.client("cognito-idp", region_name=region)
        response = cognito_client.list_user_pools(MaxResults=60)

        for pool in response.get("UserPools", []):
            if pool.get("Name") == pool_name:
                return True, pool.get("Id", "")

        return False, ""
    except ClientError:
        return False, ""


def check_cloudwatch_log_group_exists(log_group_name: str, region: str) -> bool:
    """Check if a CloudWatch log group exists.

    Args:
        log_group_name: Name of the log group
        region: AWS region

    Returns:
        True if log group exists, False otherwise
    """
    try:
        cloudwatch = boto3.client("logs", region_name=region)
        response = cloudwatch.describe_log_groups(logGroupNamePrefix=log_group_name, limit=1)

        groups = response.get("logGroups", [])
        return any(group.get("logGroupName") == log_group_name for group in groups)
    except ClientError:
        return False


def check_codebuild_project_exists(project_name: str, region: str) -> bool:
    """Check if a CodeBuild project exists.

    Args:
        project_name: Name of the project
        region: AWS region

    Returns:
        True if project exists, False otherwise
    """
    try:
        cb_client = boto3.client("codebuild", region_name=region)
        response = cb_client.batch_get_projects(names=[project_name])
        return len(response.get("projects", [])) > 0
    except ClientError:
        return False


def check_lambda_function_exists(function_name: str, region: str) -> bool:
    """Check if a Lambda function exists.

    Args:
        function_name: Name of the function
        region: AWS region

    Returns:
        True if function exists, False otherwise
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        lambda_client.get_function(FunctionName=function_name)
        return True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code")
        if error_code == "ResourceNotFoundException":
            return False
        return False


def check_lambda_layer_exists(layer_name: str, region: str) -> bool:
    """Check if a Lambda layer exists.

    Args:
        layer_name: Name of the layer
        region: AWS region

    Returns:
        True if layer exists, False otherwise
    """
    try:
        lambda_client = boto3.client("lambda", region_name=region)
        response = lambda_client.list_layer_versions(LayerName=layer_name)
        return len(response.get("LayerVersions", [])) > 0
    except ClientError:
        return False


def get_hosted_zone(scope: Construct, domain: str):
    """Get Route53 hosted zone for the domain.

    Args:
        scope: CDK construct scope
        domain: Domain name

    Returns:
        Hosted zone construct or None if not found
    """
    try:
        route53_client = boto3.client("route53")
        response = route53_client.list_hosted_zones_by_name(DNSName=domain, MaxItems="1")

        zones = response.get("HostedZones", [])
        if zones and zones[0]["Name"].rstrip(".") == domain:
            zone_id = zones[0]["Id"].split("/")[-1]
            return route53.HostedZone.from_hosted_zone_attributes(
                scope,
                "HostedZone",
                hosted_zone_id=zone_id,
                zone_name=domain,
            )
    except ClientError:
        pass

    return None


def get_hosted_zone_by_id(scope: Construct, hosted_zone_id: str, domain: str):
    """Get Route53 hosted zone by ID.

    Args:
        scope: CDK construct scope
        hosted_zone_id: Route53 Hosted Zone ID
        domain: Domain name

    Returns:
        Hosted zone construct
    """
    if not hosted_zone_id:
        # Fall back to lookup by domain if no ID provided
        return get_hosted_zone(scope, domain)

    return route53.HostedZone.from_hosted_zone_attributes(
        scope,
        "HostedZone",
        hosted_zone_id=hosted_zone_id,
        zone_name=domain,
    )


def check_acm_certificate_exists(domain_name: str, region: str) -> tuple[bool, str]:
    """Check if an ACM certificate exists for a domain.

    Args:
        domain_name: Domain name to check
        region: AWS region

    Returns:
        Tuple of (exists, certificate_arn)
    """
    try:
        acm_client = boto3.client("acm", region_name=region)
        response = acm_client.list_certificates(CertificateStatuses=["ISSUED"])

        for cert in response.get("CertificateSummaryList", []):
            if cert.get("DomainName") == domain_name:
                return True, cert.get("CertificateArn", "")

        return False, ""
    except ClientError:
        return False, ""


def check_cloudfront_distribution_exists(comment: str) -> tuple[bool, str, str]:
    """Check if a CloudFront distribution exists by comment.

    Args:
        comment: Comment to search for

    Returns:
        Tuple of (exists, distribution_id, domain_name)
    """
    try:
        cf_client = boto3.client("cloudfront", region_name="us-east-1")
        response = cf_client.list_distributions()

        items = response.get("DistributionList", {}).get("Items", [])
        for dist in items:
            if dist.get("Comment") == comment:
                return True, dist.get("Id", ""), dist.get("DomainName", "")

        return False, "", ""
    except ClientError:
        return False, "", ""
