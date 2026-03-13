"""Update config.yml with values from CloudFormation stack outputs."""

from pathlib import Path

import yaml
from deployment.cloudformation import get_stack_output


def update_config_from_stacks(cf_client, config_path: str, deployment_mode: str):
    """Read stack outputs and update config.yml with infrastructure values.

    Preserves game settings, DynamoDB table names, and other static config.
    Only updates fields that come from CloudFormation stack outputs.

    Args:
        cf_client: boto3 CloudFormation client
        config_path: Path to config.yml
        deployment_mode: Current deployment mode
    """
    config_file = Path(config_path)
    with open(config_file, "r", encoding="utf-8") as fh:
        config = yaml.safe_load(fh)

    # Cognito outputs
    user_pool_id = get_stack_output(cf_client, "eidolon-cognito", "UserPoolId")
    user_pool_arn = get_stack_output(cf_client, "eidolon-cognito", "UserPoolArn")
    user_pool_client_id = get_stack_output(cf_client, "eidolon-cognito", "UserPoolClientId")

    if user_pool_id:
        config["Cognito"]["UserPoolId"] = user_pool_id
    if user_pool_arn:
        config["Cognito"]["UserPoolArn"] = user_pool_arn
    if user_pool_client_id:
        config["Cognito"]["UserPoolClientId"] = user_pool_client_id
        config["Cognito"]["ClientId"] = user_pool_client_id

    # Story outputs (conditional)
    if deployment_mode in ("incremental", "hybrid"):
        processing_url = get_stack_output(cf_client, "eidolon-lambda-story", "ProcessingQueueUrl")
        advancement_url = get_stack_output(cf_client, "eidolon-lambda-story", "AdvancementQueueUrl")
        ssm_param = get_stack_output(cf_client, "eidolon-lambda-story", "StoryConfigParameterName")

        if "Story" not in config:
            config["Story"] = {}
        if processing_url:
            config["Story"]["ProcessingQueueUrl"] = processing_url
        if advancement_url:
            config["Story"]["AdvancementQueueUrl"] = advancement_url
        if ssm_param:
            config["Story"]["SSMParameter"] = ssm_param

    # CloudWatch outputs (conditional)
    if deployment_mode in ("mud", "hybrid"):
        log_group = get_stack_output(cf_client, "eidolon-cloudwatch", "LogGroupName")
        metrics_ns = get_stack_output(cf_client, "eidolon-cloudwatch", "MetricsNamespace")

        if "CloudWatch" not in config:
            config["CloudWatch"] = {}
        if log_group:
            config["CloudWatch"]["LogGroup"] = log_group
        if metrics_ns:
            config["CloudWatch"]["MetricsNamespace"] = metrics_ns

    # Deployment mode
    config["DeploymentMode"] = deployment_mode
    if "Deployment" not in config:
        config["Deployment"] = {}
    config["Deployment"]["Mode"] = deployment_mode

    # Write updated config
    with open(config_file, "w", encoding="utf-8") as fh:
        yaml.dump(config, fh, default_flow_style=False, sort_keys=False)

    print("  Updated config.yml with stack outputs")
    updated_fields = []
    if user_pool_id:
        updated_fields.append(f"Cognito.UserPoolId={user_pool_id}")
    if user_pool_client_id:
        updated_fields.append(f"Cognito.ClientId={user_pool_client_id}")
    for field in updated_fields:
        print(f"    {field}")
