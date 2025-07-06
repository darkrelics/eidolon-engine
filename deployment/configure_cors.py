#!/usr/bin/env python3
"""
Configure CORS origins for Eidolon Engine deployments.

This script helps configure CORS origins for both MUD and Incremental
applications by updating the config.yml file.
"""

import argparse
from pathlib import Path

import yaml


def load_config(config_path: str) -> dict:
    """Load configuration from YAML file."""
    path = Path(config_path)
    if not path.exists():
        print(f"Configuration file {config_path} not found. Creating from template...")
        template_path = Path(__file__).parent / "config.yml.template"
        if template_path.exists():
            with open(template_path, "r") as f:
                config = yaml.safe_load(f)
            # Save initial config
            with open(path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            return config
        else:
            print("Template file not found. Creating minimal configuration...")
            return {}

    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def save_config(config_path: str, config: dict) -> None:
    """Save configuration to YAML file."""
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)


def configure_cors(config: dict, app_type: str, origins: list, replace: bool = False) -> dict:
    """Configure CORS origins for specified application type."""
    if "CORS" not in config:
        config["CORS"] = {}

    if app_type == "mud":
        key = "MUDOrigins"
    elif app_type == "incremental":
        key = "IncrementalOrigins"
    else:
        raise ValueError(f"Unknown application type: {app_type}")

    if replace or key not in config["CORS"]:
        config["CORS"][key] = origins
    else:
        # Add to existing origins
        existing = set(config["CORS"][key])
        existing.update(origins)
        config["CORS"][key] = list(existing)

    return config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Configure CORS origins for Eidolon Engine deployments")
    parser.add_argument("--config", default="config.yml", help="Path to configuration file (default: config.yml)")
    parser.add_argument("--type", choices=["mud", "incremental", "both"], required=True, help="Application type to configure")
    parser.add_argument("--origins", nargs="+", required=True, help="CORS origins to allow (e.g., https://darkrelics.net)")
    parser.add_argument("--replace", action="store_true", help="Replace existing origins instead of adding to them")
    parser.add_argument("--cloudfront", help="Add CloudFront distribution URL as an allowed origin")
    parser.add_argument(
        "--localhost", action="store_true", help="Add localhost origins for development (http://localhost:3000, etc.)"
    )

    args = parser.parse_args()

    # Load existing configuration
    config = load_config(args.config)

    # Prepare origins list
    origins = list(args.origins)

    # Add CloudFront origin if specified
    if args.cloudfront:
        origins.append(f"https://{args.cloudfront}")

    # Add localhost origins if specified
    if args.localhost:
        localhost_origins = [
            "http://localhost:3000",
            "http://localhost:8080",
            "http://localhost:8000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:8000",
        ]
        origins.extend(localhost_origins)

    # Remove duplicates
    origins = list(set(origins))

    # Configure CORS
    if args.type == "both":
        config = configure_cors(config, "mud", origins, args.replace)
        config = configure_cors(config, "incremental", origins, args.replace)
    else:
        config = configure_cors(config, args.type, origins, args.replace)

    # Save configuration
    save_config(args.config, config)

    # Display configured origins
    print(f"CORS origins configured for {args.type}:")
    if args.type == "both":
        print("\nMUD Origins:")
        for origin in config["CORS"]["MUDOrigins"]:
            print(f"  - {origin}")
        print("\nIncremental Origins:")
        for origin in config["CORS"]["IncrementalOrigins"]:
            print(f"  - {origin}")
    else:
        key = "MUDOrigins" if args.type == "mud" else "IncrementalOrigins"
        for origin in config["CORS"][key]:
            print(f"  - {origin}")

    print(f"\nConfiguration saved to {args.config}")
    print("\nTo deploy with these CORS settings, run:")
    print("  cdk deploy --all")


if __name__ == "__main__":
    main()
