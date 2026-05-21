from typing import Literal

from app.models.base import AppModel


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


class QualifyingClassification(AppModel):
    position: int
    driver_id: str
    lap_time: float
    gap_to_pole: float
    note: str


class QualifyingResult(AppModel):
    track_id: str
    weather: WeatherState
    classification: list[QualifyingClassification]


class RunningOrderEntry(AppModel):
    position: int
    driver_id: str
    gap_to_leader: float
    gap_to_car_ahead: float
    tire_compound: TireCompound
    tire_age: int
    tire_wear: float
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
