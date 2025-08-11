#!/usr/bin/env python3
"""Clean up CloudWatch log groups for Lambda functions before deployment."""

import boto3
from botocore.exceptions import ClientError


class LogGroupCleanup:
    """Manages cleanup of CloudWatch log groups for Lambda functions."""

    def __init__(self, session: boto3.Session):
        """Initialize the log cleanup component.

        Args:
            session: Boto3 session for AWS operations
        """
        self.session = session
        self.logs_client = session.client("logs")
        self.lambda_client = session.client("lambda")

    def find_lambda_log_groups(self) -> list:
        """Find all CloudWatch log groups for Lambda functions.

        Returns:
            List of log group names that belong to Lambda functions
        """
        lambda_log_groups = []

        try:
            paginator = self.logs_client.get_paginator("describe_log_groups")

            for page in paginator.paginate(logGroupNamePrefix="/aws/lambda/"):
                for log_group in page.get("logGroups", []):
                    lambda_log_groups.append(log_group["logGroupName"])

        except ClientError as err:
            print(f"    [ERROR] Failed to list log groups: {err}")
            return []

        return lambda_log_groups

    def check_lambda_exists(self, function_name: str) -> bool:
        """Check if a Lambda function exists.

        Args:
            function_name: Name of the Lambda function

        Returns:
            True if function exists, False otherwise
        """
        try:
            self.lambda_client.get_function(FunctionName=function_name)
            return True
        except ClientError as err:
            if err.response["Error"]["Code"] == "ResourceNotFoundException":
                return False
            return False

    def delete_orphaned_log_groups(self) -> int:
        """Delete log groups for Lambda functions that no longer exist.

        Returns:
            Number of log groups deleted
        """
        print("\n  Checking for orphaned Lambda log groups...")

        lambda_log_groups = self.find_lambda_log_groups()

        if not lambda_log_groups:
            print("    No Lambda log groups found")
            return 0

        print(f"    Found {len(lambda_log_groups)} Lambda log group(s)")

        deleted_count = 0
        orphaned_groups = []

        for log_group in lambda_log_groups:
            # Extract function name from log group name
            # Format: /aws/lambda/function-name
            if log_group.startswith("/aws/lambda/"):
                function_name = log_group.replace("/aws/lambda/", "")

                # Check if Lambda function exists
                if not self.check_lambda_exists(function_name):
                    orphaned_groups.append(log_group)

        if orphaned_groups:
            print(f"    Found {len(orphaned_groups)} orphaned log group(s) to delete:")
            for log_group in orphaned_groups:
                print(f"      - {log_group}")

            print("    Deleting orphaned log groups...")
            for log_group in orphaned_groups:
                try:
                    self.logs_client.delete_log_group(logGroupName=log_group)
                    print(f"      [OK] Deleted {log_group}")
                    deleted_count += 1
                except ClientError as err:
                    print(f"      [ERROR] Failed to delete {log_group}: {err}")
        else:
            print("    No orphaned log groups found")

        return deleted_count

    def cleanup_all_lambda_logs(self, force: bool = False) -> int:
        """Delete all Lambda function log groups.

        Args:
            force: If True, delete all Lambda log groups without checking if functions exist

        Returns:
            Number of log groups deleted
        """
        if force:
            print("\n  Force deleting all Lambda log groups...")
        else:
            print("\n  Cleaning up Lambda log groups...")

        lambda_log_groups = self.find_lambda_log_groups()

        if not lambda_log_groups:
            print("    No Lambda log groups found")
            return 0

        print(f"    Found {len(lambda_log_groups)} Lambda log group(s) to delete")

        deleted_count = 0

        for log_group in lambda_log_groups:
            # If not force mode, only delete orphaned log groups
            if not force:
                function_name = log_group.replace("/aws/lambda/", "")
                if self.check_lambda_exists(function_name):
                    print(f"      Skipping {log_group} (function exists)")
                    continue

            try:
                self.logs_client.delete_log_group(logGroupName=log_group)
                print(f"      [OK] Deleted {log_group}")
                deleted_count += 1
            except ClientError as err:
                if err.response["Error"]["Code"] == "ResourceNotFoundException":
                    print(f"      [SKIP] {log_group} already deleted")
                else:
                    print(f"      [ERROR] Failed to delete {log_group}: {err}")

        print(f"    Successfully deleted {deleted_count} log group(s)")
        return deleted_count

    def clean_before_deployment(self) -> bool:
        """Clean up Lambda log groups before deployment.

        This checks for orphaned log groups (logs without corresponding Lambda functions)
        and deletes them to prevent deployment conflicts.

        Returns:
            True if cleanup was successful, False if errors occurred
        """
        try:
            deleted_count = self.delete_orphaned_log_groups()

            if deleted_count > 0:
                print(f"  Cleanup complete: deleted {deleted_count} orphaned log group(s)")
            else:
                print("  No cleanup needed: all log groups are valid")

            return True

        except Exception as err:
            print(f"  [ERROR] Log cleanup failed: {err}")
            return False
