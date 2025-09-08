"""
Pydantic models for the Eidolon MUD backend.

These models provide type safety, validation, and serialization for all
core game entities. They maintain backward compatibility with the existing
dictionary-based system while adding strong validation.
"""

import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator
from pydantic.alias_generators import to_pascal


class CharState(str, Enum):
    """Character state enumeration for MUD consumption."""

    STANDING = "standing"
    UNCONSCIOUS = "unconscious"
    DEAD = "dead"


class GameMode(str, Enum):
    """Game mode enumeration."""

    EXPLORATION = "Exploration"
    COMBAT = "Combat"
    STORY = "Story"
    SOCIAL = "Social"


class SegmentType(str, Enum):
    """Story segment type enumeration."""

    NARRATIVE = "Narrative"
    CHALLENGE = "Challenge"
    COMBAT = "Combat"
    DECISION = "Decision"
    REST = "Rest"
    REWARD = "Reward"


class SegmentStatus(str, Enum):
    """Segment processing status."""

    PENDING = "Pending"
    IN_PROGRESS = "InProgress"
    COMPLETED = "Completed"
    FAILED = "Failed"
    ABANDONED = "Abandoned"


class StoryType(str, Enum):
    """Story type enumeration."""

    MAIN = "Main"
    SIDE = "Side"
    PERSONAL = "Personal"
    GUILD = "Guild"
    EVENT = "Event"


class BaseEidolonModel(BaseModel):
    """
    Base model for all Eidolon entities.

    Provides common configuration for PascalCase serialization,
    flexible field name acceptance, and Decimal handling.
    """

    model_config = ConfigDict(
        populate_by_name=True,  # Accept both PascalCase and camelCase
        alias_generator=to_pascal,  # Output as PascalCase
        validate_assignment=True,
        arbitrary_types_allowed=True,
        use_enum_values=True,
    )

    @field_serializer("*", mode="wrap")
    def serialize_special_types(self, value, serializer):
        """Handle special type serialization."""
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat() if value else None
        return serializer(value)


class Wound(BaseEidolonModel):
    """Wound/injury model for character damage tracking."""

    location: str = Field(..., description="Body location of the wound")
    severity: int = Field(..., ge=1, le=5, description="Wound severity (1-5)")
    description: str | None = Field(default=None, description="Wound description")
    healing_time: int | None = Field(default=None, ge=0, description="Turns until healed")


class Attributes(BaseEidolonModel):
    """Character attributes model."""

    strength: float = Field(1.00000, ge=0, le=10)
    agility: float = Field(1.00000, ge=0, le=10)
    endurance: float = Field(1.00000, ge=0, le=10)
    charisma: float = Field(1.00000, ge=0, le=10)
    intrigue: float = Field(1.00000, ge=0, le=10)
    presence: float = Field(1.00000, ge=0, le=10)
    perception: float = Field(1.00000, ge=0, le=10)
    intelligence: float = Field(1.00000, ge=0, le=10)
    cunning: float = Field(1.00000, ge=0, le=10)

    @model_validator(mode="before")
    @classmethod
    def normalize_attributes(cls, data):
        """Normalize attribute names to lowercase."""
        if isinstance(data, dict):
            return {k.lower(): v for k, v in data.items()}
        return data


class Skills(BaseEidolonModel):
    """Character skills model."""

    melee: float = Field(0.00000, ge=0, le=10)
    archery: float = Field(0.00000, ge=0, le=10)
    brawling: float = Field(0.00000, ge=0, le=10)
    dodge: float = Field(0.00000, ge=0, le=10)
    parry: float = Field(0.00000, ge=0, le=10)
    stealth: float = Field(0.00000, ge=0, le=10)
    investigation: float = Field(0.00000, ge=0, le=10)
    tumbling: float = Field(0.00000, ge=0, le=10)
    climbing: float = Field(0.00000, ge=0, le=10)
    lockpicking: float = Field(0.00000, ge=0, le=10)
    mythos: float = Field(0.00000, ge=0, le=10)
    arcane: float = Field(0.00000, ge=0, le=10)
    first_aid: float = Field(0.00000, ge=0, le=10, alias="FirstAid")
    foraging: float = Field(0.00000, ge=0, le=10)
    appraise: float = Field(0.00000, ge=0, le=10)

    model_config = ConfigDict(
        extra="allow",  # Allow additional skills for future expansion
        populate_by_name=True,
        alias_generator=to_pascal,
        validate_assignment=True,
        use_enum_values=True,
    )


class InventoryItem(BaseEidolonModel):
    """Inventory item model."""

    item_id: str = Field(..., alias="ItemID")
    quantity: int = Field(1, ge=1)
    equipped: bool = Field(False)
    slot: str | None = Field(default=None, description="Equipment slot if equipped")
    metadata: dict = Field(default_factory=dict)


class CharacterModel(BaseEidolonModel):
    """
    Complete character model with all game state.

    This model represents a player character with all their
    attributes, inventory, story progress, and current state.
    """

    # Identity
    character_id: UUID = Field(..., alias="CharacterID")
    player_id: UUID = Field(..., alias="PlayerID")
    character_name: str = Field(..., alias="CharacterName", min_length=3, max_length=20)
    archetype: str = Field(..., alias="Archetype")

    # Stats
    attributes: Attributes = Field(default_factory=Attributes)  # type: ignore
    skills: Skills = Field(default_factory=Skills)  # type: ignore
    max_health: int = Field(100, ge=1, alias="MaxHealth")
    current_health: int | None = Field(default=None, ge=0, alias="CurrentHealth")
    essence: int = Field(0, ge=0, alias="Essence")
    max_essence: int = Field(100, ge=0, alias="MaxEssence")
    experience: int = Field(0, ge=0, alias="Experience", description="Total XP")
    level: int = Field(1, ge=1, le=100, alias="Level")

    # Status
    wounds: list[Wound] = Field(default_factory=list)
    char_state: CharState = Field(CharState.STANDING, alias="CharState")
    game_mode: GameMode = Field(GameMode.EXPLORATION, alias="GameMode")
    room_id: str | None = Field(default=None, alias="RoomID")

    # Inventory
    inventory: dict[str, InventoryItem] = Field(default_factory=dict)
    resources: dict[str, int] = Field(default_factory=dict)
    gold: int = Field(0, ge=0)

    # Story Progress
    active_story_id: UUID | None = Field(default=None, alias="ActiveStoryID")
    active_segment_id: UUID | None = Field(default=None, alias="ActiveSegmentID")
    available_stories: list[str] = Field(default_factory=list, alias="AvailableStories")
    completed_stories: list[str] = Field(default_factory=list, alias="CompletedStories")
    abandoned_stories: list[str] = Field(default_factory=list, alias="AbandonedStories")

    # Metadata
    created_at: datetime = Field(..., alias="CreatedAt")
    updated_at: datetime = Field(..., alias="UpdatedAt")
    last_played: datetime | None = Field(default=None, alias="LastPlayed")
    hidden: bool = Field(False, alias="Hidden")

    @field_validator("character_name")
    @classmethod
    def validate_character_name(cls, v: str) -> str:
        """Validate character name format and content."""

        # Check format
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_-]*$", v):
            raise ValueError("Character name must start with a letter and contain only letters, numbers, underscores, and hyphens")

        # Check for inappropriate content (integrate with bloom filter if needed)
        # This is a placeholder - integrate with existing validation

        return v

    @model_validator(mode="after")
    def validate_health(self) -> "CharacterModel":
        """Ensure current health doesn't exceed max health."""
        if self.current_health is None:
            self.current_health = self.max_health
        elif self.current_health > self.max_health:
            self.current_health = self.max_health
        return self


class Challenge(BaseEidolonModel):
    """
    Runtime challenge model matching current backend format.

    This matches the format expected by segment.py and schema.py.
    """

    attribute: str | None = Field(default=None, alias="Attribute")
    skill: str | None = Field(default=None, alias="Skill")
    difficulty: int = Field(..., ge=1, le=10, alias="Difficulty")
    attempts: int = Field(1, ge=1, alias="Attempts")


class CombatEncounter(BaseEidolonModel):
    """Combat encounter configuration."""

    opponent_ids: list[str] = Field(..., alias="OpponentIDs")
    difficulty_modifier: float = Field(1.0, alias="DifficultyModifier")
    victory_conditions: dict | None = Field(default=None, alias="VictoryConditions")
    defeat_conditions: dict | None = Field(default=None, alias="DefeatConditions")


class SegmentResult(BaseEidolonModel):
    """Result configuration for a segment outcome."""

    next_segment_id: str | None = Field(default=None, alias="NextSegmentID")
    narrative: str = Field(..., alias="Narrative")
    rewards: dict = Field(default_factory=dict, alias="Rewards")
    character_updates: dict | None = Field(default=None, alias="CharacterUpdates")
    unlock_stories: list[str] | None = Field(default=None, alias="UnlockStories")


class DecisionOption(BaseEidolonModel):
    """Decision option within a segment."""

    option_id: str = Field(..., alias="OptionID")
    text: str = Field(..., alias="Text")
    requirements: dict | None = Field(default=None, alias="Requirements")
    next_segment_id: str | None = Field(default=None, alias="NextSegmentID")
    consequences: dict | None = Field(default=None, alias="Consequences")


class StorySegment(BaseEidolonModel):
    """
    Story segment model representing a single unit of story content.

    Segments can be narrative, challenges, combat, or decision points.
    """

    # Identity
    story_id: str = Field(..., alias="StoryID")
    segment_id: str = Field(..., alias="SegmentID")
    segment_type: SegmentType = Field(..., alias="SegmentType")

    # Content
    title: str | None = Field(default=None, alias="Title")
    short_status: str | None = Field(default=None, alias="ShortStatus")
    description: str = Field(..., alias="Description")
    narrative: str | None = Field(default=None, alias="Narrative")

    # Mechanics
    segment_duration: int = Field(60, ge=1, alias="SegmentDuration", description="Duration in seconds")
    challenges: list[Challenge] | None = Field(default=None, alias="Challenges")
    combat: CombatEncounter | None = Field(default=None, alias="Combat")

    # Decisions
    decision_text: str | None = Field(default=None, alias="DecisionText")
    decision_options: dict[str, DecisionOption] | None = Field(default=None, alias="DecisionOptions")
    default_decision: str | None = Field(default=None, alias="DefaultDecision")

    # Flow
    next_segment_id: str | None = Field(default=None, alias="NextSegmentID")
    results: dict[str, SegmentResult] | None = Field(default=None, alias="Results")

    @model_validator(mode="after")
    def validate_segment_type_fields(self) -> "StorySegment":
        """Ensure required fields are present based on segment type."""
        if self.segment_type == SegmentType.CHALLENGE and not self.challenges:
            raise ValueError("Challenge segments must have challenges defined")
        if self.segment_type == SegmentType.COMBAT and not self.combat:
            raise ValueError("Combat segments must have combat configuration")
        if self.segment_type == SegmentType.DECISION and not self.decision_options:
            raise ValueError("Decision segments must have decision options")
        return self


class RewardTier(BaseEidolonModel):
    """Reward tier for story completion."""

    experience: int = Field(0, ge=0, alias="Experience")
    gold: int = Field(0, ge=0, alias="Gold")
    items: list[str] | None = Field(default=None, alias="Items")
    unlock_stories: list[str] | None = Field(default=None, alias="UnlockStories")


class StoryModel(BaseEidolonModel):
    """
    Story model representing a complete story arc.

    Stories contain multiple segments and define the overall
    narrative structure and rewards.
    """

    # Identity
    story_id: str = Field(..., alias="StoryID")
    title: str = Field(..., alias="Title")
    story_type: StoryType = Field(StoryType.SIDE, alias="StoryType")

    # Structure
    first_segment_id: str = Field(..., alias="FirstSegmentID")
    total_segments: int = Field(..., ge=1, alias="TotalSegments")
    estimated_duration: int = Field(..., ge=60, alias="EstimatedDuration", description="Total duration in seconds")

    # Requirements
    prerequisites: dict | None = Field(default=None, alias="Prerequisites")
    minimum_level: int = Field(1, ge=1, alias="MinimumLevel")
    maximum_level: int | None = Field(default=None, ge=1, alias="MaximumLevel")

    # Rewards
    base_xp_multiplier: float = Field(1.0, ge=0.1, alias="BaseXPMultiplier")
    reward_tiers: dict[str, RewardTier] = Field(default_factory=dict, alias="RewardTiers")

    # Metadata
    description: str | None = Field(default=None, alias="Description")
    tags: list[str] | None = Field(default=None, alias="Tags")
    created_at: datetime = Field(..., alias="CreatedAt")
    updated_at: datetime = Field(..., alias="UpdatedAt")


class ActiveSegment(BaseEidolonModel):
    """
    Active segment model for tracking in-progress story segments.

    This model tracks the runtime state of a segment being played
    by a character, including timing, outcomes, and state changes.
    """

    # Identity
    active_segment_id: UUID = Field(..., alias="ActiveSegmentID")
    character_id: UUID = Field(..., alias="CharacterID")
    player_id: UUID = Field(..., alias="PlayerID")
    story_id: str = Field(..., alias="StoryID")
    segment_id: str = Field(..., alias="SegmentID")

    # Timing
    start_time: datetime = Field(..., alias="StartTime")
    end_time: datetime = Field(..., alias="EndTime")
    status: SegmentStatus = Field(SegmentStatus.PENDING, alias="Status")
    processing_status: str | None = Field(default=None, alias="ProcessingStatus")

    # State
    outcome: str | None = Field(default=None, alias="Outcome")
    decision: str | None = Field(default=None, alias="Decision")
    challenge_results: list[dict] | None = Field(default=None, alias="ChallengeResults")
    combat_state: dict | None = Field(default=None, alias="CombatState")

    # Updates
    character_updates: dict | None = Field(default=None, alias="CharacterUpdates")
    client_events: list[dict] | None = Field(default=None, alias="ClientEvents")

    @model_validator(mode="after")
    def validate_timing(self) -> "ActiveSegment":
        """Ensure end time is after start time."""
        if self.end_time <= self.start_time:
            raise ValueError("End time must be after start time")
        return self


# --- Runtime result and event models (for segment processing) ---


class ChallengeAttempt(BaseEidolonModel):
    """Single attempt in a challenge result."""

    effective_score: float = Field(..., alias="EffectiveScore")
    difficulty: int = Field(..., alias="Difficulty")
    sigma: float = Field(..., alias="Sigma")
    success: bool = Field(..., alias="Success")

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, data):
        if isinstance(data, dict):
            # Accept lowerCamelCase
            return {
                "effective_score": data.get("effectiveScore", data.get("EffectiveScore")),
                "difficulty": data.get("difficulty", data.get("Difficulty")),
                "sigma": data.get("sigma", data.get("Sigma")),
                "success": data.get("success", data.get("Success")),
            }
        return data


class ChallengeResultModel(BaseEidolonModel):
    """Challenge resolution result."""

    attribute: str | None = Field(default=None, alias="Attribute")
    skill: str | None = Field(default=None, alias="Skill")
    difficulty: int = Field(..., alias="Difficulty")
    attempts: list[ChallengeAttempt] = Field(default_factory=list, alias="Attempts")
    best_sigma: float = Field(..., alias="BestSigma")
    passed: bool = Field(..., alias="Passed")

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, data):
        if isinstance(data, dict):
            return {
                "attribute": data.get("attribute", data.get("Attribute")),
                "skill": data.get("skill", data.get("Skill")),
                "difficulty": data.get("difficulty", data.get("Difficulty")),
                "attempts": data.get("attempts", data.get("Attempts", [])),
                "best_sigma": data.get("bestSigma", data.get("BestSigma")),
                "passed": data.get("passed", data.get("Passed")),
            }
        return data


class CombatAttack(BaseEidolonModel):
    """An attack entry in a combat round."""

    hit: bool = Field(..., alias="Hit")
    sigma: float = Field(..., alias="Sigma")
    damage: int | None = Field(default=None, alias="Damage")
    damage_type: str | None = Field(default=None, alias="DamageType")

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, data):
        if isinstance(data, dict):
            return {
                "hit": data.get("hit", data.get("Hit")),
                "sigma": data.get("sigma", data.get("Sigma")),
                "damage": data.get("damage", data.get("Damage")),
                "damage_type": data.get("damageType", data.get("DamageType")),
            }
        return data


class CombatRound(BaseEidolonModel):
    """One round of combat log."""

    round: int = Field(..., alias="Round")
    player_attack: CombatAttack | None = Field(default=None, alias="PlayerAttack")
    opponent_attack: CombatAttack | None = Field(default=None, alias="OpponentAttack")

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, data):
        if isinstance(data, dict):
            return {
                "round": data.get("Round", data.get("round")),
                "player_attack": data.get("PlayerAttack", data.get("playerAttack")),
                "opponent_attack": data.get("OpponentAttack", data.get("opponentAttack")),
            }
        return data


class CombatStateModel(BaseEidolonModel):
    """Persisted combat state for active segments/history."""

    round: int = Field(0, alias="Round")
    player_wounds: list[dict] = Field(default_factory=list, alias="PlayerWounds")
    opponent_wounds: list[dict] = Field(default_factory=list, alias="OpponentWounds")
    opponent_health: int | None = Field(default=None, alias="OpponentHealth")
    opponent_id: str | None = Field(default=None, alias="OpponentID")
    combat_log: list[CombatRound] | None = Field(default=None, alias="CombatLog")
    victor: str | None = Field(default=None, alias="Victor")
    opponent_defeated: bool | None = Field(default=None, alias="OpponentDefeated")

    @model_validator(mode="before")
    @classmethod
    def normalize_keys(cls, data):
        if isinstance(data, dict):
            return {
                "round": data.get("Round", data.get("round", data.get("rounds", 0))),
                "player_wounds": data.get("PlayerWounds", data.get("playerWounds", [])),
                "opponent_wounds": data.get("OpponentWounds", data.get("opponentWounds", [])),
                "opponent_health": data.get("OpponentHealth", data.get("opponentHealth")),
                "opponent_id": data.get("OpponentID", data.get("opponentId")),
                "combat_log": data.get("CombatLog", data.get("combatLog")),
                "victor": data.get("Victor", data.get("victor")),
                "opponent_defeated": data.get("OpponentDefeated", data.get("opponentDefeated")),
            }
        return data


class NarrativeData(BaseEidolonModel):
    """Payload for narrative event."""

    outcome: str = Field(..., alias="Outcome")


class ClientEvent(BaseEidolonModel):
    """Client event shape with PascalCase aliases."""

    event_type: str = Field(..., alias="EventType")
    title: str | None = Field(default=None, alias="Title")
    description: str | None = Field(default=None, alias="Description")
    data: dict | BaseEidolonModel | None = Field(default=None, alias="Data")


# Explicit module exports for type checkers and consumers
__all__ = [
    # Base
    "BaseEidolonModel",
    # Characters
    "CharacterModel",
    # Stories/Segments
    "StoryModel",
    "StorySegment",
    "ActiveSegment",
    # Rewards
    "RewardTier",
    # Runtime results and events
    "ChallengeAttempt",
    "ChallengeResultModel",
    "CombatAttack",
    "CombatRound",
    "CombatStateModel",
    "NarrativeData",
    "ClientEvent",
]
