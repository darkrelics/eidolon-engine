"""
API-facing Pydantic models for Lambda request/response payloads.

These models use PascalCase aliases for serialization and are tolerant of
existing dict-based shapes. They sit on top of core domain models and keep
API wire contracts explicit.
"""

from pydantic import Field

from .models import BaseEidolonModel, ChallengeResultModel, ClientEvent, CombatStateModel


class SegmentStatusResponse(BaseEidolonModel):
    """Response model for the segment status endpoint."""

    active_segment_id: str = Field(..., alias="ActiveSegmentID")
    story_id: str = Field(..., alias="StoryID")
    segment_id: str = Field(..., alias="SegmentID")
    status: str = Field(..., alias="Status")
    is_complete: bool = Field(..., alias="IsComplete")
    time_remaining: int = Field(..., alias="TimeRemaining")
    end_time: str = Field(..., alias="EndTime")

    # Optional details when complete
    challenge_results: list[ChallengeResultModel | dict] | None = Field(default=None, alias="ChallengeResults")
    outcome: str | None = Field(default=None, alias="Outcome")
    decision: str | None = Field(default=None, alias="Decision")
    combat_state: CombatStateModel | dict | None = Field(default=None, alias="CombatState")
    healing_applied: bool | None = Field(default=None, alias="HealingApplied")


class SegmentHistoryItem(BaseEidolonModel):
    """One entry in a character's segment history."""

    active_segment_id: str | None = Field(default=None, alias="ActiveSegmentID")
    segment_id: str | None = Field(default=None, alias="SegmentID")
    segment_type: str | None = Field(default=None, alias="SegmentType")
    status: str | None = Field(default=None, alias="Status")
    processing_status: str | None = Field(default=None, alias="ProcessingStatus")
    start_time: str | None = Field(default=None, alias="StartTime")
    end_time: str | None = Field(default=None, alias="EndTime")

    # Enriched data for clients
    outcome: str | None = Field(default=None, alias="Outcome")
    client_events: list[ClientEvent | dict] | None = Field(default=None, alias="ClientEvents")
    character_updates: dict | None = Field(default=None, alias="CharacterUpdates")
    decision: str | None = Field(default=None, alias="Decision")
    challenge_results: list[ChallengeResultModel | dict] | None = Field(default=None, alias="ChallengeResults")
    skill_xp_awarded: dict | None = Field(default=None, alias="SkillXPAwarded")
    attribute_xp_awarded: dict | None = Field(default=None, alias="AttributeXPAwarded")
    combat_state: CombatStateModel | dict | None = Field(default=None, alias="CombatState")
    next_segment_id: str | None = Field(default=None, alias="NextSegmentID")


class SegmentHistoryResponse(BaseEidolonModel):
    """Response model for the segment history endpoint."""

    character_id: str = Field(..., alias="CharacterID")
    story_id: str | None = Field(default=None, alias="StoryID")
    segments: list[SegmentHistoryItem] = Field(default_factory=list, alias="Segments")
