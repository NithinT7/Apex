"""Models for the post-race interview system."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


# Interview trigger types
InterviewTrigger = Literal[
    "race_win",
    "podium",
    "pole_position",
    "major_crash",
    "penalty_received",
    "team_orders",
    "strategy_controversy",
    "rival_incident",
    "big_recovery",
    "underperformance",
    "academy_evaluation",
    "first_f1_race",
    "first_f1_points",
    "championship_leader",
    "championship_clinch",
    "first_career_win",
    "first_career_podium",
    "dnf_mechanical",
    "dnf_collision",
    "teammate_battle",
    "contract_speculation",
]


# Risk levels for interview choices
RiskLevel = Literal["safe", "moderate", "risky", "controversial"]


class InterviewEffect(AppModel):
    """Effects of an interview choice."""

    # Direct attribute changes (capped to reasonable ranges)
    marketability: int = 0
    reputation: int = 0
    confidence: int = 0
    morale: int = 0

    # Relationship changes
    team_trust: int = 0  # With current team
    academy_trust: int = 0  # With academy (if any)
    fan_support: int = 0  # General popularity

    # Narrative effects
    rivalry_intensity: int = 0  # Increase/decrease active rivalry
    rumor_intensity: int = 0  # How much media speculation this generates
    sponsor_interest: int = 0  # Affects future sponsor value

    # XP gains
    media_xp: int = 0  # media_marketability branch XP

    # Perception tags to add (positive or negative)
    perception_tags: list[str] = Field(default_factory=list)

    # News narrative style
    narrative_tone: Literal["positive", "neutral", "negative", "controversial"] = "neutral"


class InterviewChoice(AppModel):
    """A single choice in an interview question."""

    id: str
    text: str
    tone: Literal["diplomatic", "honest", "deflecting", "aggressive", "humble", "confident"]
    effects: InterviewEffect
    risk_level: RiskLevel = "safe"
    follow_up_headline: str  # News headline if this choice is selected
    follow_up_body: str  # News body text
    hidden_effects_hint: str | None = None  # Vague hint for player ("May affect team relationship")


class InterviewQuestion(AppModel):
    """A single interview question with choices."""

    id: str
    trigger: InterviewTrigger
    reporter_name: str = "Sky Sports Reporter"
    question: str
    context: str  # Background for the question
    choices: list[InterviewChoice]
    priority: int = 1  # Higher = more likely to be selected when multiple triggers
    requires_academy: bool = False  # Only show if player has academy
    requires_rival: bool = False  # Only show if player has active rival
    requires_f1: bool = False  # Only show if player is in F1
    requires_f2: bool = False  # Only show if player is in F2


class PendingInterview(AppModel):
    """An interview waiting for player response."""

    id: str
    round_id: str
    trigger: InterviewTrigger
    question: InterviewQuestion
    context_data: dict = Field(default_factory=dict)  # Dynamic context (rival name, team name, etc.)
    created_date: str
    expires_after_round: str | None = None  # Interview expires if not answered by this round


class InterviewResponse(AppModel):
    """Record of a completed interview."""

    interview_id: str
    round_id: str
    trigger: InterviewTrigger
    question_id: str
    choice_id: str
    choice_text: str
    effects_applied: InterviewEffect
    news_headline: str
    news_body: str
    response_date: str


class InterviewState(AppModel):
    """Tracks all interview-related state for a save."""

    pending_interviews: list[PendingInterview] = Field(default_factory=list)
    interview_history: list[InterviewResponse] = Field(default_factory=list)
    total_interviews_completed: int = 0
    # Track cooldowns for certain triggers
    last_trigger_round: dict[str, str] = Field(default_factory=dict)
