from app.models.academy import Academy
from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.team import Team
from app.models.track import Track

from app.models.base import AppModel


class DataBootstrap(AppModel):
    f1_drivers: list[Driver]
    f2_drivers: list[Driver]
    f1_teams: list[Team]
    f2_teams: list[Team]
    academies: list[Academy]
    tracks: list[Track]
    f1_calendar: list[CalendarRound]
    f2_calendar: list[CalendarRound]
