from __future__ import annotations

from typing import Literal

from app.models.base import AppModel


TeamSeries = Literal["F1", "F2"]
HiringProfile = Literal[
    "title_contender",
    "big_brand",
    "junior_pipeline",
    "rebuilding",
    "financially_pressured",
    "veteran_stability",
    "high_risk",
    "long_term_project",
]


class Team(AppModel):
    id: str
    name: str
    series: TeamSeries
    country: str
    car_performance: int
    reliability: int
    strategy: int
    development_rate: int
    financial_health: int
    academy_id: str | None = None
    hiring_profile: HiringProfile | None = None
    seat_security: int | None = None
