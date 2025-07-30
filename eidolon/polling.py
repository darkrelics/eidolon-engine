"""
Polling infrastructure management for Lambda functions.

Provides centralized functions for managing EventBridge rules and SSM parameters
used in the segment polling system.
"""

import boto3
from botocore.exceptions import ClientError

from eidolon.environment import EVENTBRIDGE_RULE_NAME, SSM_POLLER_STATE_PARAMETER
from eidolon.logger import get_logger
from eidolon.ssm import get_parameter, put_parameter

# Configure logging
logger = get_logger(__name__)

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
            logger.info("EventBridge rule enabled", extra={"rule_name": EVENTBRIDGE_RULE_NAME})
        else:
            events_client.disable_rule(Name=EVENTBRIDGE_RULE_NAME)
            logger.info("EventBridge rule disabled", extra={"rule_name": EVENTBRIDGE_RULE_NAME})
    except ClientError as err:
        logger.error(
            "Failed to manage EventBridge rule",
            extra={
                "rule_name": EVENTBRIDGE_RULE_NAME,
                "action": "enable" if should_enable else "disable",
                "error": str(err),
                "error_code": err.response.get("Error", {}).get("Code", "Unknown"),
            },
            exc_info=True,
        )
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
        logger.info(
            "Updated polling state",
            extra={
                "parameter": SSM_POLLER_STATE_PARAMETER,
                "state": state,
            },
        )
    except Exception as err:
        logger.error(
            "Failed to update polling state",
            extra={
                "parameter": SSM_POLLER_STATE_PARAMETER,
                "state": state,
                "error": str(err),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to update polling state: {str(err)}")


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
        logger.info(
            "Polling state parameter not found, creating with default",
            extra={"parameter": SSM_POLLER_STATE_PARAMETER},
        )
        update_polling_state("run")
        return "run"
    except Exception as err:
        logger.error(
            "Failed to get polling state",
            extra={
                "parameter": SSM_POLLER_STATE_PARAMETER,
                "error": str(err),
            },
            exc_info=True,
        )
        raise RuntimeError(f"Failed to get polling state: {str(err)}")


def enable_polling_infrastructure() -> None:
    """
    Enable the polling infrastructure by updating SSM state and enabling EventBridge rule.
    
    This is typically called when a new story starts and polling needs to be activated.
    """
    logger.info("Enabling polling infrastructure")
    
    # Update SSM parameter first
    update_polling_state("run")
    
    # Then enable EventBridge rule
    manage_eventbridge_rule(True)
    
    logger.info("Polling infrastructure enabled")


def disable_polling_infrastructure() -> None:
    """
    Disable the polling infrastructure by updating SSM state and disabling EventBridge rule.
    
    This is typically called when no active segments remain and polling should stop
    to save costs.
    """
    logger.info("Disabling polling infrastructure")
    
    # Update SSM parameter first
    try:
        update_polling_state("stop")
    except Exception as err:
        logger.warning(
            "Failed to update SSM parameter during shutdown",
            extra={"error": str(err)},
        )
    
    # Then disable EventBridge rule
    manage_eventbridge_rule(False)
    
    logger.info("Polling infrastructure disabled")


def ensure_polling_enabled() -> None:
    """
    Ensure polling is enabled, starting it if necessary.
    
    This is typically called when starting a new story to make sure
    the polling system is active.
    """
    try:
        state = get_polling_state()
        if state == "stop":
            enable_polling_infrastructure()
            logger.info("Polling was stopped, now enabled")
        else:
            logger.info("Polling already running")
    except Exception as err:
        # If we can't determine state, try to enable anyway
        logger.warning(
            "Could not determine polling state, attempting to enable",
            extra={"error": str(err)},
        )
        try:
            enable_polling_infrastructure()
        except Exception as enable_err:
            logger.error(
                "Failed to enable polling infrastructure",
                extra={"error": str(enable_err)},
                exc_info=True,
            )
            # Don't block story start if polling setup fails
            logger.warning("Continuing despite polling setup failure")