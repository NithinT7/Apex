from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


TireCompoundName = Literal["soft", "medium", "hard", "inter", "wet"]


class StrategyCall(AppModel):
    id: str
    lap: int
    call_type: Literal["pit", "stay_out", "push", "manage", "compound_switch", "safety_car"] = "manage"
    recommendation: str
    selected: bool = False
    expected_delta: float | None = None
    actual_delta: float | None = None
    notes: str | None = None


class PitStopEvent(AppModel):
    id: str
    driver_id: str
    lap: int
    compound_in: TireCompoundName | None = None
    compound_out: TireCompoundName
    pit_loss: float | None = None
    under_safety_car: bool = False
    reason: str | None = None


class StintSummary(AppModel):
    driver_id: str
    stint_number: int
    start_lap: int
    end_lap: int
    compound: TireCompoundName
    average_lap_time: float | None = None
    tire_wear_start: float | None = None
    tire_wear_end: float | None = None
    notes: str | None = None


class SafetyCarDecisionContext(AppModel):
    id: str
    lap: int
    mode: Literal["vsc", "safety_car"]
    trigger: str | None = None
    pit_window_open: bool = False
    projected_position_if_pit: int | None = None
    projected_position_if_stay_out: int | None = None
    decision: Literal["pit", "stay_out", "no_call"] = "no_call"


class RaceStrategyPlan(AppModel):
    driver_id: str
    planned_stops: int = 0
    planned_pit_laps: list[int] = Field(default_factory=list)
    starting_compound: TireCompoundName | None = None
    target_compounds: list[TireCompoundName] = Field(default_factory=list)
    strategy_style: Literal["aggressive", "balanced", "conservative", "reactive", "long_run"] = "balanced"
    notes: str | None = None


class KeyIncident(AppModel):
    """Notable incident during the race."""

    lap: int
    type: Literal["crash", "mechanical", "pit_stop", "safety_car", "overtake", "mistake"] = "crash"
    driver_id: str | None = None
    description: str
    impact: str | None = None


class StrategySummary(AppModel):
    """Summary of overall race strategy execution."""

    total_pit_stops: int
    safety_car_count: int
    vsc_count: int
    drivers_who_pitted_under_sc: list[str] = Field(default_factory=list)
    one_stop_drivers: list[str] = Field(default_factory=list)
    two_stop_drivers: list[str] = Field(default_factory=list)
    three_plus_stop_drivers: list[str] = Field(default_factory=list)
    average_stint_length: float | None = None
    most_used_compound: TireCompoundName | None = None


class RaceAnalysis(AppModel):
    """Complete race strategy analysis."""

    save_id: str
    round_id: str
    race_type: Literal["sprint", "feature"]
    total_laps: int
    strategy_plans: list[RaceStrategyPlan] = Field(default_factory=list)
    pit_stop_events: list[PitStopEvent] = Field(default_factory=list)
    stint_summaries: list[StintSummary] = Field(default_factory=list)
    strategy_calls: list[StrategyCall] = Field(default_factory=list)
    safety_car_decisions: list[SafetyCarDecisionContext] = Field(default_factory=list)
    key_incidents: list[KeyIncident] = Field(default_factory=list)
    strategy_summary: StrategySummary | None = None
