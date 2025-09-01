"""
Game constants and configuration values.

Centralizes magic numbers and configuration constants used throughout the game.
"""

# XP calculation constants
BASE_XP = 0.25  # Base experience per action
FAILURE_XP_PENALTY = 0.5  # Failed actions give 50% XP
ATTRIBUTE_XP_RATIO = 0.1  # Attributes gain 10% of skill XP

# Sigma thresholds for challenge outcomes
SIGMA_EXCEPTIONAL = 3.0  # 3+ sigma for exceptional success
SIGMA_NORMAL = 0.0  # 0+ sigma for normal success
SIGMA_MINIMAL = -3.0  # -3+ sigma for minimal success
# Below -3 sigma is failure

# Combat constants
DEFAULT_COMBAT_ROUNDS = 10  # Default max rounds if not specified in segment
MAX_COMBAT_ROUNDS = 100  # Maximum rounds before combat times out (safety limit)
COMBAT_TIMEOUT_OUTCOME = "failure"  # Outcome when combat exceeds max rounds

# Time windows for segment processing (seconds)
SEGMENT_STUCK_THRESHOLD = 900  # 15 minutes - segment considered stuck
SEGMENT_RETRY_WINDOW = 900  # 15 minutes - minimum time remaining to retry
