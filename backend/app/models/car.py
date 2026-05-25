from __future__ import annotations

from pydantic import Field

from app.models.base import AppModel


def _clamp_rating(value: int) -> int:
    return max(1, min(100, value))


class CarPerformanceProfile(AppModel):
    overall_performance: int = 75
    aero_efficiency: int = 75
    low_speed_cornering: int = 75
    medium_speed_cornering: int = 75
    high_speed_cornering: int = 75
    straight_line_speed: int = 75
    traction: int = 75
    tire_wear: int = 75
    tire_warmup: int = 75
    reliability: int = 75
    cooling: int = 75
    setup_window: int = 75
    upgrade_potential: int = 75
    development_rate: int = 75
    strategy_team: int = 75
    pit_crew: int = 75

    @classmethod
    def from_legacy(
        cls,
        *,
        overall_performance: int,
        reliability: int,
        strategy: int,
        development_rate: int,
        financial_health: int | None = None,
    ) -> "CarPerformanceProfile":
        """Derive a detailed profile from the old team ratings."""
        overall = _clamp_rating(overall_performance)
        reliability_rating = _clamp_rating(reliability)
        strategy_rating = _clamp_rating(strategy)
        development = _clamp_rating(development_rate)
        financial = _clamp_rating(financial_health if financial_health is not None else development)
        aero = _clamp_rating(round(overall * 0.68 + development * 0.17 + strategy_rating * 0.08 + financial * 0.07))
        mechanical = _clamp_rating(round(overall * 0.68 + reliability_rating * 0.18 + strategy_rating * 0.14))

        return cls(
            overall_performance=overall,
            aero_efficiency=aero,
            low_speed_cornering=mechanical,
            medium_speed_cornering=_clamp_rating(round((aero + mechanical) / 2)),
            high_speed_cornering=aero,
            straight_line_speed=_clamp_rating(round(overall * 0.74 + reliability_rating * 0.10 + development * 0.08 + financial * 0.08)),
            traction=mechanical,
            tire_wear=_clamp_rating(round(overall * 0.45 + strategy_rating * 0.35 + reliability_rating * 0.20)),
            tire_warmup=_clamp_rating(round(overall * 0.58 + strategy_rating * 0.27 + reliability_rating * 0.15)),
            reliability=reliability_rating,
            cooling=_clamp_rating(round(reliability_rating * 0.70 + overall * 0.20 + strategy_rating * 0.10)),
            setup_window=_clamp_rating(round(strategy_rating * 0.55 + overall * 0.30 + development * 0.15)),
            upgrade_potential=_clamp_rating(round(development * 0.72 + financial * 0.28)),
            development_rate=development,
            strategy_team=strategy_rating,
            pit_crew=_clamp_rating(round(strategy_rating * 0.72 + reliability_rating * 0.18 + overall * 0.10)),
        )


class CarComponentReliability(AppModel):
    power_unit: int = 75
    gearbox: int = 75
    hydraulics: int = 75
    electronics: int = 75
    cooling_system: int = 75
    suspension: int = 75
    brakes: int = 75

    @classmethod
    def from_legacy(cls, reliability: int) -> "CarComponentReliability":
        rating = _clamp_rating(reliability)
        return cls(
            power_unit=rating,
            gearbox=rating,
            hydraulics=rating,
            electronics=rating,
            cooling_system=rating,
            suspension=rating,
            brakes=rating,
        )


class TeamCarState(AppModel):
    team_id: str | None = None
    season: int | None = None
    profile: CarPerformanceProfile = Field(default_factory=CarPerformanceProfile)
    component_reliability: CarComponentReliability = Field(default_factory=CarComponentReliability)
    component_wear: dict[str, int] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class TrackCarDemandProfile(AppModel):
    track_id: str
    low_speed_importance: int = 50
    medium_speed_importance: int = 50
    high_speed_importance: int = 50
    straight_line_importance: int = 50
    traction_importance: int = 50
    tire_deg_importance: int = 50
    cooling_stress: int = 50
    setup_complexity: int = 50
