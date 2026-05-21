from fastapi import APIRouter, HTTPException, status

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


@router.post("/{round_id}/simulate", response_model=SaveGame)
def simulate_round(save_id: str, round_id: str) -> SaveGame:
    save = _get_save(save_id)
    if any(weekend.round_id == round_id for weekend in save.weekend_results):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Weekend already completed")

    if not any(calendar_round.id == round_id for calendar_round in save.calendar):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Calendar round not found")

    weekend = simulate_weekend(save, round_id)
    standings = apply_race_points(save.standings, weekend.sprint)
    standings = apply_race_points(standings, weekend.feature)
    standings = standings.model_copy(update={"team_standings": _team_standings(save, standings)})
    completed_round = next(calendar_round for calendar_round in save.calendar if calendar_round.id == round_id)

    updated = save.model_copy(
        update={
            "phase": "between_races",
            "current_date": completed_round.end_date,
            "calendar": [
                calendar_round.model_copy(update={"completed": True})
                if calendar_round.id == round_id
                else calendar_round
                for calendar_round in save.calendar
            ],
            "standings": standings,
            "weekend_results": [*save.weekend_results, weekend],
            "news": [
                *save.news,
                NewsItem(
                    id=f"{round_id}_feature_headline",
                    date=completed_round.end_date,
                    category="race",
                    headline=weekend.headline,
                    body="The F2 weekend is complete, with sprint and feature race points now applied.",
                    linked_driver_ids=[save.player_driver_id] if save.player_driver_id else [],
                    importance=4,
                ),
            ],
        }
    )
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
