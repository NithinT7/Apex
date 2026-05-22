from __future__ import annotations

import random

from app.models.base import AppModel
from app.models.driver import Driver
from app.models.save_game import SaveGame


class SkillNode(AppModel):
    id: str
    name: str
    branch: str
    description: str
    attribute: str
    cost: int
    max_rank: int


SKILL_TREE: list[SkillNode] = [
    SkillNode(id="raw_pace_1", name="Raw Pace", branch="Pace", description="Sharper minimum speed and lap execution.", attribute="pace", cost=2, max_rank=5),
    SkillNode(id="qualifying_1", name="One-Lap Focus", branch="Pace", description="Better tyre prep and push-lap commitment.", attribute="qualifying", cost=2, max_rank=5),
    SkillNode(id="racecraft_1", name="Racecraft", branch="Racecraft", description="Cleaner attacking and defensive judgement.", attribute="racecraft", cost=2, max_rank=5),
    SkillNode(id="starts_1", name="Launch Control", branch="Racecraft", description="Stronger race starts and first-lap positioning.", attribute="starts", cost=1, max_rank=4),
    SkillNode(id="tyres_1", name="Tyre Management", branch="Racecraft", description="Lower degradation over long runs.", attribute="tire_management", cost=2, max_rank=5),
    SkillNode(id="consistency_1", name="Consistency", branch="Mental", description="Fewer costly laps and cleaner sessions.", attribute="consistency", cost=2, max_rank=5),
    SkillNode(id="pressure_1", name="Pressure Handling", branch="Mental", description="Better execution in decisive moments.", attribute="pressure", cost=1, max_rank=4),
    SkillNode(id="wet_1", name="Wet Weather", branch="Technical", description="More confidence in damp and wet conditions.", attribute="wet_weather", cost=2, max_rank=5),
    SkillNode(id="feedback_1", name="Technical Feedback", branch="Technical", description="Improved setup direction with engineers.", attribute="technical_feedback", cost=1, max_rank=4),
    SkillNode(id="marketability_1", name="Marketability", branch="Profile", description="More sponsor and paddock appeal.", attribute="marketability", cost=1, max_rank=4),
]

SKILL_MAP = {node.id: node for node in SKILL_TREE}

CORE_DEVELOPMENT_ATTRIBUTES = {
    "pace",
    "qualifying",
    "racecraft",
    "tire_management",
    "consistency",
    "pressure",
    "wet_weather",
    "technical_feedback",
}


def f1_development_cap(driver: Driver, attribute: str) -> int:
    """F1 drivers can outgrow junior-series ceilings into elite ratings."""
    if driver.series != "F1":
        return 100
    if attribute in CORE_DEVELOPMENT_ATTRIBUTES:
        return max(99, min(108, driver.hidden.potential + 8, driver.hidden.adaptation_ceiling + 14))
    return 105


def _effective_skill_max_rank(node: SkillNode, driver: Driver | None) -> int:
    if driver and driver.series == "F1" and node.attribute in CORE_DEVELOPMENT_ATTRIBUTES:
        return node.max_rank + 5
    return node.max_rank


def _automatic_development_cap(driver: Driver, attribute: str) -> int:
    if driver.series == "F1":
        return f1_development_cap(driver, attribute)
    return min(99, driver.hidden.adaptation_ceiling)


def award_development_points(save: SaveGame, points: int) -> SaveGame:
    if points <= 0:
        return save
    development = save.development.model_copy(
        update={
            "available_points": save.development.available_points + points,
            "total_earned": save.development.total_earned + points,
        }
    )
    return save.model_copy(update={"development": development})


def points_for_weekend(save: SaveGame, round_id: str) -> int:
    weekend = next((result for result in save.weekend_results if result.round_id == round_id), None)
    if weekend is None or save.player_driver_id is None:
        return 1

    points = 1
    player_results = [
        row
        for race in (weekend.sprint, weekend.feature)
        for row in race.classification
        if row.driver_id == save.player_driver_id
    ]
    points += sum(1 for row in player_results if row.points > 0)
    points += sum(1 for row in player_results if row.position <= 3)
    points += sum(1 for row in player_results if row.position == 1)
    return min(points, 5)


def get_development_status(save: SaveGame) -> dict:
    player = next((driver for driver in save.drivers if driver.id == save.player_driver_id), None)
    skills = []
    for node in SKILL_TREE:
        payload = node.model_dump(by_alias=True)
        payload["maxRank"] = _effective_skill_max_rank(node, player)
        skills.append(payload)
    return {
        "availablePoints": save.development.available_points,
        "totalEarned": save.development.total_earned,
        "spentPoints": save.development.spent_points,
        "skills": skills,
        "attributes": player.attributes.model_dump(by_alias=True) if player else {},
    }


def spend_development_point(save: SaveGame, skill_id: str) -> SaveGame:
    node = SKILL_MAP.get(skill_id)
    if node is None:
        raise ValueError("Unknown skill")
    if save.development.available_points < node.cost:
        raise ValueError("Not enough development points")

    player = next((driver for driver in save.drivers if driver.id == save.player_driver_id), None)
    if player is None:
        raise ValueError("Player driver not found")

    current_rank = save.development.spent_points.get(skill_id, 0)
    if current_rank >= _effective_skill_max_rank(node, player):
        raise ValueError("Skill is already maxed")

    current_value = getattr(player.attributes, node.attribute)
    cap = f1_development_cap(player, node.attribute)
    updated_attributes = player.attributes.model_copy(
        update={node.attribute: min(cap, current_value + 1)}
    )
    updated_player = player.model_copy(update={"attributes": updated_attributes})
    updated_drivers = [updated_player if driver.id == player.id else driver for driver in save.drivers]
    spent_points = {**save.development.spent_points, skill_id: current_rank + 1}
    development = save.development.model_copy(
        update={
            "available_points": save.development.available_points - node.cost,
            "spent_points": spent_points,
        }
    )
    return save.model_copy(update={"drivers": updated_drivers, "development": development})


def _series_position_map(save: SaveGame, series: str) -> dict[str, int]:
    standings = save.f1_standings if series == "F1" and save.f1_standings else save.standings
    driver_ids = {driver.id for driver in save.drivers if driver.series == series}
    ordered = sorted(
        [entry for entry in standings.driver_standings if entry.driver_id in driver_ids],
        key=lambda entry: entry.points,
        reverse=True,
    )
    return {entry.driver_id: index + 1 for index, entry in enumerate(ordered)}


def _season_start_points(driver: Driver, position: int | None, field_size: int, rng: random.Random) -> int:
    if driver.series not in {"F1", "F2"}:
        return 0
    if driver.age > 35 and driver.hidden.development_rate < 55:
        return 0

    age_bonus = 3 if driver.age <= 20 else 2 if driver.age <= 23 else 1 if driver.age <= 28 else 0
    potential_bonus = max(0, (driver.hidden.potential - 78) // 5)
    development_bonus = max(0, (driver.hidden.development_rate - 55) // 12)
    performance_bonus = 0
    if position is not None and field_size > 0:
        if position == 1:
            performance_bonus = 3
        elif position <= 3:
            performance_bonus = 2
        elif position <= max(6, field_size // 3):
            performance_bonus = 1

    series_bonus = 1 if driver.series == "F1" else 0
    rng_bonus = rng.choice([0, 0, 1, 1, 2])
    points = 1 + age_bonus + potential_bonus + development_bonus + performance_bonus + series_bonus + rng_bonus
    return max(1, min(10, points))


def _smart_ai_attribute_order(driver: Driver) -> list[str]:
    attrs = driver.attributes
    if driver.series == "F1":
        priority = ["pace", "qualifying", "racecraft", "consistency", "tire_management", "pressure"]
    else:
        priority = ["pace", "qualifying", "racecraft", "consistency", "starts", "pressure"]
    return sorted(priority, key=lambda attr: (getattr(attrs, attr), priority.index(attr)))


def _spend_ai_development_points(driver: Driver, points: int, rng: random.Random) -> Driver:
    if points <= 0:
        return driver

    updated = driver
    for _ in range(points):
        candidates = [
            attr
            for attr in _smart_ai_attribute_order(updated)
            if getattr(updated.attributes, attr) < _automatic_development_cap(updated, attr)
        ]
        if not candidates:
            break
        attr = candidates[0] if rng.random() < 0.75 else rng.choice(candidates[: min(3, len(candidates))])
        current = getattr(updated.attributes, attr)
        cap = _automatic_development_cap(updated, attr)
        updated = updated.model_copy(
            update={"attributes": updated.attributes.model_copy(update={attr: min(cap, current + 1)})}
        )
    return updated


def apply_start_of_season_development(save: SaveGame) -> SaveGame:
    """Award preseason development points and let AI drivers spend theirs."""
    rng = random.Random(f"{save.random_seed}:{save.season}:season_start_development")
    position_maps = {
        "F1": _series_position_map(save, "F1"),
        "F2": _series_position_map(save, "F2"),
    }
    field_sizes = {
        series: len({driver.id for driver in save.drivers if driver.series == series})
        for series in position_maps
    }

    player_points = 0
    updated_drivers: list[Driver] = []
    for driver in save.drivers:
        position = position_maps.get(driver.series, {}).get(driver.id)
        points = _season_start_points(driver, position, field_sizes.get(driver.series, 0), rng)
        if driver.id == save.player_driver_id:
            player_points = points
            updated_drivers.append(driver)
        else:
            updated_drivers.append(_spend_ai_development_points(driver, points, rng))

    updated_save = save.model_copy(update={"drivers": updated_drivers})
    return award_development_points(updated_save, player_points)
