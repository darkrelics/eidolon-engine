"""
Game constants and configuration values.

Centralizes magic numbers and configuration constants used throughout the game.
"""

# XP calculation constants
# Wound healing durations
from datetime import timedelta
from enum import Enum

BASE_XP = 0.25  # Base experience per action
FAILURE_XP_PENALTY = 0.5  # Failed actions give 50% XP (when D >= S; 0% XP when S > D)
ATTRIBUTE_XP_RATIO = 0.1  # Attributes gain 10% of skill XP

MAX_SKILL_LEVEL = 10.0  # Hard cap on skill/attribute values

# Sigma thresholds for challenge outcomes
SIGMA_EXCEPTIONAL = 3.0  # 3+ sigma for exceptional success
SIGMA_NORMAL = 0.0  # 0+ sigma for normal success
SIGMA_MINIMAL = -3.0  # -3+ sigma for minimal success
# Below -3 sigma is failure

# Combat constants
DEFAULT_COMBAT_ROUNDS = 10  # Default max rounds if not specified in segment
MAX_COMBAT_ROUNDS = 100  # Maximum rounds before combat times out (safety limit)

# Player durability thresholds
PLAYER_DEATH_LETHAL_WOUNDS = 5  # Lethal wounds causing death
PLAYER_INCAPACITATED_TOTAL_WOUNDS = 10  # Total wounds causing incapacitation

# Opponent defeat heuristics
DEFAULT_OPPONENT_HEALTH = 5  # Default opponent health when unknown
COMBAT_OPPONENT_WOUNDS_MULTIPLIER_FOR_DEFEAT = 2  # Total wounds vs health

# Opposed check mechanics (MUD mechanics)
OPPOSED_SHIFT = 0.20  # How much rating difference matters
OPPOSED_VARIANCE = 0.35  # Variance scaling
OPPOSED_MIN_SIGMA = 0.25  # Minimum variance


BASHING_HEAL_TIME = timedelta(minutes=15)
LETHAL_HEAL_TIME = timedelta(hours=6)
AGGRAVATED_HEAL_TIME = timedelta(days=7)

# Default room used when character dies (NUMBER per schema)
DEFAULT_DEATH_ROOM_ID = 0


class CharState(str, Enum):
    """Character state values used throughout the system."""

    STANDING = "standing"
    UNCONSCIOUS = "unconscious"
    DEAD = "dead"


# Time windows for segment processing (seconds)
SEGMENT_STUCK_THRESHOLD = 900  # 15 minutes - segment considered stuck
SEGMENT_RETRY_WINDOW = 900  # 15 minutes - minimum time remaining to retry
