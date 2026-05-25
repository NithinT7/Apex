from __future__ import annotations

import random
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models.base import AppModel
from app.models.driver import Driver
from app.models.save_game import SaveGame
from app.models.development_profile import (
    ALL_BRANCHES,
    DevelopmentHistoryEntry,
    DevelopmentProfile,
    create_default_development_profile,
)

if TYPE_CHECKING:
    from app.models.race import WeekendResult


# Deprecation flag - set to True to warn about direct stat buying
DIRECT_STAT_BUYING_DEPRECATED = True


@dataclass
class WeekendDevelopmentSummary:
    """Summary of development earned from a race weekend."""

    round_id: str
    xp_gained: dict[str, int]  # branch -> XP
    development_points_gained: int
    total_branch_xp: dict[str, int]  # updated totals after gain
    new_nodes_available: list[str]
    trait_progress: dict[str, dict]  # trait_id -> progress info
    breakdown: list[str]  # human-readable breakdown

    def to_dict(self) -> dict:
        """Convert to API response format."""
        return {
            "roundId": self.round_id,
            "xpGained": self.xp_gained,
            "developmentPointsGained": self.development_points_gained,
            "totalBranchXp": self.total_branch_xp,
            "newNodesAvailable": self.new_nodes_available,
            "traitProgress": self.trait_progress,
            "breakdown": self.breakdown,
        }


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


def f1_development_cap(
    driver: Driver,
    attribute: str,
    difficulty: str = "realistic_prospect",
    unlocked_traits: list[str] | None = None,
    achievements: list[str] | None = None,
) -> int:
    """
    F1 drivers can outgrow junior-series ceilings into elite ratings.

    The cap is determined by:
    - Base potential
    - Difficulty preset soft/hard caps
    - Cap-breaking traits and achievements
    """
    from app.engine.player_balance import get_effective_cap

    if driver.series != "F1":
        # In junior series, use adaptation ceiling as soft limit
        return min(99, driver.hidden.adaptation_ceiling + 5)

    if attribute in CORE_DEVELOPMENT_ATTRIBUTES:
        # Use the new soft cap system
        effective_cap = get_effective_cap(
            base_potential=driver.hidden.potential,
            difficulty=difficulty,
            unlocked_traits=unlocked_traits or [],
            achievements=achievements or [],
        )
        # F1 can push slightly above the effective cap
        return min(99, effective_cap + 2)

    # Non-core attributes have higher caps
    return 99


def _effective_skill_max_rank(node: SkillNode, driver: Driver | None) -> int:
    if driver and driver.series == "F1" and node.attribute in CORE_DEVELOPMENT_ATTRIBUTES:
        return node.max_rank + 5
    return node.max_rank


def _automatic_development_cap(
    driver: Driver,
    attribute: str,
    difficulty: str = "realistic_prospect",
    unlocked_traits: list[str] | None = None,
    achievements: list[str] | None = None,
) -> int:
    """Get the development cap for automatic (AI) development."""
    if driver.series == "F1":
        return f1_development_cap(driver, attribute, difficulty, unlocked_traits, achievements)
    # Junior series has a soft cap but allows elite potential
    from app.engine.player_balance import get_difficulty_config
    config = get_difficulty_config(difficulty)
    return min(config.soft_cap, driver.hidden.adaptation_ceiling + 3)


def award_development_points(save: SaveGame, points: int, round_id: str | None = None) -> SaveGame:
    """
    Award development points to both legacy and new skill tree systems.

    Points go to:
    - save.development.available_points (legacy system, for backwards compat)
    - save.development_profile.current_points (new skill tree system)
    """
    if points <= 0:
        return save

    # Update legacy development state
    development = save.development.model_copy(
        update={
            "available_points": save.development.available_points + points,
            "total_earned": save.development.total_earned + points,
        }
    )

    # Update new development profile (if it exists)
    profile = save.development_profile
    if profile is not None:
        profile = profile.model_copy(
            update={
                "current_points": profile.current_points + points,
                "total_points_earned": profile.total_points_earned + points,
            }
        )
        return save.model_copy(update={"development": development, "development_profile": profile})

    return save.model_copy(update={"development": development})


def points_for_weekend(save: SaveGame, round_id: str) -> int:
    """
    Calculate development points earned from a race weekend.

    Realistic career sim rates - DP is hard to earn:
    - Feature race win: 1 DP
    - Sprint race win: 1 DP
    - Pole position: 1 DP (only if also won the feature)
    - Podium (not win): 0 DP (but earns good XP)
    - Points finish: 0 DP

    Most weekends: 0-1 DP
    Great weekend (pole + feature win): 2 DP
    Perfect weekend (pole + sprint win + feature win): 3 DP (very rare)
    """
    weekend = next((result for result in save.weekend_results if result.round_id == round_id), None)
    if weekend is None or save.player_driver_id is None:
        return 0

    points = 0
    feature_win = False

    # Check feature race
    for row in weekend.feature.classification:
        if row.driver_id == save.player_driver_id:
            if row.position == 1:
                points += 1
                feature_win = True
            break

    # Check sprint race (if exists)
    if weekend.sprint and weekend.sprint.classification:
        for row in weekend.sprint.classification:
            if row.driver_id == save.player_driver_id:
                if row.position == 1:
                    points += 1
                break

    # Pole position bonus (only if you also won the feature - reward complete dominance)
    if feature_win and weekend.qualifying and weekend.qualifying.classification:
        for row in weekend.qualifying.classification:
            if row.driver_id == save.player_driver_id:
                if row.position == 1:
                    points += 1
                break

    return points


def points_for_position(feature_pos: int, sprint_pos: int | None = None, quali_pos: int | None = None) -> int:
    """
    Calculate development points from race positions (for frontend local mode).

    Same logic as points_for_weekend but takes positions directly.
    """
    points = 0
    feature_win = feature_pos == 1

    if feature_win:
        points += 1

    if sprint_pos == 1:
        points += 1

    # Pole bonus only if also won feature
    if feature_win and quali_pos == 1:
        points += 1

    return points


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
    """
    DEPRECATED: Direct stat buying is deprecated.
    Use skill tree nodes via unlock_node() instead.

    This function is kept for backwards compatibility with existing saves
    that may have unspent points in the old system.
    """
    if DIRECT_STAT_BUYING_DEPRECATED:
        warnings.warn(
            "spend_development_point is deprecated. Use skill tree nodes instead.",
            DeprecationWarning,
            stacklevel=2,
        )

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


# =============================================================================
# Race Performance XP System
# =============================================================================


def calculate_race_weekend_xp(
    save: SaveGame,
    weekend_result: "WeekendResult",
) -> dict[str, int]:
    """
    Calculate branch XP earned from a race weekend based on performance.

    XP Mapping:
    - raw_pace: Strong qualifying performance
    - racecraft: Overtakes, battles, wheel-to-wheel racing
    - tire_strategy: Long stints, tire overperformance
    - mentality_pressure: Pressure races, title fights, comebacks
    - technical_feedback: Setup work, practice performance
    - starts_execution: Good starts/restarts
    - media_marketability: Interviews, news, sponsors
    - academy_path: Academy objectives
    """
    if save.player_driver_id is None:
        return {}

    player_id = save.player_driver_id
    xp_gained: dict[str, int] = {branch: 0 for branch in ALL_BRANCHES}

    # Get player's results
    quali_result = next(
        (r for r in weekend_result.qualifying.classification if r.driver_id == player_id),
        None,
    )
    practice_result = next(
        (r for r in weekend_result.practice.classification if r.driver_id == player_id),
        None,
    )
    sprint_result = next(
        (r for r in weekend_result.sprint.classification if r.driver_id == player_id),
        None,
    ) if weekend_result.sprint else None
    feature_result = next(
        (r for r in weekend_result.feature.classification if r.driver_id == player_id),
        None,
    )

    field_size = len(weekend_result.qualifying.classification)

    # --- RAW PACE: Strong qualifying ---
    if quali_result:
        quali_pos = quali_result.position
        if quali_pos == 1:
            xp_gained["raw_pace"] += 25  # Pole position
        elif quali_pos <= 3:
            xp_gained["raw_pace"] += 18
        elif quali_pos <= 6:
            xp_gained["raw_pace"] += 12
        elif quali_pos <= 10:
            xp_gained["raw_pace"] += 8
        else:
            xp_gained["raw_pace"] += 3  # Base XP for participating

        # Bonus for qualifying ahead of grid expectation
        # (Compare quali vs feature position - if you qualified well but fell back, still get XP)

    # --- RACECRAFT: Overtakes and battles ---
    if feature_result and quali_result:
        grid_pos = quali_result.position
        finish_pos = feature_result.position
        positions_gained = grid_pos - finish_pos

        if positions_gained >= 10:
            xp_gained["racecraft"] += 25  # Incredible drive through field
        elif positions_gained >= 6:
            xp_gained["racecraft"] += 18
        elif positions_gained >= 3:
            xp_gained["racecraft"] += 12
        elif positions_gained >= 1:
            xp_gained["racecraft"] += 8
        else:
            xp_gained["racecraft"] += 3  # Held position

        # Extra for fighting in midfield
        if 5 < finish_pos <= 15:
            xp_gained["racecraft"] += 5

    # Sprint race also contributes
    if sprint_result and quali_result:
        sprint_grid = quali_result.position
        sprint_finish = sprint_result.position
        sprint_gained = sprint_grid - sprint_finish
        if sprint_gained >= 3:
            xp_gained["racecraft"] += 8
        elif sprint_gained >= 1:
            xp_gained["racecraft"] += 4

    # --- TIRE STRATEGY: Long stints, tire management ---
    if weekend_result.feature.stint_summaries:
        player_stints = [
            s for s in weekend_result.feature.stint_summaries
            if s.driver_id == player_id
        ]
        for stint in player_stints:
            stint_length = stint.end_lap - stint.start_lap
            if stint_length >= 20:
                xp_gained["tire_strategy"] += 12  # Very long stint
            elif stint_length >= 15:
                xp_gained["tire_strategy"] += 8
            elif stint_length >= 10:
                xp_gained["tire_strategy"] += 4

            # Bonus for low tire wear at stint end
            if stint.tire_wear_end is not None and stint.tire_wear_end < 50:
                xp_gained["tire_strategy"] += 5

    # If no stint data, give base XP
    if xp_gained["tire_strategy"] == 0:
        xp_gained["tire_strategy"] = 5

    # --- MENTALITY/PRESSURE: Title fights, comebacks, pressure ---
    championship_position = _get_championship_position(save, player_id)
    if championship_position is not None:
        if championship_position <= 3:
            # Fighting for title = high pressure XP
            xp_gained["mentality_pressure"] += 15
        elif championship_position <= 6:
            xp_gained["mentality_pressure"] += 10
        else:
            xp_gained["mentality_pressure"] += 5

    # Comeback bonus: finished in points after starting outside top 10
    if feature_result and quali_result:
        if quali_result.position > 10 and feature_result.position <= 10:
            xp_gained["mentality_pressure"] += 10  # Comeback to points

        # Defending under pressure (finished ahead of higher-rated driver)
        if feature_result.points > 0:
            xp_gained["mentality_pressure"] += 5

    # --- TECHNICAL FEEDBACK: Setup work, practice ---
    if practice_result:
        setup_score = practice_result.setup_score or 70
        if setup_score >= 85:
            xp_gained["technical_feedback"] += 15  # Excellent setup work
        elif setup_score >= 75:
            xp_gained["technical_feedback"] += 10
        elif setup_score >= 65:
            xp_gained["technical_feedback"] += 6
        else:
            xp_gained["technical_feedback"] += 3

    # --- STARTS EXECUTION: Good starts ---
    if feature_result and quali_result:
        grid_to_lap1 = quali_result.position - (
            feature_result.position if len(weekend_result.feature.lap_log) == 0
            else _lap1_position(weekend_result.feature, player_id) or feature_result.position
        )
        if grid_to_lap1 >= 3:
            xp_gained["starts_execution"] += 15  # Great start
        elif grid_to_lap1 >= 1:
            xp_gained["starts_execution"] += 10
        elif grid_to_lap1 >= 0:
            xp_gained["starts_execution"] += 5  # Held position
        else:
            xp_gained["starts_execution"] += 2  # Lost positions

    # Sprint start too
    if sprint_result:
        xp_gained["starts_execution"] += 5  # Extra practice

    # --- MEDIA/MARKETABILITY: Points, podiums, wins ---
    if feature_result:
        if feature_result.position == 1:
            xp_gained["media_marketability"] += 20  # Win = big media
        elif feature_result.position <= 3:
            xp_gained["media_marketability"] += 12  # Podium
        elif feature_result.points > 0:
            xp_gained["media_marketability"] += 6  # Points finish
        else:
            xp_gained["media_marketability"] += 2

    # --- ACADEMY PATH: Academy objectives ---
    player = next((d for d in save.drivers if d.id == player_id), None)
    if player and player.academy_id:
        # Academy driver gets base academy XP
        xp_gained["academy_path"] += 8

        # Bonus for good results while in academy
        if feature_result and feature_result.position <= 5:
            xp_gained["academy_path"] += 10

    # Apply difficulty XP multiplier
    from app.engine.player_balance import get_xp_multiplier
    multiplier = get_xp_multiplier(save.difficulty)

    if multiplier != 1.0:
        xp_gained = {
            branch: max(1, int(xp * multiplier)) if xp > 0 else 0
            for branch, xp in xp_gained.items()
        }

    return xp_gained


def _lap1_position(race_result, player_id: str) -> int | None:
    """Get player position at end of lap 1."""
    if not race_result.lap_log:
        return None
    lap1 = race_result.lap_log[0] if race_result.lap_log else None
    if lap1 is None:
        return None
    for entry in lap1.running_order:
        if entry.driver_id == player_id:
            return entry.position
    return None


def _get_championship_position(save: SaveGame, player_id: str) -> int | None:
    """Get player's current championship position."""
    standings = save.standings
    if not standings or not standings.driver_standings:
        return None

    sorted_standings = sorted(
        standings.driver_standings,
        key=lambda s: s.points,
        reverse=True,
    )
    for idx, entry in enumerate(sorted_standings, start=1):
        if entry.driver_id == player_id:
            return idx
    return None


def award_weekend_development(
    save: SaveGame,
    weekend_result: "WeekendResult",
) -> tuple[SaveGame, WeekendDevelopmentSummary]:
    """
    Award all development (XP and points) from a race weekend.

    Returns the updated save and a summary of what was earned.
    """
    round_id = weekend_result.round_id

    # Calculate development points (existing logic)
    dev_points = points_for_weekend(save, round_id)

    # Calculate branch XP
    xp_gained = calculate_race_weekend_xp(save, weekend_result)

    # Build breakdown
    breakdown: list[str] = []
    if dev_points > 0:
        breakdown.append(f"+{dev_points} development points")

    for branch, xp in xp_gained.items():
        if xp > 0:
            branch_label = branch.replace("_", " ").title()
            breakdown.append(f"+{xp} {branch_label} XP")

    # Award points (unified to both systems)
    updated_save = award_development_points(save, dev_points, round_id)

    # Award branch XP to development profile
    profile = updated_save.development_profile
    if profile is None:
        profile = create_default_development_profile()

    # Apply XP gains
    updated_branch_xp = dict(profile.branch_xp)
    for branch, xp in xp_gained.items():
        updated_branch_xp[branch] = updated_branch_xp.get(branch, 0) + xp

    # Add history entry
    new_history = list(profile.history)
    new_history.append(
        DevelopmentHistoryEntry(
            date=_get_weekend_date(save, round_id),
            round_id=round_id,
            source="race_result",
            xp_gained=xp_gained,
            development_points_gained=dev_points,
            summary=_generate_weekend_summary(weekend_result, dev_points, xp_gained),
        )
    )
    # Keep only last 50 entries
    if len(new_history) > 50:
        new_history = new_history[-50:]

    updated_profile = profile.model_copy(
        update={
            "branch_xp": updated_branch_xp,
            "history": new_history,
        }
    )

    updated_save = updated_save.model_copy(update={"development_profile": updated_profile})

    # Check what new nodes are now available
    new_nodes_available = _check_new_available_nodes(profile, updated_profile)

    # Build summary
    summary = WeekendDevelopmentSummary(
        round_id=round_id,
        xp_gained=xp_gained,
        development_points_gained=dev_points,
        total_branch_xp=updated_branch_xp,
        new_nodes_available=new_nodes_available,
        trait_progress={},  # TODO: implement trait progress tracking
        breakdown=breakdown,
    )

    return updated_save, summary


def _get_weekend_date(save: SaveGame, round_id: str) -> str:
    """Get the date for a weekend round."""
    calendar_round = next(
        (r for r in save.calendar if r.id == round_id),
        None,
    )
    if calendar_round:
        return calendar_round.end_date
    return f"round_{round_id}"


def _generate_weekend_summary(
    weekend_result: "WeekendResult",
    dev_points: int,
    xp_gained: dict[str, int],
) -> str:
    """Generate a human-readable summary of weekend development."""
    total_xp = sum(xp_gained.values())
    # Find highest XP branch
    if xp_gained:
        top_branch = max(xp_gained.items(), key=lambda x: x[1])
        branch_label = top_branch[0].replace("_", " ").title()
        return f"+{dev_points} pts, +{total_xp} XP ({branch_label} focused)"
    return f"+{dev_points} development points"


def _check_new_available_nodes(
    old_profile: DevelopmentProfile,
    new_profile: DevelopmentProfile,
) -> list[str]:
    """
    Check which skill tree nodes became newly available after XP gains.

    This is a simplified check - full node availability is calculated
    by the skill tree engine.
    """
    # This would need the skill tree data to properly check
    # For now, return empty - the frontend will recalculate
    return []


# =============================================================================
# Legacy Compatibility Helpers
# =============================================================================


def migrate_legacy_points_to_profile(save: SaveGame) -> SaveGame:
    """
    Migrate points from the legacy development system to the new profile.

    Call this when loading a save to ensure points are synced.
    """
    if save.development_profile is None:
        return save

    profile = save.development_profile
    legacy_available = save.development.available_points

    # If legacy has more points than profile, sync them
    if legacy_available > profile.current_points:
        diff = legacy_available - profile.current_points
        updated_profile = profile.model_copy(
            update={
                "current_points": legacy_available,
                "total_points_earned": profile.total_points_earned + diff,
            }
        )
        return save.model_copy(update={"development_profile": updated_profile})

    return save


def get_unified_development_points(save: SaveGame) -> int:
    """
    Get the total available development points from both systems.

    Returns the higher of the two to ensure no points are lost.
    """
    legacy_points = save.development.available_points
    profile_points = save.development_profile.current_points if save.development_profile else 0
    return max(legacy_points, profile_points)


def is_direct_stat_buying_enabled(save: SaveGame) -> bool:
    """
    Check if direct stat buying should be available.

    Returns False if the save has been migrated to the new system.
    Direct stat buying is kept for backwards compatibility only.
    """
    # If player has used the skill tree, disable direct stat buying
    if save.development_profile and save.development_profile.unlocked_node_ids:
        return False
    # Also disable if the save has the new system flag
    if save.event_flags.get("skill_tree_enabled"):
        return True
    # Default: deprecated but available for legacy saves
    return not DIRECT_STAT_BUYING_DEPRECATED
