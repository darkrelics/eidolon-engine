"""Health checks for deployed infrastructure."""

import boto3
from botocore.exceptions import ClientError


def check_dynamodb_tables_health(session: boto3.Session, table_names: list) -> dict:
    """Check health of DynamoDB tables.

    Args:
        session: AWS session
        table_names: List of table names to check

    Returns:
        Dictionary with health status and any issues found
    """
    dynamodb = session.client("dynamodb")
    issues = []
    healthy_tables = []

    for table_name in table_names:
        try:
            response = dynamodb.describe_table(TableName=table_name)
            table_status = response["Table"]["TableStatus"]

            if table_status == "ACTIVE":
                healthy_tables.append(table_name)
            else:
                issues.append(f"Table {table_name} is in {table_status} state")

        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                issues.append(f"Table {table_name} not found")
            else:
                issues.append(f"Error checking table {table_name}: {err}")

    return {"healthy": len(issues) == 0, "healthy_tables": healthy_tables, "issues": issues}


def check_lambda_functions_health(session: boto3.Session, function_names: list) -> dict:
    """Check health of Lambda functions.

    Args:
        session: AWS session
        function_names: List of function names to check

    Returns:
        Dictionary with health status and issues
    """
    lambda_client = session.client("lambda")
    issues = []
    healthy_functions = []

    for func_name in function_names:
        try:
            response = lambda_client.get_function(FunctionName=func_name)
            state = response["Configuration"]["State"]

            if state == "Active":
                # Check if function can be invoked (dry run)
                try:
                    lambda_client.invoke(FunctionName=func_name, InvocationType="DryRun")
                    healthy_functions.append(func_name)
                except ClientError as err:
                    if err.response.get("Error", {}).get("Code") != "DryRunOperation":
                        issues.append(f"Function {func_name} cannot be invoked: {err}")
            else:
                issues.append(f"Function {func_name} is in {state} state")

        except ClientError as err:
            if err.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
                issues.append(f"Function {func_name} not found")
            else:
                issues.append(f"Error checking function {func_name}: {err}")

    return {"healthy": len(issues) == 0, "healthy_functions": healthy_functions, "issues": issues}


def check_api_gateway_health(session: boto3.Session, api_name: str) -> dict:
    """Check health of API Gateway.

    Args:
        session: AWS session
        api_name: Name of the REST API

    Returns:
        Dictionary with health status
    """
    apigateway = session.client("apigateway")
    issues = []

    try:
        # Find the API by name
        apis = apigateway.get_rest_apis()
        api_id = None

        for api in apis.get("items", []):
            if api["name"] == api_name:
                api_id = api["id"]
                break

        if not api_id:
            issues.append(f"API Gateway {api_name} not found")
        else:
            # Check deployment
            deployments = apigateway.get_deployments(restApiId=api_id)
            if not deployments.get("items"):
                issues.append(f"API Gateway {api_name} has no deployments")

    except ClientError as err:
        issues.append(f"Error checking API Gateway: {err}")

    return {"healthy": len(issues) == 0, "api_id": api_id, "issues": issues}


def check_s3_buckets_health(session: boto3.Session, bucket_names: list) -> dict:
    """Check health of S3 buckets.

    Args:
        session: AWS session
        bucket_names: List of bucket names to check

    Returns:
        Dictionary with health status
    """
    s3 = session.client("s3")
    issues = []
    healthy_buckets = []

    for bucket_name in bucket_names:
        if not bucket_name:  # Skip empty bucket names
            continue

        try:
            # Check bucket exists and is accessible
            s3.head_bucket(Bucket=bucket_name)

            # Check versioning (should be enabled for safety)
            versioning = s3.get_bucket_versioning(Bucket=bucket_name)
            if versioning.get("Status") != "Enabled":
                issues.append(f"Bucket {bucket_name} versioning is not enabled")

            healthy_buckets.append(bucket_name)

        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code")
            if error_code == "404":
                issues.append(f"Bucket {bucket_name} not found")
            elif error_code == "403":
                issues.append(f"Access denied to bucket {bucket_name}")
            else:
                issues.append(f"Error checking bucket {bucket_name}: {err}")

    return {"healthy": len(issues) == 0, "healthy_buckets": healthy_buckets, "issues": issues}


def run_phase_health_check(session: boto3.Session, phase_name: str, deployed_stacks: list, config: dict) -> bool:
    """Run health checks for a deployment phase.

    Args:
        session: AWS session
        phase_name: Name of the deployment phase
        deployed_stacks: List of stacks deployed in this phase
        config: Deployment configuration

    Returns:
        True if all health checks pass
    """
    print(f"\n  Running health checks for {phase_name}...")
    all_healthy = True

    if phase_name == "Foundation":
        # Check DynamoDB tables if dynamodb stack was deployed
        if "dynamodb" in deployed_stacks:
            table_names = [
                config.get("players_table", "players"),
                config.get("characters_table", "characters"),
                config.get("archetypes_table", "archetypes"),
                config.get("rooms_table", "rooms"),
                config.get("items_table", "items"),
            ]
            result = check_dynamodb_tables_health(session, table_names)
            if not result["healthy"]:
                print(f"    ✗ DynamoDB tables unhealthy:")
                for issue in result["issues"]:
                    print(f"      - {issue}")
                all_healthy = False
            else:
                print(f"    ✓ DynamoDB tables healthy ({len(result['healthy_tables'])} tables)")

        # Check S3 buckets if s3 stack was deployed
        if "s3" in deployed_stacks:
            bucket_names = [config.get("portal_bucket_name"), config.get("scripts_bucket_name"), config.get("lambda_bucket_name")]
            result = check_s3_buckets_health(session, bucket_names)
            if not result["healthy"]:
                print(f"    ✗ S3 buckets unhealthy:")
                for issue in result["issues"]:
                    print(f"      - {issue}")
                all_healthy = False
            else:
                print(f"    ✓ S3 buckets healthy ({len(result['healthy_buckets'])} buckets)")

    elif phase_name == "Application Layer":
        # Check Lambda functions if lambda stack was deployed
        if "lambda" in deployed_stacks:
            function_names = [
                "api-get-archetypes",
                "api-add-character",
                "api-get-character",
                "api-list-characters",
                "api-delete-character",
                "cognito-new-player",
                "cognito-delete-player",
            ]
            result = check_lambda_functions_health(session, function_names)
            if not result["healthy"]:
                print(f"    ✗ Lambda functions unhealthy:")
                for issue in result["issues"]:
                    print(f"      - {issue}")
                all_healthy = False
            else:
                print(f"    ✓ Lambda functions healthy ({len(result['healthy_functions'])} functions)")

        # Check API Gateway
        result = check_api_gateway_health(session, "eidolon-engine-api")
        if not result["healthy"]:
            print(f"    ✗ API Gateway unhealthy:")
            for issue in result["issues"]:
                print(f"      - {issue}")
            all_healthy = False
        else:
            print(f"    ✓ API Gateway healthy")

    if all_healthy:
        print(f"  ✓ All health checks passed for {phase_name}")
    else:
        print(f"  ✗ Health checks failed for {phase_name}")

    return all_healthy
