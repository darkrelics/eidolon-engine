"""Configuration management for deployment."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Config:
    """Deployment configuration - only operational information."""
    
    # Region for deployment
    region: str = "us-east-1"
    
    # Table name mappings (logical to physical)
    dynamodb_tables: dict = field(default_factory=dict)
    
    # S3 buckets
    s3_artifacts_bucket: str = ""
    s3_scripts_bucket: str = ""
    
    # CloudWatch settings
    cloudwatch_log_group: str = "/eidolon/server"
    cloudwatch_metrics_namespace: str = "eidolon/metrics"
    
    def save(self, path: str) -> None:
        """Save operational configuration to config.yml."""
        config_path = Path(path)
        
        # Load existing config if it exists
        existing_config = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                existing_config = yaml.safe_load(f) or {}
        
        # Update DynamoDB section
        existing_config["DynamoDB"] = {
            "Tables": self.dynamodb_tables
        }
        
        # Update S3 section if buckets are set
        if self.s3_artifacts_bucket or self.s3_scripts_bucket:
            if "S3" not in existing_config:
                existing_config["S3"] = {}
            if self.s3_artifacts_bucket:
                existing_config["S3"]["ArtifactsBucket"] = self.s3_artifacts_bucket
            if self.s3_scripts_bucket:
                existing_config["S3"]["ScriptsBucket"] = self.s3_scripts_bucket
        
        # Update CloudWatch section if settings are set
        if self.cloudwatch_log_group or self.cloudwatch_metrics_namespace:
            if "CloudWatch" not in existing_config:
                existing_config["CloudWatch"] = {}
            if self.cloudwatch_log_group:
                existing_config["CloudWatch"]["LogGroup"] = self.cloudwatch_log_group
            if self.cloudwatch_metrics_namespace:
                existing_config["CloudWatch"]["MetricsNamespace"] = self.cloudwatch_metrics_namespace
        
        with open(config_path, "w") as f:
            yaml.dump(existing_config, f, default_flow_style=False, sort_keys=False)
    
    @classmethod
    def load(cls, path: str) -> "Config":
        """Load configuration from config.yml, creating from template if needed."""
        config_path = Path(path)
        instance = cls()
        
        # If config.yml doesn't exist, copy from template
        if not config_path.exists():
            template_path = config_path.parent / "config.template.yml"
            if template_path.exists():
                print(f"Creating config.yml from template...")
                with open(template_path, "r") as template_file:
                    template_data = template_file.read()
                with open(config_path, "w") as config_file:
                    config_file.write(template_data)
                print(f"Config file created at {config_path}")
            else:
                # No template, return defaults
                return instance
        
        # Load the config file
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        if "AWS" in data:
            instance.region = data.get("AWS", {}).get("Region", instance.region)
        if "DynamoDB" in data:
            instance.dynamodb_tables = data.get("DynamoDB", {}).get("Tables", {})
        if "S3" in data:
            instance.s3_artifacts_bucket = data.get("S3", {}).get("ArtifactsBucket", "")
            instance.s3_scripts_bucket = data.get("S3", {}).get("ScriptsBucket", "")
        if "CloudWatch" in data:
            instance.cloudwatch_log_group = data.get("CloudWatch", {}).get("LogGroup", instance.cloudwatch_log_group)
            instance.cloudwatch_metrics_namespace = data.get("CloudWatch", {}).get("MetricsNamespace", instance.cloudwatch_metrics_namespace)
        
        return instance