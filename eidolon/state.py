"""Infrastructure state management for incremental deployments.

This module tracks deployed resources, their configurations, and deployment history
to enable incremental updates and configuration drift detection.
"""

import json
from datetime import datetime
from pathlib import Path

import yaml


class DeploymentState:
    """Represents the current state of deployed infrastructure."""

    def __init__(self, state_file: str = ".deployment_state.json"):
        """Initialize deployment state manager.

        Args:
            state_file: Path to state file for persistence
        """
        self.state_file = Path(state_file)
        self.state: dict = self._load_state()

    def _load_state(self) -> dict:
        """Load state from file or create new state."""
        if self.state_file.exists():
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {
            "version": "1.0",
            "last_deployment": None,
            "stacks": {},
            "resources": {},
            "parameters": {},
            "deployment_history": [],
        }

    def save_state(self) -> None:
        """Persist current state to file."""
        self.state["last_deployment"] = datetime.now().isoformat()
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, default=str)

    def add_stack(self, stack_name: str, stack_info: dict) -> None:
        """Record CloudFormation stack deployment.

        Args:
            stack_name: Name of the CloudFormation stack
            stack_info: Stack metadata including outputs, parameters, etc.
        """
        self.state["stacks"][stack_name] = {
            "deployed_at": datetime.now().isoformat(),
            "stack_id": stack_info.get("stack_id"),
            "outputs": stack_info.get("outputs", {}),
            "parameters": stack_info.get("parameters", {}),
            "template_hash": stack_info.get("template_hash"),
            "status": stack_info.get("status", "CREATE_COMPLETE"),
        }

    def get_stack(self, stack_name: str) -> dict:
        """Get information about a deployed stack.

        Args:
            stack_name: Name of the CloudFormation stack

        Returns:
            Stack information if exists, empty dict otherwise
        """
        return self.state["stacks"].get(stack_name, {})

    def add_resource(self, resource_type: str, resource_id: str, resource_info: dict) -> None:
        """Track individual AWS resource.

        Args:
            resource_type: AWS resource type (e.g., 'dynamodb_table')
            resource_id: Unique identifier for the resource
            resource_info: Resource metadata and configuration
        """
        if resource_type not in self.state["resources"]:
            self.state["resources"][resource_type] = {}

        self.state["resources"][resource_type][resource_id] = {
            "created_at": datetime.now().isoformat(),
            "configuration": resource_info.get("configuration", {}),
            "stack_name": resource_info.get("stack_name"),
            "physical_id": resource_info.get("physical_id"),
        }

    def get_resource(self, resource_type: str, resource_id: str) -> dict:
        """Get information about a deployed resource.

        Args:
            resource_type: AWS resource type
            resource_id: Resource identifier

        Returns:
            Resource information if exists, empty dict otherwise
        """
        return self.state["resources"].get(resource_type, {}).get(resource_id, {})

    def update_parameters(self, parameters: dict) -> None:
        """Update deployment parameters.

        Args:
            parameters: Dictionary of parameter key-value pairs
        """
        self.state["parameters"].update(parameters)

    def get_parameters(self) -> dict:
        """Get all stored deployment parameters.

        Returns:
            Copy of parameters dictionary
        """
        return self.state["parameters"].copy()

    def add_deployment_event(self, event_type: str, event_data: dict) -> None:
        """Add entry to deployment history.

        Args:
            event_type: Type of deployment event
            event_data: Event details
        """
        self.state["deployment_history"].append(
            {"timestamp": datetime.now().isoformat(), "event_type": event_type, "data": event_data}
        )

        # Keep only last 100 events
        if len(self.state["deployment_history"]) > 100:
            self.state["deployment_history"] = self.state["deployment_history"][-100:]

    def get_deployed_stacks(self) -> set:
        """Get set of all deployed stack names.

        Returns:
            Set of stack names
        """
        return set(self.state["stacks"].keys())

    def get_deployment_summary(self) -> dict:
        """Get summary of current deployment state.

        Returns:
            Dict containing:
                - last_deployment: ISO timestamp of last deployment
                - deployed_stacks: List of deployed stack names
                - total_resources: Total count of all resources
                - parameter_count: Number of stored parameters
        """
        return {
            "last_deployment": self.state["last_deployment"],
            "deployed_stacks": list(self.get_deployed_stacks()),
            "total_resources": sum(len(resources) for resources in self.state["resources"].values()),
            "parameter_count": len(self.state["parameters"]),
        }


class ConfigurationManager:
    """Manages server configuration file operations."""

    def __init__(self, config_path: str = "../config.yml"):
        """Initialize configuration manager.

        Args:
            config_path: Path to server configuration file
        """
        self.config_path = Path(config_path)
        self.config: dict = self._load_config()

    def _load_config(self) -> dict:
        """Load configuration from file."""
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def save_config(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

    def update_section(self, section: str, values: dict) -> None:
        """Update a configuration section.

        Args:
            section: Configuration section name
            values: Values to update in the section
        """
        if section not in self.config:
            self.config[section] = {}
        self.config[section].update(values)

    def get_section(self, section: str) -> dict:
        """Get a configuration section.

        Args:
            section: Configuration section name

        Returns:
            Section configuration or empty dict
        """
        return self.config.get(section, {})

    def exists(self) -> bool:
        """Check if configuration file exists.

        Returns:
            True if config file exists, False otherwise
        """
        return self.config_path.exists()

    def get_aws_config(self) -> dict:
        """Get AWS-specific configuration.

        Returns:
            AWS configuration section, empty dict if not found
        """
        return self.config.get("AWS", {})

    def merge_with_template(self, template_path: str) -> None:
        """Merge current config with template, preserving existing values.

        Args:
            template_path: Path to configuration template
        """
        if Path(template_path).exists():
            with open(template_path, "r", encoding="utf-8") as f:
                template = yaml.safe_load(f) or {}

            # Deep merge template with existing config
            self._deep_merge(template, self.config)
            self.config = template

    def _deep_merge(self, base: dict, override: dict) -> None:
        """Deep merge override dict into base dict.

        Recursively merges nested dictionaries, with values from override
        taking precedence. Non-dict values are replaced entirely.

        Args:
            base: Base dictionary to merge into (modified in place)
            override: Dictionary with values to override
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
