from typing import Literal

from app.models.base import AppModel


SessionType = Literal["practice", "qualifying", "sprint", "feature"]
TireCompound = Literal["soft", "medium", "hard", "inter", "wet"]
RunnerStatus = Literal["running", "dnf"]
WeatherCondition = Literal["dry", "damp", "wet"]


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


class LapSnapshot(AppModel):
    lap: int
    running_order: list[RunningOrderEntry]
    commentary: list[str]
    safety_car: bool
    weather: WeatherState


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
