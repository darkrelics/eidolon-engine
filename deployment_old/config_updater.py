"""Configuration updater for managing deployment configuration updates."""

from state_manager import ConfigurationManager


class ConfigurationUpdater:
    """Base class for updating configuration from stack outputs."""

    def __init__(self, config_manager: ConfigurationManager):
        """Initialize the configuration updater.

        Args:
            config_manager: ConfigurationManager instance
        """
        self.config_manager = config_manager

    def update_from_stack_outputs(self, stack_name: str, outputs: dict):
        """Update configuration based on stack outputs.

        Args:
            stack_name: Name of the CloudFormation stack
            outputs: Dictionary of stack outputs
        """
        # Map stack names to update methods
        updaters = {
            "cognito": self._update_cognito_config,
            "dynamodb": self._update_dynamodb_config,
            "cloudwatch": self._update_cloudwatch_config,
            "s3": self._update_s3_config,
            "cloudfront": self._update_cloudfront_config,
            "codebuild": self._update_codebuild_config,
            "iam": self._update_iam_config,
            "lambda": self._update_lambda_config,
        }

        # Find matching updater
        for key, updater in updaters.items():
            if key in stack_name.lower():
                updater(outputs)
                break

    def _update_cognito_config(self, outputs: dict):
        """Update Cognito configuration section."""
        # Only create Cognito section if we have actual values
        if outputs.get("UserPoolId"):
            config_data = {
                "UserPoolId": outputs.get("UserPoolId", ""),
                "UserPoolClientId": outputs.get("AppClientId", ""),
                "UserPoolDomain": outputs.get("UserPoolDomain", ""),
                "UserPoolArn": outputs.get("UserPoolArn", ""),
            }
            self.config_manager.update_section("Cognito", config_data)

    def _update_dynamodb_config(self, outputs: dict):
        """Update DynamoDB configuration section."""
        # Extract table names
        tables = {}
        for key, value in outputs.items():
            if key.endswith("TableName"):
                # Convert PlayersTableName -> Players
                table_type = key.replace("TableName", "")
                tables[table_type] = value

        config_data = {"Tables": tables}
        if "DynamoDBAccessPolicyArn" in outputs:
            config_data["AccessPolicyArn"] = outputs["DynamoDBAccessPolicyArn"]

        self.config_manager.update_section("DynamoDB", config_data)

    def _update_cloudwatch_config(self, outputs: dict):
        """Update Logging configuration section."""
        # Update Logging section with log group and metrics namespace
        logging_data = {}
        if "LogGroupName" in outputs:
            logging_data["LogGroup"] = outputs["LogGroupName"]
        if "MetricsNamespace" in outputs:
            logging_data["MetricNamespace"] = outputs["MetricsNamespace"]

        if logging_data:
            self.config_manager.update_section("Logging", logging_data)

    def _update_s3_config(self, outputs: dict):
        """Update S3 bucket configuration."""
        # Update S3 section with all bucket names
        s3_data = {}
        if "PortalBucketName" in outputs:
            s3_data["PortalBucket"] = outputs["PortalBucketName"]
        if "ScriptsBucketName" in outputs:
            s3_data["ScriptsBucket"] = outputs["ScriptsBucketName"]
        if "LambdaBucketName" in outputs:
            s3_data["ArtifactsBucket"] = outputs["LambdaBucketName"]

        if s3_data:
            self.config_manager.update_section("S3", s3_data)

    def _update_cloudfront_config(self, outputs: dict):
        """Update CloudFront configuration section."""
        # Only create CloudFront section if we have actual values
        if outputs.get("DistributionId"):
            config_data = {
                "DistributionId": outputs.get("DistributionId", ""),
                "DomainName": outputs.get("DistributionDomainName", ""),
                "PortalUrl": outputs.get("PortalUrl", ""),
            }
            self.config_manager.update_section("CloudFront", config_data)

    def _update_codebuild_config(self, outputs: dict):
        """Update CodeBuild configuration section."""
        config_data = {}
        if "CodeBuildProjectName" in outputs:
            config_data["ProjectName"] = outputs["CodeBuildProjectName"]
        if "LambdaLayerProjectName" in outputs:
            config_data["LambdaLayerProjectName"] = outputs["LambdaLayerProjectName"]
        if "LambdaFunctionsProjectName" in outputs:
            config_data["LambdaFunctionsProjectName"] = outputs["LambdaFunctionsProjectName"]

        if config_data:
            self.config_manager.update_section("CodeBuild", config_data)

    def _update_iam_config(self, outputs: dict):
        """Update IAM configuration section."""
        if "ServerExecutionRoleArn" in outputs:
            aws_data = {"ServerExecutionRoleArn": outputs["ServerExecutionRoleArn"]}
            self.config_manager.update_section("AWS", aws_data)

    def _update_lambda_config(self, outputs: dict):
        """Update Lambda configuration section."""
        # Currently no specific Lambda config to update
        pass

    def update_game_config(self, game_name: str):
        """Update game configuration.

        Args:
            game_name: Name of the game
        """
        self.config_manager.update_section("Game", {"name": game_name})

    def save_configuration(self) -> str:
        """Save the configuration and return the file path.

        Returns:
            Path to the saved configuration file
        """
        self.config_manager.save_config()
        return str(self.config_manager.config_path)
