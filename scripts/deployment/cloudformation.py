"""CloudFormation stack operations."""

import os

from botocore.exceptions import ClientError, WaiterError
from deployment.aws_utils import retry_on_transient_error


def get_stack_failure_reason(cf_client, stack_name: str) -> list:
    """Get failure reasons from CloudFormation stack events.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Stack name

    Returns:
        list: List of failure messages
    """
    failures = []
    try:
        response = cf_client.describe_stack_events(StackName=stack_name)
        events = response.get("StackEvents", [])

        for event in events:
            status = event.get("ResourceStatus", "")
            if "FAILED" in status or status == "ROLLBACK_IN_PROGRESS":
                resource_id = event.get("LogicalResourceId", "Unknown")
                reason = event.get("ResourceStatusReason", "No reason provided")
                resource_type = event.get("ResourceType", "Unknown")

                if reason and reason not in ["Resource creation cancelled", "Resource update cancelled"]:
                    failures.append(f"  {resource_id} ({resource_type}): {reason}")

        # Deduplicate while preserving order
        seen = set()
        unique_failures = []
        for failure in failures:
            if failure not in seen:
                seen.add(failure)
                unique_failures.append(failure)

        return unique_failures[:10]
    except ClientError:
        return []


def deploy_stack(cf_client, stack_name: str, template_path: str, parameters=None, capabilities=None) -> bool:
    """Deploy a CloudFormation stack.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Name of the CloudFormation stack
        template_path: Path to CloudFormation template file
        parameters: Dictionary of stack parameters
        capabilities: List of IAM capabilities required

    Returns:
        bool: True if deployment succeeded, False otherwise
    """
    print(f"Deploying {stack_name}...")

    # Check if stack already exists and its status
    stack_exists = False
    try:
        response = retry_on_transient_error(lambda: cf_client.describe_stacks(StackName=stack_name))
        stacks = response.get("Stacks", [])
        if stacks:
            existing = stacks[0]
            status = existing.get("StackStatus", "")
            print(f"  Stack exists with status: {status}")
            if status in ["ROLLBACK_COMPLETE", "ROLLBACK_FAILED", "CREATE_FAILED", "DELETE_FAILED"]:
                try:
                    print("  Stack in failed state, deleting...")
                    retry_on_transient_error(lambda: cf_client.delete_stack(StackName=stack_name))
                    waiter = cf_client.get_waiter("stack_delete_complete")
                    waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 60})
                    print("  Stack deleted, recreating...")
                except (ClientError, WaiterError) as err:
                    print(f"  Error deleting stack: {err}")
                    return False
            else:
                stack_exists = True
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code != "ValidationError":
            print(f"  Error checking stack: {err}")
            return False

    if not os.path.exists(template_path):
        print(f"  Error: Template file not found: {template_path}")
        return False

    with open(template_path, "r", encoding="utf-8") as template_file:
        template_body = template_file.read()

    params = [{"ParameterKey": key, "ParameterValue": value} for key, value in parameters.items()] if parameters else []
    caps = capabilities if capabilities else []

    try:
        if stack_exists:
            print("  Updating existing stack...")
            try:
                retry_on_transient_error(
                    lambda: cf_client.update_stack(
                        StackName=stack_name, TemplateBody=template_body, Parameters=params, Capabilities=caps
                    )
                )
                waiter = cf_client.get_waiter("stack_update_complete")
                waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 180})
                print(f"  Stack {stack_name} updated successfully")
            except ClientError as update_err:
                if "No updates are to be performed" in str(update_err):
                    print(f"  No updates needed for {stack_name}")
                    return True
                raise update_err
        else:
            return create_new_stack(cf_client, stack_name, template_body, params, caps)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ["ValidationError", "ValidationException"]:
            return create_new_stack(cf_client, stack_name, template_body, params, caps)
        else:
            print(f"  Error deploying stack: {err}")
            failures = get_stack_failure_reason(cf_client, stack_name)
            if failures:
                print("  Stack failure details:")
                for failure in failures:
                    print(failure)
            return False
    except WaiterError as err:
        print(f"  Error waiting for stack: {err}")
        failures = get_stack_failure_reason(cf_client, stack_name)
        if failures:
            print("  Stack failure details:")
            for failure in failures:
                print(failure)
        return False

    return True


def create_new_stack(cf_client, stack_name: str, template_body: str, params: list, caps: list) -> bool:
    """Create a new CloudFormation stack.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Name of the CloudFormation stack
        template_body: CloudFormation template content
        params: List of parameter dictionaries
        caps: List of IAM capabilities

    Returns:
        bool: True if creation succeeded
    """
    print("  Creating new stack...")
    try:
        retry_on_transient_error(
            lambda: cf_client.create_stack(StackName=stack_name, TemplateBody=template_body, Parameters=params, Capabilities=caps)
        )
        waiter = cf_client.get_waiter("stack_create_complete")
        waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 180})
        print(f"  Stack {stack_name} created successfully")
        return True
    except WaiterError as waiter_err:
        print(f"  Stack creation failed: {waiter_err}")
        failures = get_stack_failure_reason(cf_client, stack_name)
        if failures:
            print("  Stack failure details:")
            for failure in failures:
                print(failure)
        return False
    except ClientError as create_err:
        print(f"  Error creating stack: {create_err}")
        return False


def get_stack_output(cf_client, stack_name: str, output_key: str) -> str:
    """Get output value from CloudFormation stack.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Stack name
        output_key: Output key to retrieve

    Returns:
        str: Output value or empty string if not found
    """
    try:
        response = retry_on_transient_error(lambda: cf_client.describe_stacks(StackName=stack_name))
        stacks = response.get("Stacks", [])
        if not stacks:
            return ""
        stack = stacks[0]
        outputs = stack.get("Outputs", [])
        output_value = next((output.get("OutputValue") for output in outputs if output.get("OutputKey") == output_key), "")
        return output_value
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code == "ValidationError":
            return ""
        print(f"  Warning: Error retrieving output {output_key} from {stack_name}: {err}")
        return ""
