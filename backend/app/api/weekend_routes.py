import random

from fastapi import APIRouter, HTTPException, status

from app.data.loaders import get_f1_calendar, get_tracks
from app.engine.academy_engine import apply_race_trust_change, check_season_milestone
from app.engine.car_development_engine import apply_due_upgrades
from app.engine.development_engine import award_development_points, award_weekend_development, points_for_weekend, points_for_position
from app.engine.interview_engine import add_pending_interview, generate_interviews_for_weekend
from app.engine.identity_engine import update_driver_identities
from app.engine.news_engine import dedupe_news_items, generate_weekend_narratives
from app.engine.rivalry_engine import process_race_rivalries
from app.engine.season_engine import apply_driver_development, apply_in_season_team_development, is_season_complete, transition_to_offseason
from app.engine.silly_season_engine import generate_mid_season_drama
from app.engine.standings_engine import apply_race_points, award_bonus_points
from app.engine.storyline_engine import generate_pre_race_storylines, storylines_to_dict
from app.engine.weekend_engine import simulate_weekend
from app.models.race import (
    ChampionshipContext,
    PreRaceStorylineView,
    TrackPreview,
    WeatherState,
    WeekendPreview,
    WeekendResult,
)
from app.models.car_development import PracticeCorrelationReport
from app.models.save_game import NewsItem, SaveGame
from app.models.strategy import KeyIncident, RaceAnalysis, StrategySummary
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


@router.get("/{round_id}/analysis", response_model=RaceAnalysis)
def get_race_analysis(save_id: str, round_id: str, race_type: str = "feature") -> RaceAnalysis:
    """Get detailed strategy analysis for a completed race.

    Returns stint summaries, pit stop history, safety car moments,
    strategy summary, and key incidents.
    """
    save = _get_save(save_id)
    result = next((weekend for weekend in save.weekend_results if weekend.round_id == round_id), None)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekend result not found")

    race = result.feature if race_type == "feature" else result.sprint
    if race is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{race_type} race not found")

    # Extract key incidents from lap log
    key_incidents = _extract_key_incidents(race, save)

    # Build strategy summary
    strategy_summary = _build_strategy_summary(race)

    return RaceAnalysis(
        save_id=save_id,
        round_id=round_id,
        race_type=race_type,  # type: ignore[arg-type]
        total_laps=race.total_laps,
        strategy_plans=race.strategy_plans,
        pit_stop_events=race.pit_stop_events,
        stint_summaries=race.stint_summaries,
        strategy_calls=race.strategy_calls,
        safety_car_decisions=race.safety_car_decisions,
        key_incidents=key_incidents,
        strategy_summary=strategy_summary,
    )


def _extract_key_incidents(race, save: SaveGame) -> list[KeyIncident]:
    """Extract notable incidents from the race."""
    incidents: list[KeyIncident] = []
    driver_names = {d.id: d.name for d in save.drivers}

    # DNFs
    for driver_id in race.dnfs:
        driver_name = driver_names.get(driver_id, driver_id)
        # Find the lap where DNF occurred from lap log
        dnf_lap = None
        for snapshot in race.lap_log:
            for entry in snapshot.running_order:
                if entry.driver_id == driver_id and entry.status == "dnf":
                    dnf_lap = snapshot.lap
                    break
            if dnf_lap:
                break

        if dnf_lap:
            # Check commentary for crash vs mechanical
            lap_snapshot = next((s for s in race.lap_log if s.lap == dnf_lap), None)
            is_crash = lap_snapshot and any("crash" in c.lower() for c in lap_snapshot.commentary)
            incidents.append(
                KeyIncident(
                    lap=dnf_lap,
                    type="crash" if is_crash else "mechanical",
                    driver_id=driver_id,
                    description=f"{driver_name} {'crashes out' if is_crash else 'retires with mechanical failure'}",
                    impact="DNF",
                )
            )

    # Safety car deployments
    for sc_decision in race.safety_car_decisions:
        trigger_parts = sc_decision.trigger.split("_") if sc_decision.trigger else []
        trigger_type = trigger_parts[0] if trigger_parts else "unknown"
        trigger_driver = trigger_parts[1] if len(trigger_parts) > 1 else None
        trigger_name = driver_names.get(trigger_driver, trigger_driver) if trigger_driver else "incident"

        incidents.append(
            KeyIncident(
                lap=sc_decision.lap,
                type="safety_car",
                driver_id=trigger_driver,
                description=f"{'Safety Car' if sc_decision.mode == 'safety_car' else 'VSC'} deployed ({trigger_name})",
                impact=f"Pit window {'open' if sc_decision.pit_window_open else 'closed'}",
            )
        )

    # Pit stops under safety car (strategic moments)
    sc_pit_stops = [ps for ps in race.pit_stop_events if ps.under_safety_car]
    for ps in sc_pit_stops:
        driver_name = driver_names.get(ps.driver_id, ps.driver_id)
        incidents.append(
            KeyIncident(
                lap=ps.lap,
                type="pit_stop",
                driver_id=ps.driver_id,
                description=f"{driver_name} pits under safety car ({ps.compound_in} -> {ps.compound_out})",
                impact=f"Reduced pit loss ({ps.pit_loss:.1f}s)" if ps.pit_loss else None,
            )
        )

    # Sort by lap
    incidents.sort(key=lambda i: i.lap)
    return incidents


def _build_strategy_summary(race) -> StrategySummary:
    """Build an overall strategy summary from the race data."""
    # Count pit stops
    total_pit_stops = len(race.pit_stop_events)

    # Count safety cars
    sc_count = sum(1 for sc in race.safety_car_decisions if sc.mode == "safety_car")
    vsc_count = sum(1 for sc in race.safety_car_decisions if sc.mode == "vsc")

    # Drivers who pitted under safety car
    sc_pitters = list({ps.driver_id for ps in race.pit_stop_events if ps.under_safety_car})

    # Group drivers by stop count
    driver_stops: dict[str, int] = {}
    for ps in race.pit_stop_events:
        driver_stops[ps.driver_id] = driver_stops.get(ps.driver_id, 0) + 1

    one_stop = [d for d, c in driver_stops.items() if c == 1]
    two_stop = [d for d, c in driver_stops.items() if c == 2]
    three_plus = [d for d, c in driver_stops.items() if c >= 3]

    # Average stint length
    if race.stint_summaries:
        stint_lengths = [s.end_lap - s.start_lap + 1 for s in race.stint_summaries if s.end_lap]
        avg_stint = sum(stint_lengths) / len(stint_lengths) if stint_lengths else None
    else:
        avg_stint = None

    # Most used compound
    compound_counts: dict[str, int] = {}
    for stint in race.stint_summaries:
        compound_counts[stint.compound] = compound_counts.get(stint.compound, 0) + 1
    most_used = max(compound_counts, key=compound_counts.get) if compound_counts else None

    return StrategySummary(
        total_pit_stops=total_pit_stops,
        safety_car_count=sc_count,
        vsc_count=vsc_count,
        drivers_who_pitted_under_sc=sc_pitters,
        one_stop_drivers=one_stop,
        two_stop_drivers=two_stop,
        three_plus_stop_drivers=three_plus,
        average_stint_length=round(avg_stint, 1) if avg_stint else None,
        most_used_compound=most_used,  # type: ignore[arg-type]
    )


@router.get("/{round_id}/correlation-report", response_model=list[PracticeCorrelationReport])
def get_correlation_reports(save_id: str, round_id: str) -> list[PracticeCorrelationReport]:
    """Get upgrade correlation reports from practice for a specific round.

    Returns detailed reports showing how upgrades correlated with predictions,
    including driver feedback and engineer verdicts based on Technical Feedback.
    """
    save = _get_save(save_id)
    result = next((weekend for weekend in save.weekend_results if weekend.round_id == round_id), None)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekend result not found")

    return result.practice.correlation_reports


@router.get("/{round_id}/correlation-report/{team_id}", response_model=list[PracticeCorrelationReport])
def get_team_correlation_reports(save_id: str, round_id: str, team_id: str) -> list[PracticeCorrelationReport]:
    """Get upgrade correlation reports for a specific team.

    Returns detailed reports for a specific team, useful for showing
    the player's team correlation data on the race weekend UI.
    """
    save = _get_save(save_id)
    result = next((weekend for weekend in save.weekend_results if weekend.round_id == round_id), None)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Weekend result not found")

    return [report for report in result.practice.correlation_reports if report.team_id == team_id]


@router.get("/next/round")
def get_next_round(save_id: str):
    save = _get_save(save_id)
    next_round = _next_round(save)
    if next_round is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season complete")

    return next_round


@router.get("/next/preview", response_model=WeekendPreview)
def get_weekend_preview(save_id: str) -> WeekendPreview:
    """Get a pre-race preview with storylines, championship context, and drama."""
    save = _get_save(save_id)
    next_round = _next_round(save)
    if next_round is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season complete")

    track = next((t for t in get_tracks() if t.id == next_round.track_id), None)
    if track is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")

    # Generate storylines
    storylines = generate_pre_race_storylines(save, next_round.id, track)
    storyline_views = [
        PreRaceStorylineView(
            id=s.id,
            type=s.story_type,
            headline=s.headline,
            narrative=s.narrative,
            drama_level=s.drama_level,
            driver_ids=s.driver_ids,
            team_ids=s.team_ids,
        )
        for s in storylines
    ]

    # Build championship context
    championship_context = _build_championship_context(save, next_round.series)

    # Get player info
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    teammate = None
    if player:
        teammate = next(
            (d for d in save.drivers if d.team_id == player.team_id and d.id != player.id),
            None,
        )

    # Generate weather forecast
    rng = random.Random(f"{save.random_seed}:{next_round.id}:weather")
    rain_roll = rng.randint(1, 100)
    forecast = WeatherState(
        condition="wet" if rain_roll <= track.rain_chance else "dry",
        air_temp=rng.randint(18, 32),
        track_temp=rng.randint(28, 48),
        rain_intensity=rng.randint(20, 80) if rain_roll <= track.rain_chance else 0,
        track_grip=rng.randint(70, 90),
    )

    return WeekendPreview(
        save_id=save.save_id,
        round_id=next_round.id,
        round_name=next_round.name,
        round_number=next_round.round_number,
        series=next_round.series,
        has_sprint=next_round.has_sprint,
        track=TrackPreview(
            id=track.id,
            name=track.name,
            country=track.country,
            overtaking_difficulty=track.overtaking_difficulty,
            tire_deg=track.tire_deg,
            safety_car_chance=track.safety_car_chance,
            rain_chance=track.rain_chance,
            qualifying_importance=track.qualifying_importance,
            street_circuit=track.street_circuit,
        ),
        storylines=storyline_views,
        championship_context=championship_context,
        player_form=player.current_form if player else None,
        player_morale=player.morale if player else None,
        teammate_name=teammate.name if teammate else None,
        weather_forecast=forecast,
    )


def _build_championship_context(save: SaveGame, series: str) -> ChampionshipContext:
    """Build championship context for the preview."""
    standings = save.f1_standings if series == "F1" and save.f1_standings else save.standings
    sorted_standings = sorted(standings.driver_standings, key=lambda e: e.points, reverse=True)

    player_entry = next(
        (e for e in sorted_standings if e.driver_id == save.player_driver_id),
        None,
    )
    if not player_entry:
        return ChampionshipContext()

    player_idx = next(
        (i for i, e in enumerate(sorted_standings) if e.driver_id == save.player_driver_id),
        None,
    )
    if player_idx is None:
        return ChampionshipContext()

    total_rounds = sum(1 for r in save.calendar if r.series == series)
    completed_rounds = sum(1 for r in save.calendar if r.completed and r.series == series)
    rounds_remaining = total_rounds - completed_rounds

    leader_points = sorted_standings[0].points if sorted_standings else 0
    points_to_leader = leader_points - player_entry.points

    points_to_next = 0
    if player_idx > 0:
        points_to_next = sorted_standings[player_idx - 1].points - player_entry.points

    points_from_behind = 0
    if player_idx < len(sorted_standings) - 1:
        points_from_behind = player_entry.points - sorted_standings[player_idx + 1].points

    # Title in reach if gap to leader is less than max points available
    max_points_remaining = rounds_remaining * 25  # Rough F1/F2 max
    title_in_reach = points_to_leader <= max_points_remaining and player_idx <= 3

    # Relegation danger check (for F2 championship standings)
    relegation_danger = player_idx + 1 > 10 and completed_rounds >= 4

    return ChampionshipContext(
        player_position=player_idx + 1,
        points_to_leader=points_to_leader,
        points_to_next=points_to_next,
        points_from_behind=points_from_behind,
        rounds_remaining=rounds_remaining,
        title_in_reach=title_in_reach,
        relegation_danger=relegation_danger,
    )


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
    save, upgrade_reports, upgrade_news = apply_due_upgrades(save, completed_round.round_number, round_id)
    weekend = simulate_weekend(save, round_id, practice_correlation_reports=upgrade_reports)
    standings = apply_race_points(save.standings, weekend.sprint)
    standings = apply_race_points(standings, weekend.feature)
    if completed_round.series == "F2" and weekend.qualifying.classification:
        standings = award_bonus_points(standings, weekend.qualifying.classification[0].driver_id, 2)
    standings = standings.model_copy(update={"team_standings": _team_standings(save, standings)})

    # Apply academy trust changes
    news_items: list[NewsItem] = [*upgrade_news]
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

    # Generate mid-season transfer drama and rumors
    updated_save, transfer_drama_news = generate_mid_season_drama(updated_save, completed_rounds)
    news_items.extend(transfer_drama_news)

    track = next(item for item in get_tracks() if item.id == completed_round.track_id)
    updated_save, identity_news = update_driver_identities(updated_save, weekend, track, completed_round.end_date)
    news_items.extend(identity_news)
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

    # Award development points AND branch XP based on race performance
    updated, dev_summary = award_weekend_development(updated, weekend)

    # Store development summary in event flags for frontend retrieval
    updated = updated.model_copy(
        update={
            "event_flags": {
                **updated.event_flags,
                "last_weekend_development": dev_summary.to_dict(),
            }
        }
    )

    # Generate post-race interviews based on weekend results
    weekend_data = _extract_interview_trigger_data(updated, weekend)
    interviews = generate_interviews_for_weekend(
        updated, round_id, weekend_result=weekend_data, max_interviews=1
    )
    for interview in interviews:
        updated = add_pending_interview(updated, interview)

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
        temp_save, upgrade_reports, upgrade_news = apply_due_upgrades(temp_save, calendar_round.round_number, calendar_round.id)
        weekend = simulate_weekend(temp_save, calendar_round.id, practice_correlation_reports=upgrade_reports)
        news.extend(upgrade_news)
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

    return save.model_copy(
        update={
            "teams": temp_save.teams,
            "team_development": temp_save.team_development,
            "f1_standings": f1_standings,
            "f1_weekend_results": f1_results,
        }
    ), news


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


def _extract_interview_trigger_data(save: SaveGame, weekend) -> dict:
    """Extract trigger-relevant data from weekend results for interview generation."""
    player_id = save.player_driver_id
    if not player_id:
        return {}

    data: dict = {}

    # Feature race data
    if weekend.feature:
        player_result = next(
            (r for r in weekend.feature.classification if r.driver_id == player_id),
            None,
        )
        if player_result:
            data["feature_position"] = player_result.position
            data["points_scored"] = getattr(player_result, "points", 0)
            if getattr(player_result, "dnf", False):
                data["dnf_reason"] = getattr(player_result, "dnf_reason", "crash")

    # Qualifying data
    if weekend.qualifying:
        player_quali = next(
            (r for r in weekend.qualifying.classification if r.driver_id == player_id),
            None,
        )
        if player_quali:
            data["qualifying_position"] = player_quali.position
            if "feature_position" in data:
                data["positions_gained"] = player_quali.position - data["feature_position"]

    # Check for first F1 race
    player = next((d for d in save.drivers if d.id == player_id), None)
    if player and player.series == "F1":
        # Count F1 races completed (including this one in weekend_results already)
        f1_race_count = len([
            w for w in save.weekend_results
            if w.feature and any(r.driver_id == player_id for r in w.feature.classification)
        ])
        data["is_first_f1_race"] = f1_race_count == 1

        # Check first F1 points
        if data.get("points_scored", 0) > 0:
            previous_points = 0
            for w in save.weekend_results[:-1]:  # Exclude the just-added result
                if w.feature:
                    for r in w.feature.classification:
                        if r.driver_id == player_id:
                            previous_points += getattr(r, "points", 0)
            data["first_f1_points"] = previous_points == 0

    # Check for strategy controversy (if race result differs significantly from quali)
    if data.get("qualifying_position") and data.get("feature_position"):
        quali_pos = data["qualifying_position"]
        race_pos = data["feature_position"]
        # If finished 5+ positions worse than quali, possible strategy issue
        if race_pos - quali_pos >= 5:
            data["strategy_controversy"] = True

    # Check for team orders (from race context if available)
    if weekend.feature and hasattr(weekend.feature, "team_orders_given"):
        data["team_orders"] = weekend.feature.team_orders_given

    # Check for close teammate battle
    if player and weekend.feature:
        teammate = next(
            (d for d in save.drivers if d.team_id == player.team_id and d.id != player_id),
            None,
        )
        if teammate:
            player_result = next(
                (r for r in weekend.feature.classification if r.driver_id == player_id),
                None,
            )
            teammate_result = next(
                (r for r in weekend.feature.classification if r.driver_id == teammate.id),
                None,
            )
            if player_result and teammate_result:
                pos_diff = abs(player_result.position - teammate_result.position)
                # Within 1 position is a close battle
                data["close_teammate_battle"] = pos_diff <= 1

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Session-by-session weekend simulation
# ─────────────────────────────────────────────────────────────────────────────

from app.models.race import ActiveWeekendState


@router.post("/session/start")
def start_weekend(save_id: str) -> dict:
    """Start a new weekend, initializing the active weekend state."""
    save = _get_save(save_id)
    next_round = _next_round(save)
    if next_round is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Season complete")

    if save.active_weekend and save.active_weekend.round_id == next_round.id:
        # Already started this weekend
        return {
            "success": True,
            "message": "Weekend already in progress",
            "roundId": next_round.id,
            "phase": save.active_weekend.phase,
            "hasSprint": next_round.has_sprint,
        }

    # Create new active weekend
    active_weekend = ActiveWeekendState(
        round_id=next_round.id,
        phase="not_started",
        has_sprint=next_round.has_sprint,
    )
    updated = save.model_copy(update={"active_weekend": active_weekend, "phase": "race_week"})
    manager.save(updated)

    return {
        "success": True,
        "message": "Weekend started",
        "roundId": next_round.id,
        "phase": "not_started",
        "hasSprint": next_round.has_sprint,
    }


@router.post("/session/practice")
def run_practice(save_id: str) -> dict:
    """Run the practice session."""
    from app.engine.weekend_engine import _simulate_practice, _weather, _find_round, _find_track
    from app.engine.car_development_engine import apply_due_upgrades

    save = _get_save(save_id)
    if not save.active_weekend:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Weekend not started. Call /session/start first.")

    if save.active_weekend.phase not in ("not_started",):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Practice already completed. Current phase: {save.active_weekend.phase}")

    round_id = save.active_weekend.round_id
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)
    drivers = [d for d in save.drivers if d.series == calendar_round.series]
    teams = {t.id: t for t in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}")
    weather = _weather(track, rng)

    # Apply any pending upgrades
    save, upgrade_reports, _ = apply_due_upgrades(save, calendar_round.round_number, round_id)

    practice = _simulate_practice(drivers, teams, track, weather, rng, upgrade_reports)

    # Find player result
    player_result = next(
        (p for p in practice.classification if p.driver_id == save.player_driver_id),
        None
    )

    # Update active weekend
    active_weekend = save.active_weekend.model_copy(update={
        "phase": "practice",
        "practice_result": practice,
    })
    updated = save.model_copy(update={"active_weekend": active_weekend})
    manager.save(updated)

    return {
        "success": True,
        "session": "practice",
        "playerPosition": player_result.position if player_result else None,
        "playerSetupScore": player_result.setup_score if player_result else None,
        "classification": [
            {"position": p.position, "driverId": p.driver_id, "lapTime": p.lap_time, "note": p.note}
            for p in practice.classification[:10]
        ],
    }


@router.post("/session/qualifying")
def run_qualifying(save_id: str) -> dict:
    """Run the qualifying session."""
    from app.engine.weekend_engine import _simulate_qualifying, _weather, _find_round, _find_track

    save = _get_save(save_id)
    if not save.active_weekend:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Weekend not started")

    if save.active_weekend.phase != "practice":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Must complete practice first. Current phase: {save.active_weekend.phase}")

    round_id = save.active_weekend.round_id
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)
    drivers = [d for d in save.drivers if d.series == calendar_round.series]
    teams = {t.id: t for t in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}:quali")
    weather = _weather(track, rng)

    qualifying = _simulate_qualifying(drivers, teams, track, weather, rng, series=calendar_round.series)

    # Find player result
    player_result = next(
        (q for q in qualifying.classification if q.driver_id == save.player_driver_id),
        None
    )

    # Update active weekend
    active_weekend = save.active_weekend.model_copy(update={
        "phase": "qualifying",
        "qualifying_result": qualifying,
    })
    updated = save.model_copy(update={"active_weekend": active_weekend})
    manager.save(updated)

    return {
        "success": True,
        "session": "qualifying",
        "playerPosition": player_result.position if player_result else None,
        "playerGap": f"+{player_result.gap_to_pole:.3f}" if player_result and player_result.gap_to_pole > 0 else "POLE",
        "classification": [
            {"position": q.position, "driverId": q.driver_id, "gapToPole": q.gap_to_pole, "note": q.note}
            for q in qualifying.classification[:10]
        ],
    }


@router.post("/session/sprint")
def run_sprint(save_id: str) -> dict:
    """Run the sprint race."""
    from app.engine.weekend_engine import (
        _simulate_race, _weather, _find_round, _find_track,
        sprint_grid_for_round, empty_race_result,
    )

    save = _get_save(save_id)
    if not save.active_weekend:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Weekend not started")

    if save.active_weekend.phase != "qualifying":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Must complete qualifying first. Current phase: {save.active_weekend.phase}")

    if not save.active_weekend.has_sprint:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This weekend has no sprint race")

    round_id = save.active_weekend.round_id
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)
    drivers = [d for d in save.drivers if d.series == calendar_round.series]
    teams = {t.id: t for t in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}:sprint")
    weather = _weather(track, rng)

    qualifying_order = [q.driver_id for q in save.active_weekend.qualifying_result.classification]
    sprint_grid = sprint_grid_for_round(calendar_round, qualifying_order)

    if not sprint_grid:
        sprint = empty_race_result("sprint", track)
    else:
        sprint = _simulate_race("sprint", calendar_round, sprint_grid, drivers, teams, track, weather, rng, save)

    # Find player result
    player_result = next(
        (r for r in sprint.classification if r.driver_id == save.player_driver_id),
        None
    )

    # Update active weekend
    active_weekend = save.active_weekend.model_copy(update={
        "phase": "sprint",
        "sprint_result": sprint,
    })
    updated = save.model_copy(update={"active_weekend": active_weekend})
    manager.save(updated)

    return {
        "success": True,
        "session": "sprint",
        "playerPosition": player_result.position if player_result else None,
        "playerPoints": player_result.points if player_result else 0,
        "classification": [
            {"position": r.position, "driverId": r.driver_id, "points": r.points}
            for r in sprint.classification[:10]
        ],
    }


@router.post("/session/feature")
def run_feature(save_id: str) -> dict:
    """Run the feature race."""
    from app.engine.weekend_engine import _simulate_race, _weather, _find_round, _find_track

    save = _get_save(save_id)
    if not save.active_weekend:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Weekend not started")

    expected_phase = "sprint" if save.active_weekend.has_sprint else "qualifying"
    if save.active_weekend.phase != expected_phase:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Must complete {expected_phase} first. Current phase: {save.active_weekend.phase}"
        )

    round_id = save.active_weekend.round_id
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)
    drivers = [d for d in save.drivers if d.series == calendar_round.series]
    teams = {t.id: t for t in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}:feature")
    weather = _weather(track, rng)

    qualifying_order = [q.driver_id for q in save.active_weekend.qualifying_result.classification]
    feature = _simulate_race("feature", calendar_round, qualifying_order, drivers, teams, track, weather, rng, save)

    # Find player result
    player_result = next(
        (r for r in feature.classification if r.driver_id == save.player_driver_id),
        None
    )

    # Update active weekend
    active_weekend = save.active_weekend.model_copy(update={
        "phase": "feature",
        "feature_result": feature,
    })
    updated = save.model_copy(update={"active_weekend": active_weekend})
    manager.save(updated)

    return {
        "success": True,
        "session": "feature",
        "playerPosition": player_result.position if player_result else None,
        "playerPoints": player_result.points if player_result else 0,
        "classification": [
            {"position": r.position, "driverId": r.driver_id, "points": r.points}
            for r in feature.classification[:10]
        ],
    }


from pydantic import BaseModel
from typing import Optional


class LocalRaceResults(BaseModel):
    """Results from races run locally in the frontend."""
    qualifying_position: Optional[int] = None
    sprint_position: Optional[int] = None
    feature_position: Optional[int] = None
    sprint_points: int = 0
    feature_points: int = 0


@router.post("/session/complete")
def complete_weekend(save_id: str, results: Optional[LocalRaceResults] = None) -> dict:
    """Finalize the weekend and apply all results to standings.

    Supports two modes:
    1. Backend session flow: active_weekend.phase == "feature" (races run via backend APIs)
    2. Frontend local flow: active_weekend exists but races were run locally in browser
       - Pass results in request body to get DP awarded
    """
    from app.engine.weekend_engine import _headline, _find_round, _find_track, empty_race_result

    save = _get_save(save_id)

    # If no active weekend, check if we should just advance the calendar
    # (Frontend ran races locally without using backend session APIs)
    if not save.active_weekend:
        next_round = _next_round(save)
        if next_round is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No weekend to complete - season is over")

        # Calculate DP from local results if provided
        dp_earned = 0
        if results:
            dp_earned = points_for_position(
                feature_pos=results.feature_position or 22,
                sprint_pos=results.sprint_position,
                quali_pos=results.qualifying_position,
            )

        # Mark the round as complete and advance
        updated_calendar = [
            cr.model_copy(update={"completed": True}) if cr.id == next_round.id else cr
            for cr in save.calendar
        ]

        # Award DP if earned
        updated_save = save
        if dp_earned > 0:
            updated_save = award_development_points(save, dp_earned, next_round.id)

        # Also award championship points to standings
        if results:
            standings = updated_save.standings
            player_id = updated_save.player_driver_id
            if player_id and standings:
                total_race_points = results.sprint_points + results.feature_points
                if total_race_points > 0:
                    for entry in standings.driver_standings:
                        if entry.driver_id == player_id:
                            entry.points += total_race_points
                            if results.feature_position == 1:
                                entry.wins += 1
                            if results.feature_position and results.feature_position <= 3:
                                entry.podiums += 1
                            break
                    updated_save = updated_save.model_copy(update={"standings": standings})

        final_save = updated_save.model_copy(
            update={
                "phase": "between_races",
                "current_date": next_round.end_date,
                "calendar": updated_calendar,
            }
        )
        manager.save(final_save)
        return {
            "success": True,
            "message": "Weekend completed (local mode)",
            "headline": f"{next_round.name} complete",
            "qualifyingPosition": results.qualifying_position if results else None,
            "featurePosition": results.feature_position if results else None,
            "pointsEarned": (results.sprint_points + results.feature_points) if results else 0,
            "developmentPointsEarned": dp_earned,
        }

    # If active weekend exists but races were run locally (not via backend APIs),
    # just mark the round complete and clear the active weekend
    if save.active_weekend.phase == "not_started" or save.active_weekend.feature_result is None:
        round_id = save.active_weekend.round_id
        calendar_round = _find_round(save, round_id)

        # Calculate DP from local results if provided
        dp_earned = 0
        if results:
            dp_earned = points_for_position(
                feature_pos=results.feature_position or 22,
                sprint_pos=results.sprint_position,
                quali_pos=results.qualifying_position,
            )

        # Award DP if earned
        updated_save = save
        if dp_earned > 0:
            updated_save = award_development_points(save, dp_earned, round_id)

        # Also award championship points to standings
        if results:
            standings = updated_save.standings
            player_id = updated_save.player_driver_id
            if player_id and standings:
                total_race_points = results.sprint_points + results.feature_points
                if total_race_points > 0:
                    for entry in standings.driver_standings:
                        if entry.driver_id == player_id:
                            entry.points += total_race_points
                            if results.feature_position == 1:
                                entry.wins += 1
                            if results.feature_position and results.feature_position <= 3:
                                entry.podiums += 1
                            break
                    updated_save = updated_save.model_copy(update={"standings": standings})

        # Mark round complete and clear active weekend
        updated_calendar = [
            cr.model_copy(update={"completed": True}) if cr.id == round_id else cr
            for cr in save.calendar
        ]
        final_save = updated_save.model_copy(
            update={
                "phase": "between_races",
                "current_date": calendar_round.end_date,
                "calendar": updated_calendar,
                "active_weekend": None,
            }
        )
        manager.save(final_save)
        return {
            "success": True,
            "message": "Weekend completed (local mode)",
            "headline": f"{calendar_round.name} complete",
            "qualifyingPosition": results.qualifying_position if results else None,
            "featurePosition": results.feature_position if results else None,
            "pointsEarned": (results.sprint_points + results.feature_points) if results else 0,
            "developmentPointsEarned": dp_earned,
        }

    # Full backend session flow - active_weekend has all race results
    aw = save.active_weekend
    round_id = aw.round_id
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)

    # Build WeekendResult from active weekend
    weekend = WeekendResult(
        save_id=save.save_id,
        round_id=round_id,
        track_id=track.id,
        completed=True,
        practice=aw.practice_result,
        qualifying=aw.qualifying_result,
        sprint=aw.sprint_result or empty_race_result("sprint", track),
        feature=aw.feature_result,
        headline=_headline(save, aw.feature_result),
    )

    # Apply standings
    standings = apply_race_points(save.standings, weekend.sprint)
    standings = apply_race_points(standings, weekend.feature)
    if calendar_round.series == "F2" and weekend.qualifying.classification:
        standings = award_bonus_points(standings, weekend.qualifying.classification[0].driver_id, 2)
    standings = standings.model_copy(update={"team_standings": _team_standings(save, standings)})

    # Apply all the post-race updates (simplified version)
    news_items: list[NewsItem] = []
    updated_save = save.model_copy(update={"standings": standings})

    # Apply academy trust changes
    updated_save, sprint_news = apply_race_trust_change(updated_save, weekend.sprint, is_feature=False)
    if sprint_news:
        news_items.append(sprint_news)
    updated_save, feature_news = apply_race_trust_change(updated_save, weekend.feature, is_feature=True)
    if feature_news:
        news_items.append(feature_news)

    # Update calendar
    updated_calendar = [
        cr.model_copy(update={"completed": True}) if cr.id == round_id else cr
        for cr in save.calendar
    ]

    # Award development points
    updated_save, dev_summary = award_weekend_development(updated_save, weekend)

    # Clear active weekend and save
    final_save = updated_save.model_copy(
        update={
            "phase": "between_races",
            "current_date": calendar_round.end_date,
            "calendar": updated_calendar,
            "weekend_results": [*save.weekend_results, weekend],
            "active_weekend": None,
            "news": dedupe_news_items([
                *updated_save.news,
                NewsItem(
                    id=f"{round_id}_feature_headline",
                    date=calendar_round.end_date,
                    category="race",
                    headline=weekend.headline,
                    body=f"The {calendar_round.series} weekend is complete.",
                    linked_driver_ids=[save.player_driver_id] if save.player_driver_id else [],
                    importance=4,
                ),
                *news_items,
            ]),
            "event_flags": {
                **updated_save.event_flags,
                "last_weekend_development": dev_summary.to_dict(),
            },
        }
    )

    manager.save(final_save)

    # Get player final results
    player_quali = next(
        (q for q in weekend.qualifying.classification if q.driver_id == save.player_driver_id),
        None
    )
    player_feature = next(
        (r for r in weekend.feature.classification if r.driver_id == save.player_driver_id),
        None
    )

    return {
        "success": True,
        "message": "Weekend completed",
        "headline": weekend.headline,
        "qualifyingPosition": player_quali.position if player_quali else None,
        "featurePosition": player_feature.position if player_feature else None,
        "pointsEarned": (player_feature.points if player_feature else 0),
    }


@router.get("/session/status")
def get_weekend_status(save_id: str) -> dict:
    """Get the current weekend session status."""
    save = _get_save(save_id)

    if not save.active_weekend:
        next_round = _next_round(save)
        return {
            "active": False,
            "nextRoundId": next_round.id if next_round else None,
            "nextRoundName": next_round.name if next_round else None,
        }

    aw = save.active_weekend
    return {
        "active": True,
        "roundId": aw.round_id,
        "phase": aw.phase,
        "hasSprint": aw.has_sprint,
        "practiceComplete": aw.practice_result is not None,
        "qualifyingComplete": aw.qualifying_result is not None,
        "sprintComplete": aw.sprint_result is not None,
        "featureComplete": aw.feature_result is not None,
    }
