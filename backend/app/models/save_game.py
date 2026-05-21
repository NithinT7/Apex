from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.academy import Academy
from app.models.base import AppModel
from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.race import ActiveRaceState, WeekendResult
from app.models.rivalry import Rivalry
from app.models.team import Team


CareerPhase = Literal["preseason", "race_week", "between_races", "offseason"]


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
    news: list[NewsItem] = Field(default_factory=list)
    rivalries: list[Rivalry] = Field(default_factory=list)
    contracts: list[Contract] = Field(default_factory=list)
    weekend_results: list[WeekendResult] = Field(default_factory=list)
    random_seed: int
    event_flags: dict[str, bool] = Field(default_factory=dict)
    active_race: ActiveRaceState | None = None


class SaveSummary(AppModel):
    save_id: str
    name: str
    updated_at: datetime
    season: int
    phase: CareerPhase
    player_driver_id: str | None


class CreateSaveRequest(AppModel):
    name: str | None = None
