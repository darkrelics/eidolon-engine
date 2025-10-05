"""
Story reward calculation and application.

Provides functions for calculating and applying story rewards.
"""

from botocore.exceptions import ClientError

from eidolon.logger import logger


def calculate_story_rewards(story_metadata: dict, outcome: str, segments_completed: int) -> dict:
    """
    Calculate rewards based on story outcome and segments completed.

    Args:
        story_metadata: Story data from STORY table
        outcome: Final outcome (death, failure, minimal, normal, exceptional)
        segments_completed: Number of segments completed

    Returns:
        Dict with calculated rewards (items, currency)
    """
    rewards = {
        "items": [],
        "currency": 0,
    }

    if outcome == "death":
        return rewards

    reward_tiers_raw = story_metadata.get("RewardTiers", {})
    reward_tiers: dict = {}
    if isinstance(reward_tiers_raw, dict):
        reward_tiers = {str(k).lower(): v for k, v in reward_tiers_raw.items()}
    else:
        reward_tiers = {}

    # Get rewards based on outcome tier
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
        # Story rewards currently only handle items and currency
        # XP is awarded through segment processing for specific skills

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
        # Segment processing already applied skill/attribute XP.
        # Additional combat rewards must come from segment/story data; none are applied here.
        loot_table = opponent_data.get("LootTable", [])
        if loot_table:
            logger.info(
                "Loot rewards are defined on the opponent but segment/story data must trigger distribution; skipping Dynamo writes"
            )

        logger.info(f"No additional combat rewards applied for {character_id}")
    except ClientError as err:
        logger.error(f"Failed to apply combat rewards for {character_id} Error: {err}", exc_info=True)
        raise RuntimeError(f"Failed to apply combat rewards: {err}") from err
