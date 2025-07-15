"""Utilities for CloudFormation stack operations."""

from botocore.exceptions import ClientError


class StackOutputHelper:
    """Helper class for retrieving CloudFormation stack outputs."""

    def __init__(self, cfn_client):
        """Initialize with a CloudFormation client.

        Args:
            cfn_client: boto3 CloudFormation client
        """
        self.cfn_client = cfn_client

    def get_outputs(self, stack_name: str) -> dict:
        """Get outputs from a CloudFormation stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Dictionary of output key-value pairs
        """
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            if response["Stacks"]:
                stack = response["Stacks"][0]
                outputs = {}
                for output in stack.get("Outputs", []):
                    outputs[output["OutputKey"]] = output["OutputValue"]
                return outputs
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "ValidationError":
                # Stack doesn't exist
                return {}
            # Re-raise other errors
            raise
        return {}

    def get_output_value(self, stack_name: str, output_key: str, default: str = "") -> str:
        """Get a specific output value from a stack.

        Args:
            stack_name: Name of the CloudFormation stack
            output_key: The output key to retrieve
            default: Default value if output not found

        Returns:
            The output value or default
        """
        outputs = self.get_outputs(stack_name)
        return outputs.get(output_key, default)

    def get_stack_status(self, stack_name: str) -> str:
        """Get the current status of a CloudFormation stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Stack status string or empty string if stack doesn't exist
        """
        try:
            response = self.cfn_client.describe_stacks(StackName=stack_name)
            if response["Stacks"]:
                return response["Stacks"][0].get("StackStatus", "")
        except ClientError:
            pass
        return ""

    def stack_exists(self, stack_name: str) -> bool:
        """Check if a CloudFormation stack exists.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            True if stack exists, False otherwise
        """
        try:
            self.cfn_client.describe_stacks(StackName=stack_name)
            return True
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "")
            if error_code == "ValidationError":
                return False
            # Re-raise other errors
            raise

    def get_stack_resources(self, stack_name: str) -> dict:
        """Get resources from a CloudFormation stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Dictionary mapping logical resource ID to resource info
        """
        resources = {}
        try:
            response = self.cfn_client.list_stack_resources(StackName=stack_name)
            for resource in response.get("StackResourceSummaries", []):
                resources[resource.get("LogicalResourceId")] = {
                    "physical_id": resource.get("PhysicalResourceId"),
                    "type": resource.get("ResourceType"),
                    "status": resource.get("ResourceStatus")
                }
        except ClientError:
            pass
        return resources

    def wait_for_stack(self, stack_name: str, wait_type: str = "create"):
        """Wait for a stack operation to complete.

        Args:
            stack_name: Name of the CloudFormation stack
            wait_type: Type of waiter ('create', 'update', 'delete')
        """
        waiter_map = {
            "create": "stack_create_complete",
            "update": "stack_update_complete",
            "delete": "stack_delete_complete"
        }
        
        waiter_name = waiter_map.get(wait_type, "stack_create_complete")
        waiter = self.cfn_client.get_waiter(waiter_name)
        waiter.wait(StackName=stack_name)