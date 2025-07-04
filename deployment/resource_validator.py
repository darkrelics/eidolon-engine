"""Resource validation for AWS infrastructure drift detection.

This module provides validators for individual AWS resources to detect
configuration drift and validate resource states against desired configurations.
"""

import boto3
from botocore.exceptions import ClientError


class ValidationResult:
    """Result of a resource validation check."""

    def __init__(self, resource_id: str, resource_type: str):
        """Initialize validation result.

        Args:
            resource_id: Identifier for the resource
            resource_type: Type of AWS resource
        """
        self.resource_id = resource_id
        self.resource_type = resource_type
        self.exists = False
        self.valid = False
        self.drift_detected = False
        self.messages: list = []
        self.actual_config: dict = {}
        self.expected_config: dict = {}

    def add_message(self, message: str) -> None:
        """Add a validation message."""
        self.messages.append(message)

    def to_dict(self) -> dict:
        """Convert to dictionary representation."""
        return {
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "exists": self.exists,
            "valid": self.valid,
            "drift_detected": self.drift_detected,
            "messages": self.messages,
            "actual_config": self.actual_config,
            "expected_config": self.expected_config,
        }


class ResourceValidator:
    """Base class for AWS resource validators."""

    def __init__(self, session: boto3.Session):
        """Initialize validator with AWS session.

        Args:
            session: Boto3 session for AWS access
        """
        self.session = session

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a specific resource.

        Args:
            resource_id: AWS resource identifier
            expected_config: Expected configuration for the resource

        Returns:
            ValidationResult with validation details
        """
        raise NotImplementedError("Subclasses must implement validate()")

    def list_resources(self, filter_params = None) -> list:
        """List all resources of this type.

        Args:
            filter_params: Optional filters for listing

        Returns:
            List of resource identifiers
        """
        raise NotImplementedError("Subclasses must implement list_resources()")


class DynamoDBTableValidator(ResourceValidator):
    """Validator for DynamoDB tables."""

    def __init__(self, session: boto3.Session):
        """Initialize DynamoDB validator."""
        super().__init__(session)
        self.client = session.client("dynamodb")

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a DynamoDB table configuration."""
        result = ValidationResult(resource_id, "dynamodb_table")
        result.expected_config = expected_config

        try:
            # Get table description
            response = self.client.describe_table(TableName=resource_id)
            table = response.get("Table", {})
            result.exists = True

            # Extract actual configuration
            result.actual_config = {
                "table_name": table.get("TableName"),
                "billing_mode": table.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED"),
                "key_schema": table.get("KeySchema", []),
                "attribute_definitions": table.get("AttributeDefinitions", []),
                "point_in_time_recovery": self._get_point_in_time_recovery(resource_id),
                "table_status": table.get("TableStatus"),
            }

            # Check table status
            if table.get("TableStatus") != "ACTIVE":
                result.add_message(f"Table is not active (status: {table.get('TableStatus')})")
                result.valid = False
                return result

            # Validate billing mode
            if expected_config.get("billing_mode"):
                actual_billing = result.actual_config["billing_mode"]
                expected_billing = expected_config["billing_mode"]
                if actual_billing != expected_billing:
                    result.drift_detected = True
                    result.add_message(f"Billing mode drift: expected {expected_billing}, got {actual_billing}")

            # Validate key schema
            if expected_config.get("key_schema"):
                if not self._compare_key_schemas(result.actual_config["key_schema"], expected_config["key_schema"]):
                    result.drift_detected = True
                    result.add_message("Key schema mismatch")

            # Validate point-in-time recovery
            if "point_in_time_recovery" in expected_config:
                actual_pitr = result.actual_config["point_in_time_recovery"]
                expected_pitr = expected_config["point_in_time_recovery"]
                if actual_pitr != expected_pitr:
                    result.drift_detected = True
                    result.add_message(f"Point-in-time recovery: expected {expected_pitr}, got {actual_pitr}")

            result.valid = True

        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                result.exists = False
                result.add_message(f"Table {resource_id} does not exist")
            else:
                result.add_message(f"Error validating table: {err}")

        return result

    def list_resources(self, filter_params = None) -> list:
        """List all DynamoDB tables."""
        tables = []
        paginator = self.client.get_paginator("list_tables")

        for page in paginator.paginate():
            tables.extend(page.get("TableNames", []))

        # Apply filters if provided
        if filter_params and "prefix" in filter_params:
            prefix = filter_params["prefix"]
            tables = [t for t in tables if t.startswith(prefix)]

        return tables

    def _get_point_in_time_recovery(self, table_name: str) -> bool:
        """Check if point-in-time recovery is enabled."""
        try:
            response = self.client.describe_continuous_backups(TableName=table_name)
            pitr_status = (
                response.get("ContinuousBackupsDescription", {})
                .get("PointInTimeRecoveryDescription", {})
                .get("PointInTimeRecoveryStatus")
            )
            return pitr_status == "ENABLED"
        except ClientError:
            return False

    def _compare_key_schemas(self, actual: list, expected: list) -> bool:
        """Compare key schemas for equality."""
        if len(actual) != len(expected):
            return False

        # Sort by attribute name for comparison
        actual_sorted = sorted(actual, key=lambda x: x.get("AttributeName", ""))
        expected_sorted = sorted(expected, key=lambda x: x.get("AttributeName", ""))

        for a, e in zip(actual_sorted, expected_sorted):
            if a.get("AttributeName") != e.get("AttributeName") or a.get("KeyType") != e.get("KeyType"):
                return False

        return True


class CognitoValidator(ResourceValidator):
    """Validator for Cognito resources."""

    def __init__(self, session: boto3.Session):
        """Initialize Cognito validator."""
        super().__init__(session)
        self.client = session.client("cognito-idp")

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a Cognito user pool."""
        result = ValidationResult(resource_id, "cognito_user_pool")
        result.expected_config = expected_config

        try:
            # Get user pool description
            response = self.client.describe_user_pool(UserPoolId=resource_id)
            pool = response.get("UserPool", {})
            result.exists = True

            # Extract actual configuration
            result.actual_config = {
                "pool_name": pool.get("Name"),
                "status": pool.get("Status"),
                "mfa_configuration": pool.get("MfaConfiguration", "OFF"),
                "password_policy": pool.get("Policies", {}).get("PasswordPolicy", {}),
                "auto_verified_attributes": pool.get("AutoVerifiedAttributes", []),
                "username_attributes": pool.get("UsernameAttributes", []),
            }

            # Check pool status
            if pool.get("Status") != "Enabled":
                result.add_message(f"User pool is not enabled (status: {pool.get('Status')})")
                result.valid = False
                return result

            # Validate MFA configuration
            if expected_config.get("mfa_configuration"):
                actual_mfa = result.actual_config["mfa_configuration"]
                expected_mfa = expected_config["mfa_configuration"]
                if actual_mfa != expected_mfa:
                    result.drift_detected = True
                    result.add_message(f"MFA configuration drift: expected {expected_mfa}, got {actual_mfa}")

            # Validate password policy
            if expected_config.get("password_policy"):
                if not self._compare_password_policies(result.actual_config["password_policy"], expected_config["password_policy"]):
                    result.drift_detected = True
                    result.add_message("Password policy mismatch")

            result.valid = True

        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                result.exists = False
                result.add_message(f"User pool {resource_id} does not exist")
            else:
                result.add_message(f"Error validating user pool: {err}")

        return result

    def list_resources(self, filter_params = None) -> list:
        """List all Cognito user pools."""
        pools = []
        paginator = self.client.get_paginator("list_user_pools")

        for page in paginator.paginate(MaxResults=60):
            for pool in page.get("UserPools", []):
                pools.append(pool["Id"])

        return pools

    def _compare_password_policies(self, actual: dict, expected: dict) -> bool:
        """Compare password policies for equality."""
        policy_keys = ["MinimumLength", "RequireUppercase", "RequireLowercase", "RequireNumbers", "RequireSymbols"]

        for key in policy_keys:
            if key in expected:
                if actual.get(key) != expected.get(key):
                    return False

        return True


class CloudWatchValidator(ResourceValidator):
    """Validator for CloudWatch resources."""

    def __init__(self, session: boto3.Session):
        """Initialize CloudWatch validator."""
        super().__init__(session)
        self.logs_client = session.client("logs")

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a CloudWatch log group."""
        result = ValidationResult(resource_id, "cloudwatch_log_group")
        result.expected_config = expected_config

        try:
            # Get log group description
            response = self.logs_client.describe_log_groups(logGroupNamePrefix=resource_id, limit=1)

            log_groups = response.get("logGroups", [])
            if not log_groups or log_groups[0]["logGroupName"] != resource_id:
                result.exists = False
                result.add_message(f"Log group {resource_id} does not exist")
                return result

            log_group = log_groups[0]
            result.exists = True

            # Extract actual configuration
            result.actual_config = {
                "log_group_name": log_group["logGroupName"],
                "retention_days": log_group.get("retentionInDays"),
                "kms_key_id": log_group.get("kmsKeyId"),
                "stored_bytes": log_group.get("storedBytes", 0),
            }

            # Validate retention policy
            if expected_config.get("retention_days") is not None:
                actual_retention = result.actual_config["retention_days"]
                expected_retention = expected_config["retention_days"]
                if actual_retention != expected_retention:
                    result.drift_detected = True
                    result.add_message(f"Retention days drift: expected {expected_retention}, got {actual_retention}")

            result.valid = True

        except ClientError as err:
            result.add_message(f"Error validating log group: {err}")

        return result

    def list_resources(self, filter_params = None) -> list:
        """List all CloudWatch log groups."""
        log_groups = []
        paginator = self.logs_client.get_paginator("describe_log_groups")

        kwargs = {}
        if filter_params and "prefix" in filter_params:
            kwargs["logGroupNamePrefix"] = filter_params["prefix"]

        for page in paginator.paginate(**kwargs):
            for group in page.get("logGroups", []):
                log_groups.append(group.get("logGroupName"))

        return log_groups


class CodeBuildValidator(ResourceValidator):
    """Validator for CodeBuild projects."""

    def __init__(self, session: boto3.Session):
        """Initialize CodeBuild validator."""
        super().__init__(session)
        self.client = session.client("codebuild")

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a CodeBuild project."""
        result = ValidationResult(resource_id, "codebuild_project")
        result.expected_config = expected_config

        try:
            # Get project description
            response = self.client.batch_get_projects(names=[resource_id])

            if not response.get("projects", []):
                result.exists = False
                result.add_message(f"CodeBuild project {resource_id} does not exist")
                return result

            project = response.get("projects", [{}])[0]
            result.exists = True

            # Extract actual configuration
            result.actual_config = {
                "project_name": project.get("name"),
                "source_type": project.get("source", {}).get("type"),
                "environment": {
                    "compute_type": project.get("environment", {}).get("computeType"),
                    "image": project.get("environment", {}).get("image"),
                    "type": project.get("environment", {}).get("type"),
                },
                "service_role": project.get("serviceRole"),
            }

            # Validate source configuration
            if expected_config.get("source_type"):
                actual_source = result.actual_config["source_type"]
                expected_source = expected_config["source_type"]
                if actual_source != expected_source:
                    result.drift_detected = True
                    result.add_message(f"Source type drift: expected {expected_source}, got {actual_source}")

            # Validate environment
            if expected_config.get("environment"):
                if not self._compare_environments(result.actual_config["environment"], expected_config["environment"]):
                    result.drift_detected = True
                    result.add_message("Environment configuration mismatch")

            result.valid = True

        except ClientError as err:
            result.add_message(f"Error validating CodeBuild project: {err}")

        return result

    def list_resources(self, filter_params = None) -> list:
        """List all CodeBuild projects."""
        projects = []
        paginator = self.client.get_paginator("list_projects")

        for page in paginator.paginate():
            projects.extend(page.get("projects", []))

        # Apply filters if provided
        if filter_params and "prefix" in filter_params:
            prefix = filter_params["prefix"]
            projects = [p for p in projects if p.startswith(prefix)]

        return projects

    def _compare_environments(self, actual: dict, expected: dict) -> bool:
        """Compare CodeBuild environments for equality."""
        env_keys = ["compute_type", "image", "type"]

        for key in env_keys:
            if key in expected:
                if actual.get(key) != expected.get(key):
                    return False

        return True


class S3BucketValidator(ResourceValidator):
    """Validator for S3 buckets."""

    def __init__(self, session: boto3.Session):
        """Initialize S3 validator."""
        super().__init__(session)
        self.client = session.client("s3")
        self.region = session.region_name

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate an S3 bucket configuration."""
        result = ValidationResult(resource_id, "s3_bucket")
        result.expected_config = expected_config

        try:
            # Check if bucket exists
            self.client.head_bucket(Bucket=resource_id)
            result.exists = True

            # Get bucket location
            location_response = self.client.get_bucket_location(Bucket=resource_id)
            bucket_region = location_response.get("LocationConstraint") or "us-east-1"

            # Extract actual configuration
            result.actual_config = {
                "bucket_name": resource_id,
                "region": bucket_region,
                "versioning": self._get_versioning_status(resource_id),
                "public_access_block": self._get_public_access_block(resource_id),
                "website_enabled": self._is_website_enabled(resource_id),
                "cors_enabled": self._has_cors_configuration(resource_id),
            }

            # Validate region
            if expected_config.get("region"):
                if bucket_region != expected_config.get("region"):
                    result.drift_detected = True
                    result.add_message(f"Region mismatch: expected {expected_config.get('region')}, got {bucket_region}")

            # Validate versioning
            if "versioning" in expected_config:
                actual_versioning = result.actual_config["versioning"]
                expected_versioning = expected_config["versioning"]
                if actual_versioning != expected_versioning:
                    result.drift_detected = True
                    result.add_message(f"Versioning drift: expected {expected_versioning}, got {actual_versioning}")

            # Validate public access block
            if expected_config.get("public_access_block"):
                if not self._compare_public_access_block(
                    result.actual_config["public_access_block"], expected_config["public_access_block"]
                ):
                    result.drift_detected = True
                    result.add_message("Public access block configuration mismatch")

            # Validate website configuration
            if "website_enabled" in expected_config:
                actual_website = result.actual_config["website_enabled"]
                expected_website = expected_config["website_enabled"]
                if actual_website != expected_website:
                    result.drift_detected = True
                    result.add_message(f"Website configuration: expected {expected_website}, got {actual_website}")

            result.valid = True

        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code")
            if error_code in ["NoSuchBucket", "404"]:
                result.exists = False
                result.add_message(f"Bucket {resource_id} does not exist")
            elif error_code == "403":
                result.exists = True  # Bucket exists but no access
                result.add_message(f"Access denied to bucket {resource_id}")
                result.valid = False
            else:
                result.add_message(f"Error validating bucket: {err}")

        return result

    def list_resources(self, filter_params = None) -> list:
        """List all S3 buckets."""
        buckets = []
        try:
            response = self.client.list_buckets()
            for bucket in response.get("Buckets", []):
                buckets.append(bucket.get("Name"))

            # Apply filters if provided
            if filter_params and "prefix" in filter_params:
                prefix = filter_params["prefix"]
                buckets = [b for b in buckets if b.startswith(prefix)]

        except ClientError:
            # Return empty list on error
            pass

        return buckets

    def _get_versioning_status(self, bucket_name: str) -> str:
        """Get bucket versioning status."""
        try:
            response = self.client.get_bucket_versioning(Bucket=bucket_name)
            return response.get("Status", "Disabled")
        except ClientError:
            return "Unknown"

    def _get_public_access_block(self, bucket_name: str) -> dict:
        """Get public access block configuration."""
        try:
            response = self.client.get_public_access_block(Bucket=bucket_name)
            config = response.get("PublicAccessBlockConfiguration", {})
            return {
                "block_public_acls": config.get("BlockPublicAcls", False),
                "block_public_policy": config.get("BlockPublicPolicy", False),
                "ignore_public_acls": config.get("IgnorePublicAcls", False),
                "restrict_public_buckets": config.get("RestrictPublicBuckets", False),
            }
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "NoSuchPublicAccessBlockConfiguration":
                # No public access block means all False
                return {
                    "block_public_acls": False,
                    "block_public_policy": False,
                    "ignore_public_acls": False,
                    "restrict_public_buckets": False,
                }
            return {}

    def _is_website_enabled(self, bucket_name: str) -> bool:
        """Check if static website hosting is enabled."""
        try:
            self.client.get_bucket_website(Bucket=bucket_name)
            return True
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "NoSuchWebsiteConfiguration":
                return False
            return False

    def _has_cors_configuration(self, bucket_name: str) -> bool:
        """Check if CORS configuration exists."""
        try:
            self.client.get_bucket_cors(Bucket=bucket_name)
            return True
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "NoSuchCORSConfiguration":
                return False
            return False

    def _compare_public_access_block(self, actual: dict, expected: dict) -> bool:
        """Compare public access block configurations."""
        keys = ["block_public_acls", "block_public_policy", "ignore_public_acls", "restrict_public_buckets"]

        for key in keys:
            if key in expected:
                if actual.get(key, False) != expected.get(key):
                    return False

        return True


class ResourceValidatorFactory:
    """Factory for creating resource validators."""

    @staticmethod
    def create_validator(resource_type: str, session: boto3.Session) -> ResourceValidator:
        """Create a validator for the specified resource type.

        Args:
            resource_type: Type of AWS resource
            session: Boto3 session

        Returns:
            Appropriate ResourceValidator instance

        Raises:
            ValueError: If resource type is not supported
        """
        validators = {
            "dynamodb_table": DynamoDBTableValidator,
            "cognito_user_pool": CognitoValidator,
            "cloudwatch_log_group": CloudWatchValidator,
            "codebuild_project": CodeBuildValidator,
            "s3_bucket": S3BucketValidator,
        }

        validator_class = validators.get(resource_type)
        if not validator_class:
            raise ValueError(f"Unsupported resource type: {resource_type}")

        return validator_class(session)


def validate_stack_resources(session: boto3.Session, stack_name: str, expected_resources: dict) -> dict:
    """Validate all resources in a CloudFormation stack.

    Args:
        session: Boto3 session
        stack_name: Name of the CloudFormation stack
        expected_resources: Expected resource configurations

    Returns:
        Dictionary of resource ID to ValidationResult
    """
    results = {}

    for resource_id, resource_config in expected_resources.items():
        resource_type = resource_config.get("type")
        if not resource_type:
            continue

        try:
            validator = ResourceValidatorFactory.create_validator(resource_type, session)
            result = validator.validate(resource_id, resource_config.get("config", {}))
            results[resource_id] = result
        except ValueError as err:
            # Unsupported resource type
            result = ValidationResult(resource_id, resource_type)
            result.add_message(str(err))
            results[resource_id] = result

    return results


def generate_drift_report(validation_results: dict) -> str:
    """Generate a human-readable drift report.

    Args:
        validation_results: Dictionary of validation results

    Returns:
        Formatted drift report
    """
    report_lines = ["=== Infrastructure Drift Report ===\n"]

    total_resources = len(validation_results)
    existing_resources = sum(1 for r in validation_results.values() if r.exists)
    valid_resources = sum(1 for r in validation_results.values() if r.valid)
    drift_detected = sum(1 for r in validation_results.values() if r.drift_detected)

    report_lines.append(f"Total Resources: {total_resources}")
    report_lines.append(f"Existing Resources: {existing_resources}")
    report_lines.append(f"Valid Resources: {valid_resources}")
    report_lines.append(f"Resources with Drift: {drift_detected}\n")

    if drift_detected > 0:
        report_lines.append("Resources with Configuration Drift:")
        for resource_id, result in validation_results.items():
            if result.drift_detected:
                report_lines.append(f"\n  • {resource_id} ({result.resource_type}):")
                for message in result.messages:
                    report_lines.append(f"    - {message}")

    missing_resources = [r for r, result in validation_results.items() if not result.exists]
    if missing_resources:
        report_lines.append("\nMissing Resources:")
        for resource_id in missing_resources:
            result = validation_results[resource_id]
            report_lines.append(f"  • {resource_id} ({result.resource_type})")

    return "\n".join(report_lines)
