"""CloudFormation stack operations."""

import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, WaiterError
from deployment.aws_utils import retry_on_transient_error

# CloudFormation rejects an inline TemplateBody larger than this many bytes;
# larger templates must be uploaded to S3 and referenced via TemplateURL.
_MAX_INLINE_TEMPLATE_BYTES = 51200

# Set once per deployment via configure_template_uploads(); used to stage
# oversized templates in S3 so they can be deployed by URL.
_TEMPLATE_BUCKET = None
_TEMPLATE_REGION = None


def configure_template_uploads(s3_bucket: str, region: str) -> None:
    """Configure the S3 bucket used to stage oversized CloudFormation templates.

    Args:
        s3_bucket: Bucket that can hold templates over the inline size limit
        region: AWS region of the bucket
    """
    global _TEMPLATE_BUCKET, _TEMPLATE_REGION
    _TEMPLATE_BUCKET = s3_bucket
    _TEMPLATE_REGION = region


def _template_source_kwargs(stack_name: str, template_body: str) -> dict:
    """Return the CloudFormation template argument for a stack operation.

    Templates within the inline limit are passed as TemplateBody. Larger
    templates are uploaded to the configured S3 bucket and referenced by
    TemplateURL, which is CloudFormation's only way to accept them.

    Args:
        stack_name: Stack name (used to build the S3 key)
        template_body: Full template text

    Returns:
        dict: Either {"TemplateBody": ...} or {"TemplateURL": ...}

    Raises:
        RuntimeError: If the template is too large and no staging bucket is set
    """
    if len(template_body.encode("utf-8")) <= _MAX_INLINE_TEMPLATE_BYTES:
        return {"TemplateBody": template_body}

    if not _TEMPLATE_BUCKET:
        raise RuntimeError(
            f"Template for {stack_name} exceeds the {_MAX_INLINE_TEMPLATE_BYTES}-byte inline limit "
            "and no S3 staging bucket is configured (call configure_template_uploads)."
        )

    key = f"cf-templates/{stack_name}.yml"
    s3_client = boto3.client("s3", region_name=_TEMPLATE_REGION)
    retry_on_transient_error(
        lambda: s3_client.put_object(
            Bucket=_TEMPLATE_BUCKET,
            Key=key,
            Body=template_body.encode("utf-8"),
            ContentType="application/x-yaml",
        )
    )
    template_url = f"https://{_TEMPLATE_BUCKET}.s3.{_TEMPLATE_REGION}.amazonaws.com/{key}"
    print(f"  Template exceeds inline limit, staged to S3: {template_url}")
    return {"TemplateURL": template_url}


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


def _get_rollback_failed_resources(cf_client, stack_name: str) -> list:
    """Get resource IDs that failed during rollback.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Stack name

    Returns:
        list: Logical resource IDs that failed during rollback
    """
    failed = []
    try:
        response = cf_client.describe_stack_events(StackName=stack_name)
        for event in response.get("StackEvents", []):
            if event.get("ResourceStatus") == "UPDATE_FAILED":
                resource_id = event.get("LogicalResourceId", "")
                if resource_id and resource_id != stack_name and resource_id not in failed:
                    failed.append(resource_id)
    except ClientError:
        pass
    return failed


def _continue_update_rollback(cf_client, stack_name: str) -> bool:
    """Continue a stuck UPDATE_ROLLBACK_FAILED stack by skipping failed resources.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Stack name

    Returns:
        bool: True if rollback completed successfully
    """
    resources_to_skip = _get_rollback_failed_resources(cf_client, stack_name)
    print("  Stack stuck in UPDATE_ROLLBACK_FAILED, continuing rollback...")
    if resources_to_skip:
        print(f"  Skipping failed resources: {', '.join(resources_to_skip)}")
    try:
        retry_on_transient_error(
            lambda: cf_client.continue_update_rollback(
                StackName=stack_name,
                ResourcesToSkip=resources_to_skip,
            )
        )
        waiter = cf_client.get_waiter("stack_rollback_complete")
        waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 60})
        print("  Rollback completed, proceeding with update...")
        return True
    except (ClientError, WaiterError) as err:
        print(f"  Error continuing rollback: {err}")
        return False


def deploy_stack(
    cf_client, stack_name: str, template_path: Path, parameters=None, capabilities=None, resources_to_import=None
) -> bool:
    """Deploy a CloudFormation stack.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Name of the CloudFormation stack
        template_path: Path to CloudFormation template file
        parameters: Dictionary of stack parameters
        capabilities: List of IAM capabilities required
        resources_to_import: List of resource dicts for CF import (pre-existing resources)

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
            elif status == "UPDATE_ROLLBACK_FAILED":
                if not _continue_update_rollback(cf_client, stack_name):
                    return False
                try:
                    print("  Deleting stack after rollback recovery...")
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
                template_kwargs = _template_source_kwargs(stack_name, template_body)
                retry_on_transient_error(
                    lambda: cf_client.update_stack(StackName=stack_name, Parameters=params, Capabilities=caps, **template_kwargs)
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
            if resources_to_import:
                return create_stack_via_import(cf_client, stack_name, template_body, params, caps, resources_to_import)
            return create_new_stack(cf_client, stack_name, template_body, params, caps)
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "")
        if error_code in ["ValidationError", "ValidationException"]:
            if resources_to_import:
                return create_stack_via_import(cf_client, stack_name, template_body, params, caps, resources_to_import)
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
        template_kwargs = _template_source_kwargs(stack_name, template_body)
        retry_on_transient_error(
            lambda: cf_client.create_stack(StackName=stack_name, Parameters=params, Capabilities=caps, **template_kwargs)
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


def create_stack_via_import(
    cf_client, stack_name: str, template_body: str, params: list, caps: list, resources_to_import: list
) -> bool:
    """Create a CloudFormation stack by importing existing resources.

    Uses CloudFormation's resource import to adopt pre-existing resources
    into a new stack without recreating them. CloudFormation import does
    not allow Outputs, so they are stripped for the import and restored
    via a follow-up update.

    Args:
        cf_client: boto3 CloudFormation client
        stack_name: Name of the CloudFormation stack
        template_body: CloudFormation template content
        params: List of parameter dictionaries
        caps: List of IAM capabilities
        resources_to_import: List of resource import dicts

    Returns:
        bool: True if import succeeded
    """
    print("  Importing existing resources into new stack...")
    change_set_name = f"{stack_name}-import"

    # CloudFormation import does not allow Outputs in the template.
    # Strip them for import, then restore via a follow-up update.
    lines = template_body.splitlines(True)
    output_start = None
    for i, line in enumerate(lines):
        if line.startswith("Outputs:"):
            output_start = i
            break
    has_outputs = output_start is not None
    import_template = "".join(lines[:output_start]) if has_outputs else template_body

    create_params = {
        "StackName": stack_name,
        "ChangeSetName": change_set_name,
        "ChangeSetType": "IMPORT",
        "TemplateBody": import_template,
        "ResourcesToImport": resources_to_import,
    }
    if params:
        create_params["Parameters"] = params
    if caps:
        create_params["Capabilities"] = caps

    try:
        retry_on_transient_error(lambda: cf_client.create_change_set(**create_params))
    except ClientError as err:
        print(f"  Error creating import change set: {err}")
        return False

    try:
        waiter = cf_client.get_waiter("change_set_create_complete")
        waiter.wait(StackName=stack_name, ChangeSetName=change_set_name, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
    except WaiterError as err:
        print(f"  Error waiting for import change set: {err}")
        return False

    try:
        retry_on_transient_error(lambda: cf_client.execute_change_set(StackName=stack_name, ChangeSetName=change_set_name))
    except ClientError as err:
        print(f"  Error executing import change set: {err}")
        return False

    try:
        waiter = cf_client.get_waiter("stack_import_complete")
        waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 60})
        print(f"  Stack {stack_name} created via resource import")
    except WaiterError as err:
        print(f"  Error during resource import: {err}")
        failures = get_stack_failure_reason(cf_client, stack_name)
        if failures:
            print("  Stack failure details:")
            for failure in failures:
                print(failure)
        return False

    # Restore outputs via a follow-up update with the full template
    if has_outputs:
        print("  Updating imported stack to add outputs...")
        try:
            retry_on_transient_error(
                lambda: cf_client.update_stack(
                    StackName=stack_name, TemplateBody=template_body, Parameters=params, Capabilities=caps
                )
            )
            waiter = cf_client.get_waiter("stack_update_complete")
            waiter.wait(StackName=stack_name, WaiterConfig={"Delay": 10, "MaxAttempts": 60})
            print(f"  Stack {stack_name} outputs configured")
        except ClientError as err:
            if "No updates are to be performed" in str(err):
                print(f"  Stack {stack_name} outputs already configured")
            else:
                print(f"  Error adding outputs to imported stack: {err}")
                return False
        except WaiterError as err:
            print(f"  Error waiting for output update: {err}")
            return False

    return True


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
