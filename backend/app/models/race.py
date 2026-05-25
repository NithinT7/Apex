from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel
from app.models.strategy import (
    PitStopEvent,
    RaceStrategyPlan,
    SafetyCarDecisionContext,
    StintSummary,
    StrategyCall,
)
from app.models.car_development import PracticeCorrelationReport


SessionType = Literal["practice", "qualifying", "sprint", "feature"]
TireCompound = Literal["soft", "medium", "hard", "inter", "wet"]
RunnerStatus = Literal["running", "dnf"]
WeatherCondition = Literal["dry", "damp", "wet"]
DecisionType = Literal["start", "attack", "defend", "tires", "strategy", "safety_car", "weather", "late_pressure"]


class WeatherState(AppModel):
    condition: WeatherCondition
    air_temp: int
    track_temp: int
    rain_intensity: int = 0
    track_grip: int = 70


class PracticeClassification(AppModel):
    position: int
    driver_id: str
    lap_time: float
    setup_score: int
    note: str


class PracticeResult(AppModel):
    track_id: str
    weather: WeatherState
    classification: list[PracticeClassification]
    correlation_reports: list[PracticeCorrelationReport] = Field(default_factory=list)


class QualifyingClassification(AppModel):
    position: int
    driver_id: str
    lap_time: float
    gap_to_pole: float
    note: str


class QualifyingSegment(AppModel):
    """Single qualifying segment (Q1, Q2, or Q3)."""
    segment: Literal["Q1", "Q2", "Q3"]
    classification: list[QualifyingClassification]
    eliminated: list[str]  # Driver IDs eliminated in this segment
    stories: list[str]  # Narrative moments from this segment


class QualifyingResult(AppModel):
    track_id: str
    weather: WeatherState
    classification: list[QualifyingClassification]  # Final overall classification
    segments: list[QualifyingSegment] | None = None  # Q1/Q2/Q3 breakdown (F1 only)


class RunningOrderEntry(AppModel):
    position: int
    driver_id: str
    gap_to_leader: float
    gap_to_car_ahead: float
    current_lap_time: float | None = None
    previous_lap_time: float | None = None
    best_lap_time: float | None = None
    tire_compound: TireCompound
    tire_age: int
    tire_wear: float
    component_wear: float = 0
    status: RunnerStatus


class DecisionChoice(AppModel):
    id: str
    label: str
    risk: int
    effects: dict[str, int | float | str]


class DecisionPrompt(AppModel):
    id: str
    lap: int
    type: DecisionType
    title: str
    description: str
    default_choice_id: str
    choices: list[DecisionChoice]


class LapSnapshot(AppModel):
    lap: int
    running_order: list[RunningOrderEntry]
    commentary: list[str]
    safety_car: bool
    weather: WeatherState
    decision_prompt: DecisionPrompt | None = None


class RaceClassification(AppModel):
    position: int
    driver_id: str
    status: RunnerStatus
    total_time: float
    gap_to_winner: float
    points: int
    pit_stops: int
    fastest_lap: float


class RaceResult(AppModel):
    race_id: str
    session_type: Literal["sprint", "feature"]
    track_id: str
    total_laps: int
    starting_grid: list[str]
    classification: list[RaceClassification]
    lap_log: list[LapSnapshot]
    decision_prompts: list[DecisionPrompt]
    safety_car_laps: list[int]
    dnfs: list[str]
    strategy_plans: list[RaceStrategyPlan] = Field(default_factory=list)
    pit_stop_events: list[PitStopEvent] = Field(default_factory=list)
    stint_summaries: list[StintSummary] = Field(default_factory=list)
    strategy_calls: list[StrategyCall] = Field(default_factory=list)
    safety_car_decisions: list[SafetyCarDecisionContext] = Field(default_factory=list)


class WeekendResult(AppModel):
    save_id: str
    round_id: str
    track_id: str
    completed: bool
    practice: PracticeResult
    qualifying: QualifyingResult
    sprint: RaceResult
    feature: RaceResult
    headline: str


# Interactive race models for player decisions


class DecisionOutcome(AppModel):
    """Result of a player's decision."""

    decision_id: str
    choice_id: str
    choice_label: str
    pace_modifier: float
    tire_wear_modifier: float
    incident_risk_modifier: float
    narrative: str


class PendingDecision(AppModel):
    """A decision awaiting player input."""

    prompt: DecisionPrompt
    race_type: Literal["sprint", "feature"]
    expires_at_lap: int


class DecisionResponse(AppModel):
    """Player's response to a decision prompt."""

    decision_id: str
    choice_index: int  # 0, 1, or 2


class ActiveRaceState(AppModel):
    """State for a race in progress with interactive decisions."""

    save_id: str
    round_id: str
    race_type: Literal["sprint", "feature"]
    current_lap: int
    total_laps: int
    lap_snapshots: list[LapSnapshot]
    pending_decision: PendingDecision | None = None
    decision_history: list[DecisionOutcome]
    is_complete: bool
    player_position: int | None = None
    player_tire_wear: float = 0
    safety_car_active: bool = False


WeekendPhase = Literal["not_started", "practice", "qualifying", "sprint", "feature", "complete"]


class ActiveWeekendState(AppModel):
    """Tracks progress through a race weekend."""

    round_id: str
    phase: WeekendPhase = "not_started"
    practice_result: PracticeResult | None = None
    qualifying_result: QualifyingResult | None = None
    sprint_result: RaceResult | None = None
    feature_result: RaceResult | None = None
    has_sprint: bool = False


class PreRaceStorylineView(AppModel):
    """A storyline heading into a race weekend."""

    id: str
    type: str
    headline: str
    narrative: str
    drama_level: int
    driver_ids: list[str]
    team_ids: list[str]


class ChampionshipContext(AppModel):
    """Championship context for the weekend."""

    player_position: int | None = None
    points_to_leader: int = 0
    points_to_next: int = 0
    points_from_behind: int = 0
    rounds_remaining: int = 0
    title_in_reach: bool = False
    relegation_danger: bool = False


class TrackPreview(AppModel):
    """Track information for weekend preview."""

    id: str
    name: str
    country: str
    overtaking_difficulty: int
    tire_deg: int
    safety_car_chance: int
    rain_chance: int
    qualifying_importance: int
    street_circuit: bool


class WeekendPreview(AppModel):
    """Complete pre-race weekend preview with storylines and context."""

    save_id: str
    round_id: str
    round_name: str
    round_number: int
    series: str
    has_sprint: bool
    track: TrackPreview
    storylines: list[PreRaceStorylineView]
    championship_context: ChampionshipContext
    player_form: int | None = None
    player_morale: int | None = None
    teammate_name: str | None = None
    weather_forecast: WeatherState | None = None
