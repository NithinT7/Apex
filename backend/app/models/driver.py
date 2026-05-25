from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel
from app.models.perception import PaddockPerception


DriverSeries = Literal["F1", "F2", "Reserve", "Other"]


class DriverAttributes(AppModel):
    pace: int
    qualifying: int
    racecraft: int
    tire_management: int
    wet_weather: int
    consistency: int
    starts: int
    awareness: int
    adaptability: int
    technical_feedback: int
    pressure: int
    confidence: int
    composure: int
    aggression: int
    discipline: int
    focus: int
    reputation: int
    marketability: int
    sponsor_value: int


class HiddenDriverAttributes(AppModel):
    potential: int
    development_rate: int
    clutch_factor: int
    crash_proneness: int
    loyalty: int
    adaptation_ceiling: int
    retirement_chance: int = 0


class CareerStats(AppModel):
    wins: int = 0
    podiums: int = 0
    poles: int = 0
    fastest_laps: int = 0
    dnfs: int = 0
    penalties: int = 0


class DriverIdentity(AppModel):
    primary_trait: str | None = None
    trait_scores: dict[str, int] = Field(default_factory=dict)
    summary: str = "Profile still forming"
    last_updated_round: str | None = None


class Driver(AppModel):
    id: str
    name: str
    nationality: str
    age: int
    driver_number: int | None = None
    series: DriverSeries
    team_id: str
    academy_id: str | None = None
    attributes: DriverAttributes
    hidden: HiddenDriverAttributes
    career: CareerStats = CareerStats()
    identity: DriverIdentity = Field(default_factory=DriverIdentity)
    paddock_perception: PaddockPerception = Field(default_factory=PaddockPerception)
    current_form: int = 50
    fatigue: int = 0
    morale: int = 50
