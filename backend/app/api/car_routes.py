"""API routes for car performance and development surfaces."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.data.loaders import get_tracks
from app.engine.car_development_engine import ensure_car_development_state
from app.engine.car_performance_engine import (
    car_strengths_weaknesses,
    car_tier,
    team_track_score,
    track_car_fit,
    track_demand_profile,
)
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/car", tags=["car"])
manager = SaveManager()


@router.get("/overview")
def get_car_overview(save_id: str) -> dict:
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")

    save = ensure_car_development_state(save)
    next_round = next((round_ for round_ in save.calendar if not round_.completed), None)
    tracks = {track.id: track for track in get_tracks()}
    next_track = tracks.get(next_round.track_id) if next_round else None
    player = next((driver for driver in save.drivers if driver.id == save.player_driver_id), None)
    player_team_id = player.team_id if player else None

    rankings = []
    for team in save.teams:
        profile = team.effective_car_profile()
        strengths, weaknesses = car_strengths_weaknesses(profile)
        fit = track_car_fit(profile, next_track) if next_track else profile.overall_performance
        rankings.append(
            {
                "teamId": team.id,
                "teamName": team.name,
                "series": team.series,
                "tier": car_tier(profile),
                "overallPerformance": profile.overall_performance,
                "trackFit": fit,
                "trackScore": team_track_score(team, next_track) if next_track else profile.overall_performance,
                "profile": profile.model_dump(by_alias=True),
                "strengths": strengths,
                "weaknesses": weaknesses,
                "isPlayerTeam": team.id == player_team_id,
            }
        )
    rankings.sort(key=lambda item: (item["series"], -item["trackScore"], -item["overallPerformance"]))

    latest_reports = []
    for weekend in reversed(save.weekend_results):
        if weekend.practice.correlation_reports:
            latest_reports = [report.model_dump(by_alias=True) for report in weekend.practice.correlation_reports]
            break

    current_projects = []
    upgrade_timeline = []
    for team in save.teams:
        state = save.team_development.get(team.id)
        if state is None:
            continue
        for project in state.active_projects:
            row = {
                **project.model_dump(by_alias=True),
                "teamId": team.id,
                "teamName": team.name,
                "series": team.series,
            }
            current_projects.append(row)
            upgrade_timeline.append(row)
        for entry in state.upgrade_history[-5:]:
            upgrade_timeline.append(
                {
                    **entry.model_dump(by_alias=True),
                    "teamId": team.id,
                    "teamName": team.name,
                    "series": team.series,
                    "status": "delivered",
                }
            )
    upgrade_timeline.sort(key=lambda item: (item.get("deliveryRound") or 99, item["teamName"]))

    years_to_regulation = (4 - ((save.season + 1) % 4)) % 4
    return {
        "season": save.season,
        "nextRound": next_round.model_dump(by_alias=True) if next_round else None,
        "nextTrack": next_track.model_dump(by_alias=True) if next_track else None,
        "trackDemand": track_demand_profile(next_track).model_dump(by_alias=True) if next_track else None,
        "playerTeamId": player_team_id,
        "rankings": rankings,
        "currentProjects": current_projects,
        "upgradeTimeline": upgrade_timeline[:40],
        "latestCorrelationReports": latest_reports,
        "regulationTracker": {
            "nextRegulationSeason": save.season + years_to_regulation + 1,
            "yearsRemaining": years_to_regulation + 1,
            "isNextOffseasonRegulationChange": (save.season + 1) % 4 == 0,
            "description": "Major rule changes reduce car carryover and reward regulation research.",
        },
    }
