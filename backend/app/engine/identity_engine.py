"""Evolving driver identity and reputation labels."""

from __future__ import annotations

import uuid

from app.models.driver import Driver
from app.models.race import RaceResult, WeekendResult
from app.models.save_game import NewsItem, SaveGame
from app.models.team import Team
from app.models.track import Track


TRAIT_LABELS: dict[str, str] = {
    "qualifying_merchant": "Qualifying Merchant",
    "tire_whisperer": "Tire Whisperer",
    "rain_god": "Rain God",
    "street_demon": "Street Circuit Demon",
    "aggressive_menace": "Aggressive Menace",
    "team_leader": "Team Leader",
    "pay_driver_with_pace": "Pay Driver With Pace",
    "comeback_kid": "Comeback Kid",
}

TRAIT_DESCRIPTIONS: dict[str, str] = {
    "qualifying_merchant": "Explosive over one lap, with Saturdays becoming the main selling point.",
    "tire_whisperer": "Trusted to extend stints, protect rubber, and turn strategy into results.",
    "rain_god": "Valued when grip disappears and races become chaotic.",
    "street_demon": "Especially dangerous on narrow walls-close circuits.",
    "aggressive_menace": "Box-office in battle, but carrying a higher incident risk.",
    "team_leader": "Known for feedback, setup direction, and helping a team improve.",
    "pay_driver_with_pace": "Commercially attractive without being dismissed as only sponsor-backed.",
    "comeback_kid": "The paddock remembers the recoveries more than the setbacks.",
}


def update_driver_identities(save: SaveGame, weekend: WeekendResult, track: Track, date: str) -> tuple[SaveGame, list[NewsItem]]:
    """Update the player's evolving identity after a completed weekend."""
    if save.player_driver_id is None:
        return save, []

    player = next((driver for driver in save.drivers if driver.id == save.player_driver_id), None)
    if player is None:
        return save, []

    updated_player, news = _update_driver_identity(save, player, weekend, track, date)
    if updated_player is player:
        return save, []

    updated_drivers = [updated_player if driver.id == updated_player.id else driver for driver in save.drivers]
    return save.model_copy(update={"drivers": updated_drivers}), news


def identity_team_fit_bonus(driver: Driver, team: Team) -> int:
    """Translate identity into hiring fit without overpowering results."""
    trait = driver.identity.primary_trait
    score = driver.identity.trait_scores.get(trait or "", 0)
    if trait is None or score < 25:
        return 0

    strength = 1 if score < 45 else 2 if score < 70 else 3
    profile = team.hiring_profile or "established_midfield"

    if trait == "qualifying_merchant":
        return strength * (4 if profile in {"big_brand", "title_contender"} else 2)
    if trait == "tire_whisperer":
        return strength * (4 if profile in {"rebuilding", "veteran_stability", "established_midfield"} else 2)
    if trait == "rain_god":
        return strength * 3
    if trait == "street_demon":
        return strength * (3 if team.id in {"f1_ferrari", "f1_red_bull", "f1_mclaren"} else 2)
    if trait == "aggressive_menace":
        return strength * (4 if profile in {"high_risk", "big_brand"} else -1 if profile == "title_contender" else 1)
    if trait == "team_leader":
        return strength * (5 if profile in {"rebuilding", "long_term_project", "veteran_stability"} else 2)
    if trait == "pay_driver_with_pace":
        return strength * (5 if profile in {"financially_pressured", "big_brand"} else 1)
    if trait == "comeback_kid":
        return strength * 3
    return 0


def identity_summary(driver: Driver) -> str:
    trait = driver.identity.primary_trait
    if trait is None:
        return "Profile still forming"
    label = TRAIT_LABELS.get(trait, trait.replace("_", " ").title())
    return f"{label}: {TRAIT_DESCRIPTIONS.get(trait, 'A clear paddock identity is emerging.')}"


def _update_driver_identity(
    save: SaveGame,
    driver: Driver,
    weekend: WeekendResult,
    track: Track,
    date: str,
) -> tuple[Driver, list[NewsItem]]:
    previous_primary = driver.identity.primary_trait
    previous_scores = driver.identity.trait_scores
    increments = _weekend_identity_increments(driver, weekend, track)
    if not increments:
        return driver, []

    scores = dict(previous_scores)
    for trait, points in increments.items():
        scores[trait] = min(100, scores.get(trait, 0) + points)

    primary = _primary_trait(scores)
    summary = _summary_for_primary(driver, primary, scores)
    identity = driver.identity.model_copy(
        update={
            "primary_trait": primary,
            "trait_scores": scores,
            "summary": summary,
            "last_updated_round": weekend.round_id,
        }
    )
    updated_driver = driver.model_copy(update={"identity": identity})

    news = _identity_news(save, updated_driver, primary, previous_primary, previous_scores, scores, date)
    return updated_driver, news


def _weekend_identity_increments(driver: Driver, weekend: WeekendResult, track: Track) -> dict[str, int]:
    qualifying_pos = _position_in_qualifying(weekend, driver.id)
    feature_pos = _position_in_race(weekend.feature, driver.id)
    sprint_pos = _position_in_race(weekend.sprint, driver.id)
    feature_grid = _grid_position(weekend.feature, driver.id)
    best_finish = min([pos for pos in [feature_pos, sprint_pos] if pos is not None], default=None)
    gained = max(0, (feature_grid or 0) - feature_pos) if feature_grid and feature_pos else 0
    wet_weekend = _has_wet_running(weekend)
    dnf = driver.id in weekend.feature.dnfs or driver.id in weekend.sprint.dnfs
    player_moves = _count_player_overtakes(weekend.feature, driver.name)
    attrs = driver.attributes

    increments: dict[str, int] = {}
    if qualifying_pos is not None and qualifying_pos <= 10:
        increments["qualifying_merchant"] = 2 + max(0, 11 - qualifying_pos) // 2 + max(0, attrs.qualifying - 78) // 6
        if feature_pos is not None and feature_pos - qualifying_pos >= 4:
            increments["qualifying_merchant"] += 2

    if feature_pos is not None and feature_grid is not None and feature_pos <= feature_grid:
        increments["tire_whisperer"] = 1 + min(5, gained) + max(0, attrs.tire_management - 78) // 6
    elif attrs.tire_management >= 84 and best_finish is not None and best_finish <= 8:
        increments["tire_whisperer"] = 3

    if wet_weekend and best_finish is not None:
        increments["rain_god"] = 2 + max(0, 12 - best_finish) // 2 + max(0, attrs.wet_weather - 76) // 5

    if track.street_circuit and best_finish is not None and (best_finish <= 8 or gained >= 3):
        increments["street_demon"] = 2 + max(0, 10 - best_finish) // 2 + min(4, gained)

    if player_moves or attrs.aggression >= 78:
        increments["aggressive_menace"] = player_moves * 3 + max(0, attrs.aggression - attrs.discipline) // 5
        if dnf:
            increments["aggressive_menace"] += 3

    practice_row = next((row for row in weekend.practice.classification if row.driver_id == driver.id), None)
    if attrs.technical_feedback >= 76 or (practice_row and practice_row.setup_score >= 78):
        increments["team_leader"] = 1 + max(0, attrs.technical_feedback - 76) // 5
        if practice_row and practice_row.setup_score >= 82:
            increments["team_leader"] += 2

    if attrs.sponsor_value >= 68 and best_finish is not None and best_finish <= 8:
        increments["pay_driver_with_pace"] = 2 + max(0, attrs.sponsor_value - 68) // 7 + max(0, attrs.marketability - 70) // 8

    if feature_grid is not None and feature_pos is not None and (gained >= 6 or (feature_grid >= 12 and feature_pos <= 6)):
        increments["comeback_kid"] = 4 + min(6, gained)

    return {trait: max(1, min(12, points)) for trait, points in increments.items() if points > 0}


def _primary_trait(scores: dict[str, int]) -> str | None:
    if not scores:
        return None
    trait, score = max(scores.items(), key=lambda item: item[1])
    return trait if score >= 20 else None


def _summary_for_primary(driver: Driver, primary: str | None, scores: dict[str, int]) -> str:
    if primary is None:
        strongest = max(scores.items(), key=lambda item: item[1], default=None)
        if strongest is None:
            return "Profile still forming"
        return f"Early signs of a {TRAIT_LABELS.get(strongest[0], 'distinctive')} reputation."

    label = TRAIT_LABELS.get(primary, primary.replace("_", " ").title())
    score = scores.get(primary, 0)
    if score >= 70:
        tone = "firmly known as"
    elif score >= 45:
        tone = "becoming known as"
    else:
        tone = "starting to look like"
    return f"{driver.name} is {tone} a {label.lower()}."


def _identity_news(
    save: SaveGame,
    driver: Driver,
    primary: str | None,
    previous_primary: str | None,
    previous_scores: dict[str, int],
    scores: dict[str, int],
    date: str,
) -> list[NewsItem]:
    if primary is None:
        return []

    score = scores.get(primary, 0)
    old_score = previous_scores.get(primary, 0)
    crossed = any(old_score < mark <= score for mark in (20, 45, 70))
    if primary == previous_primary and not crossed:
        return []

    interested = _identity_interested_teams(save, primary)
    label = TRAIT_LABELS.get(primary, primary.replace("_", " ").title())
    team_phrase = ""
    if interested:
        team_phrase = f" {interested} are among the teams expected to value that profile."

    return [
        NewsItem(
            id=f"identity_{uuid.uuid4().hex[:8]}",
            date=date,
            category="media",
            headline=f"{driver.name}'s paddock identity takes shape",
            body=f"{driver.name} is quickly becoming known as a {label.lower()}. {TRAIT_DESCRIPTIONS[primary]}{team_phrase}",
            linked_driver_ids=[driver.id],
            importance=4 if score >= 45 else 3,
        )
    ]


def _identity_interested_teams(save: SaveGame, trait: str) -> str:
    team_ids_by_trait = {
        "qualifying_merchant": ["f1_williams", "f1_audi"],
        "tire_whisperer": ["f1_williams", "f1_sauber", "f1_alpine"],
        "rain_god": ["f1_red_bull", "f1_mercedes"],
        "street_demon": ["f1_ferrari", "f1_red_bull"],
        "aggressive_menace": ["f1_red_bull", "f1_haas"],
        "team_leader": ["f1_audi", "f1_williams", "f1_alpine"],
        "pay_driver_with_pace": ["f1_cadillac", "f1_haas"],
        "comeback_kid": ["f1_williams", "f1_aston_martin"],
    }
    names = [
        team.name
        for team in save.teams
        if team.id in team_ids_by_trait.get(trait, []) and team.series == "F1"
    ]
    return " and ".join(names[:2])


def _position_in_qualifying(weekend: WeekendResult, driver_id: str) -> int | None:
    row = next((entry for entry in weekend.qualifying.classification if entry.driver_id == driver_id), None)
    return row.position if row else None


def _position_in_race(race: RaceResult, driver_id: str) -> int | None:
    row = next((entry for entry in race.classification if entry.driver_id == driver_id), None)
    return row.position if row else None


def _grid_position(race: RaceResult, driver_id: str) -> int | None:
    try:
        return race.starting_grid.index(driver_id) + 1
    except ValueError:
        return None


def _has_wet_running(weekend: WeekendResult) -> bool:
    if weekend.practice.weather.condition != "dry" or weekend.qualifying.weather.condition != "dry":
        return True
    return any(snapshot.weather.condition != "dry" for snapshot in weekend.feature.lap_log + weekend.sprint.lap_log)


def _count_player_overtakes(race: RaceResult, driver_name: str) -> int:
    needle = f"{driver_name} completes a move"
    return sum(1 for snapshot in race.lap_log for line in snapshot.commentary if needle in line)
