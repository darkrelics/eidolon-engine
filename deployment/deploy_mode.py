"""Deployment mode utilities for Eidolon Engine infrastructure."""

VALID_MODES = ["mud", "incremental", "hybrid"]
DEFAULT_MODE = "hybrid"


def validate_deployment_mode(mode: str) -> str:
    """Validate and normalize deployment mode.

    Args:
        mode: Input deployment mode string

    Returns:
        str: Valid deployment mode or default if invalid
    """
    normalized = mode.lower().strip() if mode else DEFAULT_MODE

    if normalized not in VALID_MODES:
        print(f"Invalid deployment mode '{mode}'. Using default: {DEFAULT_MODE}")
        return DEFAULT_MODE

    return normalized


def get_portal_buildspec(mode: str) -> str:
    """Get the portal buildspec file based on deployment mode.

    Args:
        mode: Deployment mode (mud, incremental, or hybrid)

    Returns:
        str: Buildspec filename
    """
    if mode == "mud":
        return "portal.yml"
    else:
        return "incremental.yml"


def get_deployment_order(mode: str) -> list:
    """Get the stack deployment order based on deployment mode.

    Stacks not in the returned list will not be deployed.

    Dependencies:
    - Lambda provides shared Lambda layer and role
    - Character, Story and Player stacks use shared resources from Lambda
    - API requires Lambda functions from all stacks

    Args:
        mode: Deployment mode (mud, incremental, or hybrid)

    Returns:
        List of stack names in deployment order
    """
    if mode == "mud":
        # MUD: Lambda first (shared resources), no Story stack
        return ["codebuild", "dynamodb", "lambda", "player", "character", "s3", "cloudwatch", "api", "client"]
    elif mode == "incremental":
        # Incremental: Lambda first, then Player, Character, Story
        return ["codebuild", "dynamodb", "lambda", "player", "character", "story", "api", "client"]
    else:  # hybrid
        # Hybrid: Lambda first, then Player, Character, Story
        return ["codebuild", "dynamodb", "lambda", "player", "character", "story", "s3", "cloudwatch", "api", "client"]


def get_stack_phase_number(stack_name: str, mode: str) -> int:
    """Get the phase number for a stack based on deployment mode.

    Args:
        stack_name: Name of the stack
        mode: Deployment mode

    Returns:
        int: Phase number (1-based index)
    """
    order = get_deployment_order(mode)
    try:
        return order.index(stack_name) + 1
    except ValueError:
        return 0  # Stack not in deployment order


def get_stack_description(stack_name: str) -> str:
    """Get a human-readable description of a stack.

    Args:
        stack_name: Name of the stack

    Returns:
        str: Description of the stack
    """
    descriptions = {
        "codebuild": "2 projects, 1 S3 bucket, 1 role, 2 policies",
        "dynamodb": "14 tables, 1 IAM policy",
        "lambda": "Shared Lambda layer, shared execution role, logs policy",
        "character": "5 Lambda functions",
        "story": "10 Lambda functions, 2 SQS queues, EventBridge, SSM, 1 policy",
        "player": "Cognito User Pool, client, 1 Lambda function",
        "s3": "1 bucket, 1 IAM policy, Lua scripts upload",
        "cloudwatch": "1 log group, metrics, 1 IAM policy",
        "api": "API Gateway, custom domain, ACM certificate, Route53 record",
        "client": "1 S3 bucket, CloudFront, CodeBuild project, ACM certificate, Route53 record",
    }
    return descriptions.get(stack_name, "Unknown stack")


def display_mode_summary(mode: str) -> None:
    """Display a summary of what the deployment mode includes.

    Args:
        mode: Deployment mode
    """
    deployment_order = get_deployment_order(mode)

    print(f"\n  Deployment Mode: {mode.upper()}")
    print(f"  Portal Buildspec: {get_portal_buildspec(mode)}")
    # Add 1 for Phase 11 (Lambda Function Updates)
    total_phases = len(deployment_order) + 1
    print(f"  Phases to deploy ({total_phases} total):")

    for i, stack_name in enumerate(deployment_order, 1):
        description = get_stack_description(stack_name)
        print(f"    {i}. {stack_name.capitalize()}: {description}")
    
    # Add Phase 11
    print(f"    11. Lambda Function Updates: Update function code from S3 artifacts")

    # Show what's excluded
    if mode == "mud":
        print("\n  Excluded: Story Stack (not needed for MUD mode)")
    elif mode == "incremental":
        print("\n  Excluded: S3 and CloudWatch Stacks (not needed for Incremental mode)")
