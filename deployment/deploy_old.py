"""
Eidolon Engine

Copyright 2024-2025 Jason Robinson

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

Eidolon Engine Deployment Script
"""

import os

import boto3
import yaml
from botocore.exceptions import ClientError

# Constants for stack names
COGNITO_STACK_NAME = "Eidolon-Cognito-Stack"
DYNAMO_STACK_NAME = "Eidolon-DynamoDB-Stack"
CODEBUILD_STACK_NAME = "Eidolon-CodeBuild-Stack"
CLOUDWATCH_STACK_NAME = "Eidolon-CloudWatch-Stack"

# Paths to the CloudFormation templates
COGNITO_TEMPLATE_PATH = "../cloudformation/cognito.yml"
DYNAMO_TEMPLATE_PATH = "../cloudformation/dynamo.yml"
CODEBUILD_TEMPLATE_PATH = "../cloudformation/codebuild.yml"
CLOUDWATCH_TEMPLATE_PATH = "../cloudformation/cloudwatch.yml"

# Configuration file paths
CONFIG_PATH = "../config.yml"
CONFIG_TEMPLATE_PATH = "../config.template.yml"
ENV_FILE_PATH = "../portal/.env"
SCRIPTS_PATH = "../scripts_lua"


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        if not os.path.exists(CONFIG_TEMPLATE_PATH):
            raise FileNotFoundError(f"Neither {CONFIG_PATH} nor {CONFIG_TEMPLATE_PATH} exist")
        with open(CONFIG_TEMPLATE_PATH, "r", encoding="utf-8") as template_file:
            config = yaml.safe_load(template_file)
        with open(CONFIG_PATH, "w", encoding="utf-8") as config_file:
            yaml.dump(config, config_file, default_flow_style=False)
        return config

    with open(CONFIG_PATH, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


def validate_s3_bucket(bucket_name, region="us-east-1") -> bool:
    s3_client = boto3.client("s3", region_name=region)
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"S3 bucket '{bucket_name}' exists and is accessible")
        return True
    except ClientError as err:
        print(f"Error accessing S3 bucket '{bucket_name}': {err}")
        return False


def load_template(template_path) -> str:
    with open(template_path, "r", encoding="utf-8") as file:
        return file.read()


def deploy_stack(client, stack_name, template_body, parameters) -> bool:
    cf_parameters: list = [{"ParameterKey": k, "ParameterValue": v} for k, v in parameters.items()]
    try:
        if stack_exists(client, stack_name):
            print(f"Updating existing stack: {stack_name}")
            client.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
            )
        else:
            print(f"Creating new stack: {stack_name}")
            client.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=cf_parameters,
                Capabilities=["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"],
            )
        wait_for_stack_completion(client, stack_name)
        return True
    except ClientError as err:
        print(f"Error in stack operation for {stack_name}: {err}")
        if not stack_exists(client, stack_name):
            print(f"Stack {stack_name} was not created due to an error.")
        else:
            print(f"Attempting to delete stack {stack_name} due to error...")
            try:
                client.delete_stack(StackName=stack_name)
                print(f"Stack {stack_name} deletion initiated.")
            except ClientError as delete_err:
                print(f"Error deleting stack {stack_name}: {delete_err}")
        return False


def stack_exists(client, stack_name) -> bool:
    try:
        client.describe_stacks(StackName=stack_name)
        return True
    except client.exceptions.ClientError:
        return False


def wait_for_stack_completion(client, stack_name) -> None:
    print(f"Waiting for stack {stack_name} to complete...")
    waiter = client.get_waiter("stack_create_complete")
    waiter.wait(StackName=stack_name)
    print("Stack operation completed.")


def get_stack_outputs(client, stack_name) -> dict:
    try:
        stack = client.describe_stacks(StackName=stack_name)
        outputs = stack["Stacks"][0]["Outputs"]
        return {output["OutputKey"]: output["OutputValue"] for output in outputs}
    except ClientError as err:
        print(f"Error getting stack outputs for {stack_name}: {err}")
        return {}


def update_configuration_file(config_updates, user_pool_name=None) -> None:
    try:
        config: dict = load_config()
    except (IOError, yaml.YAMLError) as err:
        print(f"Error loading configuration file: {err}")
        return

    # Ensure top-level keys exist
    for key in ["Server", "AWS", "Cognito", "Game", "Logging", "SSH", "CloudWatch"]:
        if key not in config or config[key] is None:
            config[key] = {}

    # Update AWS configuration
    if "Region" not in config.get("AWS", {}):
        config["AWS"]["Region"] = "us-east-1"

    # Update Game configuration - only set defaults if not present
    game_config = config.get("Game", {})
    game_defaults = {
        "Balance": 0.25,
        "AutoSave": 5,
        "StartingHealth": 10,
        "StartingEssence": 3,
    }
    for key, value in game_defaults.items():
        if key not in game_config:
            game_config[key] = value
    config["Game"] = game_config

    # Update Logging configuration - preserve existing values
    logging_config = config.get("Logging", {})
    cloudwatch_updates = config_updates.get("CloudWatch", {})

    logging_updates = {
        "ApplicationName": logging_config.get("ApplicationName", "Eidolon Engine"),
        "LogLevel": logging_config.get("LogLevel", 20),
        "LogGroup": cloudwatch_updates.get("LogGroupName", logging_config.get("LogGroup", "/eidolon/game-logs")),
        "LogStream": logging_config.get("LogStream", "application"),
        "MetricNamespace": cloudwatch_updates.get("MetricNamespace", logging_config.get("MetricNamespace", "eidolon/application")),
    }
    logging_config.update(logging_updates)
    config["Logging"] = logging_config

    # Update Cognito configuration
    cognito_updates = config_updates.get("Cognito", {})
    cognito_config = config.get("Cognito", {})

    # Generate UserPoolDomain from UserPoolId if not explicitly provided
    user_pool_id = cognito_updates.get("UserPoolId", "")
    user_pool_domain = ""
    if user_pool_id:
        # Extract region from the UserPoolId (format: region_xxxxx)
        region_prefix = user_pool_id.split("_")[0]
        # Create domain name using the user pool name if provided
        if user_pool_name:
            user_pool_domain = f"{region_prefix}-{user_pool_name}"

    cognito_config.update(
        {
            "UserPoolId": user_pool_id,
            "UserPoolClientId": cognito_updates.get("UserPoolClientId", ""),
            "UserPoolDomain": user_pool_domain,
            "UserPoolArn": cognito_updates.get("UserPoolArn", ""),
        }
    )
    config["Cognito"] = cognito_config

    # Update Game configuration with script settings
    game_updates = config_updates.get("Game", {})
    if game_updates:
        game_config = config.get("Game", {})
        game_config.update(game_updates)
        config["Game"] = game_config

    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            yaml.dump(config, file, default_flow_style=False)
        print("Configuration file updated successfully.")
    except (IOError, yaml.YAMLError) as err:
        print(f"Error writing configuration file: {err}")
        print("Current config_updates:", config_updates)
        print("Current config:", config)


def deploy_scripts(bucket_name, prefix="scripts") -> bool:
    """
    Deploy Lua scripts to S3.
    """
    try:
        s3_client = boto3.client("s3")

        # Check if scripts directory exists
        if not os.path.exists(SCRIPTS_PATH):
            print(f"Scripts directory not found: {SCRIPTS_PATH}")
            return False

        # Find all .lua files
        lua_files = []
        for filename in os.listdir(SCRIPTS_PATH):
            if filename.endswith(".lua"):
                lua_files.append(filename)

        if not lua_files:
            print(f"No .lua files found in {SCRIPTS_PATH}")
            return True

        print(f"Found {len(lua_files)} Lua scripts to deploy")

        # Upload each script
        success_count = 0
        for filename in lua_files:
            local_path = os.path.join(SCRIPTS_PATH, filename)
            s3_key = f"{prefix}/{filename}"

            try:
                with open(local_path, "rb") as file_data:
                    s3_client.put_object(Bucket=bucket_name, Key=s3_key, Body=file_data, ContentType="text/x-lua")
                print(f"Uploaded: {filename} -> s3://{bucket_name}/{s3_key}")
                success_count += 1
            except ClientError as err:
                print(f"Failed to upload {filename}: {err}")

        print(f"Script deployment complete: {success_count}/{len(lua_files)} scripts uploaded")
        return success_count == len(lua_files)

    except Exception as err:
        print(f"Error deploying scripts: {err}")
        return False


def gather_all_parameters() -> dict:
    parameters: dict = {}

    # Cognito parameters
    parameters["cognito"] = {
        "UserPoolName": input("Enter the Name of the user pool [default: eidolon-user-pool]: ") or "eidolon-user-pool",
        "AppClientName": input("Enter the Name of the app client [default: eidolon-app-client]: ") or "eidolon-app-client",
        "ReplyEmailAddress": input("Enter the email address to send from [default: contact@darkrelics.net]: ")
        or "contact@darkrelics.net",
    }

    # DynamoDB parameters
    parameters["dynamo"] = {}

    # CloudWatch parameters
    parameters["cloudwatch"] = {
        "LogGroupName": input("Enter the name for the CloudWatch Log Group [default: /eidolon/game-logs]: ")
        or "/eidolon/game-logs",
        "MetricNamespace": input("Enter the namespace for CloudWatch Metrics [default: eidolon/application]: ")
        or "eidolon/application",
    }

    # CodeBuild parameters
    parameters["codebuild"] = {
        "GitHubSourceRepo": input(
            "Enter the GitHub repository URL for the source code [default: https://github.com/robinje/eidolon-engine]: "
        )
        or "https://github.com/robinje/eidolon-engine",
        "S3BucketName": input("Enter the name of the existing S3 bucket for build artifacts [default: mud-web-site]: ")
        or "mud-web-site",
    }

    # Scripts parameters
    parameters["scripts"] = {
        "S3BucketName": input("Enter the S3 bucket name for Lua scripts [default: mud-scripts]: ") or "mud-scripts",
        "S3Prefix": input("Enter the S3 prefix for Lua scripts [default: scripts]: ") or "scripts",
    }

    return parameters


def main() -> None:
    cloudformation_client = boto3.client("cloudformation")
    try:
        # Gather all parameters upfront
        all_parameters: dict = gather_all_parameters()

        # Validate S3 bucket
        S3_BUCKET = all_parameters["codebuild"]["S3BucketName"]
        if not validate_s3_bucket(S3_BUCKET):
            print("Invalid or inaccessible S3 bucket. Exiting...")
            return

        # Deploy Cognito stack
        cognito_template: str = load_template(COGNITO_TEMPLATE_PATH)
        if not deploy_stack(cloudformation_client, COGNITO_STACK_NAME, cognito_template, all_parameters["cognito"]):
            print("Deployment failed at Cognito stack. Exiting...")
            return

        cognito_outputs: dict = get_stack_outputs(cloudformation_client, COGNITO_STACK_NAME)

        # Deploy DynamoDB stack
        dynamo_template: str = load_template(DYNAMO_TEMPLATE_PATH)
        if not deploy_stack(cloudformation_client, DYNAMO_STACK_NAME, dynamo_template, all_parameters["dynamo"]):
            print("Deployment failed at DynamoDB stack. Exiting...")
            return

        dynamo_outputs: dict = get_stack_outputs(cloudformation_client, DYNAMO_STACK_NAME)

        # Update CodeBuild parameters with Cognito outputs
        all_parameters["codebuild"].update(
            {
                "UserPoolId": cognito_outputs.get("UserPoolId", ""),
                "ClientId": cognito_outputs.get("UserPoolClientId", ""),
            }
        )

        # Deploy CodeBuild stack
        codebuild_template: str = load_template(CODEBUILD_TEMPLATE_PATH)
        if not deploy_stack(cloudformation_client, CODEBUILD_STACK_NAME, codebuild_template, all_parameters["codebuild"]):
            print("Deployment failed at CodeBuild stack. Exiting...")
            return

        codebuild_outputs: dict = get_stack_outputs(cloudformation_client, CODEBUILD_STACK_NAME)

        # Start the 'PortalApplicationBuild' CodeBuild job
        codebuild_client = boto3.client("codebuild")
        try:
            print("Starting PortalApplicationBuild CodeBuild job...")
            build_response = codebuild_client.start_build(projectName="PortalApplicationBuild")
            print(f"Build started successfully: {build_response['build']['id']}")
        except ClientError as build_err:
            print(f"Failed to start PortalApplicationBuild CodeBuild job: {build_err}")

        # Deploy CloudWatch stack
        cloudwatch_template: str = load_template(CLOUDWATCH_TEMPLATE_PATH)
        if not deploy_stack(cloudformation_client, CLOUDWATCH_STACK_NAME, cloudwatch_template, all_parameters["cloudwatch"]):
            print("Deployment failed at CloudWatch stack. Exiting...")
            return

        cloudwatch_outputs: dict = get_stack_outputs(cloudformation_client, CLOUDWATCH_STACK_NAME)

        # Deploy Lua scripts to S3
        scripts_bucket = all_parameters["scripts"]["S3BucketName"]
        scripts_prefix = all_parameters["scripts"]["S3Prefix"]

        # Validate scripts bucket exists
        if not validate_s3_bucket(scripts_bucket):
            print(f"Invalid or inaccessible S3 bucket for scripts: {scripts_bucket}. Exiting...")
            return

        # Deploy scripts
        if not deploy_scripts(scripts_bucket, scripts_prefix):
            print("Warning: Some scripts failed to deploy, but continuing with deployment...")

        # Update configuration file with outputs from all stacks and scripts configuration
        config_updates: dict = {
            "Cognito": cognito_outputs,
            "Dynamo": dynamo_outputs,
            "CodeBuild": codebuild_outputs,
            "CloudWatch": cloudwatch_outputs,
            "Game": {
                "ScriptsS3Bucket": scripts_bucket,
                "ScriptsS3Prefix": scripts_prefix,
            },
        }
        update_configuration_file(config_updates, all_parameters["cognito"]["UserPoolName"])

        print("Deployment completed successfully.")
    except Exception as err:
        print(f"An unexpected error occurred during deployment: {err}")


if __name__ == "__main__":
    main()
