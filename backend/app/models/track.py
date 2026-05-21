from app.models.base import AppModel


class Track(AppModel):
    id: str
    name: str
    country: str
    base_lap_time: float
    overtaking_difficulty: int
    tire_deg: int
    safety_car_chance: int
    rain_chance: int
    qualifying_importance: int
    street_circuit: bool
    drs_strength: int
    setup_complexity: int
