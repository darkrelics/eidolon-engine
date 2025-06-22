"""AWS CDK application for Eidolon Engine infrastructure.

This application defines all AWS resources needed for the Eidolon Engine
game server using AWS CDK for infrastructure as code.
"""

import os
from pathlib import Path

import aws_cdk as cdk
import yaml
from stacks.cloudfront_stack import CloudFrontStack
from stacks.cloudwatch_stack import CloudWatchStack
from stacks.codebuild_stack import CodeBuildStack
from stacks.cognito_stack import CognitoStack
from stacks.dynamodb_stack import DynamoDBStack
from stacks.iam_stack import IAMStack
from stacks.s3_stack import S3Stack
from state_manager import ConfigurationManager, DeploymentState


class EidolonEngineApp:
    """Main CDK application for Eidolon Engine infrastructure."""

    def __init__(self):
        """Initialize the CDK app with configuration."""
        self.app = cdk.App()
        self.config_manager = ConfigurationManager()
        self.state_manager = DeploymentState()

        # Load configuration if exists
        self.config = self.load_configuration()

        # Create stacks with dependencies
        self.create_stacks()

    def load_configuration(self) -> dict:
        """Load configuration from config.yml or use defaults."""
        if self.config_manager.exists():
            return self.config_manager.config
        else:
            # Load from template if no config exists
            template_path = Path(__file__).parent.parent / "config.yml.template"
            if template_path.exists():
                with open(template_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            return {}

    def create_stacks(self):
        """Create all CDK stacks with proper dependencies."""
        env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))

        # Get deployment parameters
        params = self.get_deployment_parameters()

        # Create Cognito stack
        self.cognito_stack = CognitoStack(
            self.app,
            "cognito",
            game_name=params["game_name"],
            contact_email=params["contact_email"],
            env=env,
        )

        # Create DynamoDB stack
        self.dynamodb_stack = DynamoDBStack(
            self.app, "dynamodb", game_name=params["game_name"], table_names=params.get("dynamodb_tables"), env=env
        )

        # Create CloudWatch stack
        self.cloudwatch_stack = CloudWatchStack(
            self.app,
            "cloudwatch",
            dynamodb_policy_arn=self.dynamodb_stack.access_policy.managed_policy_arn,
            retention_days=params.get("log_retention_days", 365),
            env=env,
        )

        # Create IAM stack with server execution role
        self.iam_stack = IAMStack(
            self.app,
            "iam",
            game_name=params["game_name"],
            cloudwatch_policy_arn=self.cloudwatch_stack.access_policy.managed_policy_arn,
            dynamodb_policy_arn=self.dynamodb_stack.access_policy.managed_policy_arn,
            env=env,
        )
        self.iam_stack.add_dependency(self.cloudwatch_stack)
        self.iam_stack.add_dependency(self.dynamodb_stack)

        # Create S3 stack (handles existing buckets)
        self.s3_stack = S3Stack(
            self.app,
            "s3",
            game_name=params["game_name"],
            portal_bucket_name=params.get("portal_bucket_name"),
            scripts_bucket_name=params.get("scripts_bucket_name"),
            env=env,
        )

        # Create CloudFront stack for portal distribution
        self.cloudfront_stack = CloudFrontStack(
            self.app,
            "cloudfront",
            game_name=params["game_name"],
            portal_bucket=self.s3_stack.portal_bucket,
            existing_distribution_id=params.get("cloudfront_distribution_id"),
            env=env,
        )
        self.cloudfront_stack.add_dependency(self.s3_stack)

        # Create CodeBuild stack with dependencies
        self.codebuild_stack = CodeBuildStack(
            self.app,
            "codebuild",
            game_name=params["game_name"],
            github_owner=params["github_owner"],
            github_repo=params["github_repo"],
            github_branch=params.get("github_branch", "main"),
            cognito_user_pool_id=self.cognito_stack.user_pool.user_pool_id,
            cognito_app_client_id=self.cognito_stack.app_client.user_pool_client_id,
            portal_bucket=self.s3_stack.portal_bucket,
            buildspec_path=params.get("portal_buildspec_path", "buildspec/portal.yml"),
            cloudfront_distribution_id=self.cloudfront_stack.distribution.distribution_id,
            env=env,
        )
        self.codebuild_stack.add_dependency(self.cognito_stack)
        self.codebuild_stack.add_dependency(self.s3_stack)
        self.codebuild_stack.add_dependency(self.cloudfront_stack)

    def get_deployment_parameters(self) -> dict:
        """Get deployment parameters from config or state."""
        # Start with defaults
        params = {
            "game_name": "eidolon-engine",
            "contact_email": "admin@example.com",
            "github_owner": "robinje",
            "github_repo": "eidolon-engine",
            "github_branch": "main",
            "log_retention_days": 365,
        }

        # Override with stored parameters
        stored_params = self.state_manager.get_parameters()
        params.update(stored_params)

        # Override with config values
        if "Game" in self.config:
            game_config = self.config["Game"]
            params["game_name"] = game_config.get("name", params["game_name"])

            # Check for existing bucket configurations
            if "PortalS3Bucket" in game_config:
                params["portal_bucket_name"] = game_config["PortalS3Bucket"]
            if "ScriptsS3Bucket" in game_config:
                params["scripts_bucket_name"] = game_config["ScriptsS3Bucket"]

        # Check for existing DynamoDB table configurations
        if "DynamoDB" in self.config and "Tables" in self.config["DynamoDB"]:
            params["dynamodb_tables"] = self.config["DynamoDB"]["Tables"]

        # Check for CodeBuild configuration
        if "CodeBuild" in self.config:
            codebuild_config = self.config["CodeBuild"]
            if "PortalBuildspecPath" in codebuild_config:
                params["portal_buildspec_path"] = codebuild_config["PortalBuildspecPath"]

        return params

    def synth(self):
        """Synthesize the CDK app."""
        return self.app.synth()


def main():
    """Main entry point for CDK app."""
    app = EidolonEngineApp()
    app.synth()


if __name__ == "__main__":
    main()
