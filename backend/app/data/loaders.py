import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from app.models.academy import Academy
from app.models.bootstrap import DataBootstrap
from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.player_creation import DriverArchetype, DriverBackground
from app.models.team import Team
from app.models.track import Track


DATA_DIR = Path(__file__).resolve().parent
T = TypeVar("T")


def _load_json(filename: str) -> object:
    return json.loads((DATA_DIR / filename).read_text(encoding="utf-8"))


def _load_list(filename: str, model_type: type[T]) -> list[T]:
    adapter = TypeAdapter(list[model_type])
    return adapter.validate_python(_load_json(filename))


@lru_cache
def get_f1_drivers() -> list[Driver]:
    return _load_list("f1_drivers_2026.json", Driver)


@lru_cache
def get_f2_drivers() -> list[Driver]:
    return _load_list("f2_drivers_2026.json", Driver)


@lru_cache
def get_f1_teams() -> list[Team]:
    return _load_list("f1_teams_2026.json", Team)


@lru_cache
def get_f2_teams() -> list[Team]:
    return _load_list("f2_teams_2026.json", Team)


@lru_cache
def get_academies() -> list[Academy]:
    return _load_list("academies.json", Academy)


@lru_cache
def get_tracks() -> list[Track]:
    return _load_list("tracks.json", Track)


@lru_cache
def get_f2_calendar() -> list[CalendarRound]:
    return _load_list("calendar_f2_2026.json", CalendarRound)


@lru_cache
def get_f1_calendar() -> list[CalendarRound]:
    return _load_list("calendar_f1_2026.json", CalendarRound)


@lru_cache
def get_driver_backgrounds() -> list[DriverBackground]:
    return _load_list("driver_backgrounds.json", DriverBackground)


@lru_cache
def get_driver_archetypes() -> list[DriverArchetype]:
    return _load_list("driver_archetypes.json", DriverArchetype)


def get_bootstrap() -> DataBootstrap:
    return DataBootstrap(
        f1_drivers=get_f1_drivers(),
        f2_drivers=get_f2_drivers(),
        f1_teams=get_f1_teams(),
        f2_teams=get_f2_teams(),
        academies=get_academies(),
        tracks=get_tracks(),
        f1_calendar=get_f1_calendar(),
        f2_calendar=get_f2_calendar(),
    )


def validate_data_references() -> list[str]:
    errors: list[str] = []
    teams = {team.id for team in [*get_f1_teams(), *get_f2_teams()]}
    academies = {academy.id for academy in get_academies()}
    tracks = {track.id for track in get_tracks()}

    for driver in [*get_f1_drivers(), *get_f2_drivers()]:
        if driver.team_id not in teams:
            errors.append(f"{driver.id} references missing team {driver.team_id}")
        if driver.academy_id is not None and driver.academy_id not in academies:
            errors.append(f"{driver.id} references missing academy {driver.academy_id}")

    for team in [*get_f1_teams(), *get_f2_teams()]:
        if team.academy_id is not None and team.academy_id not in academies:
            errors.append(f"{team.id} references missing academy {team.academy_id}")

    for academy in get_academies():
        if academy.f1_team_id is not None and academy.f1_team_id not in teams:
            errors.append(f"{academy.id} references missing F1 team {academy.f1_team_id}")

    for calendar_round in get_f2_calendar():
        if calendar_round.track_id not in tracks:
            errors.append(f"{calendar_round.id} references missing track {calendar_round.track_id}")

    for calendar_round in get_f1_calendar():
        if calendar_round.track_id not in tracks:
            errors.append(f"{calendar_round.id} references missing track {calendar_round.track_id}")

    return errors
