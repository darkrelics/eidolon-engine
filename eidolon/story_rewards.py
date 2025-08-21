"""
Story reward calculation and application.

Provides functions for calculating and applying story rewards.
"""

from botocore.exceptions import ClientError

from eidolon.dynamo import TableName, dynamo
from eidolon.logger import logger


def calculate_story_rewards(story_metadata: dict, outcome: str, segments_completed: int) -> dict:
    """
    Calculate rewards based on story outcome and segments completed.

    Args:
        story_metadata: Story data from STORY table
        outcome: Final outcome (death, failure, minimal, normal, exceptional)
        segments_completed: Number of segments completed

    Returns:
        Dict with calculated rewards (xp, items, etc.)
    """
    rewards = {
        "xp": 0,
        "items": [],
        "currency": 0,
    }

    if outcome == "death":
        return rewards

    base_xp_multiplier = float(story_metadata.get("BaseXPMultiplier", 0.5))
    reward_tiers_raw = story_metadata.get("RewardTiers", {})
    reward_tiers: dict = {}
    if isinstance(reward_tiers_raw, dict):
        reward_tiers = {str(k).lower(): v for k, v in reward_tiers_raw.items()}
    else:
        reward_tiers = {}

    outcome_multipliers = {
        "failure": 0.25,
        "minimal": 0.5,
        "normal": 1.0,
        "exceptional": 1.5,
    }

    outcome_multiplier = outcome_multipliers.get(outcome, 0)
    base_xp = story_metadata.get("EstimatedDuration", 300) * base_xp_multiplier

    total_segments = story_metadata.get("TotalSegments", 1)
    completion_ratio = min(1.0, segments_completed / max(1, total_segments))

    rewards["xp"] = int(base_xp * outcome_multiplier * completion_ratio)

    tier_rewards = reward_tiers.get(outcome, {})
    if isinstance(tier_rewards, dict):
        rewards["items"] = tier_rewards.get("items", [])
        rewards["currency"] = tier_rewards.get("currency", 0)
    else:
        rewards["items"] = []
        rewards["currency"] = 0

    return rewards


def apply_story_rewards(character_id: str, rewards: dict) -> None:
    """
    Apply calculated rewards to a character.

    Args:
        character_id: Character UUID
        rewards: Dict containing xp, items, currency

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        if rewards.get("xp", 0) > 0:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="ADD #skills.#story :xp",
                ExpressionAttributeNames={
                    "#skills": "Skills",
                    "#story": "story",
                },
                ExpressionAttributeValues={
                    ":xp": rewards["xp"],
                },
            )

        logger.info(f"Applied story rewards for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply rewards: {err}") from err


def apply_combat_rewards(character_id: str, opponent_data: dict) -> None:
    """
    Apply rewards from defeating an opponent in combat.

    Args:
        character_id: Character UUID
        opponent_data: Opponent data including XPReward and LootTable

    Raises:
        RuntimeError: If database operations fail
    """
    try:
        xp_reward = opponent_data.get("XPReward", 10)
        if xp_reward > 0:
            dynamo.update_item(
                TableName.CHARACTERS,
                Key={"CharacterID": character_id},
                UpdateExpression="ADD #skills.#combat :xp",
                ExpressionAttributeNames={
                    "#skills": "Skills",
                    "#combat": "combat",
                },
                ExpressionAttributeValues={
                    ":xp": xp_reward,
                },
            )

        _ = opponent_data.get("LootTable", [])

        logger.info(f"Applied combat rewards for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply combat rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply combat rewards: {err}") from err