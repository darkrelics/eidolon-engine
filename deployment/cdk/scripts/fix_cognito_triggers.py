#!/usr/bin/env python3
"""Fix Cognito triggers by granting permissions and updating User Pool configuration.

This script addresses the issue where Cognito Lambda triggers are not being invoked
after user registration. It:
1. Grants Cognito permission to invoke the Lambda function
2. Updates the User Pool to ensure the trigger is properly configured
"""

import json
import sys
import boto3
from botocore.exceptions import ClientError


def get_user_pool_info():
    """Get the Cognito User Pool information."""
    cognito = boto3.client("cognito-idp", region_name="us-east-1")

    try:
        # List user pools to find ours
        response = cognito.list_user_pools(MaxResults=60)

        for pool in response["UserPools"]:
            if pool["Name"] == "eidolon-users":
                return pool["Id"]

        print("Error: Could not find 'eidolon-users' user pool")
        return None

    except ClientError as err:
        print(f"Error listing user pools: {err}")
        return None


def grant_cognito_permission(lambda_function_name, user_pool_id) -> bool:
    """Grant Cognito permission to invoke the Lambda function."""
    lambda_client = boto3.client("lambda", region_name="us-east-1")

    # Construct the source ARN for Cognito
    account_id = boto3.client("sts").get_caller_identity()["Account"]
    source_arn: str = f"arn:aws:cognito-idp:us-east-1:{account_id}:userpool/{user_pool_id}"

    try:
        # Add permission for Cognito to invoke the Lambda
        _ = lambda_client.add_permission(
            FunctionName=lambda_function_name,
            StatementId="CognitoInvokePermission",
            Action="lambda:InvokeFunction",
            Principal="cognito-idp.amazonaws.com",
            SourceArn=source_arn,
        )
        print(f"Successfully granted Cognito permission to invoke {lambda_function_name}")
        return True

    except ClientError as err:
        if "ResourceConflictException" in str(err):
            print(f"Permission already exists for {lambda_function_name}")
            return True
        else:
            print(f"Error granting permission: {err}")
            return False


def update_user_pool_triggers(user_pool_id, lambda_function_name) -> bool:
    """Update the User Pool to ensure triggers are configured."""
    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    lambda_client = boto3.client("lambda", region_name="us-east-1")

    try:
        # Get the Lambda function ARN
        lambda_info = lambda_client.get_function(FunctionName=lambda_function_name)
        lambda_arn = lambda_info["Configuration"]["FunctionArn"]

        # Get current user pool configuration
        pool_info = cognito.describe_user_pool(UserPoolId=user_pool_id)
        current_lambda_config = pool_info["UserPool"].get("LambdaConfig", {})

        # Update with PostConfirmation trigger
        new_lambda_config = current_lambda_config.copy()
        new_lambda_config["PostConfirmation"] = lambda_arn

        # Update the user pool
        cognito.update_user_pool(UserPoolId=user_pool_id, LambdaConfig=new_lambda_config)

        print(f"Successfully updated User Pool {user_pool_id} with PostConfirmation trigger")
        return True

    except ClientError as err:
        print(f"Error updating user pool: {err}")
        return False


def verify_configuration(user_pool_id, lambda_function_name) -> bool:
    """Verify the configuration is correct."""
    cognito = boto3.client("cognito-idp", region_name="us-east-1")
    lambda_client = boto3.client("lambda", region_name="us-east-1")

    try:
        # Check User Pool configuration
        pool_info = cognito.describe_user_pool(UserPoolId=user_pool_id)
        lambda_config = pool_info["UserPool"].get("LambdaConfig", {})
        post_confirmation = lambda_config.get("PostConfirmation")

        if post_confirmation:
            print(f"PostConfirmation trigger is configured: {post_confirmation}")
        else:
            print("PostConfirmation trigger is NOT configured")
            return False

        # Check Lambda permissions
        try:
            policy_response = lambda_client.get_policy(FunctionName=lambda_function_name)
            policy = json.loads(policy_response["Policy"])

            cognito_permission_found = False
            for statement in policy["Statement"]:
                if statement.get("Principal", {}).get("Service") == "cognito-idp.amazonaws.com":
                    cognito_permission_found = True
                    print(f"Cognito has permission to invoke {lambda_function_name}")
                    break

            if not cognito_permission_found:
                print(f"Cognito does NOT have permission to invoke {lambda_function_name}")
                return False

        except ClientError as err:
            if "ResourceNotFoundException" in str(err):
                print(f"No permissions policy found for {lambda_function_name}")
                return False
            raise

        return True

    except ClientError as err:
        print(f"Error verifying configuration: {err}")
        return False


def main() -> None:
    """Main function to fix Cognito triggers."""
    print("Fixing Cognito Lambda triggers...")
    print("=" * 60)

    # Configuration
    lambda_function_name = "cognito-new-player"

    # Get User Pool ID
    user_pool_id = get_user_pool_info()
    if not user_pool_id:
        sys.exit(1)

    print(f"\nUser Pool ID: {user_pool_id}")
    print(f"Lambda Function: {lambda_function_name}")
    print()

    # Grant permission
    if not grant_cognito_permission(lambda_function_name, user_pool_id):
        print("\nFailed to grant Cognito permission")
        sys.exit(1)

    # Update User Pool triggers
    if not update_user_pool_triggers(user_pool_id, lambda_function_name):
        print("\nFailed to update User Pool triggers")
        sys.exit(1)

    # Verify configuration
    print("\nVerifying configuration...")
    if verify_configuration(user_pool_id, lambda_function_name):
        print("\n✓ Cognito triggers are properly configured!")
        print("\nNext steps:")
        print("1. Test user registration again")
        print("2. Check CloudWatch logs for /aws/lambda/cognito-new-player")
        print("3. Verify the Players table has the new user entry")
    else:
        print("\n✗ Configuration verification failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
