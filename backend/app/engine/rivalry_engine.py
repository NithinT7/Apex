"""Engine for driver rivalry management."""

from __future__ import annotations

import random
import uuid
from datetime import datetime
from typing import Literal

from app.models.race import RaceClassification, RaceResult
from app.models.rivalry import (
    Rivalry,
    RivalryEvent,
    RivalryIntensity,
    RivalryStatus,
    RivalryType,
)
from app.models.save_game import NewsItem, SaveGame


# Intensity thresholds
INTENSITY_MILD = 25
INTENSITY_MODERATE = 50
INTENSITY_INTENSE = 75
INTENSITY_BITTER = 90


def get_intensity_level(intensity: int) -> RivalryIntensity:
    """Get the intensity level from a numeric value."""
    if intensity >= INTENSITY_BITTER:
        return "bitter"
    if intensity >= INTENSITY_INTENSE:
        return "intense"
    if intensity >= INTENSITY_MODERATE:
        return "moderate"
    return "mild"


def initialize_rivalries(save: SaveGame) -> SaveGame:
    """
    Initialize rivalries for a new career.

    Creates a teammate rivalry automatically.
    """
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        return save

    rivalries = list(save.rivalries) if save.rivalries else []

    # Find teammate
    teammate = next(
        (
            d
            for d in save.drivers
            if d.team_id == player.team_id
            and d.id != player.id
            and d.series == player.series
        ),
        None,
    )

    if teammate:
        # Create teammate rivalry (starts friendly)
        teammate_rivalry = Rivalry(
            id=f"rivalry_{uuid.uuid4().hex[:8]}",
            opponent_id=teammate.id,
            rivalry_type="teammate",
            intensity=20,  # Starts mild
            respect=60,  # Some initial respect
            started_date=save.current_date,
            recent_events=[],
            is_active=True,
        )
        rivalries.append(teammate_rivalry)

    return save.model_copy(update={"rivalries": rivalries})


def process_race_rivalries(
    save: SaveGame,
    race_result: RaceResult,
    battles: list[tuple[str, str]] | None = None,
) -> tuple[SaveGame, list[NewsItem]]:
    """
    Process race results for rivalry updates.

    Returns (updated_save, news_items)
    """
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        return save, []

    news_items: list[NewsItem] = []
    rivalries = list(save.rivalries) if save.rivalries else []

    # Find player's result
    player_result = next(
        (r for r in race_result.classification if r.driver_id == player.id), None
    )
    if player_result is None:
        return save, news_items

    # Process existing rivalries
    updated_rivalries = []
    for rivalry in rivalries:
        updated_rivalry, event, news = _process_rivalry_race(
            save, rivalry, race_result, player_result, battles
        )
        updated_rivalries.append(updated_rivalry)
        if news:
            news_items.append(news)

    # Check for new rivalries from close battles
    new_rivalry, new_news = _check_for_new_rivalry(
        save, race_result, player_result, updated_rivalries, battles
    )
    if new_rivalry:
        updated_rivalries.append(new_rivalry)
        if new_news:
            news_items.append(new_news)

    return save.model_copy(update={"rivalries": updated_rivalries}), news_items


def _process_rivalry_race(
    save: SaveGame,
    rivalry: Rivalry,
    race_result: RaceResult,
    player_result: RaceClassification,
    battles: list[tuple[str, str]] | None,
) -> tuple[Rivalry, RivalryEvent | None, NewsItem | None]:
    """Process a single rivalry for race results."""
    opponent_result = next(
        (r for r in race_result.classification if r.driver_id == rivalry.opponent_id),
        None,
    )
    if opponent_result is None:
        return rivalry, None, None

    intensity_change = 0
    event_description = ""

    # Position battle
    position_diff = abs(player_result.position - opponent_result.position)
    if position_diff <= 2:
        # Close finish
        if player_result.position < opponent_result.position:
            intensity_change += 3
            event_description = "beat rival in close battle"
        else:
            intensity_change += 5  # Losing hurts more
            event_description = "lost to rival in close battle"

    # Direct overtake (from battles if provided)
    if battles:
        direct_battles = [
            b
            for b in battles
            if (b[0] == save.player_driver_id and b[1] == rivalry.opponent_id)
            or (b[1] == save.player_driver_id and b[0] == rivalry.opponent_id)
        ]
        if direct_battles:
            intensity_change += 2 * len(direct_battles)
            if not event_description:
                event_description = "multiple on-track battles"

    # Teammate specific - if one DNF'd and other scored points
    if rivalry.rivalry_type == "teammate":
        if player_result.status == "dnf" and opponent_result.points > 0:
            intensity_change += 4
            event_description = "rival scored while you DNF'd"
        elif opponent_result.status == "dnf" and player_result.points > 0:
            intensity_change += 2
            event_description = "scored points while rival DNF'd"

    if intensity_change == 0:
        return rivalry, None, None

    # Update rivalry
    new_intensity = max(0, min(100, rivalry.intensity + intensity_change))

    event = RivalryEvent(
        id=f"event_{uuid.uuid4().hex[:8]}",
        date=save.current_date,
        description=event_description or "race encounter",
        intensity_change=intensity_change,
        category="on_track",
    )

    # Keep only recent events (last 5)
    recent_events = [event, *rivalry.recent_events[:4]]

    updated_rivalry = rivalry.model_copy(
        update={"intensity": new_intensity, "recent_events": recent_events}
    )

    # Generate news for significant changes
    news = None
    if intensity_change >= 5 or new_intensity >= INTENSITY_INTENSE:
        opponent = next(
            (d for d in save.drivers if d.id == rivalry.opponent_id), None
        )
        if opponent:
            news = _generate_rivalry_news(save, updated_rivalry, opponent.name, event)

    return updated_rivalry, event, news


def _check_for_new_rivalry(
    save: SaveGame,
    race_result: RaceResult,
    player_result: RaceClassification,
    existing_rivalries: list[Rivalry],
    battles: list[tuple[str, str]] | None,
) -> tuple[Rivalry | None, NewsItem | None]:
    """Check if a new rivalry should form from race results."""
    existing_opponent_ids = {r.opponent_id for r in existing_rivalries}

    # Find drivers we battled closely with
    for result in race_result.classification:
        if result.driver_id == save.player_driver_id:
            continue
        if result.driver_id in existing_opponent_ids:
            continue

        # Check for close finish
        position_diff = abs(player_result.position - result.position)
        if position_diff > 2:
            continue

        # Random chance to form rivalry based on closeness
        # Closer = higher chance
        rivalry_chance = 0.1 + (0.1 * (3 - position_diff))

        # Higher chance if we lost
        if player_result.position > result.position:
            rivalry_chance += 0.1

        if random.random() < rivalry_chance:
            opponent = next(
                (d for d in save.drivers if d.id == result.driver_id), None
            )
            if opponent is None:
                continue

            # Determine rivalry type
            player = next(
                (d for d in save.drivers if d.id == save.player_driver_id), None
            )
            if player is None:
                continue

            if opponent.team_id == player.team_id:
                rivalry_type: RivalryType = "teammate"
            elif opponent.academy_id == player.academy_id and player.academy_id:
                rivalry_type = "promotional"
            else:
                rivalry_type = "championship"

            new_rivalry = Rivalry(
                id=f"rivalry_{uuid.uuid4().hex[:8]}",
                opponent_id=opponent.id,
                rivalry_type=rivalry_type,
                intensity=30,  # Starts moderate
                respect=50,
                started_date=save.current_date,
                recent_events=[
                    RivalryEvent(
                        id=f"event_{uuid.uuid4().hex[:8]}",
                        date=save.current_date,
                        description="Close battle sparked rivalry",
                        intensity_change=30,
                        category="on_track",
                    )
                ],
                is_active=True,
            )

            news = NewsItem(
                id=f"rivalry_start_{uuid.uuid4().hex[:8]}",
                date=save.current_date,
                category="rivalry",
                headline=f"New rivalry brewing between you and {opponent.name}",
                body=f"A close battle in the feature race has sparked competition between the two drivers.",
                linked_driver_ids=[save.player_driver_id or "", opponent.id],
                importance=3,
            )

            return new_rivalry, news

    return None, None


def _generate_rivalry_news(
    save: SaveGame,
    rivalry: Rivalry,
    opponent_name: str,
    event: RivalryEvent,
) -> NewsItem:
    """Generate a news item for a rivalry event."""
    intensity_level = get_intensity_level(rivalry.intensity)

    if intensity_level == "bitter":
        headline = f"Tensions boiling over with {opponent_name}"
        body = f"The rivalry has reached a critical point after {event.description}."
        importance = 4
    elif intensity_level == "intense":
        headline = f"Fierce competition with {opponent_name} continues"
        body = f"The battle intensifies: {event.description}."
        importance = 3
    elif intensity_level == "moderate":
        headline = f"Growing rivalry with {opponent_name}"
        body = f"Competition heating up after {event.description}."
        importance = 2
    else:
        headline = f"Friendly competition with {opponent_name}"
        body = f"Some sparks flew: {event.description}."
        importance = 1

    return NewsItem(
        id=f"rivalry_event_{uuid.uuid4().hex[:8]}",
        date=save.current_date,
        category="rivalry",
        headline=headline,
        body=body,
        linked_driver_ids=[save.player_driver_id or "", rivalry.opponent_id],
        importance=importance,
    )


def get_rivalry_status(save: SaveGame) -> RivalryStatus:
    """Get the current rivalry status for display."""
    rivalries = save.rivalries or []
    active_rivalries = [r for r in rivalries if r.is_active]

    # Find most intense
    most_intense = None
    if active_rivalries:
        most_intense = max(active_rivalries, key=lambda r: r.intensity)

    # Find teammate rivalry
    teammate_rivalry = next(
        (r for r in active_rivalries if r.rivalry_type == "teammate"), None
    )

    return RivalryStatus(
        rivalries=active_rivalries,
        most_intense=most_intense,
        teammate_rivalry=teammate_rivalry,
    )


def get_rivalry_with(save: SaveGame, opponent_id: str) -> Rivalry | None:
    """Get the rivalry with a specific driver, if any."""
    if not save.rivalries:
        return None
    return next((r for r in save.rivalries if r.opponent_id == opponent_id), None)


def apply_rivalry_to_decision(
    save: SaveGame,
    opponent_id: str,
    decision_type: Literal["attack", "defend", "yield"],
) -> tuple[int, str]:
    """
    Apply rivalry effects to a race decision.

    Returns (intensity_modifier, narrative_addition)
    """
    rivalry = get_rivalry_with(save, opponent_id)
    if rivalry is None:
        return 0, ""

    intensity_level = get_intensity_level(rivalry.intensity)

    if decision_type == "attack":
        if intensity_level == "bitter":
            return 15, "Your bitter rivalry adds aggression to the move"
        if intensity_level == "intense":
            return 10, "The rivalry fuels your determination"
        if intensity_level == "moderate":
            return 5, "Competition with your rival sharpens focus"
        return 0, ""

    if decision_type == "defend":
        if intensity_level in ("bitter", "intense"):
            return 10, "Pride won't let your rival pass easily"
        return 0, ""

    if decision_type == "yield":
        if intensity_level in ("bitter", "intense"):
            return -5, "Yielding to a rival stings"
        return 0, ""

    return 0, ""


def decay_rivalries(save: SaveGame, days_passed: int = 7) -> SaveGame:
    """
    Decay rivalry intensity over time when no events occur.

    Called during between-race periods.
    """
    if not save.rivalries:
        return save

    decay_amount = max(1, days_passed // 7)  # 1 point per week

    updated_rivalries = []
    for rivalry in save.rivalries:
        # Only decay if no recent events
        if rivalry.recent_events and len(rivalry.recent_events) > 0:
            # Check if most recent event was recent
            most_recent = rivalry.recent_events[0]
            days_since_event = (save.current_date - most_recent.date).days
            if days_since_event < 14:
                # Recent event, don't decay
                updated_rivalries.append(rivalry)
                continue

        # Apply decay
        new_intensity = max(10, rivalry.intensity - decay_amount)
        updated_rivalry = rivalry.model_copy(update={"intensity": new_intensity})

        # Deactivate if intensity drops too low
        if new_intensity <= 10 and rivalry.rivalry_type != "teammate":
            updated_rivalry = updated_rivalry.model_copy(update={"is_active": False})

        updated_rivalries.append(updated_rivalry)

    return save.model_copy(update={"rivalries": updated_rivalries})
