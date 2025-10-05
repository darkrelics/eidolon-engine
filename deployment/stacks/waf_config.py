"""
WAF Configuration Utility.

Provides functions to load WAF configurations from YAML and create CDK Web ACLs.
"""

from pathlib import Path

import aws_cdk.aws_wafv2 as wafv2
import yaml


def load_waf_config(yaml_path: str) -> dict:
    """
    Load WAF configuration from YAML file.

    Args:
        yaml_path: Path to WAF YAML config file (relative to project root)

    Returns:
        Dictionary containing WAF configuration

    Raises:
        FileNotFoundError: If YAML file doesn't exist
        ValueError: If YAML is malformed or invalid
        RuntimeError: If file read fails
    """
    try:
        # Resolve path relative to project root (parent of deployment/)
        project_root = Path(__file__).parent.parent.parent
        config_file = project_root / yaml_path

        if not config_file.exists():
            raise FileNotFoundError(
                f"\n"
                f"WAF Configuration Error:\n"
                f"  File not found: {yaml_path}\n"
                f"  Resolved path: {config_file}\n"
                f"  Expected location: {project_root}/waf/\n"
                f"\n"
                f"Please ensure WAF configuration files exist in the waf/ directory."
            )

        with open(config_file, encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Validate config structure
        if not isinstance(config, dict):
            raise ValueError(
                f"\n"
                f"WAF Configuration Error:\n"
                f"  File: {yaml_path}\n"
                f"  Issue: Configuration must be a YAML dictionary\n"
                f"  Got: {type(config).__name__}"
            )

        if "name" not in config:
            raise ValueError(
                f"\n"
                f"WAF Configuration Error:\n"
                f"  File: {yaml_path}\n"
                f"  Issue: Missing required 'name' field\n"
                f"  Please add a 'name' field to the WAF configuration."
            )

        return config

    except FileNotFoundError:
        raise  # Re-raise with our custom message
    except yaml.YAMLError as e:
        raise ValueError(
            f"\n"
            f"WAF Configuration Error:\n"
            f"  File: {yaml_path}\n"
            f"  Issue: Invalid YAML syntax\n"
            f"  Details: {str(e)}\n"
            f"\n"
            f"Please check the YAML syntax in the configuration file."
        ) from e
    except PermissionError as e:
        raise RuntimeError(
            f"\n"
            f"WAF Configuration Error:\n"
            f"  File: {yaml_path}\n"
            f"  Issue: Permission denied\n"
            f"  Details: {str(e)}\n"
            f"\n"
            f"Please check file permissions."
        ) from e
    except Exception as e:
        raise RuntimeError(
            f"\n"
            f"WAF Configuration Error:\n"
            f"  File: {yaml_path}\n"
            f"  Issue: Unexpected error reading configuration\n"
            f"  Details: {str(e)}\n"
        ) from e


def create_rate_based_rule(rule_config: dict) -> dict:
    """
    Create rate-based rule statement from config.

    Args:
        rule_config: Rule configuration dict

    Returns:
        CDK-compatible rate-based rule statement
    """
    statement = rule_config.get("statement", {}).get("rate_based", {})

    rate_statement = {
        "limit": statement.get("limit"),
        "aggregateKeyType": statement.get("aggregate_key_type", "IP"),
    }

    # Add custom keys if present
    custom_keys = statement.get("custom_keys")
    if custom_keys:
        rate_statement["customKeys"] = []
        for key in custom_keys:
            if "header" in key:
                # AWS WAF requires textTransformations for header custom keys
                rate_statement["customKeys"].append({
                    "header": {
                        "name": key["header"]["name"],
                        "textTransformations": [
                            {"priority": 0, "type": "NONE"}
                        ]
                    }
                })

    # Add scope down statement if present
    scope_down = statement.get("scope_down_statement")
    if scope_down:
        rate_statement["scopeDownStatement"] = create_statement(scope_down)

    return {"rateBasedStatement": rate_statement}


def create_managed_rule_group_statement(rule_config: dict) -> dict:
    """
    Create managed rule group statement from config.

    Args:
        rule_config: Rule configuration dict

    Returns:
        CDK-compatible managed rule group statement
    """
    statement = rule_config.get("statement", {}).get("managed_rule_group", {})

    return {
        "managedRuleGroupStatement": {
            "vendorName": statement.get("vendor_name"),
            "name": statement.get("name"),
            "excludedRules": [
                {"name": rule} for rule in statement.get("excluded_rules", [])
            ],
        }
    }


def create_size_constraint_statement(rule_config: dict) -> dict:
    """
    Create size constraint statement from config.

    Args:
        rule_config: Rule configuration dict

    Returns:
        CDK-compatible size constraint statement
    """
    statement = rule_config.get("statement", {}).get("size_constraint", {})

    field_to_match = {}
    field = statement.get("field")
    if field == "body":
        field_to_match = {"body": {"oversizeHandling": "CONTINUE"}}
    elif field == "uri_path":
        field_to_match = {"uriPath": {}}

    return {
        "sizeConstraintStatement": {
            "fieldToMatch": field_to_match,
            "comparisonOperator": statement.get("comparison_operator"),
            "size": statement.get("size"),
            "textTransformations": [
                {"priority": 0, "type": statement.get("text_transformation", "NONE")}
            ],
        }
    }


def create_byte_match_statement(rule_config: dict) -> dict:
    """
    Create byte match statement from config.

    Args:
        rule_config: Rule configuration dict

    Returns:
        CDK-compatible byte match statement
    """
    statement = rule_config.get("statement", {}).get("byte_match", {})

    field_to_match = {}
    field = statement.get("field")
    field_name = statement.get("field_name")

    if field == "method":
        field_to_match = {"method": {}}
    elif field == "uri_path":
        field_to_match = {"uriPath": {}}
    elif field == "header" and field_name:
        field_to_match = {"singleHeader": {"name": field_name}}

    return {
        "byteMatchStatement": {
            "fieldToMatch": field_to_match,
            "positionalConstraint": statement.get("positional_constraint"),
            "searchString": statement.get("search_string"),
            "textTransformations": [{"priority": 0, "type": "NONE"}],
        }
    }


def create_geo_match_statement(rule_config: dict) -> dict:
    """
    Create geo match statement from config.

    Args:
        rule_config: Rule configuration dict

    Returns:
        CDK-compatible geo match statement
    """
    statement = rule_config.get("statement", {}).get("geo_match", {})

    geo_statement = {
        "countryCodes": statement.get("country_codes", []),
    }

    forwarded_ip = statement.get("forwarded_ip_config")
    if forwarded_ip:
        geo_statement["forwardedIpConfig"] = {
            "headerName": forwarded_ip.get("header_name"),
            "fallbackBehavior": forwarded_ip.get("fallback_behavior"),
        }

    return {"geoMatchStatement": geo_statement}


def create_statement(statement_config: dict) -> dict:
    """
    Create rule statement from config (dispatches to specific statement types).

    Args:
        statement_config: Statement configuration dict

    Returns:
        CDK-compatible statement dict
    """
    if "or_statement" in statement_config:
        or_statements = statement_config["or_statement"]
        return {
            "orStatement": {
                "statements": [create_byte_match_statement({"statement": {"byte_match": stmt}}) for stmt in or_statements]
            }
        }

    if "not_statement" in statement_config:
        not_stmt = statement_config["not_statement"]
        return {
            "notStatement": {
                "statement": create_statement(not_stmt)
            }
        }

    if "byte_match" in statement_config:
        return create_byte_match_statement({"statement": statement_config})

    if "geo_match" in statement_config:
        return create_geo_match_statement({"statement": statement_config})

    return {}


def create_web_acl(scope: str, stack, config: dict, construct_id = None) -> wafv2.CfnWebACL:
    """
    Create WAF Web ACL from configuration.

    Args:
        scope: WAF scope ("CLOUDFRONT" or "REGIONAL")
        stack: CDK stack to create resources in
        config: WAF configuration dict from YAML
        construct_id: construct ID (defaults to config name)

    Returns:
        CDK Web ACL construct

    Raises:
        ValueError: If configuration is invalid
    """
    try:
        if construct_id is None:
            construct_id = config.get("name", "WebACL")

        # Validate scope
        if scope not in ["CLOUDFRONT", "REGIONAL"]:
            raise ValueError(
                f"\n"
                f"WAF Web ACL Error:\n"
                f"  Invalid scope: {scope}\n"
                f"  Must be 'CLOUDFRONT' or 'REGIONAL'"
            )

        rules = []
        rule_count = 0

        for rule_config in config.get("rules", []):
            rule_count += 1
            rule_name = rule_config.get("name", f"Rule-{rule_count}")

            try:
                # Skip disabled rules
                if not rule_config.get("enabled", True):
                    print(f"  Skipping disabled rule: {rule_name}")
                    continue

                # Validate required fields
                if "statement" not in rule_config:
                    print(f"  Warning: Rule '{rule_name}' missing statement, skipping")
                    continue

                if "priority" not in rule_config:
                    print(f"  Warning: Rule '{rule_name}' missing priority, skipping")
                    continue

                # Determine statement type
                statement_type = rule_config.get("statement", {})
                if "rate_based" in statement_type:
                    statement = create_rate_based_rule(rule_config)
                elif "managed_rule_group" in statement_type:
                    statement = create_managed_rule_group_statement(rule_config)
                elif "size_constraint" in statement_type:
                    statement = create_size_constraint_statement(rule_config)
                elif "byte_match" in statement_type:
                    statement = create_byte_match_statement(rule_config)
                elif "geo_match" in statement_type:
                    statement = create_geo_match_statement(rule_config)
                else:
                    print(f"  Warning: Rule '{rule_name}' has unknown statement type, skipping")
                    continue

                # Determine action
                action_type = rule_config.get("action")
                if action_type == "block":
                    action = {"block": {}}
                elif action_type == "allow":
                    action = {"allow": {}}
                elif action_type == "count":
                    action = {"count": {}}
                elif action_type == "captcha":
                    action = {"captcha": {}}
                elif action_type == "override_to_count":
                    # For managed rule groups
                    override_action = {"count": {}}
                    action = None
                else:
                    action = {"allow": {}}

                # Build visibility config
                visibility = rule_config.get("visibility", {})
                visibility_config = {
                    "sampledRequestsEnabled": visibility.get("sampled_requests", True),
                    "cloudWatchMetricsEnabled": visibility.get("cloudwatch_metrics", True),
                    "metricName": visibility.get("metric_name", rule_name),
                }

                # Build rule
                rule = {
                    "name": rule_name,
                    "priority": rule_config.get("priority"),
                    "statement": statement,
                    "visibilityConfig": visibility_config,
                }

                # Add action or override action
                if action:
                    rule["action"] = action
                elif override_action: # type: ignore
                    rule["overrideAction"] = override_action

                rules.append(rule)

            except Exception as e:
                print(
                    f"\n"
                    f"Warning: Failed to process WAF rule '{rule_name}':\n"
                    f"  {str(e)}\n"
                    f"  Skipping this rule and continuing..."
                )
                continue

        # Create Web ACL
        default_action_type = config.get("default_action", "allow")
        default_action = {"allow": {}} if default_action_type == "allow" else {"block": {}}

        web_acl = wafv2.CfnWebACL(
            stack,
            construct_id,
            scope=scope,
            default_action=default_action,
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                sampled_requests_enabled=True,
                cloud_watch_metrics_enabled=True,
                metric_name=config.get("name", "WebACL"), # type: ignore
            ),
            name=config.get("name"),
            description=config.get("description", ""),
            rules=rules,
        )

        print(f"  Created WAF Web ACL '{config.get('name')}' with {len(rules)} rules")
        return web_acl

    except Exception as e:
        raise ValueError(
            f"\n"
            f"WAF Web ACL Creation Error:\n"
            f"  Name: {config.get('name', 'Unknown')}\n"
            f"  Scope: {scope}\n"
            f"  Details: {str(e)}\n"
        ) from e
