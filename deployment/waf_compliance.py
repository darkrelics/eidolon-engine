"""
WAF Compliance Checker.

Validates deployed WAF configurations match YAML definitions.
"""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError

from deployment.stacks.waf_config import load_waf_config


def get_waf_client(scope: str) -> tuple:
    """
    Get appropriate WAF client based on scope.

    Args:
        scope: "CLOUDFRONT" or "REGIONAL"

    Returns:
        Tuple of (wafv2_client, scope_string)
    """
    if scope == "CLOUDFRONT":
        # CloudFront WAF must use us-east-1
        client = boto3.client("wafv2", region_name="us-east-1")
    else:
        # Regional WAF uses current region
        client = boto3.client("wafv2")

    return client, scope


def get_deployed_web_acl(web_acl_name: str, scope: str) -> dict:
    """
    Get deployed Web ACL configuration from AWS.

    Args:
        web_acl_name: Name of Web ACL
        scope: "CLOUDFRONT" or "REGIONAL"

    Returns:
        Web ACL configuration dict. Empty dict if not found.
    """
    client, scope_str = get_waf_client(scope)

    try:
        # List all Web ACLs
        response = client.list_web_acls(Scope=scope_str)
        web_acls = response.get("WebACLs", [])

        # Find matching Web ACL
        for acl in web_acls:
            if acl.get("Name") == web_acl_name:
                # Get full details
                acl_id = acl.get("Id")
                detail_response = client.get_web_acl(Scope=scope_str, Id=acl_id, Name=web_acl_name)
                return detail_response.get("WebACL", {})

        return {}

    except ClientError as err:
        print(f"[ERROR] Failed to get Web ACL {web_acl_name}: {err}")
        return {}


def compare_rules(deployed_rules: list, config_rules: list) -> list:
    """
    Compare deployed rules with configuration.

    Args:
        deployed_rules: List of deployed rule dicts
        config_rules: List of configured rule dicts from YAML

    Returns:
        List of difference strings
    """
    differences = []

    # Create maps by rule name
    deployed_map = {rule.get("Name"): rule for rule in deployed_rules}
    config_map = {rule.get("name"): rule for rule in config_rules if rule.get("enabled", True)}

    # Check for missing rules in deployment
    for rule_name in config_map:
        if rule_name not in deployed_map:
            differences.append(f"Missing rule in deployment: {rule_name}")

    # Check for extra rules in deployment
    for rule_name in deployed_map:
        if rule_name not in config_map:
            differences.append(f"Extra rule in deployment: {rule_name}")

    # Check rule priorities match
    for rule_name in config_map:
        if rule_name in deployed_map:
            config_priority = config_map[rule_name].get("priority")
            deployed_priority = deployed_map[rule_name].get("Priority")
            if config_priority != deployed_priority:
                differences.append(f"Priority mismatch for {rule_name}: " f"config={config_priority}, deployed={deployed_priority}")

    return differences


def check_waf_compliance(web_acl_name: str, yaml_path: str, scope: str) -> dict:
    """
    Check WAF compliance between deployed and configured.

    Args:
        web_acl_name: Name of deployed Web ACL
        yaml_path: Path to YAML configuration
        scope: "CLOUDFRONT" or "REGIONAL"

    Returns:
        Dict with compliance results:
        {
            "compliant": bool,
            "differences": list,
            "deployed": dict,
            "configured": dict
        }
    """
    # Load configuration
    try:
        config = load_waf_config(yaml_path)
    except Exception as err:
        return {
            "compliant": False,
            "differences": [f"Failed to load config: {err}"],
            "deployed": None,
            "configured": None,
        }

    # Get deployed Web ACL
    deployed = get_deployed_web_acl(web_acl_name, scope)
    if not deployed:
        return {
            "compliant": False,
            "differences": [f"Web ACL not found in AWS: {web_acl_name}"],
            "deployed": None,
            "configured": config,
        }

    # Compare rules
    deployed_rules = deployed.get("Rules", [])
    config_rules = config.get("rules", [])
    differences = compare_rules(deployed_rules, config_rules)

    # Check default action
    deployed_default = deployed.get("DefaultAction", {})
    config_default = config.get("default_action", "allow")
    if "Allow" in deployed_default and config_default != "allow":
        differences.append("Default action mismatch: deployed=allow, config=block")
    elif "Block" in deployed_default and config_default != "block":
        differences.append("Default action mismatch: deployed=block, config=allow")

    return {
        "compliant": len(differences) == 0,
        "differences": differences,
        "deployed": deployed,
        "configured": config,
    }


def check_all_wafs() -> dict:
    """
    Check compliance for all WAF configurations.

    Returns:
        Dict mapping WAF name to compliance results
    """
    waf_configs = [
        ("EidolonCloudFrontWebACL", "waf/cloudfront-cdn.yml", "CLOUDFRONT"),
        ("EidolonApiGatewayWebACL", "waf/api-gateway.yml", "REGIONAL"),
        ("EidolonCognitoWebACL", "waf/cognito.yml", "REGIONAL"),
    ]

    results = {}
    for name, yaml_path, scope in waf_configs:
        print(f"\n[CHECK] {name} ({scope})")
        result = check_waf_compliance(name, yaml_path, scope)
        results[name] = result

        if result["compliant"]:
            print("[OK] Compliant")
        else:
            print("[WARNING] Not compliant:")
            for diff in result["differences"]:
                print(f"  - {diff}")

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Check WAF compliance")
    parser.add_argument("--check-all", action="store_true", help="Check all WAF configurations")
    parser.add_argument("--name", help="Web ACL name to check")
    parser.add_argument("--config", help="Path to YAML config file")
    parser.add_argument("--scope", choices=["CLOUDFRONT", "REGIONAL"], help="WAF scope")

    args = parser.parse_args()

    if args.check_all:
        results = check_all_wafs()
        # Exit with error if any non-compliant
        if any(not r["compliant"] for r in results.values()):
            sys.exit(1)
    elif args.name and args.config and args.scope:
        result = check_waf_compliance(args.name, args.config, args.scope)
        if not result["compliant"]:
            print(f"[ERROR] {args.name} not compliant:")
            for diff in result["differences"]:
                print(f"  - {diff}")
            sys.exit(1)
        else:
            print(f"[OK] {args.name} compliant")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
