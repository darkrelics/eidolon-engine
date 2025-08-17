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
            events_client.enable_rule(Name=EVENTBRIDGE_RULE_NAME)
            logger.info(f"EventBridge rule enabled for {EVENTBRIDGE_RULE_NAME}")
        else:
            events_client.disable_rule(Name=EVENTBRIDGE_RULE_NAME)
            logger.info(f"EventBridge rule disabled for {EVENTBRIDGE_RULE_NAME}")
    except ClientError as err:
        logger.error(f"Failed to manage EventBridge rule for {EVENTBRIDGE_RULE_NAME} Error: {err}", exc_info=True)
        # Don't fail the whole operation if rule management fails
        logger.warning("Continuing despite EventBridge rule management failure")


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
        logger.info(f"Updated polling state for {state}")
    except Exception as err:
        logger.error(f"Failed to update polling state for {state} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to update polling state: {err}")


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
    except ValueError:
        # Parameter doesn't exist, create it with default value
        logger.info("Polling state parameter not found, creating with default")
        update_polling_state("run")
        return "run"
    except Exception as err:
        logger.error(f"Failed to get polling state Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to get polling state: {err}")




def ensure_polling_enabled() -> None:
    """
    Ensure polling is enabled when starting a story.
    Sets SSM parameter to "run" and enables EventBridge rule.
    Used only by api-story-start.
    """
    try:
        # Set parameter to run
        update_polling_state("run")
        # Enable the EventBridge rule
        manage_eventbridge_rule(True)
        logger.info("Polling enabled: parameter=run, rule=enabled")
    except Exception as err:
        logger.error(f"Failed to enable polling: {err}", exc_info=True)
        # Don't block story start if polling setup fails
        logger.warning("Continuing despite polling setup failure")
