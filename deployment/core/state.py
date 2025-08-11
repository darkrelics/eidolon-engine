"""CDK state management for tracking deployment progress."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class CDKState:
    """Tracks CDK deployment state and infrastructure details."""
    
    # Stack deployment status
    stacks: dict = field(default_factory=dict)
    
    # Infrastructure resources (not in config.yml)
    infrastructure: dict = field(default_factory=dict)
    
    # Last update timestamp
    last_updated: str = ""
    
    def mark_stack_deployed(self, stack_name: str, outputs: dict) -> None:
        """Mark a stack as successfully deployed."""
        self.stacks[stack_name] = {
            "deployed": True,
            "timestamp": datetime.now().isoformat(),
            "outputs": outputs
        }
        self.last_updated = datetime.now().isoformat()
    
    def save(self, path: str) -> None:
        """Save state to JSON file."""
        state_path = Path(path)
        state_data = {
            "stacks": self.stacks,
            "infrastructure": self.infrastructure,
            "last_updated": self.last_updated
        }
        
        with open(state_path, "w") as f:
            json.dump(state_data, f, indent=2)
    
    @classmethod
    def load(cls, path: str) -> "CDKState":
        """Load state from JSON file if it exists."""
        state_path = Path(path)
        instance = cls()
        
        if not state_path.exists():
            return instance
        
        with open(state_path, "r") as f:
            data = json.load(f)
        
        instance.stacks = data.get("stacks", {})
        instance.infrastructure = data.get("infrastructure", {})
        instance.last_updated = data.get("last_updated", "")
        
        return instance