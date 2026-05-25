import json
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from app.models.academy import Academy
from app.models.bootstrap import DataBootstrap
from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.driver_trait import DriverTrait, TraitConfig, validate_trait_config
from app.models.player_creation import DriverArchetype, DriverBackground
from app.models.skill_tree import SkillTreeConfig, validate_skill_tree_config
from app.models.team import Team
from app.models.track import Track
from app.models.weekly_focus import WeeklyFocus, WeeklyFocusConfig, validate_weekly_focus_config
from app.models.sponsorship import SponsorActivity, SponsorActivityEffects, SponsorActivityRisk
from app.models.world import PotentialEntrant


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


@lru_cache
def get_skill_tree_config() -> SkillTreeConfig:
    """Load the skill tree configuration."""
    data = _load_json("skill_tree.json")
    return SkillTreeConfig.model_validate(data)


@lru_cache
def get_weekly_focus_config() -> WeeklyFocusConfig:
    """Load the weekly focus configuration."""
    data = _load_json("weekly_focuses.json")
    return WeeklyFocusConfig.model_validate(data)


@lru_cache
def get_trait_config() -> TraitConfig:
    """Load the driver traits configuration."""
    data = _load_json("driver_traits.json")
    return TraitConfig.model_validate(data)


@lru_cache
def get_sponsor_activities() -> list[SponsorActivity]:
    """Load the sponsor activities configuration."""
    data = _load_json("sponsor_activities.json")
    activities = []
    for item in data["activities"]:
        effects = SponsorActivityEffects.model_validate(item["effects"])
        risk = None
        if item.get("risk"):
            risk = SponsorActivityRisk.model_validate(item["risk"])

        activity = SponsorActivity(
            id=item["id"],
            name=item["name"],
            tier=item["tier"],
            description=item["description"],
            min_marketability=item["min_marketability"],
            min_sponsor_value=item.get("min_sponsor_value", 0),
            effects=effects,
            risk=risk,
            duration_days=item.get("duration_days", 1),
            flavor_text=item.get("flavor_text", ""),
            success_headline=item.get("success_headline", ""),
            success_body=item.get("success_body", ""),
            preferred_team_ids=item.get("preferred_team_ids", []),
            preferred_academy_ids=item.get("preferred_academy_ids", []),
            is_major_event=item.get("is_major_event", False),
        )
        activities.append(activity)
    return activities


class TakeoverInvestor:
    """An investor who can take over a struggling team."""
    def __init__(self, id: str, name: str, country: str, budget_boost: int, development_boost: int):
        self.id = id
        self.name = name
        self.country = country
        self.budget_boost = budget_boost
        self.development_boost = development_boost


@lru_cache
def get_potential_entrants() -> list[PotentialEntrant]:
    """Load potential F1 team entrants (manufacturers, privateers)."""
    data = _load_json("potential_entrants.json")
    return [PotentialEntrant.model_validate(e) for e in data["potential_entrants"]]


@lru_cache
def get_takeover_investors() -> list[TakeoverInvestor]:
    """Load potential team investors/buyers."""
    data = _load_json("potential_entrants.json")
    return [
        TakeoverInvestor(
            id=i["id"],
            name=i["name"],
            country=i["country"],
            budget_boost=i["budget_boost"],
            development_boost=i["development_boost"],
        )
        for i in data["takeover_investors"]
    ]


def validate_sponsor_config() -> list[str]:
    """Validate the sponsor activities configuration."""
    errors: list[str] = []
    try:
        activities = get_sponsor_activities()
        ids = set()
        for activity in activities:
            if activity.id in ids:
                errors.append(f"Duplicate sponsor activity id: {activity.id}")
            ids.add(activity.id)

            if activity.min_marketability < 0 or activity.min_marketability > 100:
                errors.append(f"Sponsor activity {activity.id} has invalid min_marketability: {activity.min_marketability}")

            if activity.min_sponsor_value < 0 or activity.min_sponsor_value > 100:
                errors.append(f"Sponsor activity {activity.id} has invalid min_sponsor_value: {activity.min_sponsor_value}")

            if activity.effects.media_xp < 0:
                errors.append(f"Sponsor activity {activity.id} has negative media_xp")

    except Exception as e:
        errors.append(f"Sponsor config error: {e}")

    return errors


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


def validate_development_configs() -> list[str]:
    """Validate all development system configuration files."""
    errors: list[str] = []

    # Validate skill tree
    try:
        skill_tree = get_skill_tree_config()
        errors.extend(validate_skill_tree_config(skill_tree))
    except Exception as e:
        errors.append(f"Skill tree config error: {e}")

    # Validate weekly focuses
    try:
        focuses = get_weekly_focus_config()
        errors.extend(validate_weekly_focus_config(focuses))
    except Exception as e:
        errors.append(f"Weekly focus config error: {e}")

    # Validate traits
    try:
        traits = get_trait_config()
        errors.extend(validate_trait_config(traits))
    except Exception as e:
        errors.append(f"Trait config error: {e}")

    # Cross-validate: trait unlocks in skill tree reference existing traits
    try:
        skill_tree = get_skill_tree_config()
        traits = get_trait_config()
        trait_ids = {t.id for t in traits.traits}

        for branch in skill_tree.branches:
            for node in branch.nodes:
                if node.unlocks_trait_id and node.unlocks_trait_id not in trait_ids:
                    errors.append(
                        f"Skill node {node.id} unlocks non-existent trait: {node.unlocks_trait_id}"
                    )
    except Exception:
        pass  # Already reported above

    # Validate sponsor activities
    errors.extend(validate_sponsor_config())

    return errors
