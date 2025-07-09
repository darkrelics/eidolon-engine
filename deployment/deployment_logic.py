"""Business logic for the Eidolon Engine deployment orchestrator.

This module contains the functions that perform the detailed work of
analyzing the deployment environment, validating resources, and creating
a deployment plan.
"""

import sys

from resource_validator import ResourceValidatorFactory, generate_drift_report


def prompt_missing_parameters(params: dict) -> dict:
    """Prompt user for any missing required parameters.

    Args:
        params: Current parameters

    Returns:
        Updated parameters with user input
    """
    print("\n=== CONFIGURATION ===")

    # Basic required parameters
    required_params = {
        "game_name": ("Game name", "eidolon-engine"),
        "contact_email": ("Administrator contact email", "contact@darkrelics.net"),
        "github_owner": ("GitHub repository owner", "robinje"),
        "github_repo": ("GitHub repository name", "eidolon-engine"),
        "github_branch": ("GitHub branch to deploy from", "main"),
    }

    print("\nPlease provide the following configuration values:")
    print("(Press Enter to accept the default value shown in brackets)\n")

    for param, (description, default) in required_params.items():
        current_value = params.get(param, default)
        value = input(f"{description} [{current_value}]: ").strip()
        if value:
            params[param] = value
        elif current_value:
            params[param] = current_value
        else:
            print(f"ERROR: {param} is required")
            sys.exit(1)

    # API Configuration (required for Lambda deployments)
    if params.get("deploy_mud") or params.get("deploy_incremental"):
        print("\n=== API CONFIGURATION ===")
        print("API Gateway requires a custom domain name and hosted zone.")
        print("Skip this section if you don't have a domain configured in Route53.\n")

        # Check if we have API config
        if not params.get("domain_name"):
            domain = input("Domain name (e.g., darkrelics.net) [skip to use default]: ").strip()
            if domain and domain.lower() != "skip":
                params["domain_name"] = domain

                # Also need hosted zone ID
                zone_id = input("Route53 Hosted Zone ID [required if domain provided]: ").strip()
                if zone_id:
                    params["hosted_zone_id"] = zone_id
                else:
                    print("WARNING: Hosted Zone ID is required for custom domain. Skipping API Gateway setup.")
                    params.pop("domain_name", None)

    # Optional S3 bucket names
    print("\n=== S3 BUCKETS ===")
    print("Leave blank to create new buckets with auto-generated names.\n")

    portal_bucket = input(f"Portal S3 bucket name [{params.get('portal_bucket_name', 'auto-generate')}]: ").strip()
    if portal_bucket and portal_bucket != "auto-generate":
        params["portal_bucket_name"] = portal_bucket

    scripts_bucket = input(f"Scripts S3 bucket name [{params.get('scripts_bucket_name', 'auto-generate')}]: ").strip()
    if scripts_bucket and scripts_bucket != "auto-generate":
        params["scripts_bucket_name"] = scripts_bucket

    return params


def get_existing_stacks(cfn_client) -> dict:
    """Get information about existing CloudFormation stacks.

    Returns:
        Dictionary of stack name to stack information
    """
    existing_stacks = {}

    try:
        paginator = cfn_client.get_paginator("list_stacks")
        for page in paginator.paginate(StackStatusFilter=["CREATE_COMPLETE", "UPDATE_COMPLETE"]):
            for stack in page.get("StackSummaries", []):
                stack_name = stack.get("StackName")
                # Get detailed stack info
                try:
                    response = cfn_client.describe_stacks(StackName=stack_name)
                    stack_detail = response.get("Stacks", [{}])[0]

                    # Get stack resources for mapping
                    resources_response = cfn_client.list_stack_resources(StackName=stack_name)
                    resources = {}
                    for resource in resources_response.get("StackResourceSummaries", []):
                        resources[resource.get("LogicalResourceId")] = {
                            "physical_id": resource.get("PhysicalResourceId"),
                            "type": resource.get("ResourceType"),
                        }

                    existing_stacks[stack_name] = {
                        "status": stack_detail.get("StackStatus"),
                        "outputs": {
                            output.get("OutputKey"): output.get("OutputValue") for output in stack_detail.get("Outputs", [])
                        },
                        "parameters": {
                            param.get("ParameterKey"): param.get("ParameterValue") for param in stack_detail.get("Parameters", [])
                        },
                        "resources": resources,
                        "template_format": "CloudFormation",
                    }
                except Exception:
                    # Stack might have been deleted between list and describe
                    pass
    except Exception as err:
        print(f"Warning: Error querying existing stacks: {err}")

    return existing_stacks


def validate_resources(session, params: dict) -> dict:
    """Validate AWS resources for drift detection.

    Args:
        session: AWS session
        params: Deployment parameters

    Returns:
        Dictionary of resource validation results
    """
    all_results = {}

    # Validate DynamoDB tables
    try:
        validator = ResourceValidatorFactory.create_validator("dynamodb_table", session)
        # Use table names from params if provided, otherwise use defaults
        if "dynamodb_tables" in params:
            table_names = list(params["dynamodb_tables"].values())
        else:
            table_names = [
                "eidolon-players",
                "eidolon-characters",
                "eidolon-rooms",
                "eidolon-exits",
                "eidolon-items",
                "eidolon-prototypes",
                "eidolon-archetypes",
                "eidolon-motd",
            ]

        for table_name in table_names:
            expected_config = {
                "billing_mode": "PAY_PER_REQUEST",
                "point_in_time_recovery": True,
            }
            result = validator.validate(table_name, expected_config)
            all_results[table_name] = result
    except Exception as err:
        print(f"Warning: Error validating DynamoDB tables: {err}")

    # Validate CloudWatch log groups
    try:
        validator = ResourceValidatorFactory.create_validator("cloudwatch_log_group", session)
        log_group_name = "/aws/eidolon/server"
        expected_config = {
            "retention_days": params.get("log_retention_days", 365),
        }
        result = validator.validate(log_group_name, expected_config)
        all_results[log_group_name] = result
    except Exception as err:
        print(f"Warning: Error validating CloudWatch log groups: {err}")

    # Validate CodeBuild project
    try:
        validator = ResourceValidatorFactory.create_validator("codebuild_project", session)
        project_name = "eidolon-portal-build"
        expected_config = {
            "source_type": "GITHUB",
            "environment": {
                "compute_type": "BUILD_GENERAL1_SMALL",
                "type": "LINUX_CONTAINER",
            },
        }
        result = validator.validate(project_name, expected_config)
        all_results[project_name] = result
    except Exception as err:
        print(f"Warning: Error validating CodeBuild project: {err}")

    # Validate S3 buckets
    try:
        validator = ResourceValidatorFactory.create_validator("s3_bucket", session)

        # Check portal bucket
        portal_bucket = params.get("portal_bucket_name", "")
        if portal_bucket:  # Only validate if bucket name is provided
            expected_config = {
                "website_enabled": True,
                "public_access_block": {
                    "block_public_acls": False,
                    "block_public_policy": False,
                    "ignore_public_acls": False,
                    "restrict_public_buckets": False,
                },
            }
            result = validator.validate(portal_bucket, expected_config)
            all_results[portal_bucket] = result

        # Check scripts bucket
        scripts_bucket = params.get("scripts_bucket_name", "")
        if scripts_bucket:  # Only validate if bucket name is provided
            result = validator.validate(scripts_bucket, expected_config)
            all_results[scripts_bucket] = result
    except Exception as err:
        print(f"Warning: Error validating S3 buckets: {err}")

    return all_results


def map_cloudformation_to_cdk(existing_stacks: dict, _params: dict) -> dict:
    """Map existing CloudFormation stacks to CDK stacks.

    Args:
        existing_stacks: Dictionary of existing CloudFormation stacks
        _params: Deployment parameters

    Returns:
        Mapping of resources and migration strategy
    """
    mapping = {
        "cloudformation_stacks": {},
        "resource_mapping": {},
        "migration_strategy": "adopt",  # adopt, replace, or coexist
    }

    # Check for legacy CloudFormation stacks
    legacy_stacks = ["eidolon-cognito", "eidolon-dynamodb", "eidolon-cloudwatch", "eidolon-codebuild"]

    for legacy_name in legacy_stacks:
        if legacy_name in existing_stacks:
            stack_info = existing_stacks[legacy_name]
            mapping["cloudformation_stacks"][legacy_name] = {
                "outputs": stack_info["outputs"],
                "resources": stack_info["resources"],
                "can_adopt": _can_adopt_stack(legacy_name, stack_info),
            }

            # Map resources to CDK expectations
            if legacy_name == "eidolon-cognito":
                if "UserPoolId" in stack_info.get("outputs", {}):
                    mapping["resource_mapping"]["cognito_user_pool_id"] = stack_info.get("outputs", {}).get("UserPoolId")
                if "AppClientId" in stack_info.get("outputs", {}):
                    mapping["resource_mapping"]["cognito_app_client_id"] = stack_info.get("outputs", {}).get("AppClientId")
            elif legacy_name == "eidolon-dynamodb":
                # Map DynamoDB table names
                for key, value in stack_info.get("outputs", {}).items():
                    if key.endswith("TableName"):
                        table_type = key.replace("TableName", "").lower()
                        mapping["resource_mapping"][f"dynamodb_{table_type}_table"] = value
            elif legacy_name == "eidolon-cloudwatch":
                if "LogGroupName" in stack_info.get("outputs", {}):
                    mapping["resource_mapping"]["log_group_name"] = stack_info.get("outputs", {}).get("LogGroupName")

    # Determine migration strategy
    if mapping["cloudformation_stacks"]:
        # We have existing CloudFormation stacks
        can_adopt_all = all(stack.get("can_adopt", False) for stack in mapping["cloudformation_stacks"].values())
        if can_adopt_all:
            mapping["migration_strategy"] = "adopt"
        else:
            mapping["migration_strategy"] = "coexist"

    return mapping


def _can_adopt_stack(stack_name: str, _stack_info: dict) -> bool:
    """Check if a CloudFormation stack can be adopted by CDK.

    Args:
        stack_name: Name of the stack
        _stack_info: Stack information

    Returns:
        True if stack can be adopted
    """
    # DynamoDB tables and CloudWatch log groups can be imported
    # Cognito and CodeBuild are more complex
    adoptable_stacks = ["eidolon-dynamodb", "eidolon-cloudwatch"]
    return stack_name in adoptable_stacks


def analyze_changes(cfn_client, session, params: dict) -> dict:
    """Analyze what changes need to be deployed.

    Args:
        cfn_client: CloudFormation client
        session: AWS session
        params: Deployment parameters

    Returns:
        Dictionary with deployment plan
    """
    print("\nAnalyzing infrastructure changes...")

    # Get existing stacks
    existing_stacks = get_existing_stacks(cfn_client)

    # Map CloudFormation resources if they exist
    cf_mapping = map_cloudformation_to_cdk(existing_stacks, params)

    # Expected CDK stack names (in dependency order)
    expected_stacks = ["iam", "s3", "dynamodb", "cognito", "cloudwatch", "codebuild", "base-lambda", "lambda", "cognito-trigger", "cloudfront"]

    plan = {
        "create_stacks": [],
        "update_stacks": [],
        "unchanged_stacks": [],
        "adopt_resources": {},
        "cloudformation_mapping": cf_mapping,
        "parameters": params,
        "drift_report": "",
    }

    # If we have CloudFormation stacks, we can adopt or coexist
    if cf_mapping["cloudformation_stacks"]:
        print("\nDetected existing CloudFormation stacks:")
        for stack_name, info in cf_mapping["cloudformation_stacks"].items():
            print(f"  - {stack_name} (can adopt: {info.get('can_adopt', False)})")

        if cf_mapping["migration_strategy"] == "adopt":
            print("\nStrategy: Adopt existing resources into CDK stacks")
            plan["adopt_resources"] = cf_mapping["resource_mapping"]
        else:
            print("\nStrategy: CDK stacks will coexist with CloudFormation stacks")
            print("Note: Some resources cannot be adopted and will need manual migration")

    # Check each expected stack
    for stack_name in expected_stacks:
        if stack_name in existing_stacks:
            # CDK stack already exists
            plan["update_stacks"].append(stack_name)
        else:
            # Need to create CDK stack
            plan["create_stacks"].append(stack_name)

    # Validate existing resources for drift detection
    if existing_stacks or cf_mapping["cloudformation_stacks"]:
        print("\nValidating existing resources for drift...")
        drift_results = validate_resources(session, params)
        if drift_results:
            plan["drift_report"] = generate_drift_report(drift_results)
            print(plan["drift_report"])

    return plan
