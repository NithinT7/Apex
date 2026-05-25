from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.models.academy import Academy
from app.models.base import AppModel
from app.models.calendar import CalendarRound
from app.models.development_profile import DevelopmentProfile
from app.models.driver import Driver
from app.models.interview import InterviewState
from app.models.race import ActiveRaceState, ActiveWeekendState, WeekendResult
from app.models.rivalry import Rivalry
from app.models.sponsorship import SponsorshipState
from app.models.car_development import TeamDevelopmentState
from app.models.team import Team
from app.models.world import WorldState


CareerPhase = Literal["preseason", "race_week", "between_races", "offseason"]

# Difficulty preset type (matches player_creation.py)
DifficultyPreset = Literal["prodigy", "realistic_prospect", "underdog", "brutal_realism"]


class F1AdaptationProgress(AppModel):
    """Tracks player's F1 rookie adaptation progress."""

    f1_races_completed: int = 0
    adaptation_progress: float = 0.0  # 0-100%
    current_penalty: float = 0.0  # Effective rating penalty
    fully_adapted: bool = False
    first_f1_season: int | None = None  # Season when player entered F1


class AcademyState(AppModel):
    academy_id: str
    trust: int
    junior_depth: list[str] = Field(default_factory=list)
    seat_openings: int = 0
    political_stability: int


class ChampionshipEntry(AppModel):
    driver_id: str
    points: int = 0
    wins: int = 0
    podiums: int = 0
    poles: int = 0
    fastest_laps: int = 0
    dnfs: int = 0
    penalties: int = 0
    average_qualifying: float = 0
    average_finish: float = 0


class ChampionshipState(AppModel):
    driver_standings: list[ChampionshipEntry] = Field(default_factory=list)
    team_standings: dict[str, int] = Field(default_factory=dict)


class NewsItem(AppModel):
    id: str
    date: str
    category: Literal["race", "media", "academy", "rumor", "contract", "incident", "system", "rivalry"]
    headline: str
    body: str
    linked_driver_ids: list[str] = Field(default_factory=list)
    importance: int = 1


class Contract(AppModel):
    id: str
    driver_id: str
    team_id: str
    role: Literal["f1_race_seat", "f1_reserve", "f2_race_seat", "academy_deal", "loan_seat"]
    start_season: int
    length_years: int
    active: bool = True


class DevelopmentState(AppModel):
    available_points: int = 0
    total_earned: int = 0
    spent_points: dict[str, int] = Field(default_factory=dict)


class SaveGame(AppModel):
    save_id: str
    name: str
    created_at: datetime
    updated_at: datetime
    current_date: str
    season: int
    phase: CareerPhase
    player_driver_id: str | None = None
    drivers: list[Driver]
    teams: list[Team]
    academies: list[Academy]
    academy_states: list[AcademyState]
    calendar: list[CalendarRound]
    standings: ChampionshipState
    f1_standings: ChampionshipState | None = None
    news: list[NewsItem] = Field(default_factory=list)
    rivalries: list[Rivalry] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)
    weekend_results: list[WeekendResult] = Field(default_factory=list)
    f1_weekend_results: list[WeekendResult] = Field(default_factory=list)
    development: DevelopmentState = Field(default_factory=DevelopmentState)
    team_development: dict[str, TeamDevelopmentState] = Field(default_factory=dict)
    world_state: WorldState = Field(default_factory=WorldState)
    random_seed: int
    event_flags: dict[str, Any] = Field(default_factory=dict)
    active_race: ActiveRaceState | None = None
    active_weekend: ActiveWeekendState | None = None

    # New development system (coexists with old system during migration)
    development_profile: DevelopmentProfile | None = None

    # Difficulty preset - determines growth potential and development speed
    difficulty: DifficultyPreset = "realistic_prospect"

    # F1 rookie adaptation tracking
    f1_adaptation: F1AdaptationProgress = Field(default_factory=F1AdaptationProgress)

    # Player achievements for cap-breaking bonuses
    player_achievements: list[str] = Field(default_factory=list)

    # Post-race interview system state
    interview_state: InterviewState = Field(default_factory=InterviewState)

    # Sponsorship system state
    sponsorship_state: SponsorshipState | None = None


class SaveSummary(AppModel):
    save_id: str
    name: str
    updated_at: datetime
    season: int
    phase: CareerPhase
    player_driver_id: str | None


class CreateSaveRequest(AppModel):
    name: str | None = None
