"""Models for between-race activities."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


ActivityType = Literal[
    "rest",
    "simulator",
    "physical_training",
    "media_appearance",
    "sponsor_event",
    "team_debrief",
    "academy_meeting",
    "fan_engagement",
    "mental_coaching",
]


class ActivityEffect(AppModel):
    """Effects an activity has on driver stats."""

    fatigue: int = 0  # Positive = more tired, negative = recovery
    morale: int = 0
    form: int = 0
    academy_trust: int = 0
    reputation: int = 0
    sponsor_value: int = 0


class Activity(AppModel):
    """An activity a driver can perform between races."""

    id: str
    name: str
    type: ActivityType
    description: str
    duration_days: int = 1
    base_effects: ActivityEffect
    risk_chance: float = 0  # Chance of negative outcome (0-1)
    risk_effects: ActivityEffect | None = None
    requirements: dict[str, int] = Field(default_factory=dict)  # e.g., {"fatigue": 50} = must have <50 fatigue


class ActivityOutcome(AppModel):
    """Result of performing an activity."""

    activity_id: str
    activity_name: str
    success: bool
    narrative: str
    effects_applied: ActivityEffect


class AvailableActivities(AppModel):
    """Activities available to the player between races."""

    days_until_next_race: int
    activities: list[Activity]
    completed_activities: list[str] = Field(default_factory=list)  # IDs of activities done this break
