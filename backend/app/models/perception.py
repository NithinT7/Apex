from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


PerceptionSignalType = Literal[
    "race_result",
    "qualifying",
    "strategy",
    "media",
    "rivalry",
    "academy",
    "contract",
    "incident",
    "development",
]


class PerceptionSignal(AppModel):
    id: str
    date: str
    signal_type: PerceptionSignalType
    label: str
    impact: int = 0
    source_id: str | None = None
    notes: str | None = None


class TeamInterestProfile(AppModel):
    team_id: str
    interest_level: int = 0
    fit_score: int = 0
    reasons: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    last_updated: str | None = None


class MediaNarrative(AppModel):
    id: str
    title: str
    status: Literal["emerging", "active", "fading", "resolved"] = "emerging"
    sentiment: Literal["positive", "neutral", "negative", "mixed"] = "neutral"
    intensity: int = 0
    linked_signal_ids: list[str] = Field(default_factory=list)
    started_date: str | None = None
    last_updated: str | None = None


class PaddockPerception(AppModel):
    media_rating_history: list[dict[str, int | str]] = Field(default_factory=list)
    perception_tags: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    team_interest: dict[str, TeamInterestProfile] = Field(default_factory=dict)
    reputation_signals: list[PerceptionSignal] = Field(default_factory=list)
    marketability_signals: list[PerceptionSignal] = Field(default_factory=list)
    narratives: list[MediaNarrative] = Field(default_factory=list)
