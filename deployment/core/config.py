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
    
    def save(self, path: str = "config.yml") -> None:
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
    def load(cls, path: str = "config.yml") -> "Config":
        """Load configuration from config.yml if it exists."""
        config_path = Path(path)
        instance = cls()
        
        if not config_path.exists():
            return instance
        
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}
        
        if "AWS" in data:
            instance.region = data["AWS"].get("Region", instance.region)
        if "DynamoDB" in data:
            instance.dynamodb_tables = data["DynamoDB"].get("Tables", {})
        
        return instance