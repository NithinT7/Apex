from fastapi import APIRouter, HTTPException, status

from app.data.loaders import get_f1_calendar
from app.engine.academy_engine import apply_race_trust_change, check_season_milestone
from app.engine.development_engine import award_development_points, points_for_weekend
from app.engine.news_engine import dedupe_news_items, generate_weekend_narratives
from app.engine.rivalry_engine import process_race_rivalries
from app.engine.season_engine import apply_driver_development, apply_in_season_team_development, is_season_complete, transition_to_offseason
from app.engine.standings_engine import apply_race_points, award_bonus_points
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

    completed_round = next(calendar_round for calendar_round in save.calendar if calendar_round.id == round_id)
    weekend = simulate_weekend(save, round_id)
    standings = apply_race_points(save.standings, weekend.sprint)
    standings = apply_race_points(standings, weekend.feature)
    if completed_round.series == "F2" and weekend.qualifying.classification:
        standings = award_bonus_points(standings, weekend.qualifying.classification[0].driver_id, 2)
    standings = standings.model_copy(update={"team_standings": _team_standings(save, standings)})

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

    completed_rounds = sum(1 for r in save.calendar if r.completed) + 1
    updated_save, development_news = apply_in_season_team_development(updated_save, completed_rounds)
    news_items.extend(development_news)
    updated_save, driver_development_news = apply_driver_development(updated_save, completed_rounds)
    news_items.extend(driver_development_news)
    news_items.extend(
        generate_weekend_narratives(
            updated_save,
            weekend,
            completed_round.series,
            completed_rounds,
            completed_round.end_date,
        )
    )

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
            "news": dedupe_news_items([
                *updated_save.news,
                NewsItem(
                    id=f"{round_id}_feature_headline",
                    date=completed_round.end_date,
                    category="race",
                    headline=weekend.headline,
                    body=f"The {completed_round.series} weekend is complete, with race points now applied.",
                    linked_driver_ids=[save.player_driver_id] if save.player_driver_id else [],
                    importance=4,
                ),
                *news_items,
            ]),
        }
    )

    if completed_round.series == "F2":
        updated, f1_news = _simulate_parallel_f1(updated, completed_round.end_date)
        if f1_news:
            updated = updated.model_copy(update={"news": dedupe_news_items([*updated.news, *f1_news])})

    # Check if season is complete and transition to offseason
    if is_season_complete(updated):
        updated, season_news = transition_to_offseason(updated)

    updated = award_development_points(updated, points_for_weekend(updated, round_id))

    return manager.save(updated)


def _simulate_parallel_f1(save: SaveGame, through_date: str) -> tuple[SaveGame, list[NewsItem]]:
    f1_calendar = get_f1_calendar()
    completed_ids = {weekend.round_id for weekend in save.f1_weekend_results}
    due_rounds = [
        calendar_round
        for calendar_round in f1_calendar
        if calendar_round.end_date <= through_date and calendar_round.id not in completed_ids
    ]
    if not due_rounds:
        return save, []

    f1_standings = save.f1_standings or _initial_f1_standings(save)
    f1_results = list(save.f1_weekend_results)
    news: list[NewsItem] = []
    temp_save = save.model_copy(update={"calendar": f1_calendar, "standings": f1_standings})

    for calendar_round in due_rounds:
        weekend = simulate_weekend(temp_save, calendar_round.id)
        f1_results.append(weekend)
        f1_standings = apply_race_points(f1_standings, weekend.sprint)
        f1_standings = apply_race_points(f1_standings, weekend.feature)
        f1_standings = f1_standings.model_copy(update={"team_standings": _team_standings_for_series(save, f1_standings, "F1")})
        temp_save = temp_save.model_copy(update={"standings": f1_standings, "f1_weekend_results": f1_results})
        winner = next((driver for driver in save.drivers if driver.id == weekend.feature.classification[0].driver_id), None)
        news.append(
            NewsItem(
                id=f"{calendar_round.id}_f1_headline",
                date=calendar_round.end_date,
                category="race",
                headline=f"F1: {winner.name if winner else 'Unknown'} wins {calendar_round.name}",
                body="Formula 1 continues in parallel while your F2 season develops.",
                linked_driver_ids=[winner.id] if winner else [],
                importance=2,
            )
        )

    return save.model_copy(update={"f1_standings": f1_standings, "f1_weekend_results": f1_results}), news


def _initial_f1_standings(save: SaveGame):
    from app.models.save_game import ChampionshipEntry, ChampionshipState

    f1_driver_ids = [driver.id for driver in save.drivers if driver.series == "F1"]
    f1_team_ids = [team.id for team in save.teams if team.series == "F1"]
    return ChampionshipState(
        driver_standings=[ChampionshipEntry(driver_id=driver_id) for driver_id in f1_driver_ids],
        team_standings={team_id: 0 for team_id in f1_team_ids},
    )


def _get_save(save_id: str) -> SaveGame:
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    return save


def _team_standings(save: SaveGame, standings) -> dict[str, int]:
    next_round = _next_round(save)
    series = next_round.series if next_round is not None else "F2"
    return _team_standings_for_series(save, standings, series)


def _team_standings_for_series(save: SaveGame, standings, series: str) -> dict[str, int]:
    driver_points = {entry.driver_id: entry.points for entry in standings.driver_standings}
    team_points = {team.id: 0 for team in save.teams if team.series == series}
    for driver in save.drivers:
        if driver.series == series and driver.team_id in team_points:
            team_points[driver.team_id] += driver_points.get(driver.id, 0)

    return dict(sorted(team_points.items(), key=lambda item: item[1], reverse=True))


def _next_round(save: SaveGame):
    return next((calendar_round for calendar_round in save.calendar if not calendar_round.completed), None)
