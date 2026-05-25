"""Engine for F1 silly season driver market simulation."""

from __future__ import annotations

import random
import uuid
from typing import Literal

from app.engine.identity_engine import identity_team_fit_bonus
from app.models.driver import Driver
from app.models.save_game import Contract, NewsItem, SaveGame
from app.models.team import Team


# Hiring profile preferences for teams
HIRING_PREFERENCES = {
    "title_contender": {"min_rating": 86, "prefer_experienced": True, "academy_weight": 0.25},
    "big_brand": {"min_rating": 82, "prefer_experienced": True, "academy_weight": 0.35},
    "junior_pipeline": {"min_rating": 74, "prefer_experienced": False, "academy_weight": 0.85},
    "rebuilding": {"min_rating": 72, "prefer_experienced": False, "academy_weight": 0.55},
    "financially_pressured": {"min_rating": 70, "prefer_experienced": False, "academy_weight": 0.45},
    "veteran_stability": {"min_rating": 78, "prefer_experienced": True, "academy_weight": 0.35},
    "high_risk": {"min_rating": 73, "prefer_experienced": False, "academy_weight": 0.6},
    "long_term_project": {"min_rating": 72, "prefer_experienced": False, "academy_weight": 0.65},
    "established_midfield": {"min_rating": 76, "prefer_experienced": True, "academy_weight": 0.45},
}

# F2 championship position thresholds for F1 interest
F1_INTEREST_THRESHOLDS = {
    "high": 3,  # Top 3 finishers get strong interest
    "medium": 6,  # Top 6 get moderate interest
    "low": 10,  # Top 10 get some interest
}

CONTENDER_PERFORMANCE = 88
UPPER_MIDFIELD_PERFORMANCE = 81
LOWER_MIDFIELD_PERFORMANCE = 72

# Expected championship positions based on car performance
# This is used to detect drivers who are outperforming their car
CAR_PERFORMANCE_TO_EXPECTED_POSITION = {
    # (min_car_perf, max_car_perf): (expected_best, expected_worst)
    (92, 100): (1, 4),    # Top car: should be P1-P4
    (88, 91): (3, 8),     # Contender: P3-P8
    (81, 87): (6, 14),    # Upper midfield: P6-P14
    (72, 80): (10, 18),   # Lower midfield: P10-P18
    (0, 71): (14, 22),    # Backmarker: P14-P22
}

# Only the major real-world-style programmes exist in the sim. Smaller teams
# can still act as historical affiliate/customer landing spots.
ACADEMY_TEAM_AFFINITY: dict[str, dict[str, int]] = {
    "academy_red_bull": {
        "f1_red_bull": 28,
        "f1_racing_bulls": 24,
    },
    "academy_ferrari": {
        "f1_ferrari": 28,
        "f1_haas": 16,
        "f1_audi": 10,
    },
    "academy_mercedes": {
        "f1_mercedes": 28,
        "f1_williams": 16,
        "f1_aston_martin": 10,
    },
    "academy_mclaren": {
        "f1_mclaren": 28,
        "f1_audi": 8,
    },
    "academy_alpine": {
        "f1_alpine": 28,
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# DRIVER-TEAM RELATIONSHIP HISTORY
# Based on real F1 patterns: drivers dropped by top teams rarely return
# ─────────────────────────────────────────────────────────────────────────────

# Drivers who were dropped/demoted by teams - they won't return
# Format: driver_id -> list of team_ids that dropped them
DROPPED_BY_TEAM: dict[str, list[str]] = {
    "alex_albon": ["f1_red_bull"],      # Dropped after 2020, went to Williams
    "pierre_gasly": ["f1_red_bull"],    # Demoted to AlphaTauri after 2019
    "daniil_kvyat": ["f1_red_bull"],    # Dropped multiple times
    "nyck_de_vries": ["f1_racing_bulls"],  # Dropped after half a season
    "daniel_ricciardo": ["f1_red_bull", "f1_mclaren"],  # Left RB, dropped by McLaren
    "sebastian_vettel": ["f1_ferrari"],  # Not renewed after 2020
    "valtteri_bottas": ["f1_mercedes"],  # Replaced by Russell
    "sergio_perez": ["f1_mclaren"],      # Dropped after 2013
}

# Teams considered "ambitious projects" that can attract veteran drivers
# even if their car is worse - based on investment, development, trajectory
AMBITIOUS_PROJECT_TEAMS: set[str] = {
    "f1_aston_martin",  # Stroll investment, new factory
    "f1_williams",      # Dorilton investment, historic team
    "f1_audi",          # Manufacturer backing coming
    "f1_alpine",        # Renault works team
}

# Real F1 move patterns (2020-2025) for reference:
# - Hamilton RB->McLaren->Merc->Ferrari (only moved for championships)
# - Alonso Renault->McLaren->Ferrari->Alpine->AM (chased competitive cars)
# - Sainz TR->Renault->McLaren->Ferrari->Williams (took best available)
# - Ricciardo RB->Renault->McLaren->RB(reserve) (left top team, couldn't return)
# - Vettel RB->Ferrari->AM->retired (stepped down gracefully)
# - Bottas Merc->Alfa (no top seat, took midfield)
# - Gasly RB->AT->Alpine (never returned to RB)
# - Albon RB->Williams (never returned to RB)


def _was_dropped_by_team(driver_id: str, team_id: str) -> bool:
    """Check if a driver was previously dropped by this team."""
    return team_id in DROPPED_BY_TEAM.get(driver_id, [])


def _is_ambitious_project(team: Team) -> bool:
    """
    Check if a team is an 'ambitious project' that can attract veterans.

    Based on:
    - Explicit list of known ambitious teams
    - High development rate (investing in future)
    - Strong financial health (can sustain long-term project)
    """
    if team.id in AMBITIOUS_PROJECT_TEAMS:
        return True
    # Dynamic check: high investment teams
    return team.development_rate >= 78 and team.financial_health >= 80


def _driver_has_better_options(
    driver: Driver,
    current_team: Team,
    all_teams: list[Team],
    open_team_ids: set[str],
    driver_rating: int,
) -> bool:
    """
    Check if a driver likely has better options than a specific team.

    Used to prevent top drivers from moving to worse cars unless necessary.
    """
    # Count teams with better cars that might want this driver
    better_options = 0
    for team in all_teams:
        if team.id not in open_team_ids:
            continue
        if team.id == current_team.id:
            continue
        if team.car_performance <= current_team.car_performance:
            continue
        # Would this team want this driver?
        team_min_rating = int(_team_prefs(team).get("min_rating", 75))
        if driver_rating >= team_min_rating - 2:
            better_options += 1

    return better_options > 0


def _is_seatless_situation(
    driver: Driver,
    contracts: list[Contract],
    current_season: int,
    seat_risk: int,
    current_team_performance: int,
) -> bool:
    """
    Check if a driver is effectively 'seatless' - contract expiring and unlikely to be renewed.

    This is the Sainz-to-Williams situation: good driver pushed out of top team,
    no other top seat available, takes best available option.

    Key distinctions:
    - Drivers at TOP teams with expiring contracts are NOT seatless - they'll get renewed or retire
    - Drivers being pushed out (high seat risk) at midfield teams ARE seatless
    - This prevents Hamilton/Alonso from taking massive step-downs
    """
    contract = next(
        (c for c in contracts if c.driver_id == driver.id and c.active),
        None
    )
    if contract is None:
        return True  # No contract = seatless

    years_left = max(0, (contract.start_season + contract.length_years) - (current_season + 1))

    if years_left > 0:
        return False  # Has contract, not seatless

    # Expiring contract scenarios:

    # Top team drivers (car >= 88) with expiring contracts are NOT seatless
    # They'd get renewed or retire, not move to backmarkers
    if current_team_performance >= CONTENDER_PERFORMANCE:
        return False

    # Upper midfield drivers are seatless only if seat risk is HIGH
    if current_team_performance >= UPPER_MIDFIELD_PERFORMANCE:
        return seat_risk >= 55

    # Midfield/backmarker drivers with expiring contracts and moderate risk are seatless
    return seat_risk >= 35


TransferType = Literal["promotion", "lateral", "demotion", "new_signing", "retirement"]


class TransferRumor:
    """Represents a transfer rumor."""

    def __init__(
        self,
        driver_id: str,
        from_team_id: str | None,
        to_team_id: str,
        transfer_type: TransferType,
        likelihood: int,  # 0-100
        reason: str,
    ):
        self.id = f"rumor_{uuid.uuid4().hex[:8]}"
        self.driver_id = driver_id
        self.from_team_id = from_team_id
        self.to_team_id = to_team_id
        self.transfer_type = transfer_type
        self.likelihood = likelihood
        self.reason = reason
        self.confirmed = False


def _with_path_adjusted_academy(driver: Driver, to_team: Team) -> Driver:
    academy_id = driver.academy_id if _has_academy_path_to_team(to_team, driver.academy_id) else None
    return driver.model_copy(update={"team_id": to_team.id, "series": to_team.series, "academy_id": academy_id})


def get_driver_rating(driver: Driver) -> int:
    """Calculate overall driver rating from attributes."""
    attrs = driver.attributes
    pace_rating = (attrs.pace + attrs.qualifying + attrs.racecraft) / 3
    consistency_rating = (attrs.consistency + attrs.composure + attrs.focus) / 3
    return int((pace_rating * 0.6 + consistency_rating * 0.4))


def _team_prefs(team: Team) -> dict[str, int | bool | float]:
    return HIRING_PREFERENCES.get(team.hiring_profile or "established_midfield", HIRING_PREFERENCES["established_midfield"])


def _series_position_map(save: SaveGame, series: str) -> dict[str, int]:
    standings = save.f1_standings if series == "F1" and save.f1_standings else save.standings
    driver_ids = {driver.id for driver in save.drivers if driver.series == series}
    sorted_standings = sorted(
        [entry for entry in standings.driver_standings if entry.driver_id in driver_ids],
        key=lambda entry: entry.points,
        reverse=True,
    )
    return {entry.driver_id: index + 1 for index, entry in enumerate(sorted_standings)}


def _driver_profile_fit(team: Team, driver: Driver, championship_position: int | None = None) -> int:
    rating = get_driver_rating(driver)
    attrs = driver.attributes
    profile = team.hiring_profile or "established_midfield"
    age_peak = 22 <= driver.age <= 33
    score = rating
    score += max(-10, min(12, (driver.current_form - 60) // 2))
    if championship_position is not None:
        score += max(-8, 14 - championship_position)
    if age_peak:
        score += 4
    elif driver.age >= 37:
        score -= 6 + (driver.age - 37) * 2
    elif driver.age <= 21:
        score += 3 if profile in {"junior_pipeline", "rebuilding", "long_term_project", "high_risk"} else -3

    if profile == "title_contender":
        score += (attrs.pressure + attrs.composure + attrs.consistency - 255) // 5
        score -= max(0, driver.hidden.crash_proneness - 28) // 4
    elif profile == "big_brand":
        score += (attrs.marketability + attrs.reputation + attrs.sponsor_value - 230) // 4
    elif profile == "junior_pipeline":
        score += (driver.hidden.potential - 82) // 2 + (driver.hidden.development_rate - 62) // 4
        score += 8 if team.academy_id and driver.academy_id == team.academy_id else 0
    elif profile == "rebuilding":
        score += (driver.hidden.potential - 80) // 3 + (attrs.technical_feedback - 76) // 3
    elif profile == "financially_pressured":
        score += (attrs.sponsor_value + attrs.marketability - 145) // 3
    elif profile == "veteran_stability":
        score += (attrs.consistency + attrs.discipline + attrs.technical_feedback - 235) // 4
        score += 5 if driver.age >= 29 else -3
    elif profile == "high_risk":
        score += (attrs.pace + attrs.aggression + driver.hidden.potential - 245) // 4
    elif profile == "long_term_project":
        score += (driver.hidden.potential - 82) // 2 + (driver.hidden.loyalty - 68) // 4

    score += identity_team_fit_bonus(driver, team)
    return int(score)


def _seat_risk_score(team: Team, driver: Driver, championship_position: int | None = None) -> int:
    """Calculate how at-risk a driver's seat is. Higher = more likely to be replaced."""
    prefs = _team_prefs(team)
    min_rating = int(prefs["min_rating"])
    rating = get_driver_rating(driver)
    fit = _driver_profile_fit(team, driver, championship_position)
    risk = 0

    # Base risk from rating gap (increased weight)
    risk += max(0, (min_rating - rating) * 5)

    # Risk from poor fit (increased weight)
    risk += max(0, 70 - fit) * 3

    # Risk from poor form (increased impact)
    risk += max(0, 60 - driver.current_form) * 2

    # Championship position risk (more aggressive)
    if championship_position is not None:
        team_driver_count = 22
        position_gap = championship_position - team_driver_count // 2
        risk += max(0, position_gap) * 2

    # Age risk (increased)
    if driver.age >= 35:
        risk += (driver.age - 34) * 6 + driver.hidden.retirement_chance

    # Low loyalty means they might leave anyway
    if driver.hidden.loyalty < 60:
        risk += 6

    # Hot-headed drivers are a liability
    if driver.attributes.aggression - driver.attributes.discipline > 10:
        risk += 8

    # Financial considerations
    if team.hiring_profile == "financially_pressured":
        risk -= max(0, driver.attributes.sponsor_value - 75) // 2
    if team.hiring_profile == "big_brand":
        risk -= max(0, driver.attributes.marketability - 80) // 2

    # Morale and confidence impact
    if driver.morale < 40:
        risk += 8

    return max(0, risk)


def get_team_rookie_tier(team: Team) -> Literal["contender", "upper_midfield", "lower_midfield", "backmarker"]:
    """Classify how realistic a direct rookie opening is at this team."""
    if team.car_performance >= CONTENDER_PERFORMANCE:
        return "contender"
    if team.car_performance >= UPPER_MIDFIELD_PERFORMANCE:
        return "upper_midfield"
    if team.car_performance >= LOWER_MIDFIELD_PERFORMANCE:
        return "lower_midfield"
    return "backmarker"


def _stable_team_roll(save: SaveGame, team_id: str, salt: int = 0) -> int:
    seed = save.random_seed + save.season * 7919 + sum(ord(char) for char in team_id) + salt
    return random.Random(seed).randint(1, 100)


def _academy_affinity(team: Team, academy_id: str | None) -> int:
    if not academy_id:
        return 0
    if team.academy_id == academy_id:
        return 28
    return ACADEMY_TEAM_AFFINITY.get(academy_id, {}).get(team.id, 0)


def _has_academy_path_to_team(team: Team, academy_id: str | None) -> bool:
    return _academy_affinity(team, academy_id) > 0


def _marketability_package(driver: Driver) -> int:
    attrs = driver.attributes
    return round(attrs.marketability * 0.5 + attrs.reputation * 0.3 + attrs.sponsor_value * 0.2)


def _is_top_team(team: Team) -> bool:
    return team.car_performance >= UPPER_MIDFIELD_PERFORMANCE or team.hiring_profile in {"title_contender", "big_brand"}


def _is_main_academy_team(team: Team, academy_id: str | None) -> bool:
    return bool(
        academy_id
        and team.academy_id == academy_id
        and (team.hiring_profile in {"title_contender", "big_brand"} or team.car_performance >= UPPER_MIDFIELD_PERFORMANCE)
    )


def _get_expected_position_range(car_performance: int) -> tuple[int, int]:
    """Get expected championship position range based on car performance."""
    for (min_perf, max_perf), (best, worst) in CAR_PERFORMANCE_TO_EXPECTED_POSITION.items():
        if min_perf <= car_performance <= max_perf:
            return (best, worst)
    return (14, 22)  # Default to backmarker range


def _calculate_outperformance(
    driver: Driver,
    team: Team,
    championship_position: int | None,
) -> int:
    """
    Calculate how much a driver is outperforming their car.

    Returns a score where:
    - Positive = outperforming (hot commodity)
    - Negative = underperforming
    - Zero = meeting expectations
    """
    if championship_position is None:
        return 0

    expected_best, expected_worst = _get_expected_position_range(team.car_performance)
    expected_mid = (expected_best + expected_worst) // 2

    # How many positions better than expected midpoint
    outperformance = expected_mid - championship_position

    # Adjust for form - consistent high form is more impressive
    if driver.current_form >= 85:
        outperformance += 2
    elif driver.current_form >= 75:
        outperformance += 1
    elif driver.current_form < 60:
        outperformance -= 2

    return outperformance


def _is_hot_commodity(
    driver: Driver,
    team: Team,
    championship_position: int | None,
) -> tuple[bool, int, str]:
    """
    Check if a driver is a 'hot commodity' - significantly outperforming their car.

    Returns (is_hot, outperformance_score, reason).
    """
    outperformance = _calculate_outperformance(driver, team, championship_position)

    # Need to outperform by at least 3 positions to be considered hot
    if outperformance >= 5:
        return True, outperformance, "Dramatically outperforming car expectations"
    elif outperformance >= 3:
        return True, outperformance, "Consistently outperforming car"

    return False, outperformance, ""


def _get_contract_years_remaining(
    driver: Driver,
    contracts: list[Contract],
    current_season: int,
) -> int:
    """Get years remaining on driver's current contract."""
    contract = next(
        (c for c in contracts if c.driver_id == driver.id and c.active),
        None
    )
    if contract is None:
        return 0
    return max(0, (contract.start_season + contract.length_years) - (current_season + 1))


def _team_allows_direct_rookie_offer(
    save: SaveGame,
    team: Team,
    player: Driver,
    player_position: int,
    driver_rating: int,
    academy_trust: int | None,
    best_pipeline_position: int | None,
) -> bool:
    """Gate offers by how F1 seats usually open for rookies."""
    tier = get_team_rookie_tier(team)
    academy_affinity = _academy_affinity(team, player.academy_id)
    academy_match = academy_affinity >= 28
    affiliate_match = 0 < academy_affinity < 28
    academy_blocked = (
        best_pipeline_position is not None
        and not (academy_match or affiliate_match)
        and best_pipeline_position <= F1_INTEREST_THRESHOLDS["medium"]
    )

    if academy_blocked and player_position > max(1, best_pipeline_position - 2):
        return False

    if tier == "contender":
        if player_position != 1 or driver_rating < 88:
            return False
        if _marketability_package(player) < (84 if academy_match else 90):
            return False
        rare_chance = 6 if academy_match or (academy_trust is not None and academy_trust >= 90) else 2
        return _stable_team_roll(save, team.id, salt=31) <= rare_chance

    if tier == "upper_midfield":
        if player_position > F1_INTEREST_THRESHOLDS["high"] or driver_rating < 78:
            return False
        if _is_main_academy_team(team, player.academy_id):
            exceptional = player_position == 1 and driver_rating >= 84 and _marketability_package(player) >= 80
            trusted = academy_trust is not None and academy_trust >= 88
            if not (exceptional or trusted):
                return False
        if _is_top_team(team) and not (academy_match or affiliate_match):
            if player_position != 1 or _marketability_package(player) < 86:
                return False
        chance = 24 if academy_match else 18 if affiliate_match else 10
        return _stable_team_roll(save, team.id, salt=17) <= chance

    if tier == "lower_midfield":
        if _is_main_academy_team(team, player.academy_id):
            return player_position <= 2 and (driver_rating >= 82 or _marketability_package(player) >= 84)
        return player_position <= F1_INTEREST_THRESHOLDS["medium"] or academy_match or affiliate_match

    return player_position <= F1_INTEREST_THRESHOLDS["low"]


def _best_academy_candidate_position(
    save: SaveGame,
    team: Team,
    position_map: dict[str, int],
    exclude_driver_id: str | None = None,
) -> int | None:
    positions = [
        position_map[driver.id]
        for driver in save.drivers
        if driver.series == "F2"
        and driver.id != exclude_driver_id
        and _has_academy_path_to_team(team, driver.academy_id)
        and driver.id in position_map
        and position_map[driver.id] <= F1_INTEREST_THRESHOLDS["low"]
    ]
    return min(positions) if positions else None


def _academy_pipeline_adjustment(
    team: Team,
    driver: Driver,
    driver_position: int,
    best_pipeline_position: int | None,
) -> int:
    affinity = _academy_affinity(team, driver.academy_id)
    if affinity >= 28:
        return 24
    if affinity > 0:
        return affinity
    if not team.academy_id and best_pipeline_position is None:
        return 0
    if best_pipeline_position is None:
        return -8
    if driver_position < best_pipeline_position:
        return -18
    return -28


def _promotion_slots_for_season(save: SaveGame, candidate_count: int, opening_count: int) -> int:
    """Most F1 seasons have a reasonable number of driver moves - increased for drama."""
    if candidate_count <= 0 or opening_count <= 0:
        return 0

    rng = random.Random(save.random_seed + save.season * 3001)
    roll = rng.randint(1, 100)

    # Increased probability of multiple moves for more drama
    if roll <= 5:
        slots = 0
    elif roll <= 28:
        slots = 1
    elif roll <= 58:
        slots = 2
    elif roll <= 82:
        slots = 3
    elif roll <= 95:
        slots = 4
    else:
        slots = 5  # Big shakeup season

    return min(slots, candidate_count, opening_count)


def _choose_outgoing_f1_driver(
    drivers: list[Driver],
    contracts: list[Contract],
    team_id: str,
    season: int,
    team: Team | None = None,
    position_map: dict[str, int] | None = None,
) -> Driver | None:
    team_drivers = [driver for driver in drivers if driver.team_id == team_id and driver.series == "F1"]
    if not team_drivers:
        return None

    def replacement_pressure(driver: Driver) -> tuple[int, int, int, int]:
        contract = next((item for item in contracts if item.driver_id == driver.id and item.active), None)
        expiring = 1 if contract is None or contract.start_season + contract.length_years <= season + 1 else 0
        seat_risk = _seat_risk_score(team, driver, (position_map or {}).get(driver.id)) if team else 0
        return (expiring, seat_risk, driver.age, -get_driver_rating(driver))

    return max(team_drivers, key=replacement_pressure)


def _replace_f1_seat(
    drivers: list[Driver],
    contracts: list[Contract],
    incoming_driver_id: str,
    to_team: Team,
    season: int,
    outgoing_to_team_id: str | None = None,
    position_map: dict[str, int] | None = None,
) -> tuple[list[Driver], list[Contract], Driver | None]:
    outgoing = _choose_outgoing_f1_driver(drivers, contracts, to_team.id, season, team=to_team, position_map=position_map)
    updated_drivers: list[Driver] = []

    for driver in drivers:
        if driver.id == incoming_driver_id:
            updated_drivers.append(_with_path_adjusted_academy(driver, to_team))
        elif outgoing and driver.id == outgoing.id:
            if outgoing_to_team_id:
                updated_drivers.append(driver.model_copy(update={"team_id": outgoing_to_team_id, "series": "F1"}))
            else:
                updated_drivers.append(driver.model_copy(update={"series": "Reserve"}))
        else:
            updated_drivers.append(driver)

    inactive_driver_ids = {incoming_driver_id}
    if outgoing:
        inactive_driver_ids.add(outgoing.id)

    updated_contracts = [
        contract.model_copy(update={"active": False})
        if contract.active and contract.driver_id in inactive_driver_ids
        else contract
        for contract in contracts
    ]

    return updated_drivers, updated_contracts, outgoing


def get_f2_promotion_candidates(save: SaveGame) -> list[tuple[Driver, int]]:
    """Get F2 drivers eligible for F1 promotion with their championship position."""
    candidates = []

    # Get championship standings
    sorted_standings = sorted(
        save.standings.driver_standings, key=lambda x: x.points, reverse=True
    )
    position_map = {entry.driver_id: i + 1 for i, entry in enumerate(sorted_standings)}

    for driver in save.drivers:
        if driver.series != "F2":
            continue

        position = position_map.get(driver.id)
        if position is None:
            continue

        # Only top 10 are considered for F1
        if position <= F1_INTEREST_THRESHOLDS["low"]:
            candidates.append((driver, position))

    return candidates


def _championship_position_map(save: SaveGame) -> dict[str, int]:
    sorted_standings = sorted(
        save.standings.driver_standings, key=lambda x: x.points, reverse=True
    )
    return {entry.driver_id: i + 1 for i, entry in enumerate(sorted_standings)}


def evaluate_f1_seat_openings(save: SaveGame) -> list[tuple[Team, str | None]]:
    """
    Evaluate which F1 teams have open seats.

    Returns list of (team, reason_for_opening).
    """
    openings = []
    f1_position_map = _series_position_map(save, "F1")

    for team in save.teams:
        if team.series != "F1":
            continue

        # Get current drivers
        team_drivers = [d for d in save.drivers if d.team_id == team.id and d.series == "F1"]

        # Check contracts
        for driver in team_drivers:
            contract = next(
                (c for c in save.contracts if c.driver_id == driver.id and c.active),
                None,
            )

            if contract is None:
                openings.append((team, f"No contract for {driver.name}"))
                continue

            # Check if contract expires this season
            if contract.start_season + contract.length_years <= save.season + 1:
                seat_risk = _seat_risk_score(team, driver, f1_position_map.get(driver.id))
                if seat_risk >= 36:
                    openings.append((team, f"{driver.name} no longer fits {team.name}'s direction"))
                elif driver.age > 35 and seat_risk >= 24:
                    openings.append((team, f"{driver.name} considering retirement"))

    return openings


def _generate_affiliate_contender_rumors(
    save: SaveGame,
    openings: list[tuple[Team, str | None]],
) -> list[TransferRumor]:
    rumors: list[TransferRumor] = []
    open_team_ids = {team.id for team, _reason in openings}
    position_map = _championship_position_map(save)

    for driver in save.drivers:
        if driver.series != "F1" or not driver.academy_id:
            continue

        current_team = next((team for team in save.teams if team.id == driver.team_id), None)
        if current_team is None or _academy_affinity(current_team, driver.academy_id) <= 0:
            continue

        rating = get_driver_rating(driver)
        position = position_map.get(driver.id)
        performed_well = (
            (position is not None and position <= 8)
            or rating >= 86
            or driver.current_form >= 80
        )
        if not performed_well:
            continue

        for team in save.teams:
            if team.series != "F1" or team.id == current_team.id or team.id not in open_team_ids:
                continue
            if _academy_affinity(team, driver.academy_id) < 28:
                continue

            likelihood = 8 + max(-10, min(18, _driver_profile_fit(team, driver, position) - 78))
            if position is not None:
                if position <= 3:
                    likelihood += 26
                elif position <= 6:
                    likelihood += 18
                elif position <= 8:
                    likelihood += 10
            likelihood += max(0, min(18, rating - 80))
            likelihood += max(0, (driver.current_form - 70) // 2)
            likelihood = max(5, min(60, likelihood))

            if likelihood >= 18:
                rumors.append(
                    TransferRumor(
                        driver_id=driver.id,
                        from_team_id=current_team.id,
                        to_team_id=team.id,
                        transfer_type="lateral",
                        likelihood=likelihood,
                        reason=(
                            f"Strong affiliate-team form puts {driver.name} "
                            f"in contention for a works-team promotion"
                        ),
                    )
                )

    return rumors


def _generate_f1_lateral_move_rumors(
    save: SaveGame,
    openings: list[tuple[Team, str | None]],
) -> list[TransferRumor]:
    """
    Generate F1-to-F1 lateral move rumors based on real F1 patterns.

    Real F1 move patterns (2020-2025):
    - Drivers rarely move between top teams (Hamilton->Ferrari is historic, once per decade)
    - Drivers dropped by a team NEVER return to that team (Gasly, Albon, Ricciardo)
    - Veterans take "ambitious project" teams when no top seat available (Sainz->Williams, Alonso->AM)
    - Midfield shuffles are common (drivers moving between similar-level teams)
    - Hot commodity = young driver outperforming, NOT veteran beating a weak car
    """
    rumors: list[TransferRumor] = []
    open_team_ids = {team.id for team, _reason in openings}
    position_map = _series_position_map(save, "F1")

    # Get all F1 teams sorted by car performance
    f1_teams = sorted(
        [t for t in save.teams if t.series == "F1"],
        key=lambda t: t.car_performance,
        reverse=True
    )
    team_by_id = {t.id: t for t in f1_teams}

    for driver in save.drivers:
        if driver.series != "F1":
            continue

        # Skip player - they make their own decisions
        if driver.id == save.player_driver_id:
            continue

        current_team = team_by_id.get(driver.team_id)
        if current_team is None:
            continue

        driver_position = position_map.get(driver.id)
        driver_rating = get_driver_rating(driver)
        contract_years = _get_contract_years_remaining(driver, save.contracts, save.season)
        seat_risk = _seat_risk_score(current_team, driver, driver_position)

        # Check if driver is a hot commodity
        # BUT: veterans (30+) don't count as "hot" just for beating a weak car
        is_hot, outperformance, hot_reason = _is_hot_commodity(
            driver, current_team, driver_position
        )

        # Reduce hot commodity effect for established veterans
        # Alonso beating an Alpine is expected, not "hot commodity" material
        if driver.age >= 30 and driver_rating >= 85:
            is_hot = False  # Veterans aren't "hot commodities"
            outperformance = max(0, outperformance - 3)  # Reduce outperformance score

        # Drivers are only available if:
        # 1. Contract expiring (0 years left)
        # 2. Young hot commodity with 1 year left (teams can poach - like Piastri)
        # 3. Extremely hot young driver can force move
        driver_available = (
            contract_years == 0
            or (is_hot and contract_years <= 1 and driver.age <= 27)
            or (outperformance >= 6 and contract_years <= 1 and driver.age <= 26)
        )

        if not driver_available:
            continue

        # Is this driver in a "seatless" situation? (Sainz 2024 scenario)
        is_seatless = _is_seatless_situation(
            driver, save.contracts, save.season, seat_risk, current_team.car_performance
        )

        # Look at potential target teams
        for target_team in f1_teams:
            if target_team.id == current_team.id:
                continue
            if target_team.id not in open_team_ids:
                continue

            # ═══════════════════════════════════════════════════════════════
            # RELATIONSHIP HISTORY CHECK
            # Drivers NEVER return to teams that dropped them
            # ═══════════════════════════════════════════════════════════════
            if _was_dropped_by_team(driver.id, target_team.id):
                continue  # Gasly won't go back to Red Bull, Albon won't either

            car_improvement = target_team.car_performance - current_team.car_performance
            is_target_top_team = target_team.car_performance >= CONTENDER_PERFORMANCE
            is_current_top_team = current_team.car_performance >= CONTENDER_PERFORMANCE
            is_target_ambitious = _is_ambitious_project(target_team)

            # ═══════════════════════════════════════════════════════════════
            # ABSOLUTE LIMITS ON CAR DOWNGRADES
            # No driver takes a massive step down - they'd retire first
            # ═══════════════════════════════════════════════════════════════

            # Maximum car performance drop is -10 points
            # Beyond that is unrealistic - they'd retire or stay as reserve
            if car_improvement < -10:
                continue

            # Legends (88+ rating) won't move to backmarkers - they'd retire
            if driver_rating >= 88 and target_team.car_performance < LOWER_MIDFIELD_PERFORMANCE:
                continue

            # Old veterans (35+) won't take any step down to backmarkers
            if driver.age >= 35 and target_team.car_performance < LOWER_MIDFIELD_PERFORMANCE:
                continue

            # Very old veterans (40+) won't move to worse cars at all - they'd retire
            if driver.age >= 40 and car_improvement < 0:
                continue

            # Old veterans (35+) won't take significant step downs
            if driver.age >= 35 and car_improvement < -6:
                continue

            # ═══════════════════════════════════════════════════════════════
            # MOVE TO WORSE CAR LOGIC
            # Only happens in specific situations (Sainz->Williams, Vettel->AM)
            # ═══════════════════════════════════════════════════════════════
            if car_improvement < 0:
                # Moving to a worse car - only in specific situations:

                # 1. Seatless driver + ambitious project (reasonable step down)
                # But NOT from top team - those drivers aren't seatless
                if is_seatless and is_target_ambitious and car_improvement >= -10:
                    pass  # Allow - Sainz to Williams scenario

                # 2. Small step down (-6 or less) with expiring contract
                elif car_improvement >= -6 and contract_years == 0:
                    pass  # Allow - minor lateral move

                # 3. Driver truly has no better options and step down is reasonable
                elif (is_seatless
                      and car_improvement >= -10
                      and not _driver_has_better_options(
                          driver, current_team, f1_teams, open_team_ids, driver_rating
                      )):
                    pass  # Allow - taking best available

                else:
                    continue  # Don't move to worse car

            # ═══════════════════════════════════════════════════════════════
            # TOP TEAM TO TOP TEAM MOVES
            # Extremely rare - Hamilton to Ferrari is once per decade
            # ═══════════════════════════════════════════════════════════════
            if is_current_top_team and is_target_top_team:
                # This is a blockbuster move - needs special circumstances
                # Only WDC-level drivers even considered
                if driver_rating < 90:
                    continue

                # Need to be a true elite (top 3 in championship)
                if driver_position is None or driver_position > 3:
                    continue

                # Very low base likelihood - these are rare
                likelihood = 8

                # Only if contract is truly expiring
                if contract_years > 0:
                    continue

                # Slight boost for academy connection
                if _academy_affinity(target_team, driver.academy_id) >= 28:
                    likelihood += 5

            else:
                # Normal lateral move logic
                prefs = _team_prefs(target_team)
                min_rating = int(prefs["min_rating"])

                # ═══════════════════════════════════════════════════════════════
                # HARD RATING BLOCK
                # Drivers significantly below team's minimum are NEVER considered
                # Ferrari (86) won't sign an Ocon (77) - they just won't
                # ═══════════════════════════════════════════════════════════════
                if driver_rating < min_rating - 5:
                    continue  # Not even close to good enough

                # Top teams (title_contender, big_brand) have stricter standards
                if target_team.hiring_profile in {"title_contender", "big_brand"}:
                    if driver_rating < min_rating - 2:
                        continue  # Top teams don't compromise on quality

                likelihood = 15

                # Hot commodity bonus (only for young drivers)
                if is_hot and driver.age <= 27:
                    likelihood += min(20, outperformance * 3)

                # Championship position bonus
                if driver_position is not None:
                    if driver_position <= 5:
                        likelihood += 15
                    elif driver_position <= 10:
                        likelihood += 8
                    elif driver_position <= 15:
                        likelihood += 3

                # Rating check vs target team minimum
                if driver_rating >= min_rating + 5:
                    likelihood += 12
                elif driver_rating >= min_rating:
                    likelihood += 6
                elif driver_rating >= min_rating - 3:
                    pass
                else:
                    likelihood -= 15

                # Car improvement desire
                if car_improvement >= 10:
                    likelihood += 12
                elif car_improvement >= 5:
                    likelihood += 6
                elif car_improvement >= 0:
                    likelihood += 2
                elif is_target_ambitious:
                    # Ambitious project can offset worse car
                    likelihood += 8

                # Academy connection
                academy_affinity = _academy_affinity(target_team, driver.academy_id)
                if academy_affinity >= 28:
                    likelihood += 15
                elif academy_affinity > 0:
                    likelihood += 6

                # Veteran + ambitious project bonus (Alonso to AM, Sainz to Williams)
                if driver.age >= 28 and is_target_ambitious and is_seatless:
                    likelihood += 20

                # Profile fit
                fit_score = _driver_profile_fit(target_team, driver, driver_position)
                likelihood += max(-8, min(12, (fit_score - 75) // 2))

                # Contract status
                if contract_years == 0:
                    likelihood += 8
                elif contract_years == 1 and is_hot:
                    likelihood += 3

                # Age considerations
                if driver.age >= 35 and target_team.hiring_profile == "junior_pipeline":
                    likelihood -= 25
                elif driver.age <= 25 and target_team.hiring_profile in {"junior_pipeline", "long_term_project"}:
                    likelihood += 6

            # Tier caps - but more realistic
            team_tier = get_team_rookie_tier(target_team)
            tier_caps = {
                "contender": 25,       # Very hard to get into contenders via lateral
                "upper_midfield": 55,  # Difficult but possible
                "lower_midfield": 75,  # Common
                "backmarker": 85,
            }
            cap = tier_caps.get(team_tier, 75)

            # Young hot commodities can exceed caps slightly
            if is_hot and driver.age <= 26 and outperformance >= 4:
                cap = min(70, cap + 15)

            likelihood = max(5, min(cap, likelihood))

            if likelihood >= 20:
                # Generate appropriate reason
                if is_seatless and is_target_ambitious:
                    reason = f"{driver.name} eyes {target_team.name}'s ambitious project after losing current seat"
                elif is_hot and car_improvement >= 5:
                    reason = f"{driver.name}'s breakout performances attract {target_team.name}"
                elif contract_years == 0 and car_improvement > 0:
                    reason = f"{driver.name} available as free agent, {target_team.name} offers competitive seat"
                elif is_current_top_team and is_target_top_team:
                    reason = f"Blockbuster: {driver.name} in talks with {target_team.name} for historic move"
                else:
                    reason = f"{target_team.name} evaluating {driver.name} for vacant seat"

                rumors.append(
                    TransferRumor(
                        driver_id=driver.id,
                        from_team_id=current_team.id,
                        to_team_id=target_team.id,
                        transfer_type="lateral",
                        likelihood=likelihood,
                        reason=reason,
                    )
                )

    return rumors


def generate_transfer_rumors(save: SaveGame) -> list[TransferRumor]:
    """Generate realistic transfer rumors for the silly season."""
    rumors = []

    # Get promotion candidates
    candidates = get_f2_promotion_candidates(save)
    position_map = {driver.id: position for driver, position in candidates}

    # Get F1 seat openings
    openings = evaluate_f1_seat_openings(save)

    # Generate F1-to-F1 lateral move rumors (hot commodities, expiring contracts)
    rumors.extend(_generate_f1_lateral_move_rumors(save, openings))

    # Generate academy affiliate to parent team promotion rumors
    rumors.extend(_generate_affiliate_contender_rumors(save, openings))

    # Generate rumors for each opening
    for team, reason in openings:
        team_prefs = _team_prefs(team)
        team_candidate_positions = {
            driver.id: position
            for driver, position in candidates
            if _has_academy_path_to_team(team, driver.academy_id)
        }

        for driver, position in candidates:
            # Calculate likelihood based on multiple factors
            likelihood = 50

            # Position bonus
            if position <= F1_INTEREST_THRESHOLDS["high"]:
                likelihood += 30
            elif position <= F1_INTEREST_THRESHOLDS["medium"]:
                likelihood += 15

            # Academy connection bonus
            best_pipeline_position = _best_academy_candidate_position(
                save,
                team,
                position_map,
                exclude_driver_id=driver.id,
            )
            own_pipeline_position = team_candidate_positions.get(driver.id)
            if own_pipeline_position is not None:
                likelihood += 25
            else:
                likelihood += _academy_pipeline_adjustment(
                    team,
                    driver,
                    position,
                    best_pipeline_position,
                )

            # Rating check
            driver_rating = get_driver_rating(driver)
            marketability = _marketability_package(driver)
            if _is_main_academy_team(team, driver.academy_id):
                exceptional_main_team_case = position == 1 and driver_rating >= 84 and marketability >= 80
                if not exceptional_main_team_case:
                    continue
            if _is_top_team(team) and not _has_academy_path_to_team(team, driver.academy_id):
                if position != 1 or driver_rating < 86 or marketability < 86:
                    continue

            likelihood += max(-16, min(18, _driver_profile_fit(team, driver, position) - 76))
            if driver_rating >= int(team_prefs["min_rating"]):
                likelihood += 10
            else:
                likelihood -= 20

            # Team prestige affects likelihood
            if team.car_performance >= 90:
                likelihood -= 15  # Harder to get into top teams
            elif team.car_performance <= 70:
                likelihood += 10  # Easier for lower teams

            if _is_top_team(team):
                likelihood += max(-24, min(18, (marketability - 80) // 2))
                if not _has_academy_path_to_team(team, driver.academy_id):
                    likelihood += max(-20, min(12, marketability - 84))
                if _is_main_academy_team(team, driver.academy_id) and not (
                    position == 1 and driver_rating >= 84 and marketability >= 80
                ):
                    likelihood -= 28
            elif team.hiring_profile in {"financially_pressured", "big_brand"}:
                likelihood += max(-8, min(12, (marketability - 74) // 2))

            likelihood = max(5, min(95, likelihood))

            if likelihood >= 20:  # Only create rumors with reasonable likelihood
                rumor = TransferRumor(
                    driver_id=driver.id,
                    from_team_id=driver.team_id,
                    to_team_id=team.id,
                    transfer_type="promotion",
                    likelihood=likelihood,
                    reason=f"Strong F2 performance (P{position}) attracts interest",
                )
                rumors.append(rumor)

    return rumors


def evaluate_player_f1_offers(save: SaveGame) -> list[dict]:
    """
    Evaluate F1 offers for the player based on their performance.

    Returns list of potential offers with team info and likelihood.
    """
    offers = []

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if not player or player.series != "F2":
        return offers

    # Get player championship position
    sorted_standings = sorted(
        save.standings.driver_standings, key=lambda x: x.points, reverse=True
    )
    position_map = {entry.driver_id: i + 1 for i, entry in enumerate(sorted_standings)}
    player_position = next(
        (position for driver_id, position in position_map.items() if driver_id == player.id),
        None,
    )

    if player_position is None or player_position > F1_INTEREST_THRESHOLDS["low"]:
        return offers

    # Get player's academy trust
    academy_trust = None
    if player.academy_id:
        academy_state = next(
            (s for s in save.academy_states if s.academy_id == player.academy_id), None
        )
        if academy_state:
            academy_trust = academy_state.trust

    # Seat openings are evaluated per seat, but player offers are per team.
    openings = evaluate_f1_seat_openings(save)
    open_teams: dict[str, Team] = {}
    for team, _reason in openings:
        open_teams[team.id] = team

    for team in open_teams.values():
        team_prefs = _team_prefs(team)
        driver_rating = get_driver_rating(player)
        tier = get_team_rookie_tier(team)
        best_pipeline_position = _best_academy_candidate_position(
            save,
            team,
            position_map,
            exclude_driver_id=player.id,
        )

        if not _team_allows_direct_rookie_offer(
            save=save,
            team=team,
            player=player,
            player_position=player_position,
            driver_rating=driver_rating,
            academy_trust=academy_trust,
            best_pipeline_position=best_pipeline_position,
        ):
            continue

        # Base likelihood: rookies usually start in lower-midfield/backmarker seats.
        if tier == "backmarker":
            likelihood = 48
        elif tier == "lower_midfield":
            likelihood = 36
        elif tier == "upper_midfield":
            likelihood = 18
        else:
            likelihood = 6

        # Position bonus
        if player_position == 1:
            likelihood += 18
        elif player_position <= 3:
            likelihood += 10
        elif player_position <= 6:
            likelihood += 5

        # Academy connection
        if player.academy_id and team.academy_id == player.academy_id:
            likelihood += 24
            if academy_trust and academy_trust >= 70:
                likelihood += 10
        else:
            likelihood += _academy_pipeline_adjustment(
                team,
                player,
                player_position,
                best_pipeline_position,
            )
            if best_pipeline_position is not None and _academy_affinity(team, player.academy_id) == 0:
                likelihood -= 12

        # Rating check
        likelihood += max(-10, min(14, _driver_profile_fit(team, player, player_position) - 76))
        if driver_rating >= int(team_prefs["min_rating"]):
            likelihood += 8
        else:
            likelihood -= 14

        marketability = _marketability_package(player)
        likelihood += identity_team_fit_bonus(player, team)
        if _is_top_team(team):
            likelihood += max(-22, min(18, (marketability - 80) // 2))
            if not _has_academy_path_to_team(team, player.academy_id):
                likelihood += max(-18, min(12, marketability - 84))
        elif team.hiring_profile in {"financially_pressured", "big_brand"}:
            likelihood += max(-8, min(12, (marketability - 74) // 2))

        likelihood += max(-8, min(10, (driver_rating - 74) // 2))
        likelihood += max(0, (60 - (team.seat_security or 60)) // 3)

        tier_caps = {
            "contender": 18,
            "upper_midfield": 45,
            "lower_midfield": 72,
            "backmarker": 85,
        }
        likelihood = max(0, min(tier_caps[tier], likelihood))

        if likelihood >= 12:
            offers.append({
                "team_id": team.id,
                "team_name": team.name,
                "likelihood": likelihood,
                "role": "f1_race_seat",
                "car_performance": team.car_performance,
                "is_academy_team": team.academy_id == player.academy_id,
                "tier": tier,
            })

    # Sort by likelihood
    offers.sort(key=lambda x: x["likelihood"], reverse=True)

    return offers


def _determine_contract_length(
    rng: random.Random,
    driver: Driver,
    team: Team,
    transfer_type: TransferType,
    championship_position: int | None,
) -> int:
    """
    Determine realistic contract length based on driver/team factors.

    - Top teams offer longer contracts to stars
    - Rookies often get 1-2 year deals
    - Hot commodities can demand longer contracts
    - Older drivers get shorter deals
    """
    base_length = 2

    # Top teams offer longer contracts to proven drivers
    if team.car_performance >= CONTENDER_PERFORMANCE:
        if championship_position is not None and championship_position <= 5:
            base_length = 3  # Top performer at top team
        elif get_driver_rating(driver) >= 88:
            base_length = 3
        else:
            base_length = 2

    # Rookies get shorter initial deals
    if transfer_type == "promotion":
        base_length = rng.choice([1, 1, 2])  # Weighted toward 1 year

    # Age adjustments
    if driver.age >= 35:
        base_length = min(base_length, 1)  # Max 1 year for older drivers
    elif driver.age >= 32:
        base_length = min(base_length, 2)  # Max 2 years

    # Hot commodities can demand longer
    if championship_position is not None:
        is_hot, outperformance, _ = _is_hot_commodity(
            driver, team, championship_position
        )
        if is_hot and outperformance >= 4:
            base_length = min(4, base_length + 1)

    # High-potential young drivers may get longer deals to lock them in
    if driver.age <= 24 and driver.hidden.potential >= 88:
        base_length = max(base_length, 2)
        if team.academy_id == driver.academy_id:
            base_length = max(base_length, 3)

    # Add some randomness
    variance = rng.choice([-1, 0, 0, 0, 1])
    return max(1, min(5, base_length + variance))


def simulate_silly_season(save: SaveGame) -> tuple[SaveGame, list[NewsItem]]:
    """
    Simulate the full silly season driver market.

    Processes AI driver moves and generates news.
    """
    news = []
    updated_drivers = list(save.drivers)
    updated_contracts = list(save.contracts)
    f1_position_map = _series_position_map(save, "F1")

    # Generate rumors
    rumors = sorted(generate_transfer_rumors(save), key=lambda item: item.likelihood, reverse=True)

    # Calculate promotion slots (F2 -> F1)
    promotion_slots = _promotion_slots_for_season(
        save,
        candidate_count=len({rumor.driver_id for rumor in rumors if rumor.transfer_type == "promotion"}),
        opening_count=len({rumor.to_team_id for rumor in rumors if rumor.transfer_type == "promotion"}),
    )

    # Calculate lateral move slots (F1 -> F1) - typically 1-3 per season
    rng = random.Random(save.random_seed + save.season * 1000)
    lateral_roll = rng.randint(1, 100)
    if lateral_roll <= 30:
        lateral_slots = 1
    elif lateral_roll <= 70:
        lateral_slots = 2
    elif lateral_roll <= 90:
        lateral_slots = 3
    else:
        lateral_slots = 4  # Big shakeup season

    promotions_completed = 0
    laterals_completed = 0
    used_f1_teams: set[str] = set()
    moved_drivers: set[str] = set()  # Track all moved drivers (promotions + laterals)

    # Process rumors and make some happen
    for rumor in rumors:
        if rumor.confirmed:
            continue
        if rumor.to_team_id in used_f1_teams:
            continue
        if rumor.driver_id in moved_drivers:
            continue

        # Check slot limits by transfer type
        if rumor.transfer_type == "promotion":
            if promotions_completed >= promotion_slots:
                continue
        elif rumor.transfer_type == "lateral":
            if laterals_completed >= lateral_slots:
                continue
            # Also check that source team isn't already losing a driver
            if rumor.from_team_id and rumor.from_team_id in used_f1_teams:
                continue

        # Roll against likelihood
        if rng.randint(1, 100) <= rumor.likelihood:
            rumor.confirmed = True

            # Find driver and update
            driver_idx = next(
                (i for i, d in enumerate(updated_drivers) if d.id == rumor.driver_id), None
            )
            if driver_idx is None:
                continue

            driver = updated_drivers[driver_idx]
            to_team = next((t for t in save.teams if t.id == rumor.to_team_id), None)

            if to_team is None:
                continue

            # Skip if this is the player
            if driver.id == save.player_driver_id:
                continue

            outgoing_driver = None
            if to_team.series == "F1":
                updated_drivers, updated_contracts, outgoing_driver = _replace_f1_seat(
                    updated_drivers,
                    updated_contracts,
                    incoming_driver_id=driver.id,
                    to_team=to_team,
                    season=save.season,
                    outgoing_to_team_id=rumor.from_team_id if driver.series == "F1" else None,
                    position_map=f1_position_map,
                )
                if rumor.transfer_type == "promotion":
                    promotions_completed += 1
                elif rumor.transfer_type == "lateral":
                    laterals_completed += 1
                    # For lateral moves, mark source team as used too
                    if rumor.from_team_id:
                        used_f1_teams.add(rumor.from_team_id)
                moved_drivers.add(driver.id)
                used_f1_teams.add(rumor.to_team_id)
            else:
                updated_driver = _with_path_adjusted_academy(driver, to_team)
                updated_drivers[driver_idx] = updated_driver
                moved_drivers.add(driver.id)

            # Determine realistic contract length
            driver_position = f1_position_map.get(driver.id)
            contract_length = _determine_contract_length(
                rng, driver, to_team, rumor.transfer_type, driver_position
            )

            # Create new contract
            new_contract = Contract(
                id=f"contract_{uuid.uuid4().hex[:8]}",
                driver_id=driver.id,
                team_id=rumor.to_team_id,
                role="f1_race_seat" if to_team.series == "F1" else "f2_race_seat",
                start_season=save.season + 1,
                length_years=contract_length,
                active=True,
            )
            updated_contracts.append(new_contract)

            # Generate news
            from_team = next((t for t in save.teams if t.id == rumor.from_team_id), None)
            from_team_name = from_team.name if from_team else "F2"

            if rumor.transfer_type == "promotion":
                headline = f"{driver.name} to make F1 debut with {to_team.name}"
                replacement_note = (
                    f" The move comes as {outgoing_driver.name} exits the race seat."
                    if outgoing_driver
                    else ""
                )
                body = f"After a strong F2 campaign, {driver.name} will step up to Formula 1, " \
                       f"leaving {from_team_name} for a seat at {to_team.name}.{replacement_note}"
                importance = 5
            elif rumor.transfer_type == "lateral" and from_team:
                # F1-to-F1 lateral move - more dramatic news
                is_hot, outperformance, _ = _is_hot_commodity(
                    driver, from_team, driver_position
                )
                if is_hot:
                    headline = f"BLOCKBUSTER: {driver.name} leaves {from_team.name} for {to_team.name}"
                    body = (
                        f"In a stunning move, {driver.name} has secured a seat at {to_team.name}, "
                        f"leaving {from_team.name} after outperforming expectations. "
                        f"The {contract_length}-year deal represents a major coup for {to_team.name}."
                    )
                else:
                    headline = f"{driver.name} makes switch to {to_team.name}"
                    body = (
                        f"{driver.name} will join {to_team.name} next season, departing {from_team.name}. "
                        f"The move sees the driver sign a {contract_length}-year contract."
                    )
                if outgoing_driver:
                    body += f" {outgoing_driver.name} moves in the opposite direction to {from_team.name}."
                importance = 5
            else:
                headline = f"{driver.name} joins {to_team.name}"
                body = f"{driver.name} has signed with {to_team.name} for the upcoming season."
                importance = 4

            news.append(
                NewsItem(
                    id=f"transfer_{uuid.uuid4().hex[:8]}",
                    date=save.current_date,
                    category="contract",
                    headline=headline,
                    body=body,
                    linked_driver_ids=[driver.id],
                    importance=importance,
                )
            )

    updated_save = save.model_copy(
        update={
            "drivers": updated_drivers,
            "contracts": updated_contracts,
        }
    )

    return updated_save, news


def generate_mid_season_drama(save: SaveGame, completed_rounds: int) -> tuple[SaveGame, list[NewsItem]]:
    """
    Generate mid-season transfer rumors, drama, and occasional moves.

    Called every few rounds to keep the paddock lively.
    """
    if completed_rounds < 3 or completed_rounds % 2 != 0:
        return save, []

    rng = random.Random(f"{save.random_seed}:{save.season}:midseason:{completed_rounds}")
    news: list[NewsItem] = []
    updated_drivers = list(save.drivers)
    updated_contracts = list(save.contracts)

    # Generate rumors about seat pressure
    f1_position_map = _series_position_map(save, "F1")
    f2_position_map = _series_position_map(save, "F2")

    at_risk_drivers: list[tuple[Driver, Team, int]] = []

    for team in save.teams:
        if team.series not in ("F1", "F2"):
            continue

        position_map = f1_position_map if team.series == "F1" else f2_position_map
        team_drivers = [d for d in save.drivers if d.team_id == team.id and d.series == team.series]

        for driver in team_drivers:
            if driver.id == save.player_driver_id:
                continue

            risk = _seat_risk_score(team, driver, position_map.get(driver.id))
            if risk >= 45:
                at_risk_drivers.append((driver, team, risk))

    # Sort by risk level
    at_risk_drivers.sort(key=lambda x: x[2], reverse=True)

    # Generate pressure news for top at-risk drivers
    for driver, team, risk in at_risk_drivers[:3]:
        if rng.randint(1, 100) <= 35:  # 35% chance of news
            if risk >= 65:
                headline = f"Seat in jeopardy: {driver.name} under serious pressure at {team.name}"
                body = (
                    f"Sources suggest {team.name} is actively evaluating alternatives. "
                    f"Recent form has raised questions in the paddock about the driver's future."
                )
                importance = 4
            else:
                headline = f"Paddock whispers: {driver.name} faces scrutiny"
                body = f"Performance questions are growing around {driver.name}'s seat at {team.name}."
                importance = 3

            news.append(
                NewsItem(
                    id=f"seat_pressure_{uuid.uuid4().hex[:8]}",
                    date=save.current_date,
                    category="rumor",
                    headline=headline,
                    body=body,
                    linked_driver_ids=[driver.id],
                    importance=importance,
                )
            )

    # Rare mid-season driver swap (only in extreme cases)
    if at_risk_drivers and rng.randint(1, 100) <= 8:  # 8% chance per check
        driver, team, risk = at_risk_drivers[0]
        if risk >= 70 and team.series == "F1":
            # Find a reserve driver or F2 champion candidate
            reserves = [d for d in save.drivers if d.series == "Reserve"]
            f2_stars = [
                d for d in save.drivers
                if d.series == "F2" and get_driver_rating(d) >= 82
            ]
            candidates = reserves + f2_stars

            if candidates:
                replacement = rng.choice(candidates)
                # Execute the swap
                driver_idx = next(i for i, d in enumerate(updated_drivers) if d.id == driver.id)
                replacement_idx = next(i for i, d in enumerate(updated_drivers) if d.id == replacement.id)

                updated_drivers[driver_idx] = driver.model_copy(update={"series": "Reserve"})
                updated_drivers[replacement_idx] = replacement.model_copy(
                    update={"team_id": team.id, "series": "F1"}
                )

                # Update contracts
                for i, contract in enumerate(updated_contracts):
                    if contract.driver_id == driver.id and contract.active:
                        updated_contracts[i] = contract.model_copy(update={"active": False})

                new_contract = Contract(
                    id=f"contract_{uuid.uuid4().hex[:8]}",
                    driver_id=replacement.id,
                    team_id=team.id,
                    role="f1_race_seat",
                    start_season=save.season,
                    length_years=1,
                    active=True,
                )
                updated_contracts.append(new_contract)

                news.append(
                    NewsItem(
                        id=f"midseason_swap_{uuid.uuid4().hex[:8]}",
                        date=save.current_date,
                        category="contract",
                        headline=f"BREAKING: {team.name} drops {driver.name}, calls up {replacement.name}",
                        body=(
                            f"In a dramatic mid-season move, {team.name} has parted ways with {driver.name}. "
                            f"{replacement.name} will take over the seat effective immediately."
                        ),
                        linked_driver_ids=[driver.id, replacement.id],
                        importance=5,
                    )
                )

    # Generate hot prospect rumors
    hot_prospects = [
        d for d in save.drivers
        if d.series == "F2"
        and d.current_form >= 80
        and get_driver_rating(d) >= 80
    ]

    for prospect in hot_prospects[:2]:
        if rng.randint(1, 100) <= 25:  # 25% chance
            target_teams = [t for t in save.teams if t.series == "F1"]
            if target_teams:
                target = rng.choice(target_teams)
                news.append(
                    NewsItem(
                        id=f"prospect_rumor_{uuid.uuid4().hex[:8]}",
                        date=save.current_date,
                        category="rumor",
                        headline=f"{target.name} watching {prospect.name} closely",
                        body=(
                            f"The impressive form of {prospect.name} has caught the attention of {target.name}. "
                            f"Paddock sources suggest preliminary talks may have already begun."
                        ),
                        linked_driver_ids=[prospect.id],
                        importance=3,
                    )
                )

    updated_save = save.model_copy(
        update={
            "drivers": updated_drivers,
            "contracts": updated_contracts,
        }
    )

    return updated_save, news


def generate_silly_season_rumors_news(save: SaveGame) -> list[NewsItem]:
    """Generate news items about transfer rumors."""
    news = []
    rumors = generate_transfer_rumors(save)

    # Only generate news for high-likelihood rumors
    for rumor in rumors[:5]:  # Top 5 rumors
        if rumor.likelihood < 40:
            continue

        driver = next((d for d in save.drivers if d.id == rumor.driver_id), None)
        team = next((t for t in save.teams if t.id == rumor.to_team_id), None)

        if not driver or not team:
            continue

        if rumor.likelihood >= 70:
            headline = f"RUMOR: {driver.name} strongly linked to {team.name}"
            importance = 4
        else:
            headline = f"RUMOR: {team.name} showing interest in {driver.name}"
            importance = 3

        news.append(
            NewsItem(
                id=f"rumor_{uuid.uuid4().hex[:8]}",
                date=save.current_date,
                category="rumor",
                headline=headline,
                body=rumor.reason,
                linked_driver_ids=[driver.id],
                importance=importance,
            )
        )

    return news


def process_player_f1_decision(
    save: SaveGame,
    accept_offer: bool,
    team_id: str | None = None,
) -> tuple[SaveGame, list[NewsItem]]:
    """
    Process player's decision on F1 offers.

    If accepting, promotes player to F1.
    """
    news = []

    if not accept_offer or not team_id:
        # Player stays in F2
        news.append(
            NewsItem(
                id=f"player_stays_{uuid.uuid4().hex[:8]}",
                date=save.current_date,
                category="contract",
                headline="You commit to another F2 season",
                body="After careful consideration, you've decided to continue your F2 campaign.",
                linked_driver_ids=[save.player_driver_id] if save.player_driver_id else [],
                importance=4,
            )
        )
        return save, news

    # Find player and team
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    team = next((t for t in save.teams if t.id == team_id), None)

    if not player or not team:
        return save, news

    updated_drivers, updated_contracts, outgoing_driver = _replace_f1_seat(
        list(save.drivers),
        list(save.contracts),
        incoming_driver_id=player.id,
        to_team=team,
        season=save.season,
    )

    # Create F1 contract
    new_contract = Contract(
        id=f"contract_{uuid.uuid4().hex[:8]}",
        driver_id=player.id,
        team_id=team_id,
        role="f1_race_seat",
        start_season=save.season + 1,
        length_years=2,
        active=True,
    )
    updated_contracts = [*updated_contracts, new_contract]

    # Generate promotion news
    news.append(
        NewsItem(
            id=f"player_promoted_{uuid.uuid4().hex[:8]}",
            date=save.current_date,
            category="contract",
            headline=f"OFFICIAL: You sign with {team.name} for F1!",
            body=f"Dreams become reality as you secure an F1 seat with {team.name}. "
                 f"Your F2 journey has paid off."
                 + (
                     f" {outgoing_driver.name} exits the race seat as part of the change."
                     if outgoing_driver
                     else ""
                 ),
            linked_driver_ids=[player.id],
            importance=5,
        )
    )

    updated_save = save.model_copy(
        update={
            "drivers": updated_drivers,
            "contracts": updated_contracts,
            "news": [*save.news, *news],
        }
    )

    return updated_save, news
