"""
Polling infrastructure management for Lambda functions.

Provides centralized functions for managing EventBridge rules and SSM parameters
used in the segment polling system.
"""

import boto3
from botocore.exceptions import ClientError

from eidolon.environment import EVENTBRIDGE_RULE_NAME, SSM_POLLER_STATE_PARAMETER
from eidolon.logger import logger
from eidolon.ssm import get_parameter, put_parameter

# EventBridge client
events_client = boto3.client("events")


def manage_eventbridge_rule(should_enable: bool) -> None:
    """
    Enable or disable the EventBridge rule for segment polling.

    Args:
        should_enable: True to enable, False to disable the rule

    Raises:
        RuntimeError: If EventBridge operation fails
    """
    if not EVENTBRIDGE_RULE_NAME:
        logger.warning("EVENTBRIDGE_RULE_NAME not configured, skipping rule management")
        return

    try:
        if should_enable:
            logger.info(f"Enabling EventBridge rule: {EVENTBRIDGE_RULE_NAME}")
            response = events_client.enable_rule(Name=EVENTBRIDGE_RULE_NAME)
            logger.info(
                f"EventBridge rule enabled successfully - Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}"
            )
        else:
            logger.info(f"Disabling EventBridge rule: {EVENTBRIDGE_RULE_NAME}")
            response = events_client.disable_rule(Name=EVENTBRIDGE_RULE_NAME)
            logger.info(
                f"EventBridge rule disabled successfully - Status: {response.get('ResponseMetadata', {}).get('HTTPStatusCode')}"
            )
    except ClientError as err:
        error_code = err.response.get("Error", {}).get("Code", "Unknown")
        if error_code == "ResourceNotFoundException":
            logger.error(f"EventBridge rule '{EVENTBRIDGE_RULE_NAME}' not found", exc_info=True)
        elif error_code == "AccessDeniedException":
            logger.error(f"Access denied for EventBridge rule '{EVENTBRIDGE_RULE_NAME}'", exc_info=True)
        else:
            logger.error(f"Failed to manage EventBridge rule - Code: {error_code}", exc_info=True)
        raise RuntimeError(f"Failed to manage EventBridge rule '{EVENTBRIDGE_RULE_NAME}': {error_code}") from err


def update_polling_state(state: str) -> None:
    """
    Update the SSM parameter that controls polling state.

    Args:
        state: New state value ("run" or "stop")

    Raises:
        ValueError: If state is not "run" or "stop"
        RuntimeError: If SSM update fails
    """
    if state not in ["run", "stop"]:
        raise ValueError(f"Invalid polling state: {state}. Must be 'run' or 'stop'")

    try:
        put_parameter(SSM_POLLER_STATE_PARAMETER, state)
        logger.info(f"Updated polling state to {state}")
    except Exception as err:
        logger.error(f"Failed to update polling state to {state} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update polling state: {err}") from err


def get_polling_state() -> str:
    """
    Get the current polling state from SSM parameter.

    Returns:
        Current state ("run" or "stop")

    Raises:
        RuntimeError: If SSM read fails
    """
    try:
        state = get_parameter(SSM_POLLER_STATE_PARAMETER)
        return state
    except ValueError as err:
        # Parameter doesn't exist, create it with default value
        logger.info(f"Polling state parameter not found, creating with default: {err}")
        update_polling_state("run")
        return "run"
    except Exception as err:
        logger.error(f"Failed to get polling state Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get polling state: {err}") from err


def ensure_polling_enabled() -> None:
    """
    Ensure polling is enabled when starting a story.
    Enables EventBridge rule first, then sets SSM parameter to "run".
    Used only by api-story-start.

    Order of operations:
    1. Enable EventBridge rule (idempotent - safe to enable if already enabled)
    2. Update SSM parameter to "run"

    If EventBridge fails, we skip SSM update to avoid starting the poller
    when it can't actually run.
    """
    logger.info(f"Enabling polling system - Rule: {EVENTBRIDGE_RULE_NAME}, SSM: {SSM_POLLER_STATE_PARAMETER}")

    # 1) Enable EventBridge rule first - if this fails, don't update SSM
    try:
        manage_eventbridge_rule(True)
        logger.info("EventBridge rule enabled")
    except Exception as err:
        logger.error(f"Failed to enable EventBridge rule Error: {err}", exc_info=True)
        logger.warning("Skipping SSM update because EventBridge rule enablement failed")
        return

    # 2) Update SSM parameter to 'run'
    try:
        update_polling_state("run")
        logger.info("Polling system enabled successfully")
    except Exception as err:
        logger.error(f"Failed to update polling state to 'run' Error: {err}", exc_info=True)
        logger.warning("EventBridge enabled but SSM update failed - poller may self-correct")
