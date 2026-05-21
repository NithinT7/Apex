from fastapi import APIRouter, HTTPException, status

from app.engine.academy_engine import apply_race_trust_change, check_season_milestone
from app.engine.rivalry_engine import process_race_rivalries
from app.engine.season_engine import is_season_complete, transition_to_offseason
from app.engine.standings_engine import apply_race_points
from app.engine.weekend_engine import simulate_weekend
from app.models.race import WeekendResult
from app.models.save_game import NewsItem, SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/weekend", tags=["weekend"])
manager = SaveManager()


@router.get("/{round_id}", response_model=WeekendResult)
def get_weekend_result(save_id: str, round_id: str) -> WeekendResult:
    save = _get_save(save_id)
    result = next((weekend for weekend in save.weekend_results if weekend.round_id == round_id), None)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekend result not found")

    return result


@router.get("/next/round")
def get_next_round(save_id: str):
    save = _get_save(save_id)
    next_round = _next_round(save)
    if next_round is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season complete")

    return next_round


@router.post("/next/simulate", response_model=SaveGame)
def simulate_next_round(save_id: str) -> SaveGame:
    save = _get_save(save_id)
    next_round = _next_round(save)
    if next_round is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Season complete")

    return _simulate_and_save(save, next_round.id)


@router.post("/{round_id}/simulate", response_model=SaveGame)
def simulate_round(save_id: str, round_id: str) -> SaveGame:
    save = _get_save(save_id)
    next_round = _next_round(save)
    if next_round is not None and round_id != next_round.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Next playable round is {next_round.id}",
        )
    return _simulate_and_save(save, round_id)


def _simulate_and_save(save: SaveGame, round_id: str) -> SaveGame:
    if any(weekend.round_id == round_id for weekend in save.weekend_results):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Weekend already completed")

    if not any(calendar_round.id == round_id for calendar_round in save.calendar):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar round not found")

    weekend = simulate_weekend(save, round_id)
    standings = apply_race_points(save.standings, weekend.sprint)
    standings = apply_race_points(standings, weekend.feature)
    standings = standings.model_copy(update={"team_standings": _team_standings(save, standings)})
    completed_round = next(calendar_round for calendar_round in save.calendar if calendar_round.id == round_id)

    # Apply academy trust changes
    news_items: list[NewsItem] = []
    updated_save = save.model_copy(update={"standings": standings})

    # Sprint race trust change (weight less than feature)
    updated_save, sprint_news = apply_race_trust_change(updated_save, weekend.sprint, is_feature=False)
    if sprint_news:
        news_items.append(sprint_news)

    # Feature race trust change
    updated_save, feature_news = apply_race_trust_change(updated_save, weekend.feature, is_feature=True)
    if feature_news:
        news_items.append(feature_news)

    # Check for season milestones (every ~4 rounds)
    completed_rounds = sum(1 for r in save.calendar if r.completed) + 1  # +1 for this round
    updated_save, milestone_news = check_season_milestone(updated_save, completed_rounds)
    news_items.extend(milestone_news)

    # Process rivalries for feature race (main race)
    updated_save, rivalry_news = process_race_rivalries(updated_save, weekend.feature)
    news_items.extend(rivalry_news)

    # Update calendar with this round marked as complete
    updated_calendar = [
        calendar_round.model_copy(update={"completed": True})
        if calendar_round.id == round_id
        else calendar_round
        for calendar_round in save.calendar
    ]

    updated = updated_save.model_copy(
        update={
            "phase": "between_races",
            "current_date": completed_round.end_date,
            "calendar": updated_calendar,
            "weekend_results": [*save.weekend_results, weekend],
            "news": [
                *updated_save.news,
                NewsItem(
                    id=f"{round_id}_feature_headline",
                    date=completed_round.end_date,
                    category="race",
                    headline=weekend.headline,
                    body="The F2 weekend is complete, with sprint and feature race points now applied.",
                    linked_driver_ids=[save.player_driver_id] if save.player_driver_id else [],
                    importance=4,
                ),
                *news_items,
            ],
        }
    )

    # Check if season is complete and transition to offseason
    if is_season_complete(updated):
        updated, season_news = transition_to_offseason(updated)

    return manager.save(updated)


def _get_save(save_id: str) -> SaveGame:
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    return save


def _team_standings(save: SaveGame, standings) -> dict[str, int]:
    driver_points = {entry.driver_id: entry.points for entry in standings.driver_standings}
    team_points = {team.id: 0 for team in save.teams if team.series == "F2"}
    for driver in save.drivers:
        if driver.series == "F2" and driver.team_id in team_points:
            team_points[driver.team_id] += driver_points.get(driver.id, 0)

    return dict(sorted(team_points.items(), key=lambda item: item[1], reverse=True))


def _next_round(save: SaveGame):
    return next((calendar_round for calendar_round in save.calendar if not calendar_round.completed), None)
