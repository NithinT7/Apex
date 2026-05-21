from typing import Literal

from app.models.base import AppModel


class CalendarRound(AppModel):
    id: str
    round_number: int
    name: str
    track_id: str
    start_date: str
    end_date: str
    country: str
    series: Literal["F2"]
    has_sprint: bool
    completed: bool = False
