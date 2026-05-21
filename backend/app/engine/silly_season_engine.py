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
    "title_contender": {"min_rating": 85, "prefer_experienced": True, "academy_weight": 0.3},
    "established_midfield": {"min_rating": 75, "prefer_experienced": True, "academy_weight": 0.5},
    "rising_midfield": {"min_rating": 70, "prefer_experienced": False, "academy_weight": 0.7},
    "developing_team": {"min_rating": 60, "prefer_experienced": False, "academy_weight": 0.8},
}

# F2 championship position thresholds for F1 interest
F1_INTEREST_THRESHOLDS = {
    "high": 3,  # Top 3 finishers get strong interest
    "medium": 6,  # Top 6 get moderate interest
    "low": 10,  # Top 10 get some interest
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


def get_driver_rating(driver: Driver) -> int:
    """Calculate overall driver rating from attributes."""
    attrs = driver.attributes
    pace_rating = (attrs.pace + attrs.qualifying + attrs.racecraft) / 3
    consistency_rating = (attrs.consistency + attrs.composure + attrs.focus) / 3
    return int((pace_rating * 0.6 + consistency_rating * 0.4))


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


def evaluate_f1_seat_openings(save: SaveGame) -> list[tuple[Team, str | None]]:
    """
    Evaluate which F1 teams have open seats.

    Returns list of (team, reason_for_opening).
    """
    openings = []

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
                # Evaluate if team wants to renew
                driver_rating = get_driver_rating(driver)
                team_prefs = HIRING_PREFERENCES.get(team.hiring_profile, HIRING_PREFERENCES["established_midfield"])

                if driver_rating < team_prefs["min_rating"]:
                    openings.append((team, f"{driver.name} below team expectations"))
                elif driver.age > 35:
                    openings.append((team, f"{driver.name} considering retirement"))

    return openings


def generate_transfer_rumors(save: SaveGame) -> list[TransferRumor]:
    """Generate realistic transfer rumors for the silly season."""
    rumors = []

    # Get promotion candidates
    candidates = get_f2_promotion_candidates(save)

    # Get F1 seat openings
    openings = evaluate_f1_seat_openings(save)

    # Generate rumors for each opening
    for team, reason in openings:
        team_prefs = HIRING_PREFERENCES.get(team.hiring_profile, HIRING_PREFERENCES["established_midfield"])

        for driver, position in candidates:
            # Calculate likelihood based on multiple factors
            likelihood = 50

            # Position bonus
            if position <= F1_INTEREST_THRESHOLDS["high"]:
                likelihood += 30
            elif position <= F1_INTEREST_THRESHOLDS["medium"]:
                likelihood += 15

            # Academy connection bonus
            if driver.academy_id and team.academy_id == driver.academy_id:
                likelihood += 25

            # Rating check
            driver_rating = get_driver_rating(driver)
            if driver_rating >= team_prefs["min_rating"]:
                likelihood += 10
            else:
                likelihood -= 20

            # Team prestige affects likelihood
            if team.car_performance >= 90:
                likelihood -= 15  # Harder to get into top teams
            elif team.car_performance <= 70:
                likelihood += 10  # Easier for lower teams

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
    player_position = next(
        (i + 1 for i, entry in enumerate(sorted_standings) if entry.driver_id == player.id),
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

    # Get F1 openings
    openings = evaluate_f1_seat_openings(save)

    for team, reason in openings:
        team_prefs = HIRING_PREFERENCES.get(team.hiring_profile, HIRING_PREFERENCES["established_midfield"])

        # Base likelihood
        likelihood = 40

        # Position bonus
        if player_position == 1:
            likelihood += 40
        elif player_position <= 3:
            likelihood += 25
        elif player_position <= 6:
            likelihood += 10

        # Academy connection
        if player.academy_id and team.academy_id == player.academy_id:
            likelihood += 30
            if academy_trust and academy_trust >= 70:
                likelihood += 15

        # Rating check
        driver_rating = get_driver_rating(player)
        if driver_rating >= team_prefs["min_rating"]:
            likelihood += 10
        else:
            likelihood -= 30

        # Team tier adjustment
        if team.car_performance >= 90:
            likelihood -= 25  # Very hard to get into top teams directly
        elif team.car_performance >= 80:
            likelihood -= 10

        likelihood = max(0, min(100, likelihood))

        if likelihood >= 15:
            offers.append({
                "team_id": team.id,
                "team_name": team.name,
                "likelihood": likelihood,
                "role": "f1_race_seat",
                "car_performance": team.car_performance,
                "is_academy_team": team.academy_id == player.academy_id,
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

    # Generate rumors
    rumors = generate_transfer_rumors(save)

    # Process rumors and make some happen
    rng = random.Random(save.random_seed + save.season * 1000)

    for rumor in rumors:
        if rumor.confirmed:
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

            # Update driver team and series
            updated_driver = driver.model_copy(
                update={
                    "team_id": rumor.to_team_id,
                    "series": to_team.series,
                }
            )
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
                body = f"After a strong F2 campaign, {driver.name} will step up to Formula 1, " \
                       f"leaving {from_team_name} for a seat at {to_team.name}."
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

    # Update player
    updated_drivers = [
        d.model_copy(update={"team_id": team_id, "series": "F1"})
        if d.id == player.id else d
        for d in save.drivers
    ]

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
    updated_contracts = [*save.contracts, new_contract]

    # Generate promotion news
    news.append(
        NewsItem(
            id=f"player_promoted_{uuid.uuid4().hex[:8]}",
            date=save.current_date,
            category="contract",
            headline=f"OFFICIAL: You sign with {team.name} for F1!",
            body=f"Dreams become reality as you secure an F1 seat with {team.name}. "
                 f"Your F2 journey has paid off.",
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
