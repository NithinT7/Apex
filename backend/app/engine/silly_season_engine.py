"""Engine for F1 silly season driver market simulation."""

from __future__ import annotations

import random
import uuid
from typing import Literal

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

    return int(score)


def _seat_risk_score(team: Team, driver: Driver, championship_position: int | None = None) -> int:
    prefs = _team_prefs(team)
    min_rating = int(prefs["min_rating"])
    rating = get_driver_rating(driver)
    fit = _driver_profile_fit(team, driver, championship_position)
    risk = 0
    risk += max(0, (min_rating - rating) * 4)
    risk += max(0, 72 - fit) * 2
    risk += max(0, 58 - driver.current_form)
    if championship_position is not None:
        team_driver_count = 22
        risk += max(0, championship_position - team_driver_count // 2)
    if driver.age >= 36:
        risk += (driver.age - 35) * 5 + driver.hidden.retirement_chance
    if driver.hidden.loyalty < 62:
        risk += 4
    if driver.attributes.aggression - driver.attributes.discipline > 12:
        risk += 5
    if team.hiring_profile == "financially_pressured":
        risk -= max(0, driver.attributes.sponsor_value - 78) // 2
    if team.hiring_profile == "big_brand":
        risk -= max(0, driver.attributes.marketability - 82) // 2
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
        and (team.hiring_profile in {"title_contender", "big_brand"} or team.car_performance >= 80)
    )


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
    """Most F1 seasons have only a small number of direct junior promotions."""
    if candidate_count <= 0 or opening_count <= 0:
        return 0

    rng = random.Random(save.random_seed + save.season * 3001)
    roll = rng.randint(1, 100)

    if roll <= 12:
        slots = 0
    elif roll <= 58:
        slots = 1
    elif roll <= 88:
        slots = 2
    elif roll <= 98:
        slots = 3
    else:
        slots = 4

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


def generate_transfer_rumors(save: SaveGame) -> list[TransferRumor]:
    """Generate realistic transfer rumors for the silly season."""
    rumors = []

    # Get promotion candidates
    candidates = get_f2_promotion_candidates(save)
    position_map = {driver.id: position for driver, position in candidates}

    # Get F1 seat openings
    openings = evaluate_f1_seat_openings(save)
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
    promotion_slots = _promotion_slots_for_season(
        save,
        candidate_count=len({rumor.driver_id for rumor in rumors if rumor.transfer_type == "promotion"}),
        opening_count=len({rumor.to_team_id for rumor in rumors if rumor.transfer_type == "promotion"}),
    )
    promotions_completed = 0
    used_f1_teams: set[str] = set()
    promoted_drivers: set[str] = set()

    # Process rumors and make some happen
    rng = random.Random(save.random_seed + save.season * 1000)

    for rumor in rumors:
        if rumor.confirmed:
            continue
        if rumor.to_team_id in used_f1_teams:
            continue
        if rumor.transfer_type == "promotion":
            if promotions_completed >= promotion_slots:
                continue
            if rumor.driver_id in promoted_drivers:
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
                    promoted_drivers.add(driver.id)
                used_f1_teams.add(rumor.to_team_id)
            else:
                updated_driver = _with_path_adjusted_academy(driver, to_team)
                updated_drivers[driver_idx] = updated_driver

            # Create new contract
            new_contract = Contract(
                id=f"contract_{uuid.uuid4().hex[:8]}",
                driver_id=driver.id,
                team_id=rumor.to_team_id,
                role="f1_race_seat" if to_team.series == "F1" else "f2_race_seat",
                start_season=save.season + 1,
                length_years=rng.choice([1, 2, 3]),
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
