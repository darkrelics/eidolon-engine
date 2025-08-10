"""Configuration validation for deployment parameters."""


def validate_deployment_config(params: dict) -> list:
    """Validate deployment configuration parameters.

    Args:
        params: Deployment parameters dictionary

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []

    # Required fields
    required_fields = {"game_name": "Game name is required", "contact_email": "Contact email is required for SES configuration"}

    for field, error_msg in required_fields.items():
        if not params.get(field):
            errors.append(error_msg)

    # Email format validation
    if params.get("contact_email"):
        email = params["contact_email"]
        if "@" not in email or "." not in email.split("@")[-1]:
            errors.append(f"Invalid email format: {email}")

    # Domain configuration validation
    if params.get("domain_name") and not params.get("hosted_zone_id"):
        errors.append("Hosted Zone ID is required when domain name is specified")

    # Deployment mode validation
    valid_modes = ["mud", "incremental", "hybrid"]
    if params.get("deployment_mode") and params["deployment_mode"] not in valid_modes:
        errors.append(f"Invalid deployment mode: {params['deployment_mode']}. Must be one of: {', '.join(valid_modes)}")

    # Log retention validation
    if params.get("log_retention_days"):
        retention = params["log_retention_days"]
        valid_retentions = [1, 3, 5, 7, 14, 30, 60, 90, 120, 150, 180, 365, 400, 545, 731, 1827, 3653]
        if retention not in valid_retentions:
            errors.append(f"Invalid log retention days: {retention}. Must be one of AWS allowed values")

    return errors


def validate_stack_config(stack_name: str, config: dict) -> list:
    """Validate configuration for a specific stack.

    Args:
        stack_name: Name of the CDK stack
        config: Stack-specific configuration

    Returns:
        List of validation error messages
    """
    errors = []

    if stack_name == "cognito":
        if config.get("dev_mode") and config.get("contact_email"):
            errors.append("Contact email not needed in dev mode")
        elif not config.get("dev_mode") and not config.get("contact_email"):
            errors.append("Contact email required for production Cognito")

    elif stack_name == "dynamodb":
        # Validate table names don't have invalid characters
        if config.get("table_names"):
            for table_type, table_name in config["table_names"].items():
                if table_name and not table_name.replace("-", "").replace("_", "").isalnum():
                    errors.append(f"Invalid DynamoDB table name: {table_name}")

    elif stack_name == "s3":
        # Validate S3 bucket names
        for bucket_type in ["portal_bucket_name", "scripts_bucket_name", "lambda_bucket_name"]:
            bucket_name = config.get(bucket_type)
            if bucket_name:
                if len(bucket_name) < 3 or len(bucket_name) > 63:
                    errors.append(f"S3 bucket name must be 3-63 characters: {bucket_name}")
                if ".." in bucket_name or bucket_name.startswith(".") or bucket_name.endswith("."):
                    errors.append(f"Invalid S3 bucket name format: {bucket_name}")

    return errors
