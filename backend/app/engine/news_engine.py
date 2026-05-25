"""Additional narrative news generation for career saves."""

from __future__ import annotations

import uuid

from app.models.driver import Driver
from app.models.race import WeekendResult
from app.models.save_game import NewsItem, SaveGame


def dedupe_news_items(news: list[NewsItem]) -> list[NewsItem]:
    """Keep the latest version of each news id while preserving feed order."""
    seen: set[str] = set()
    deduped_reversed: list[NewsItem] = []
    for item in reversed(news):
        if item.id in seen:
            continue
        seen.add(item.id)
        deduped_reversed.append(item)
    return list(reversed(deduped_reversed))


def generate_weekend_narratives(
    save: SaveGame,
    weekend: WeekendResult,
    series: str,
    completed_rounds: int,
    date: str,
) -> list[NewsItem]:
    """Create reactive paddock stories after a completed weekend."""
    player = next((driver for driver in save.drivers if driver.id == save.player_driver_id), None)
    if player is None:
        return []

    news: list[NewsItem] = []
    player_finish = _feature_position(weekend, player.id)
    player_position = _championship_position(save, player.id)
    leader = _championship_leader(save)
    winner = _feature_winner(save, weekend)

    if player_finish is not None:
        news.append(_player_form_story(save, player, player_finish, player_position, date))

    if completed_rounds >= 3 and completed_rounds % 3 == 0 and leader is not None:
        news.append(_title_picture_story(save, leader, player, player_position, completed_rounds, date))

    if winner is not None and leader is not None and winner.id != leader.id and completed_rounds >= 2:
        news.append(
            NewsItem(
                id=f"narrative_{uuid.uuid4().hex[:8]}",
                date=date,
                category="media",
                headline=f"{winner.name} changes the paddock mood",
                body=(
                    f"{winner.name}'s victory has given the {series} title race a fresh edge, "
                    f"with {leader.name} still carrying the points lead."
                ),
                linked_driver_ids=[winner.id, leader.id],
                importance=3,
            )
        )

    return news[:3]


def _player_form_story(
    save: SaveGame,
    player: Driver,
    player_finish: int,
    player_position: int | None,
    date: str,
) -> NewsItem:
    identity_clause = _identity_clause(player)
    if player_finish <= 1:
        headline = f"Paddock reacts to {player.name}'s breakthrough win"
        body = (
            f"The win has shifted expectations around {player.name}, with rival teams now treating "
            f"the campaign as more than a quiet development year.{identity_clause}"
        )
        importance = 5
    elif player_finish <= 3:
        headline = f"{player.name}'s podium fuels fresh paddock interest"
        body = (
            f"Another front-running result has strengthened {player.name}'s case in the paddock, "
            f"especially with decision-makers watching race execution and marketability.{identity_clause}"
        )
        importance = 4
    elif player_finish <= 8:
        headline = f"{player.name} keeps momentum with points finish"
        body = (
            f"A controlled points finish keeps the season narrative moving in the right direction. "
            f"{_position_phrase(player_position)}{identity_clause}"
        )
        importance = 3
    else:
        headline = f"Questions grow after difficult weekend for {player.name}"
        body = (
            "The latest result has brought renewed scrutiny from the paddock, with form, confidence, "
            "and the next response now central to the story."
        )
        importance = 3 if player_finish <= 14 else 4

    return NewsItem(
        id=f"narrative_{uuid.uuid4().hex[:8]}",
        date=date,
        category="media",
        headline=headline,
        body=body,
        linked_driver_ids=[player.id],
        importance=importance,
    )


def _identity_clause(player: Driver) -> str:
    trait = player.identity.primary_trait
    if trait is None or player.identity.trait_scores.get(trait, 0) < 20:
        return ""
    label = trait.replace("_", " ")
    return f" The paddock is also starting to frame them as a {label}."


def _title_picture_story(
    save: SaveGame,
    leader: Driver,
    player: Driver,
    player_position: int | None,
    completed_rounds: int,
    date: str,
) -> NewsItem:
    if leader.id == player.id:
        headline = f"{player.name} becomes the reference point"
        body = (
            f"After {completed_rounds} rounds, the championship conversation is starting with "
            f"{player.name}. Rivals now need to respond before the gap becomes a season-defining one."
        )
        linked_ids = [player.id]
        importance = 4
    else:
        headline = f"{leader.name} sets the pace in the title picture"
        body = (
            f"{leader.name} leads the table after {completed_rounds} rounds, while "
            f"{player.name} {_title_position_phrase(player_position)}"
        )
        linked_ids = [leader.id, player.id]
        importance = 3

    return NewsItem(
        id=f"narrative_{uuid.uuid4().hex[:8]}",
        date=date,
        category="media",
        headline=headline,
        body=body,
        linked_driver_ids=linked_ids,
        importance=importance,
    )


def _feature_position(weekend: WeekendResult, driver_id: str) -> int | None:
    result = next((row for row in weekend.feature.classification if row.driver_id == driver_id), None)
    return result.position if result else None


def _feature_winner(save: SaveGame, weekend: WeekendResult) -> Driver | None:
    if not weekend.feature.classification:
        return None
    winner_id = weekend.feature.classification[0].driver_id
    return next((driver for driver in save.drivers if driver.id == winner_id), None)


def _championship_position(save: SaveGame, driver_id: str) -> int | None:
    ordered = sorted(save.standings.driver_standings, key=lambda entry: entry.points, reverse=True)
    for index, entry in enumerate(ordered, start=1):
        if entry.driver_id == driver_id:
            return index
    return None


def _championship_leader(save: SaveGame) -> Driver | None:
    ordered = sorted(save.standings.driver_standings, key=lambda entry: entry.points, reverse=True)
    if not ordered:
        return None
    return next((driver for driver in save.drivers if driver.id == ordered[0].driver_id), None)


def _position_phrase(position: int | None) -> str:
    if position is None:
        return "The championship picture is still settling."
    if position <= 3:
        return f"The championship picture has them in P{position}."
    if position <= 8:
        return f"They remain within striking range in P{position}."
    return f"They are still chasing momentum from P{position}."


def _title_position_phrase(position: int | None) -> str:
    if position is None:
        return "waits for the championship picture to settle."
    if position <= 3:
        return f"stays central to the fight in P{position}."
    if position <= 8:
        return f"remains within striking range in P{position}."
    return f"is still chasing momentum from P{position}."
