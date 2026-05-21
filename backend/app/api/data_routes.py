from fastapi import APIRouter

from app.data.loaders import (
    get_academies,
    get_bootstrap,
    get_f2_calendar,
    get_f2_drivers,
    get_f2_teams,
    get_f1_drivers,
    get_f1_teams,
    get_tracks,
)
from app.models.academy import Academy
from app.models.bootstrap import DataBootstrap
from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.team import Team
from app.models.track import Track


router = APIRouter(prefix="/data", tags=["data"])


@router.get("/bootstrap", response_model=DataBootstrap)
def bootstrap() -> DataBootstrap:
    return get_bootstrap()


@router.get("/drivers/f1", response_model=list[Driver])
def f1_drivers() -> list[Driver]:
    return get_f1_drivers()


@router.get("/drivers/f2", response_model=list[Driver])
def f2_drivers() -> list[Driver]:
    return get_f2_drivers()


@router.get("/teams/f1", response_model=list[Team])
def f1_teams() -> list[Team]:
    return get_f1_teams()


@router.get("/teams/f2", response_model=list[Team])
def f2_teams() -> list[Team]:
    return get_f2_teams()


@router.get("/academies", response_model=list[Academy])
def academies() -> list[Academy]:
    return get_academies()


@router.get("/tracks", response_model=list[Track])
def tracks() -> list[Track]:
    return get_tracks()


@router.get("/calendar/f2", response_model=list[CalendarRound])
def f2_calendar() -> list[CalendarRound]:
    return get_f2_calendar()
