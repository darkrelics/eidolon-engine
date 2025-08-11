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
    
    def save(self, path: str) -> None:
        """Save operational configuration to config.yml."""
        config_path = Path(path)
        
        # Load existing config if it exists
        existing_config = {}
        if config_path.exists():
            with open(config_path, "r") as f:
                existing_config = yaml.safe_load(f) or {}
        
        # Update only DynamoDB section
        existing_config["DynamoDB"] = {
            "Tables": self.dynamodb_tables
        }
        
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
        
        return instance