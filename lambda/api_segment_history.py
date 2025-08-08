"""
Eidolon Engine - Incremental Game

Copyright 2024-2025 Jason E. Robinson

Lambda function to retrieve segment history for a character.
Returns completed segment results from the character's story history.
"""

from botocore.exceptions import ClientError

from eidolon.character_data import character_get
from eidolon.cognito import extract_player_id
from eidolon.cors import cors_handler
from eidolon.dynamo import TableName, dynamo
from eidolon.logger import log_lambda_statistics, logger
from eidolon.player import validate_player, verify_character_ownership
from eidolon.requests import get_query_parameter_flexible
from eidolon.responses import lambda_error, lambda_response


def get_segment_history_business_logic(character_id: str, player_id: str) -> dict:
    """
    Business logic for retrieving segment history.

    Args:
        character_id: Character UUID
        player_id: Authenticated player ID

    Returns:
        Response data dict with segment history

    Raises:
        ValueError: If character not found or not owned
        RuntimeError: If database operations fail
    """
    # Verify character ownership using player record
    if not verify_character_ownership(character_id, player_id):
        raise ValueError("Character not owned by player")

    # Get character data to find active story
    character: dict = character_get(character_id, player_id)

    # Get current story ID from character
    story_id = character.get("ActiveStoryID")
    if not story_id:
        # No active story, return empty history
        logger.info(f"No active story for character for {character_id}")
        return {
            "CharacterID": character_id,
            "StoryID": None,
            "Segments": [],
        }

    # Query completed segments from ActiveSegments table
    # This gives us the full segment data including ClientEvents, CharacterUpdates, etc.
    try:
        segments = dynamo.query(
            TableName.ACTIVE_SEGMENTS,
            IndexName="CharacterID-index",
            KeyConditionExpression="CharacterID = :cid",
            FilterExpression="StoryID = :sid AND #status IN (:completed, :processed)",
            ExpressionAttributeNames={"#status": "Status"},
            ExpressionAttributeValues={
                ":cid": character_id,
                ":sid": story_id,
                ":completed": "completed",
                ":processed": "processed",
            },
        )
    except ClientError as err:
        logger.error(
            f"Failed to query active segments for {character_id} Error: {err}",
            exc_info=True,
        )
        raise RuntimeError(f"Failed to query active segments: {err}") from err

    # Format segments for response with all the data Flutter expects
    formatted_segments = []
    for segment in segments or []:
        formatted_segment = {
            "ActiveSegmentID": segment.get("ActiveSegmentID"),
            "SegmentID": segment.get("SegmentID"),
            "SegmentType": segment.get("SegmentType"),
            "Status": segment.get("Status"),
            "ProcessingStatus": segment.get("ProcessingStatus"),
            "StartTime": segment.get("StartTime"),
            "EndTime": segment.get("EndTime"),
        }

        # Add enriched data that Flutter needs
        if segment.get("Outcome"):
            formatted_segment["Outcome"] = segment.get("Outcome")

        if segment.get("ClientEvents"):
            formatted_segment["ClientEvents"] = segment.get("ClientEvents")

        if segment.get("CharacterUpdates"):
            formatted_segment["CharacterUpdates"] = segment.get("CharacterUpdates")

        if segment.get("Decision"):
            formatted_segment["Decision"] = segment.get("Decision")

        if segment.get("ChallengeResults"):
            formatted_segment["ChallengeResults"] = segment.get("ChallengeResults")

        if segment.get("SkillXPAwarded"):
            formatted_segment["SkillXPAwarded"] = segment.get("SkillXPAwarded")

        if segment.get("AttributeXPAwarded"):
            formatted_segment["AttributeXPAwarded"] = segment.get("AttributeXPAwarded")

        if segment.get("CombatState"):
            formatted_segment["CombatState"] = segment.get("CombatState")

        if segment.get("NextSegmentID"):
            formatted_segment["NextSegmentID"] = segment.get("NextSegmentID")

        formatted_segments.append(formatted_segment)

    # Sort by start time, newest first
    formatted_segments.sort(key=lambda x: x.get("StartTime", 0), reverse=True)

    response = {
        "CharacterID": character_id,
        "StoryID": story_id,
        "Segments": formatted_segments,
    }

    logger.info(f"Segment history retrieved for {character_id}")

    return response


def lambda_handler(event: dict, context: object) -> dict:
    """
    Get segment history for a character.

    Lambda function to retrieve completed segment history for a character's
    active story. Used by clients to display past outcomes and decisions.

    Query Parameters:
        characterId: Character ID to get history for (supports both CharacterID and characterId)

    Returns:
        200: Segment history data
        404: Character not found
        400: Missing parameters or invalid request
        401: Unauthorized
        500: Internal error
    """
    # Log invocation
    log_lambda_statistics(event, context)

    # Handle preflight
    preflight_response: dict = cors_handler.handle_preflight(event)
    if preflight_response:
        return preflight_response

    try:
        # Extract player ID from JWT
        player_id = extract_player_id(event)
    except ValueError as err:
        logger.error(f"Authentication failed Error: {err}", exc_info=True)
        return lambda_response(401, {"Error": "Unauthorized"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Validate player exists
    try:
        if not validate_player(player_id):
            logger.error(f"Player not found in database for {player_id}", exc_info=True)
            return lambda_response(401, {"Error": "Unauthorized"}, event)
    except RuntimeError as err:
        logger.error(f"Failed to validate player Error: {err}", exc_info=True)
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)

    # Get character ID from query parameters (flexible: CharacterID or characterId)
    character_id = get_query_parameter_flexible(event, "CharacterID", "characterId")
    if not character_id:
        return lambda_response(400, {"Error": "Missing CharacterID parameter"}, event)

    # Call business logic
    try:
        response_data = get_segment_history_business_logic(character_id, player_id)  # type: ignore
        return lambda_response(200, response_data, event)
    except ValueError as err:
        logger.warning(f"Invalid request for {character_id} Error: {err}")
        if "not found" in str(err).lower():
            return lambda_response(404, {"Error": "Character not found"}, event)
        return lambda_response(400, {"Error": str(err)}, event)
    except RuntimeError as err:
        logger.error(
            f"Failed to get segment history for {character_id} Error: {err}",
            exc_info=True,
        )
        return lambda_response(500, {"Error": "Internal server error"}, event)
    except Exception as err:
        return lambda_error(event, err)
