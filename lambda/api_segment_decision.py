"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to submit a decision for a story segment.
Updates the active segment with the player's choice and returns the next segment.
"""

from eidolon.lambda_handler import authenticated_handler
from eidolon.logger import logger
from eidolon.requests import parse_event_body
from eidolon.story_decision import submit_decision_for_character
from eidolon.validation import validate_uuid


def submit_decision_business_logic(character_id: str, decision_id: str, player_id: str) -> dict:
    """
    Business logic for submitting a decision.

    Args:
        character_id: Character UUID
        decision_id: Decision ID chosen by player
        player_id: Authenticated player ID

    Returns:
        Response data with accepted status and optional next segment time

    Raises:
        ValueError: If validation fails (with status code prefix for 403/404/409)
        RuntimeError: If database operations fail
    """
    # Submit the decision using the eidolon library
    return submit_decision_for_character(character_id, decision_id, player_id)


@authenticated_handler
def lambda_handler(event: dict, context: object, player_id: str) -> dict:
    """
    Lambda handler to submit a decision for a story segment.

    Args:
        event: API Gateway Lambda proxy event
        context: Lambda context
        player_id: Authenticated player ID

    Returns:
        Dict with status_code and body
    """
    body = parse_event_body(event)
    character_id = body.get("CharacterID")
    decision_id = body.get("Decision")

    if not character_id:
        raise ValueError("Missing CharacterID")
    if not decision_id:
        raise ValueError("Missing Decision")

    if not validate_uuid(character_id):
        raise ValueError("Invalid CharacterID format")

    logger.info(f"Processing decision submission for character={character_id}, Decision={decision_id}")

    # Call business logic
    response_data = submit_decision_business_logic(character_id, decision_id, player_id)
    return {"status_code": 200, "body": response_data}
