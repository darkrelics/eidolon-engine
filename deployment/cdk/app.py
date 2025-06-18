"""AWS CDK application for Eidolon Engine infrastructure.

This application defines all AWS resources needed for the Eidolon Engine
game server using AWS CDK for infrastructure as code.
"""

import os
import sys
from pathlib import Path

import aws_cdk as cdk
import yaml

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from cdk.stacks.cognito_stack import CognitoStack
from cdk.stacks.dynamodb_stack import DynamoDBStack
from cdk.stacks.cloudwatch_stack import CloudWatchStack
from cdk.stacks.codebuild_stack import CodeBuildStack
from cdk.stacks.s3_stack import S3Stack
from cdk.stacks.cloudfront_stack import CloudFrontStack
from state_manager import ConfigurationManager, DeploymentState


class EidolonEngineApp:
    """Main CDK application for Eidolon Engine infrastructure."""

    def __init__(self):
        """Initialize the CDK app with configuration."""
        self.app = cdk.App()
        self.config_manager = ConfigurationManager()
        self.state_manager = DeploymentState()

        # Load configuration if exists
        self.config = self._load_configuration()

        # Create stacks with dependencies
        self._create_stacks()

    def _load_configuration(self) -> dict:
        """Load configuration from server/config.yml or use defaults."""
        if self.config_manager.exists():
            return self.config_manager.config
        else:
            # Load from template if no config exists
            template_path = Path(__file__).parent.parent / "config.yml.template"
            if template_path.exists():
                with open(template_path, "r") as f:
                    return yaml.safe_load(f) or {}
            return {}

    def _create_stacks(self):
        """Create all CDK stacks with proper dependencies."""
        env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION", "us-east-1"))

        # Get deployment parameters
        params = self._get_deployment_parameters()

        # Create Cognito stack
        self.cognito_stack = CognitoStack(
            self.app,
            f"{params['game_name']}-cognito",
            game_name=params["game_name"],
            contact_email=params["contact_email"],
            env=env,
        )

        # Create DynamoDB stack
        self.dynamodb_stack = DynamoDBStack(self.app, f"{params['game_name']}-dynamodb", game_name=params["game_name"], env=env)

        # Create CloudWatch stack
        self.cloudwatch_stack = CloudWatchStack(
            self.app,
            f"{params['game_name']}-cloudwatch",
            game_name=params["game_name"],
            retention_days=params.get("log_retention_days", 365),
            env=env,
        )

        # Create S3 stack (handles existing buckets)
        self.s3_stack = S3Stack(
            self.app,
            f"{params['game_name']}-s3",
            game_name=params["game_name"],
            portal_bucket_name=params.get("portal_bucket_name"),
            scripts_bucket_name=params.get("scripts_bucket_name"),
            env=env,
        )

        # Create CloudFront stack for portal distribution
        self.cloudfront_stack = CloudFrontStack(
            self.app,
            f"{params['game_name']}-cloudfront",
            game_name=params["game_name"],
            portal_bucket=self.s3_stack.portal_bucket,
            existing_distribution_id=params.get("cloudfront_distribution_id"),
            env=env,
        )
        self.cloudfront_stack.add_dependency(self.s3_stack)

        # Create CodeBuild stack with dependencies
        self.codebuild_stack = CodeBuildStack(
            self.app,
            f"{params['game_name']}-codebuild",
            game_name=params["game_name"],
            github_owner=params["github_owner"],
            github_repo=params["github_repo"],
            github_branch=params.get("github_branch", "main"),
            cognito_user_pool_id=self.cognito_stack.user_pool.user_pool_id,
            cognito_app_client_id=self.cognito_stack.app_client.user_pool_client_id,
            portal_bucket=self.s3_stack.portal_bucket,
            cloudfront_distribution_id=self.cloudfront_stack.distribution.distribution_id,
            env=env,
        )
        self.codebuild_stack.add_dependency(self.cognito_stack)
        self.codebuild_stack.add_dependency(self.s3_stack)
        self.codebuild_stack.add_dependency(self.cloudfront_stack)

    def _get_deployment_parameters(self) -> dict:
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
