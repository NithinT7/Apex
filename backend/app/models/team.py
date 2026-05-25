from __future__ import annotations

from typing import Literal

from app.models.base import AppModel
from app.models.car import CarPerformanceProfile, TeamCarState


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
    car_state: TeamCarState | None = None

    def effective_car_profile(self) -> CarPerformanceProfile:
        if self.car_state is not None:
            return self.car_state.profile
        return CarPerformanceProfile.from_legacy(
            overall_performance=self.car_performance,
            reliability=self.reliability,
            strategy=self.strategy,
            development_rate=self.development_rate,
            financial_health=self.financial_health,
        )
