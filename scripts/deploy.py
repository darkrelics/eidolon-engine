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
CONFIG_PATH = "../server/config.yml"
CONFIG_TEMPLATE_PATH = "../server/config.template.yml"
ENV_FILE_PATH = "../portal/.env"


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


def update_configuration_file(config_updates) -> None:
    try:
        config: dict = load_config()

        # Ensure top-level keys exist
        for key in ["Server", "AWS", "Cognito", "Game", "Logging"]:
            if key not in config or config[key] is None:
                config[key] = {}

        # Update AWS configuration
        config["AWS"]["Region"] = "us-east-1"

        # Update Game configuration
        config["Game"].update(
            {
                "Balance": 0.25,
                "AutoSave": 5,
                "StartingHealth": 10,
                "StartingEssence": 3,
            }
        )

        # Update Logging configuration
        config["Logging"].update(
            {
                "ApplicationName": "Eidolon Engine",
                "LogLevel": 20,
                "LogGroup": config_updates.get("CloudWatch", {}).get("LogGroupName", "/eidolon/game-logs"),
                "LogStream": "application",
                "MetricNamespace": config_updates.get("CloudWatch", {}).get("MetricNamespace", "eidolon/application"),
            }
        )

        # Update Cognito configuration
        cognito_updates = config_updates.get("Cognito", {})
        config["Cognito"].update(
            {
                "UserPoolId": cognito_updates.get("UserPoolId", ""),
                "UserPoolClientSecret": cognito_updates.get("UserPoolClientSecret", ""),
                "UserPoolClientId": cognito_updates.get("UserPoolClientId", ""),
                "UserPoolDomain": cognito_updates.get("UserPoolDomain", ""),
                "UserPoolArn": cognito_updates.get("UserPoolArn", ""),
            }
        )

        with open(CONFIG_PATH, "w", encoding="utf-8") as file:
            yaml.dump(config, file, default_flow_style=False)

        print("Configuration file updated successfully.")
    except (IOError, yaml.YAMLError) as err:
        print(f"Error updating configuration file: {err}")
        print("Current config_updates:", config_updates)
        print("Current config:", config)


def generate_env_file(config_updates) -> None:
    """
    Generate a .env file for local Flutter development based on deployed resources.
    """
    try:
        cognito_updates = config_updates.get("Cognito", {})

        # Create content for .env file
        env_content = f"""# Eidolon Engine local development configuration
        # DO NOT COMMIT THIS FILE TO VERSION CONTROL

        USER_POOL_ID={cognito_updates.get("UserPoolId", "")}
        CLIENT_ID={cognito_updates.get("UserPoolClientId", "")}
        CLIENT_SECRET={cognito_updates.get("UserPoolClientSecret", "")}
        """

        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(ENV_FILE_PATH), exist_ok=True)

        # Write .env file
        with open(ENV_FILE_PATH, "w", encoding="utf-8") as env_file:
            env_file.write(env_content)

        print(f"Generated .env file at {ENV_FILE_PATH}")

    except IOError as err:
        print(f"Error generating .env file: {err}")


def gather_all_parameters() -> dict:
    parameters: dict = {}

    # Cognito parameters
    parameters["cognito"] = {
        "UserPoolName": input("Enter the Name of the user pool [default: eidolon-user-pool]: ") or "eidolon-user-pool",
        "AppClientName": input("Enter the Name of the app client [default: eidolon-app-client]: ") or "eidolon-app-client",
        "CallbackURL": input("Enter the URL of the callback for the app client [default: https://localhost:3000/callback]: ")
        or "https://localhost:3000/callback",
        "SignOutURL": input("Enter the URL of the sign-out page for the app client [default: https://localhost:3000/sign-out]: ")
        or "https://localhost:3000/sign-out",
        "ReplyEmailAddress": input("Enter the email address to send from [default: contact@darkrelics.net]: ")
        or "contact@darkrelics.net",
    }

    # DynamoDB parameters (empty for now)
    parameters["dynamo"] = {}

    # CodeBuild parameters
    parameters["codebuild"] = {
        "GitHubSourceRepo": input(
            "Enter the GitHub repository URL for the source code [default: https://github.com/robinje/eidolon-engine]: "
        )
        or "https://github.com/robinje/eidolon-engine",
        "S3BucketName": input("Enter the name of the existing S3 bucket for build artifacts: "),
    }

    # CloudWatch parameters
    parameters["cloudwatch"] = {
        "LogGroupName": input("Enter the name for the CloudWatch Log Group [default: /eidolon/game-logs]: ")
        or "/eidolon/game-logs",
        "MetricNamespace": input("Enter the namespace for CloudWatch Metrics [default: eidolon/application]: ")
        or "eidolon/application",
    }

    return parameters


def main() -> None:
    cloudformation_client = boto3.client("cloudformation")
    try:
        # Gather all parameters upfront
        all_parameters: dict = gather_all_parameters()

        # Validate S3 bucket
        s3_bucket_name = all_parameters["codebuild"]["S3BucketName"]
        if not validate_s3_bucket(s3_bucket_name):
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
                "ClientSecret": cognito_outputs.get("UserPoolClientSecret", ""),
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

        # Update configuration file with outputs from all stacks
        config_updates: dict = {
            "Cognito": cognito_outputs,
            "Dynamo": dynamo_outputs,
            "CodeBuild": codebuild_outputs,
            "CloudWatch": cloudwatch_outputs,
        }
        update_configuration_file(config_updates)

        # Generate .env file for local Flutter development
        generate_env_file(config_updates)

        print("Deployment completed successfully.")
    except Exception as err:
        print(f"An unexpected error occurred during deployment: {err}")


if __name__ == "__main__":
    main()
