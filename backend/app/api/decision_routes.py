"""API routes for interactive race decisions."""

from fastapi import APIRouter, HTTPException, status

from app.engine.academy_engine import (
    apply_race_trust_change,
    check_season_milestone,
)
from app.engine.rivalry_engine import process_race_rivalries
from app.engine.decision_engine import (
    auto_complete_race,
    clear_internal_state,
    simulate_to_next_decision,
    start_interactive_race,
    submit_decision,
    _build_race_result,
    _load_internal_state,
)
from app.engine.standings_engine import apply_race_points
from app.engine.weekend_engine import simulate_weekend
from app.models.race import (
    ActiveRaceState,
    DecisionResponse,
    PracticeResult,
    QualifyingResult,
    RaceResult,
    WeekendResult,
)
from app.models.save_game import NewsItem, SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/race", tags=["race"])
manager = SaveManager()


# Store practice/qualifying results for races in progress
_WEEKEND_PREP: dict[str, tuple[PracticeResult, QualifyingResult]] = {}


@router.post("/{round_id}/prepare")
def prepare_weekend(save_id: str, round_id: str) -> dict:
    """
    Simulate practice and qualifying for a round, preparing for interactive races.

    Returns practice and qualifying results.
    """
    save = _get_save(save_id)

    # Check if this round is valid
    next_round = _next_round(save)
    if next_round is not None and round_id != next_round.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Next playable round is {next_round.id}",
        )

    if any(weekend.round_id == round_id for weekend in save.weekend_results):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Weekend already completed")

    # Simulate the full weekend to get practice/qualifying (we'll reuse them)
    weekend = simulate_weekend(save, round_id)

    # Store practice and qualifying for later use
    key = f"{save_id}:{round_id}"
    _WEEKEND_PREP[key] = (weekend.practice, weekend.qualifying)

    return {
        "round_id": round_id,
        "practice": weekend.practice.model_dump(),
        "qualifying": weekend.qualifying.model_dump(),
        "sprint_grid": list(reversed([e.driver_id for e in weekend.qualifying.classification[:10]]))
        + [e.driver_id for e in weekend.qualifying.classification[10:]],
        "feature_grid": [e.driver_id for e in weekend.qualifying.classification],
    }


@router.post("/{round_id}/{race_type}/start", response_model=ActiveRaceState)
def start_race(save_id: str, round_id: str, race_type: str) -> ActiveRaceState:
    """
    Start an interactive race.

    race_type must be 'sprint' or 'feature'.
    Returns the initial ActiveRaceState.
    """
    if race_type not in ("sprint", "feature"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="race_type must be 'sprint' or 'feature'")

    save = _get_save(save_id)

    # Check if weekend is prepared
    key = f"{save_id}:{round_id}"
    if key not in _WEEKEND_PREP:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Weekend not prepared. Call /prepare first.",
        )

    practice, qualifying = _WEEKEND_PREP[key]

    # Start the interactive race
    active_state = start_interactive_race(save, round_id, race_type, practice, qualifying)

    # Store active race in save game
    updated = save.model_copy(update={"active_race": active_state})
    manager.save(updated)

    return active_state


@router.post("/{round_id}/{race_type}/simulate", response_model=ActiveRaceState)
def simulate_to_decision(save_id: str, round_id: str, race_type: str) -> ActiveRaceState:
    """
    Simulate laps until the next decision prompt or race end.

    Returns updated ActiveRaceState with any pending decision.
    """
    if race_type not in ("sprint", "feature"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="race_type must be 'sprint' or 'feature'")

    save = _get_save(save_id)

    try:
        active_state = simulate_to_next_decision(save, round_id, race_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Update save with current race state
    updated = save.model_copy(update={"active_race": active_state})
    manager.save(updated)

    return active_state


@router.post("/{round_id}/{race_type}/decide", response_model=ActiveRaceState)
def make_decision(save_id: str, round_id: str, race_type: str, response: DecisionResponse) -> ActiveRaceState:
    """
    Submit the player's decision and continue simulation.

    Returns updated ActiveRaceState.
    """
    if race_type not in ("sprint", "feature"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="race_type must be 'sprint' or 'feature'")

    save = _get_save(save_id)

    try:
        active_state = submit_decision(save, round_id, race_type, response)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Update save
    updated = save.model_copy(update={"active_race": active_state})
    manager.save(updated)

    return active_state


@router.post("/{round_id}/{race_type}/auto-complete", response_model=RaceResult)
def complete_race_auto(save_id: str, round_id: str, race_type: str) -> RaceResult:
    """
    Auto-complete the race, skipping remaining decisions.

    Returns the final RaceResult.
    """
    if race_type not in ("sprint", "feature"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="race_type must be 'sprint' or 'feature'")

    save = _get_save(save_id)

    try:
        result = auto_complete_race(save, round_id, race_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Clear internal state
    clear_internal_state(save_id, round_id, race_type)

    # Clear active race from save
    updated = save.model_copy(update={"active_race": None})
    manager.save(updated)

    return result


@router.post("/{round_id}/{race_type}/complete", response_model=RaceResult)
def complete_race(save_id: str, round_id: str, race_type: str) -> RaceResult:
    """
    Complete an interactive race that has finished all laps.

    Returns the final RaceResult.
    """
    if race_type not in ("sprint", "feature"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="race_type must be 'sprint' or 'feature'")

    save = _get_save(save_id)

    try:
        internal_state = _load_internal_state(save, round_id, race_type)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    if not internal_state.is_complete:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Race is not complete")

    result = _build_race_result(internal_state)

    # Clear internal state
    clear_internal_state(save_id, round_id, race_type)

    # Clear active race from save
    updated = save.model_copy(update={"active_race": None})
    manager.save(updated)

    return result


@router.post("/{round_id}/finalize", response_model=SaveGame)
def finalize_weekend(save_id: str, round_id: str, sprint: RaceResult, feature: RaceResult) -> SaveGame:
    """
    Finalize a weekend after both races are complete.

    Applies points and updates standings.
    """
    save = _get_save(save_id)

    # Get practice/qualifying
    key = f"{save_id}:{round_id}"
    if key not in _WEEKEND_PREP:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Weekend prep not found")

    practice, qualifying = _WEEKEND_PREP[key]

    # Build weekend result
    calendar_round = next(r for r in save.calendar if r.id == round_id)
    weekend = WeekendResult(
        save_id=save_id,
        round_id=round_id,
        track_id=calendar_round.track_id,
        completed=True,
        practice=practice,
        qualifying=qualifying,
        sprint=sprint,
        feature=feature,
        headline=_headline(save, feature),
    )

    # Apply points
    standings = apply_race_points(save.standings, sprint)
    standings = apply_race_points(standings, feature)
    standings = standings.model_copy(update={"team_standings": _team_standings(save, standings)})

    # Apply academy trust changes for both races
    news_items: list[NewsItem] = []
    updated_save = save.model_copy(update={"standings": standings})

    # Sprint race trust change (weight less than feature)
    updated_save, sprint_news = apply_race_trust_change(updated_save, sprint, is_feature=False)
    if sprint_news:
        news_items.append(sprint_news)

    # Feature race trust change
    updated_save, feature_news = apply_race_trust_change(updated_save, feature, is_feature=True)
    if feature_news:
        news_items.append(feature_news)

    # Check for season milestones (every ~4 rounds)
    completed_rounds = sum(1 for r in save.calendar if r.completed) + 1  # +1 for this round
    updated_save, milestone_news = check_season_milestone(updated_save, completed_rounds)
    news_items.extend(milestone_news)

    # Process rivalries for feature race (main race)
    updated_save, rivalry_news = process_race_rivalries(updated_save, feature)
    news_items.extend(rivalry_news)

    # Update save (use updated_save which has academy_states and rivalry changes)
    updated = updated_save.model_copy(
        update={
            "phase": "between_races",
            "current_date": calendar_round.end_date,
            "calendar": [
                r.model_copy(update={"completed": True}) if r.id == round_id else r for r in save.calendar
            ],
            "weekend_results": [*save.weekend_results, weekend],
            "active_race": None,
            "news": [
                *updated_save.news,
                NewsItem(
                    id=f"{round_id}_feature_headline",
                    date=calendar_round.end_date,
                    category="race",
                    headline=weekend.headline,
                    body="The F2 weekend is complete.",
                    linked_driver_ids=[save.player_driver_id] if save.player_driver_id else [],
                    importance=4,
                ),
                *news_items,
            ],
        }
    )

    # Clean up prep data
    del _WEEKEND_PREP[key]

    return manager.save(updated)


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save


def _next_round(save: SaveGame):
    """Get the next incomplete round."""
    return next((r for r in save.calendar if not r.completed), None)


def _headline(save: SaveGame, feature: RaceResult) -> str:
    """Generate a headline for the weekend."""
    winner = next(d for d in save.drivers if d.id == feature.classification[0].driver_id)
    player = next((r for r in feature.classification if r.driver_id == save.player_driver_id), None)

    if player and player.position <= 3:
        return f"{winner.name} wins as you secure a podium finish"
    if player and player.points > 0:
        return f"{winner.name} wins while you score points"
    if player:
        return f"{winner.name} controls the feature race, you finish P{player.position}"
    return f"{winner.name} wins the feature race"


def _team_standings(save: SaveGame, standings) -> dict[str, int]:
    """Calculate team standings from driver points."""
    driver_points = {entry.driver_id: entry.points for entry in standings.driver_standings}
    team_points = {team.id: 0 for team in save.teams if team.series == "F2"}
    for driver in save.drivers:
        if driver.series == "F2" and driver.team_id in team_points:
            team_points[driver.team_id] += driver_points.get(driver.id, 0)
    return dict(sorted(team_points.items(), key=lambda item: item[1], reverse=True))
