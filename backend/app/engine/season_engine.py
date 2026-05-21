"""Engine for season progression and career transitions."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from app.data.loaders import get_f1_calendar, get_f2_calendar
from app.models.save_game import (
    ChampionshipEntry,
    ChampionshipState,
    Contract,
    NewsItem,
    SaveGame,
)


def is_season_complete(save: SaveGame) -> bool:
    """Check if all rounds in the calendar have been completed."""
    return all(r.completed for r in save.calendar)


def get_championship_position(save: SaveGame, driver_id: str) -> int | None:
    """Get a driver's championship position."""
    sorted_standings = sorted(
        save.standings.driver_standings, key=lambda x: x.points, reverse=True
    )
    for i, entry in enumerate(sorted_standings):
        if entry.driver_id == driver_id:
            return i + 1
    return None


def get_player_season_summary(save: SaveGame) -> dict | None:
    """Generate a summary of the player's season performance."""
    if not save.player_driver_id:
        return None

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if not player:
        return None

    player_entry = next(
        (e for e in save.standings.driver_standings if e.driver_id == player.id), None
    )
    if not player_entry:
        return None

    position = get_championship_position(save, player.id)

    # Count races
    total_races = len(save.weekend_results) * 2  # Sprint + Feature per weekend
    points_finishes = sum(1 for w in save.weekend_results for r in [w.sprint, w.feature]
                         for c in r.classification if c.driver_id == player.id and c.points > 0)

    # Determine overall rating
    if position == 1:
        rating = "champion"
        headline = f"{player.name} is the F2 Champion!"
    elif position is not None and position <= 3:
        rating = "excellent"
        headline = f"{player.name} finishes P{position} in the championship"
    elif position is not None and position <= 6:
        rating = "good"
        headline = f"{player.name} secures top-six championship finish"
    elif position is not None and position <= 10:
        rating = "moderate"
        headline = f"{player.name} finishes season in P{position}"
    else:
        rating = "poor"
        headline = f"Tough season for {player.name}, finishes P{position}"

    return {
        "driver_id": player.id,
        "driver_name": player.name,
        "championship_position": position,
        "points": player_entry.points,
        "wins": player_entry.wins,
        "podiums": player_entry.podiums,
        "poles": player_entry.poles,
        "fastest_laps": player_entry.fastest_laps,
        "dnfs": player_entry.dnfs,
        "total_races": total_races,
        "points_finishes": points_finishes,
        "rating": rating,
        "headline": headline,
    }


def get_season_summary(save: SaveGame) -> dict:
    """Generate a complete season summary."""
    # Sort standings
    sorted_standings = sorted(
        save.standings.driver_standings, key=lambda x: x.points, reverse=True
    )

    # Champion info
    if sorted_standings:
        champion_id = sorted_standings[0].driver_id
        champion = next((d for d in save.drivers if d.id == champion_id), None)
        champion_name = champion.name if champion else "Unknown"
        champion_points = sorted_standings[0].points
    else:
        champion_name = "Unknown"
        champion_points = 0

    # Team champion
    team_standings_sorted = sorted(
        save.standings.team_standings.items(), key=lambda x: x[1], reverse=True
    )
    if team_standings_sorted:
        team_champion_id, team_champion_points = team_standings_sorted[0]
        team_champion = next((t for t in save.teams if t.id == team_champion_id), None)
        team_champion_name = team_champion.name if team_champion else "Unknown"
    else:
        team_champion_name = "Unknown"
        team_champion_points = 0

    return {
        "season": save.season,
        "champion": {
            "driver_id": sorted_standings[0].driver_id if sorted_standings else None,
            "name": champion_name,
            "points": champion_points,
        },
        "team_champion": {
            "team_id": team_standings_sorted[0][0] if team_standings_sorted else None,
            "name": team_champion_name,
            "points": team_champion_points,
        },
        "final_standings": [
            {
                "position": i + 1,
                "driver_id": entry.driver_id,
                "driver_name": next(
                    (d.name for d in save.drivers if d.id == entry.driver_id), "Unknown"
                ),
                "points": entry.points,
                "wins": entry.wins,
                "podiums": entry.podiums,
            }
            for i, entry in enumerate(sorted_standings)
        ],
        "player_summary": get_player_season_summary(save),
    }


def generate_season_end_news(save: SaveGame, summary: dict) -> list[NewsItem]:
    """Generate news items for season end."""
    news = []
    date = save.current_date

    # Champion announcement
    news.append(
        NewsItem(
            id=f"season_champion_{uuid.uuid4().hex[:8]}",
            date=date,
            category="race",
            headline=f"{summary['champion']['name']} crowned F2 Champion",
            body=f"After a thrilling season, {summary['champion']['name']} secures the "
            f"F2 title with {summary['champion']['points']} points.",
            linked_driver_ids=[summary['champion']['driver_id']] if summary['champion']['driver_id'] else [],
            importance=5,
        )
    )

    # Team champion
    news.append(
        NewsItem(
            id=f"season_team_champion_{uuid.uuid4().hex[:8]}",
            date=date,
            category="race",
            headline=f"{summary['team_champion']['name']} wins Teams' Championship",
            body=f"{summary['team_champion']['name']} claims the F2 Teams' Championship "
            f"with {summary['team_champion']['points']} points.",
            linked_driver_ids=[],
            importance=4,
        )
    )

    # Player-specific news
    player_summary = summary.get("player_summary")
    if player_summary:
        if player_summary["rating"] == "champion":
            news.append(
                NewsItem(
                    id=f"player_champion_{uuid.uuid4().hex[:8]}",
                    date=date,
                    category="race",
                    headline=player_summary["headline"],
                    body=f"An incredible season culminates in the championship. "
                    f"Final tally: {player_summary['wins']} wins, {player_summary['podiums']} podiums, "
                    f"{player_summary['points']} points.",
                    linked_driver_ids=[player_summary["driver_id"]],
                    importance=5,
                )
            )
        elif player_summary["rating"] in ("excellent", "good"):
            news.append(
                NewsItem(
                    id=f"player_season_{uuid.uuid4().hex[:8]}",
                    date=date,
                    category="academy",
                    headline=player_summary["headline"],
                    body=f"A strong season sees you finish with {player_summary['points']} points, "
                    f"{player_summary['wins']} wins, and {player_summary['podiums']} podiums.",
                    linked_driver_ids=[player_summary["driver_id"]],
                    importance=4,
                )
            )

    return news


def evaluate_contract_renewal(
    save: SaveGame,
    contract: Contract,
) -> dict:
    """
    Evaluate whether a contract should be renewed.

    Returns decision info with offer details or termination reason.
    """
    driver = next((d for d in save.drivers if d.id == contract.driver_id), None)
    if not driver:
        return {"decision": "terminate", "reason": "Driver not found"}

    is_player = contract.driver_id == save.player_driver_id
    position = get_championship_position(save, contract.driver_id)
    driver_entry = next(
        (e for e in save.standings.driver_standings if e.driver_id == contract.driver_id),
        None,
    )

    # Check contract expiry
    contract_end_season = contract.start_season + contract.length_years
    if save.season < contract_end_season:
        return {"decision": "continue", "reason": "Contract still active"}

    # Evaluate based on performance
    points = driver_entry.points if driver_entry else 0
    wins = driver_entry.wins if driver_entry else 0

    # Academy trust factor
    academy_trust = None
    if driver.academy_id:
        academy_state = next(
            (s for s in save.academy_states if s.academy_id == driver.academy_id), None
        )
        if academy_state:
            academy_trust = academy_state.trust

    # Decision logic
    if position is not None and position <= 3:
        decision = "renew"
        reason = "Outstanding performance"
        offer_years = 2
        offer_role = "f2_race_seat" if contract.role == "f2_race_seat" else contract.role
    elif position is not None and position <= 8:
        if academy_trust is not None and academy_trust >= 55:
            decision = "renew"
            reason = "Solid performance, academy support"
            offer_years = 1
            offer_role = contract.role
        else:
            decision = "renew"
            reason = "Acceptable performance"
            offer_years = 1
            offer_role = contract.role
    elif position is not None and position <= 12:
        if academy_trust is not None and academy_trust >= 70:
            decision = "renew"
            reason = "Academy backing"
            offer_years = 1
            offer_role = contract.role
        else:
            decision = "negotiate" if is_player else "terminate"
            reason = "Inconsistent results"
            offer_years = 1
            offer_role = contract.role
    else:
        if academy_trust is not None and academy_trust >= 85:
            decision = "renew"
            reason = "Strong academy support"
            offer_years = 1
            offer_role = contract.role
        else:
            decision = "terminate"
            reason = "Poor performance"
            offer_years = 0
            offer_role = None

    return {
        "decision": decision,
        "reason": reason,
        "offer_years": offer_years,
        "offer_role": offer_role,
        "championship_position": position,
        "points": points,
        "wins": wins,
        "academy_trust": academy_trust,
    }


def process_contract_renewals(save: SaveGame) -> tuple[SaveGame, list[NewsItem]]:
    """
    Process all contract renewals at season end.

    Returns updated save and news items.
    """
    news = []
    updated_contracts = []
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)

    for contract in save.contracts:
        if not contract.active:
            updated_contracts.append(contract)
            continue

        eval_result = evaluate_contract_renewal(save, contract)

        if eval_result["decision"] == "continue":
            updated_contracts.append(contract)
            continue

        driver = next((d for d in save.drivers if d.id == contract.driver_id), None)
        driver_name = driver.name if driver else "Unknown"
        team = next((t for t in save.teams if t.id == contract.team_id), None)
        team_name = team.name if team else "Unknown"

        if eval_result["decision"] == "renew":
            # Create new contract
            new_contract = Contract(
                id=f"contract_{uuid.uuid4().hex[:8]}",
                driver_id=contract.driver_id,
                team_id=contract.team_id,
                role=eval_result["offer_role"],
                start_season=save.season + 1,
                length_years=eval_result["offer_years"],
                active=True,
            )
            # Mark old as inactive
            updated_contracts.append(contract.model_copy(update={"active": False}))
            updated_contracts.append(new_contract)

            if contract.driver_id == save.player_driver_id:
                news.append(
                    NewsItem(
                        id=f"contract_renewed_{uuid.uuid4().hex[:8]}",
                        date=save.current_date,
                        category="contract",
                        headline=f"Contract Extension: You sign with {team_name}",
                        body=f"{eval_result['reason']}. {eval_result['offer_years']}-year deal secured.",
                        linked_driver_ids=[contract.driver_id],
                        importance=5,
                    )
                )
        elif eval_result["decision"] == "negotiate":
            # For player, mark as needing negotiation (will handle in offseason)
            updated_contracts.append(contract)
            news.append(
                NewsItem(
                    id=f"contract_negotiation_{uuid.uuid4().hex[:8]}",
                    date=save.current_date,
                    category="contract",
                    headline=f"Contract Talks: {team_name} wants to discuss your future",
                    body="Your contract is expiring. Negotiations will begin in the offseason.",
                    linked_driver_ids=[contract.driver_id],
                    importance=4,
                )
            )
        else:  # terminate
            updated_contracts.append(contract.model_copy(update={"active": False}))
            if contract.driver_id == save.player_driver_id:
                news.append(
                    NewsItem(
                        id=f"contract_ended_{uuid.uuid4().hex[:8]}",
                        date=save.current_date,
                        category="contract",
                        headline=f"{team_name} does not renew your contract",
                        body=f"{eval_result['reason']}. You'll need to find a new seat.",
                        linked_driver_ids=[contract.driver_id],
                        importance=5,
                    )
                )
            else:
                news.append(
                    NewsItem(
                        id=f"contract_ended_{uuid.uuid4().hex[:8]}",
                        date=save.current_date,
                        category="contract",
                        headline=f"{driver_name} leaves {team_name}",
                        body=f"Contract not renewed after finishing P{eval_result['championship_position']} in the championship.",
                        linked_driver_ids=[contract.driver_id],
                        importance=3,
                    )
                )

    updated_save = save.model_copy(update={"contracts": updated_contracts})
    return updated_save, news


def transition_to_offseason(save: SaveGame) -> tuple[SaveGame, list[NewsItem]]:
    """
    Transition the save to offseason after the final race.

    Generates season summary, processes contracts, and prepares for next season.
    """
    if not is_season_complete(save):
        return save, []

    news = []

    # Generate season summary
    summary = get_season_summary(save)
    season_news = generate_season_end_news(save, summary)
    news.extend(season_news)

    # Update save to offseason
    updated_save = save.model_copy(
        update={
            "phase": "offseason",
            "event_flags": {
                **save.event_flags,
                "season_complete": True,
                f"season_{save.season}_champion": summary["champion"]["driver_id"],
            },
        }
    )

    # Process contract renewals
    updated_save, contract_news = process_contract_renewals(updated_save)
    news.extend(contract_news)

    # Add news items
    updated_save = updated_save.model_copy(
        update={"news": [*updated_save.news, *news]}
    )

    return updated_save, news


def prepare_next_season(save: SaveGame) -> SaveGame:
    """
    Prepare the save for the next season.

    - Increments season number
    - Loads appropriate calendar based on player's series
    - Resets standings
    - Ages drivers
    - Updates to preseason phase
    """
    if save.phase != "offseason":
        return save

    # Increment season
    new_season = save.season + 1

    # Determine player's series for next season
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    player_series = player.series if player else "F2"

    # Load the appropriate calendar based on player's series
    if player_series == "F1":
        base_calendar = get_f1_calendar()
    else:
        base_calendar = get_f2_calendar()

    new_calendar = [
        r.model_copy(update={"completed": False}) for r in base_calendar
    ]

    # Get drivers for the relevant series
    series_driver_ids = {d.id for d in save.drivers if d.series == player_series}

    # Reset standings for the current series
    new_driver_standings = [
        ChampionshipEntry(
            driver_id=driver_id,
            points=0,
            wins=0,
            podiums=0,
            poles=0,
            fastest_laps=0,
            dnfs=0,
            penalties=0,
            average_qualifying=0,
            average_finish=0,
        )
        for driver_id in series_driver_ids
    ]

    # Get teams for the current series
    series_team_ids = {t.id for t in save.teams if t.series == player_series}

    new_standings = ChampionshipState(
        driver_standings=new_driver_standings,
        team_standings={team_id: 0 for team_id in series_team_ids},
    )

    # Age drivers
    new_drivers = [
        d.model_copy(update={"age": d.age + 1}) for d in save.drivers
    ]

    # Clear weekend results
    new_weekend_results = []

    # Update date to next season start
    new_date = new_calendar[0].start_date if new_calendar else save.current_date

    return save.model_copy(
        update={
            "season": new_season,
            "phase": "preseason",
            "current_date": new_date,
            "calendar": new_calendar,
            "standings": new_standings,
            "drivers": new_drivers,
            "weekend_results": new_weekend_results,
            "active_race": None,
            "event_flags": {
                **save.event_flags,
                "season_complete": False,
            },
        }
    )


def advance_to_next_season(save: SaveGame) -> tuple[SaveGame, list[NewsItem]]:
    """
    Full transition from offseason to next season.

    Combines prepare_next_season with any additional setup needed.
    """
    if save.phase != "offseason":
        return save, []

    news = []

    # Prepare next season
    updated_save = prepare_next_season(save)

    # Generate preseason news
    player = next((d for d in updated_save.drivers if d.id == updated_save.player_driver_id), None)
    if player:
        player_contract = next(
            (c for c in updated_save.contracts if c.driver_id == player.id and c.active),
            None,
        )
        if player_contract:
            team = next((t for t in updated_save.teams if t.id == player_contract.team_id), None)
            team_name = team.name if team else "Unknown"
            series_name = "F1" if player.series == "F1" else "F2"

            if player.series == "F1":
                headline = f"Your F1 Debut Season Begins"
                body = f"The pinnacle of motorsport awaits. You'll be racing for {team_name} in Formula 1."
            else:
                headline = f"Season {updated_save.season} begins"
                body = f"A new {series_name} season awaits. You'll be racing for {team_name}."

            news.append(
                NewsItem(
                    id=f"preseason_start_{uuid.uuid4().hex[:8]}",
                    date=updated_save.current_date,
                    category="system",
                    headline=headline,
                    body=body,
                    linked_driver_ids=[player.id],
                    importance=5 if player.series == "F1" else 4,
                )
            )

    # Add news
    updated_save = updated_save.model_copy(
        update={"news": [*updated_save.news, *news]}
    )

    return updated_save, news
