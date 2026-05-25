from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


class WorldEvent(AppModel):
    id: str
    date: str
    category: Literal["race", "media", "rumor", "contract", "politics", "development", "incident", "system"]
    title: str
    summary: str
    importance: int = 1
    linked_driver_ids: list[str] = Field(default_factory=list)
    linked_team_ids: list[str] = Field(default_factory=list)
    resolved: bool = False


class NarrativeArc(AppModel):
    id: str
    title: str
    category: Literal["championship", "market", "rivalry", "team_politics", "development", "media"]
    status: Literal["emerging", "active", "fading", "resolved"] = "emerging"
    intensity: int = 0
    started_date: str | None = None
    last_updated: str | None = None
    linked_event_ids: list[str] = Field(default_factory=list)
    linked_driver_ids: list[str] = Field(default_factory=list)
    linked_team_ids: list[str] = Field(default_factory=list)


class RumorLifecycle(AppModel):
    id: str
    topic: str
    status: Literal["whisper", "reported", "hot", "denied", "confirmed", "dead"] = "whisper"
    likelihood: int = 0
    source_confidence: int = 0
    started_date: str | None = None
    last_updated: str | None = None
    linked_driver_ids: list[str] = Field(default_factory=list)
    linked_team_ids: list[str] = Field(default_factory=list)


class TransferRumorState(AppModel):
    id: str
    driver_id: str
    from_team_id: str | None = None
    to_team_id: str
    transfer_type: Literal["promotion", "lateral", "demotion", "new_signing", "retirement"]
    likelihood: int = 0
    reason: str
    status: Literal["active", "confirmed", "denied", "expired"] = "active"
    created_date: str | None = None
    resolved_date: str | None = None


class TeamPoliticsState(AppModel):
    team_id: str
    stability: int = 70
    board_pressure: int = 30
    driver_pressure: dict[str, int] = Field(default_factory=dict)
    budget_pressure: int = 30
    technical_confidence: int = 70
    active_issues: list[str] = Field(default_factory=list)


FinancialEventType = Literal[
    "bankruptcy",           # Team goes bankrupt, replaced by new entrant
    "takeover",             # New ownership, budget and identity change
    "cash_injection",       # Major investment boost
    "manufacturer_entry",   # New manufacturer joins as team/partner
    "manufacturer_exit",    # Manufacturer withdraws support
    "title_sponsor_loss",   # Major sponsor leaves
    "title_sponsor_gain",   # New major sponsor arrives
]


class PotentialEntrant(AppModel):
    """A manufacturer or team that could enter F1."""
    id: str
    name: str
    country: str
    entrant_type: Literal["manufacturer", "privateer", "consortium"]
    base_budget: int  # Financial health if they enter (60-95)
    base_development: int  # Development rate (65-90)
    likelihood_modifier: int = 0  # Adjusts base entry chance (-20 to +20)
    interested: bool = True  # Still interested in F1
    last_considered_season: int | None = None


class FinancialEvent(AppModel):
    """A major financial event affecting a team."""
    id: str
    season: int
    event_type: FinancialEventType
    team_id: str
    new_team_id: str | None = None  # If team is replaced
    entrant_id: str | None = None  # Which entrant took over/entered
    budget_change: int = 0  # Change to financial_health
    development_change: int = 0  # Change to development_rate
    headline: str
    description: str


class WorldState(AppModel):
    events: list[WorldEvent] = Field(default_factory=list)
    narrative_arcs: list[NarrativeArc] = Field(default_factory=list)
    rumor_lifecycles: list[RumorLifecycle] = Field(default_factory=list)
    transfer_rumors: list[TransferRumorState] = Field(default_factory=list)
    team_politics: dict[str, TeamPoliticsState] = Field(default_factory=dict)
    # Financial events and potential entrants
    financial_events: list[FinancialEvent] = Field(default_factory=list)
    potential_entrants: list[PotentialEntrant] = Field(default_factory=list)
