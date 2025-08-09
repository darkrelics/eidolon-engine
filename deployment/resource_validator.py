"""Resource validation for AWS infrastructure drift detection.

This module provides validators for individual AWS resources to detect
configuration drift and validate resource states against desired configurations.
"""

from collections import Counter

import boto3
from botocore.exceptions import ClientError


class ValidationResult:
    """Result of a resource validation check."""

    def __init__(self, resource_id: str, resource_type: str) -> None:
        """Initialize validation result.

        Args:
            resource_id: Identifier for the resource
            resource_type: Type of AWS resource
        """
        self.resource_id: str = resource_id
        self.resource_type: str = resource_type
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

    def __init__(self, session: boto3.Session, service_name: str, resource_type: str):
        """Initialize validator with AWS session.

        Args:
            session: Boto3 session for AWS access
            service_name: AWS service name for client creation
            resource_type: Type of resource being validated
        """
        self.session = session
        self.client = session.client(service_name)
        self.resource_type = resource_type

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a specific resource.

        Args:
            resource_id: AWS resource identifier
            expected_config: Expected configuration for the resource

        Returns:
            ValidationResult with validation details
        """
        result = ValidationResult(resource_id, self.resource_type)
        result.expected_config = expected_config

        try:
            # Get resource description
            resource_data = self.get_resource_description(resource_id)
            if resource_data is None:
                result.exists = False
                result.add_message(f"{self.resource_type} {resource_id} does not exist")
                return result

            result.exists = True

            # Extract actual configuration
            result.actual_config = self.extract_actual_config(resource_data)

            # Check if resource is valid
            if not self.is_resource_valid(resource_data):
                result.valid = False
                return result

            # Validate configuration
            self.validate_configuration(result, expected_config)
            result.valid = True

        except ClientError as err:
            self.handle_client_error(result, err, resource_id)

        return result

    def get_resource_description(self, resource_id: str):
        """Get the resource description from AWS.

        Subclasses must implement this method.
        Returns None if resource doesn't exist.
        """
        raise NotImplementedError("Subclasses must implement get_resource_description()")

    def extract_actual_config(self, resource_data: dict) -> dict:
        """Extract the actual configuration from resource data.

        Subclasses must implement this method.
        """
        raise NotImplementedError("Subclasses must implement extract_actual_config()")

    def is_resource_valid(self, resource_data: dict) -> bool:
        """Check if the resource is in a valid state.

        Default implementation returns True. Override if needed.
        """
        # Avoid unused-argument warnings in default implementation
        try:
            # simply reference/delete to satisfy linters
            del resource_data
        except Exception:
            pass
        return True

    def validate_configuration(self, result: ValidationResult, expected_config: dict):
        """Validate the actual configuration against expected.

        Subclasses should implement specific validation logic.
        """
        # Provide a sensible default: treat expected_config as a subset that must
        # be present in actual_config. Extra fields in actual are allowed.
        # Record all mismatches as drift with precise paths.
        if not expected_config:
            return

        differences = []

        def normalize(value):
            """Produce a hashable, comparable representation for nested values."""
            if isinstance(value, dict):
                return (
                    "dict",
                    tuple(sorted((k, normalize(v)) for k, v in value.items())),
                )
            if isinstance(value, list):
                return (
                    "list",
                    tuple(sorted((normalize(v) for v in value))),
                )
            return value

        def compare(exp, act, path: str = ""):
            # Missing actual value entirely
            if act is None:
                differences.append(f"Missing value at {path or 'root'}")
                return

            # Dict: ensure all expected keys exist and match recursively
            if isinstance(exp, dict):
                if not isinstance(act, dict):
                    differences.append(f"Type mismatch at {path or 'root'}: expected dict, got {type(act).__name__}")
                    return
                for k, v in exp.items():
                    sub_path = f"{path}.{k}" if path else k
                    if k not in act:
                        differences.append(f"Missing key at {sub_path}")
                        continue
                    compare(v, act.get(k), sub_path)
                return

            # List: ensure each expected element appears in actual (multiset subset)
            if isinstance(exp, list):
                if not isinstance(act, list):
                    differences.append(f"Type mismatch at {path or 'root'}: expected list, got {type(act).__name__}")
                    return
                exp_counts = Counter(normalize(e) for e in exp)
                act_counts = Counter(normalize(a) for a in act)
                for item, cnt in exp_counts.items():
                    if act_counts.get(item, 0) < cnt:
                        differences.append(f"List at {path or 'root'} missing {cnt - act_counts.get(item, 0)} expected item(s)")
                return

            # Scalar: direct equality
            if exp != act:
                differences.append(f"Value mismatch at {path or 'root'}: expected {exp!r}, got {act!r}")

        compare(expected_config, result.actual_config)

        if differences:
            result.drift_detected = True
            for msg in differences:
                result.add_message(msg)

    def handle_client_error(self, result: ValidationResult, err: ClientError, resource_id: str):
        """Handle ClientError exceptions.

        Default implementation handles ResourceNotFoundException.
        Override to add service-specific error handling.
        """
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            result.exists = False
            result.add_message(f"{self.resource_type} {resource_id} does not exist")
        else:
            result.add_message(f"Error validating {self.resource_type}: {err}")

    def list_resources(self, filter_params=None) -> list:
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
        super().__init__(session, "dynamodb", "dynamodb_table")

    def get_resource_description(self, resource_id: str):
        """Get DynamoDB table description."""
        try:
            response = self.client.describe_table(TableName=resource_id)
            return response.get("Table", {})
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return None
            raise

    def extract_actual_config(self, resource_data: dict) -> dict:
        """Extract actual configuration from table data."""
        return {
            "table_name": resource_data.get("TableName"),
            "billing_mode": resource_data.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED"),
            "key_schema": resource_data.get("KeySchema", []),
            "attribute_definitions": resource_data.get("AttributeDefinitions", []),
            "table_status": resource_data.get("TableStatus"),
        }

    def is_resource_valid(self, resource_data: dict) -> bool:
        """Check if table is in ACTIVE status."""
        status = resource_data.get("TableStatus")
        if status != "ACTIVE":
            return False
        return True

    def validate_configuration(self, result: ValidationResult, expected_config: dict):
        """Validate DynamoDB table configuration."""
        # Validate billing mode
        if expected_config.get("billing_mode"):
            actual_billing = result.actual_config["billing_mode"]
            expected_billing = expected_config["billing_mode"]
            if actual_billing != expected_billing:
                result.drift_detected = True
                result.add_message(f"Billing mode drift: expected {expected_billing}, got {actual_billing}")

        # Validate key schema
        if expected_config.get("key_schema"):
            if not compare_key_schemas(result.actual_config["key_schema"], expected_config["key_schema"]):
                result.drift_detected = True
                result.add_message("Key schema mismatch")

    def list_resources(self, filter_params=None) -> list:
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


def compare_key_schemas(actual: list, expected: list) -> bool:
    """Compare DynamoDB key schemas for equality."""
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
        super().__init__(session, "cognito-idp", "cognito_user_pool")

    def get_resource_description(self, resource_id: str):
        """Get Cognito user pool description."""
        try:
            response = self.client.describe_user_pool(UserPoolId=resource_id)
            return response.get("UserPool", {})
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return None
            raise

    def extract_actual_config(self, resource_data: dict) -> dict:
        """Extract actual configuration from user pool data."""
        return {
            "pool_name": resource_data.get("Name"),
            "mfa_configuration": resource_data.get("MfaConfiguration", "OFF"),
            "password_policy": resource_data.get("Policies", {}).get("PasswordPolicy", {}),
            "auto_verified_attributes": resource_data.get("AutoVerifiedAttributes", []),
            "username_attributes": resource_data.get("UsernameAttributes", []),
        }

    def validate_configuration(self, result: ValidationResult, expected_config: dict):
        """Validate Cognito user pool configuration."""
        # Validate MFA configuration
        if expected_config.get("mfa_configuration"):
            actual_mfa = result.actual_config["mfa_configuration"]
            expected_mfa = expected_config["mfa_configuration"]
            if actual_mfa != expected_mfa:
                result.drift_detected = True
                result.add_message(f"MFA configuration drift: expected {expected_mfa}, got {actual_mfa}")

        # Validate password policy
        if expected_config.get("password_policy"):
            if not compare_password_policies(result.actual_config["password_policy"], expected_config["password_policy"]):
                result.drift_detected = True
                result.add_message("Password policy mismatch")

    def list_resources(self, filter_params=None) -> list:
        """List all Cognito user pools."""
        pools = []
        paginator = self.client.get_paginator("list_user_pools")

        for page in paginator.paginate(MaxResults=60):
            for pool in page.get("UserPools", []):
                pools.append(pool["Id"])

        return pools


def compare_password_policies(actual: dict, expected: dict) -> bool:
    """Compare Cognito password policies for equality."""
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
        super().__init__(session, "logs", "cloudwatch_log_group")

    def get_resource_description(self, resource_id: str):
        """Get CloudWatch log group description."""
        try:
            response = self.client.describe_log_groups(logGroupNamePrefix=resource_id, limit=1)
            log_groups = response.get("logGroups", [])
            if not log_groups or log_groups[0]["logGroupName"] != resource_id:
                return None
            return log_groups[0]
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                return None
            raise

    def extract_actual_config(self, resource_data: dict) -> dict:
        """Extract actual configuration from log group data."""
        return {
            "log_group_name": resource_data["logGroupName"],
            "retention_days": resource_data.get("retentionInDays"),
            "kms_key_id": resource_data.get("kmsKeyId"),
            "stored_bytes": resource_data.get("storedBytes", 0),
        }

    def validate_configuration(self, result: ValidationResult, expected_config: dict):
        """Validate CloudWatch log group configuration."""
        # Validate retention policy
        if expected_config.get("retention_days") is not None:
            actual_retention = result.actual_config["retention_days"]
            expected_retention = expected_config["retention_days"]
            if actual_retention != expected_retention:
                result.drift_detected = True
                result.add_message(f"Retention days drift: expected {expected_retention}, got {actual_retention}")

    def list_resources(self, filter_params=None) -> list:
        """List all CloudWatch log groups."""
        log_groups = []
        paginator = self.client.get_paginator("describe_log_groups")

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
        super().__init__(session, "codebuild", "codebuild_project")

    def get_resource_description(self, resource_id: str):
        """Retrieve the CodeBuild project description or None if missing."""
        try:
            response = self.client.batch_get_projects(names=[resource_id])
            projects = response.get("projects", [])
            if not projects:
                return None
            return projects[0]
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code")
            if error_code == "ResourceNotFoundException":
                return None
            raise

    def extract_actual_config(self, resource_data: dict) -> dict:
        return {
            "project_name": resource_data.get("name"),
            "source_type": resource_data.get("source", {}).get("type"),
            "environment": {
                "compute_type": resource_data.get("environment", {}).get("computeType"),
                "image": resource_data.get("environment", {}).get("image"),
                "type": resource_data.get("environment", {}).get("type"),
            },
            "service_role": resource_data.get("serviceRole"),
        }

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate a CodeBuild project."""
        result = ValidationResult(resource_id, "codebuild_project")
        result.expected_config = expected_config

        try:
            project = self.get_resource_description(resource_id)
            if not project:
                result.exists = False
                result.add_message(f"CodeBuild project {resource_id} does not exist")
                return result
            result.exists = True

            # Extract actual configuration
            result.actual_config = self.extract_actual_config(project)

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

    def list_resources(self, filter_params=None) -> list:
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
        super().__init__(session, "s3", "s3_bucket")
        self.region = session.region_name

    def get_resource_description(self, resource_id: str):
        """Return a minimal descriptor if bucket exists, else None."""
        try:
            self.client.head_bucket(Bucket=resource_id)
            return {"bucket": resource_id}
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code")
            if error_code in ["NoSuchBucket", "404"]:
                return None
            raise

    def extract_actual_config(self, resource_data: dict) -> dict:
        bucket_name = resource_data.get("bucket")
        location_response = self.client.get_bucket_location(Bucket=bucket_name)
        bucket_region = location_response.get("LocationConstraint") or "us-east-1"
        return {
            "bucket_name": bucket_name,
            "region": bucket_region,
            "versioning": self._get_versioning_status(bucket_name),
            "public_access_block": self._get_public_access_block(bucket_name),
            "website_enabled": self._is_website_enabled(bucket_name),
            "cors_enabled": self._has_cors_configuration(bucket_name),
        }

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate an S3 bucket configuration."""
        result = ValidationResult(resource_id, "s3_bucket")
        result.expected_config = expected_config

        try:
            descriptor = self.get_resource_description(resource_id)
            if not descriptor:
                result.exists = False
                result.add_message(f"Bucket {resource_id} does not exist")
                return result
            result.exists = True
            actual = self.extract_actual_config(descriptor)

            # Extract actual configuration
            result.actual_config = actual

            # Validate region
            if expected_config.get("region"):
                if actual.get("region") != expected_config.get("region"):
                    result.drift_detected = True
                    result.add_message(f"Region mismatch: expected {expected_config.get('region')}, got {actual.get('region')}")

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

    def list_resources(self, filter_params=None) -> list:
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


class IAMValidator(ResourceValidator):
    """Validator for IAM resources (roles and policies)."""

    def __init__(self, session: boto3.Session):
        """Initialize IAM validator."""
        super().__init__(session, "iam", "iam_resource")
        # Client is already created by parent class

    def get_resource_description(self, resource_id: str):
        """Fetch role by name, or local policy by name. Return structured info or None."""
        # Try role first
        try:
            response = self.client.get_role(RoleName=resource_id)
            return {"type": "role", "role": response.get("Role", {})}
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") != "NoSuchEntity":
                # Unexpected error
                raise
        # Try local managed policy by name
        paginator = self.client.get_paginator("list_policies")
        for page in paginator.paginate(Scope="Local"):
            for policy in page.get("Policies", []):
                if policy.get("PolicyName") == resource_id:
                    return {"type": "policy", "policy": policy}
        return None

    def extract_actual_config(self, resource_data: dict) -> dict:
        if resource_data.get("type") == "role":
            role = resource_data.get("role", {})
            role_name = role.get("RoleName")
            return {
                "role_name": role_name,
                "arn": role.get("Arn"),
                "assume_role_policy": role.get("AssumeRolePolicyDocument", {}),
                "attached_policies": self._get_attached_policies(role_name) if role_name else [],
            }
        if resource_data.get("type") == "policy":
            policy = resource_data.get("policy", {})
            return {
                "policy_name": policy.get("PolicyName"),
                "arn": policy.get("Arn"),
                "attachment_count": policy.get("AttachmentCount", 0),
            }
        return {}

    def validate(self, resource_id: str, expected_config: dict) -> ValidationResult:
        """Validate an IAM role or policy."""
        resource_type = expected_config.get("resource_type", "role")

        if resource_type == "role":
            return self._validate_role(resource_id, expected_config)
        elif resource_type == "policy":
            return self._validate_policy(resource_id, expected_config)
        else:
            result = ValidationResult(resource_id, f"iam_{resource_type}")
            result.add_message(f"Unsupported IAM resource type: {resource_type}")
            return result

    def _validate_role(self, role_name: str, expected_config: dict) -> ValidationResult:
        """Validate an IAM role."""
        result = ValidationResult(role_name, "iam_role")
        result.expected_config = expected_config

        try:
            # Get role details
            response = self.client.get_role(RoleName=role_name)
            role = response.get("Role", {})
            result.exists = True

            # Extract actual configuration
            result.actual_config = {
                "role_name": role.get("RoleName"),
                "arn": role.get("Arn"),
                "assume_role_policy": role.get("AssumeRolePolicyDocument", {}),
                "attached_policies": self._get_attached_policies(role_name),
            }

            result.valid = True

        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "NoSuchEntity":
                result.exists = False
                result.add_message(f"Role {role_name} does not exist")
            else:
                result.add_message(f"Error validating role: {err}")

        return result

    def _validate_policy(self, policy_name: str, expected_config: dict) -> ValidationResult:
        """Validate an IAM policy."""
        result = ValidationResult(policy_name, "iam_policy")
        result.expected_config = expected_config

        try:
            # List policies to find ours
            paginator = self.client.get_paginator("list_policies")
            policy_found = None

            for page in paginator.paginate(Scope="Local"):
                for policy in page.get("Policies", []):
                    if policy.get("PolicyName") == policy_name:
                        policy_found = policy
                        break
                if policy_found:
                    break

            if policy_found:
                result.exists = True
                result.actual_config = {
                    "policy_name": policy_found.get("PolicyName"),
                    "arn": policy_found.get("Arn"),
                    "attachment_count": policy_found.get("AttachmentCount", 0),
                }
                result.valid = True
            else:
                result.exists = False
                result.add_message(f"Policy {policy_name} does not exist")

        except ClientError as err:
            result.add_message(f"Error validating policy: {err}")

        return result

    def _get_attached_policies(self, role_name: str) -> list:
        """Get list of policies attached to a role."""
        policies = []
        try:
            # Get managed policies
            response = self.client.list_attached_role_policies(RoleName=role_name)
            for policy in response.get("AttachedPolicies", []):
                policies.append(policy.get("PolicyName"))
        except ClientError:
            pass
        return policies

    def list_resources(self, filter_params=None) -> list:
        """List all IAM resources."""
        resources = []

        # List roles
        try:
            paginator = self.client.get_paginator("list_roles")
            for page in paginator.paginate():
                for role in page.get("Roles", []):
                    resources.append(f"role:{role.get('RoleName')}")
        except ClientError:
            pass

        # List policies
        try:
            paginator = self.client.get_paginator("list_policies")
            for page in paginator.paginate(Scope="Local"):
                for policy in page.get("Policies", []):
                    resources.append(f"policy:{policy.get('PolicyName')}")
        except ClientError:
            pass

        return resources


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
            "iam_role": IAMValidator,
            "iam_policy": IAMValidator,
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

    # stack_name is not used presently but kept for future filtering/logging
    try:
        del stack_name
    except Exception:
        pass

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
                report_lines.append(f"\n  - {resource_id} ({result.resource_type}):")
                for message in result.messages:
                    report_lines.append(f"    - {message}")

    missing_resources = [r for r, result in validation_results.items() if not result.exists]
    if missing_resources:
        report_lines.append("\nMissing Resources:")
        for resource_id in missing_resources:
            result = validation_results[resource_id]
            report_lines.append(f"  - {resource_id} ({result.resource_type})")

    return "\n".join(report_lines)
