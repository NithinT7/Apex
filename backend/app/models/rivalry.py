"""Models for driver rivalries."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.base import AppModel


RivalryType = Literal[
    "teammate",      # Competition within the same team
    "championship",  # Fighting for championship position
    "historical",    # Past incident or grudge
    "promotional",   # Competing for same F1 seat
    "personal",      # Off-track conflict
]

RivalryIntensity = Literal["mild", "moderate", "intense", "bitter"]


class RivalryEvent(AppModel):
    """A specific event that affected a rivalry."""

    id: str
    date: datetime
    description: str
    intensity_change: int  # How much this affected the rivalry (-10 to +10)
    category: Literal["on_track", "off_track", "media", "team"]


class Rivalry(AppModel):
    """A rivalry between the player and another driver."""

    id: str
    opponent_id: str  # The other driver in the rivalry
    rivalry_type: RivalryType
    intensity: int = Field(ge=0, le=100)  # 0=friendly, 100=bitter
    respect: int = Field(ge=0, le=100)  # Mutual respect level
    started_date: datetime
    recent_events: list[RivalryEvent] = Field(default_factory=list)
    is_active: bool = True


class RivalryTrigger(AppModel):
    """A trigger condition for rivalry events."""

    trigger_type: Literal[
        "overtake",
        "collision",
        "battle",
        "championship_swing",
        "media_comment",
        "team_preference",
    ]
    intensity_modifier: int  # Base intensity change
    context: str  # Description of what happened


class RivalryStatus(AppModel):
    """Summary of player's rivalries for display."""

    rivalries: list[Rivalry]
    most_intense: Rivalry | None = None
    teammate_rivalry: Rivalry | None = None
