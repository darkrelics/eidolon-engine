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

    # Basic required parameters - use config values as defaults
    required_params = {
        "game_name": ("Game name", params.get("game_name", "eidolon-engine")),
        "contact_email": ("Administrator contact email", params.get("contact_email", "contact@darkrelics.net")),
        "github_owner": ("GitHub repository owner", params.get("github_owner", "robinje")),
        "github_repo": ("GitHub repository name", params.get("github_repo", "eidolon-engine")),
        "github_branch": ("GitHub branch to deploy from", params.get("github_branch", "main")),
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
    if params.get("deploy_mud") or params.get("deploy_incremental") or params.get("deployment_mode"):
        print("\n=== API CONFIGURATION ===")
        print("API Gateway requires a custom domain name and hosted zone.")
        print("Skip this section if you don't have a domain configured in Route53.\n")

        # Check if we have API config - prompt for domain if not set
        domain_default = params.get("domain_name", "skip to use default")
        domain = input(f"Domain name (e.g., darkrelics.net) [{domain_default}]: ").strip()

        if domain and domain.lower() != "skip":
            params["domain_name"] = domain
        elif not domain and domain_default != "skip to use default":
            # User pressed enter and we have a configured value, keep it
            params["domain_name"] = domain_default
        elif domain.lower() == "skip" or (not domain and domain_default == "skip to use default"):
            # User wants to skip API configuration
            params.pop("domain_name", None)
            params.pop("hosted_zone_id", None)

        # If we have a domain name, we need a hosted zone ID
        if params.get("domain_name"):
            zone_id_default = params.get("hosted_zone_id", "")
            zone_id = input(f"Route53 Hosted Zone ID [{zone_id_default if zone_id_default else 'required'}]: ").strip()
            if zone_id:
                params["hosted_zone_id"] = zone_id
            elif zone_id_default:
                # User pressed enter and we have a configured value, keep it
                params["hosted_zone_id"] = zone_id_default
            else:
                print("WARNING: Hosted Zone ID is required for custom domain. Skipping API Gateway setup.")
                params.pop("domain_name", None)
                params.pop("hosted_zone_id", None)

    # Optional S3 bucket names
    print("\n=== S3 BUCKETS ===")

    # Check if we already have bucket names from config
    has_portal_bucket = params.get("portal_bucket_name") and params["portal_bucket_name"] != "auto-generate"
    has_scripts_bucket = params.get("scripts_bucket_name") and params["scripts_bucket_name"] != "auto-generate"
    has_artifacts_bucket = params.get("lambda_bucket_name") and params["lambda_bucket_name"] != "auto-generate"

    if has_portal_bucket or has_scripts_bucket or has_artifacts_bucket:
        print("Existing S3 buckets detected from configuration.")
        print("Press Enter to keep existing buckets, or enter new names to change.\n")
    else:
        print("Leave blank to create new buckets with auto-generated names.\n")

    # Show actual bucket name from config if available, otherwise show 'auto-generate'
    portal_default = params.get("portal_bucket_name", "auto-generate")
    portal_bucket = input(f"Portal S3 bucket name [{portal_default}]: ").strip()
    if portal_bucket:
        params["portal_bucket_name"] = portal_bucket
    elif portal_default and portal_default != "auto-generate":
        # User pressed enter and we have a configured value, keep it
        params["portal_bucket_name"] = portal_default
    # else: leave it unset for auto-generation

    scripts_default = params.get("scripts_bucket_name", "auto-generate")
    scripts_bucket = input(f"Scripts S3 bucket name [{scripts_default}]: ").strip()
    if scripts_bucket:
        params["scripts_bucket_name"] = scripts_bucket
    elif scripts_default and scripts_default != "auto-generate":
        # User pressed enter and we have a configured value, keep it
        params["scripts_bucket_name"] = scripts_default
    # else: leave it unset for auto-generation

    artifacts_default = params.get("lambda_bucket_name", "auto-generate")
    artifacts_bucket = input(f"Artifacts S3 bucket name [{artifacts_default}]: ").strip()
    if artifacts_bucket:
        params["lambda_bucket_name"] = artifacts_bucket
    elif artifacts_default and artifacts_default != "auto-generate":
        # User pressed enter and we have a configured value, keep it
        params["lambda_bucket_name"] = artifacts_default
    # else: leave it unset for auto-generation

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
            # Use base table names as defaults - no prefixes
            table_names = [
                "players",
                "characters",
                "rooms",
                "exits",
                "items",
                "prototypes",
                "archetypes",
                "motd",
                "story",
                "segments",
                "active_segments",
            ]

        for table_name in table_names:
            expected_config = {
                "billing_mode": "PAY_PER_REQUEST",
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

        # Expected config for all private S3 buckets
        expected_config = {
            "website_enabled": False,  # No website hosting needed with CloudFront
            "public_access_block": {
                "block_public_acls": True,
                "block_public_policy": True,
                "ignore_public_acls": True,
                "restrict_public_buckets": True,
            },
        }

        # Check portal bucket - should be PRIVATE (accessed via CloudFront)
        portal_bucket = params.get("portal_bucket_name", "")
        if portal_bucket:  # Only validate if bucket name is provided
            result = validator.validate(portal_bucket, expected_config)
            all_results[portal_bucket] = result

        # Check scripts bucket - should be PRIVATE (accessed programmatically)
        scripts_bucket = params.get("scripts_bucket_name", "")
        if scripts_bucket:  # Only validate if bucket name is provided
            # Scripts bucket should also be private
            result = validator.validate(scripts_bucket, expected_config)
            all_results[scripts_bucket] = result

        # Check lambda bucket - should be PRIVATE (deployment artifacts)
        game_name = params.get("game_name", "eidolon-engine")
        account_id = session.client("sts").get_caller_identity()["Account"]
        lambda_bucket = params.get("lambda_bucket_name", f"{game_name}-lambda-{account_id}")
        result = validator.validate(lambda_bucket, expected_config)
        all_results[lambda_bucket] = result
    except Exception as err:
        print(f"Warning: Error validating S3 buckets: {err}")

    # Validate IAM resources
    try:
        game_name = params.get("game_name", "eidolon-engine")

        # Check IAM role
        role_validator = ResourceValidatorFactory.create_validator("iam_role", session)
        role_name = f"{game_name}-server-execution-role"
        result = role_validator.validate(role_name, {"resource_type": "role"})
        all_results[f"iam_role:{role_name}"] = result

        # Check IAM policies
        policy_validator = ResourceValidatorFactory.create_validator("iam_policy", session)
        policy_names = [f"eidolon-{game_name}-cloudwatch-access", f"eidolon-{game_name}-dynamodb-access"]

        for policy_name in policy_names:
            result = policy_validator.validate(policy_name, {"resource_type": "policy"})
            all_results[f"iam_policy:{policy_name}"] = result

    except Exception as err:
        print(f"Warning: Error validating IAM resources: {err}")

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


def check_iam_policies(session, game_name: str) -> dict:
    """Check for existing IAM policies.

    Args:
        session: AWS session
        game_name: Game name for policy naming

    Returns:
        Dictionary of policy existence
    """
    iam_client = session.client("iam")
    policies = {
        "cloudwatch_policy": f"eidolon-{game_name}-cloudwatch-access",
        "dynamodb_policy": f"eidolon-{game_name}-dynamodb-access",
    }

    existing_policies = {}
    try:
        paginator = iam_client.get_paginator("list_policies")
        for page in paginator.paginate(Scope="Local"):
            for policy in page["Policies"]:
                for key, policy_name in policies.items():
                    if policy["PolicyName"] == policy_name:
                        existing_policies[key] = {"name": policy_name, "arn": policy["Arn"], "exists": True}
    except Exception as err:
        print(f"Warning: Could not check IAM policies: {err}")

    return existing_policies


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

    # Check for existing IAM policies
    game_name = params.get("game_name", "eidolon-engine")
    existing_iam_policies = check_iam_policies(session, game_name)

    if existing_iam_policies:
        print("\nDetected existing IAM policies:")
        for key, policy_info in existing_iam_policies.items():
            print(f"  - {policy_info['name']}")

    # Expected CDK stack names (in dependency order)
    expected_stacks = [
        "iam",
        "s3",
        "dynamodb",
        "cognito",
        "cloudwatch",
        "codebuild",
        "base-lambda",
        "lambda",
        "cloudfront",
    ]

    plan = {
        "create_stacks": [],
        "update_stacks": [],
        "unchanged_stacks": [],
        "adopt_resources": {},
        "cloudformation_mapping": cf_mapping,
        "existing_iam_policies": existing_iam_policies,
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
        # Skip cognito stack if we have existing Cognito resources
        if stack_name == "cognito" and params.get("existing_user_pool_id"):
            print(f"\nSkipping {stack_name} stack - using existing Cognito resources")
            continue

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
