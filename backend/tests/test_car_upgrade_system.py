from __future__ import annotations

from app.data.loaders import get_tracks
from app.engine.car_development_engine import apply_due_upgrades, offseason_car_evolution
from app.engine.car_performance_engine import performance_composite, track_car_fit
from app.models.car import CarPerformanceProfile, TeamCarState
from app.models.car_development import TeamDevelopmentState, UpgradeProject
from app.models.team import Team
from app.save.save_manager import SaveManager


def test_series_weighting_makes_f1_car_dominant_and_f2_driver_dependent(tmp_path):
    f1_car_delta = performance_composite(series="F1", car_score=90, driver_score=75, setup_score=75, context_score=75) - performance_composite(
        series="F1", car_score=75, driver_score=75, setup_score=75, context_score=75
    )
    f1_driver_delta = performance_composite(series="F1", car_score=75, driver_score=90, setup_score=75, context_score=75) - performance_composite(
        series="F1", car_score=75, driver_score=75, setup_score=75, context_score=75
    )
    f2_car_delta = performance_composite(series="F2", car_score=90, driver_score=75, setup_score=75, context_score=75) - performance_composite(
        series="F2", car_score=75, driver_score=75, setup_score=75, context_score=75
    )
    f2_driver_delta = performance_composite(series="F2", car_score=75, driver_score=90, setup_score=75, context_score=75) - performance_composite(
        series="F2", car_score=75, driver_score=75, setup_score=75, context_score=75
    )

    assert f1_car_delta > f1_driver_delta
    assert f2_driver_delta > f2_car_delta


def test_track_fit_rewards_different_car_strengths_by_circuit():
    tracks = {track.id: track for track in get_tracks()}
    street_car = CarPerformanceProfile(
        overall_performance=82,
        low_speed_cornering=94,
        traction=92,
        straight_line_speed=72,
        high_speed_cornering=78,
    )
    power_car = CarPerformanceProfile(
        overall_performance=82,
        low_speed_cornering=72,
        traction=74,
        straight_line_speed=96,
        high_speed_cornering=88,
    )

    assert track_car_fit(street_car, tracks["monaco"]) > track_car_fit(power_car, tracks["monaco"])
    assert track_car_fit(power_car, tracks["monza"]) > track_car_fit(street_car, tracks["monza"])


def test_upgrades_change_car_stats_and_create_correlation_report(tmp_path):
    manager = SaveManager(tmp_path)
    save = manager.create()
    team = next(team for team in save.teams if team.series == "F1")
    project = UpgradeProject(
        id="forced_floor",
        name="Floor major package",
        department="floor",
        upgrade_type="major",
        expected_gain={"aero_efficiency": 3, "high_speed_cornering": 2},
        risk=0,
        status="in_progress",
        delivery_round=1,
    )
    state = save.team_development[team.id].model_copy(update={"active_projects": [project]})
    save = save.model_copy(update={"team_development": {**save.team_development, team.id: state}})
    before = team.effective_car_profile().aero_efficiency

    updated, reports, _ = apply_due_upgrades(save, 1, "test_round")
    after = next(item for item in updated.teams if item.id == team.id).effective_car_profile().aero_efficiency

    assert after > before
    assert reports
    assert reports[0].correlation_quality in {"ahead", "on_target"}


def test_regulation_change_reshuffles_f1_grid(tmp_path):
    manager = SaveManager(tmp_path)
    save = manager.create().model_copy(update={"season": 2027})
    before = {team.id: team.effective_car_profile().overall_performance for team in save.teams if team.series == "F1"}
    first_team_id = next(iter(before))
    save = save.model_copy(
        update={
            "team_development": {
                **save.team_development,
                first_team_id: TeamDevelopmentState(team_id=first_team_id, research_points=24),
            }
        }
    )

    updated, news = offseason_car_evolution(save)
    after = {team.id: team.effective_car_profile().overall_performance for team in updated.teams if team.series == "F1"}
    deltas = [after[team_id] - before[team_id] for team_id in before]

    assert any(abs(delta) >= 4 for delta in deltas)
    assert any(item.importance == 5 for item in news)
    assert after[first_team_id] >= before[first_team_id] - 2


def test_new_saves_schedule_two_to_three_upgrades_per_team(tmp_path):
    save = SaveManager(tmp_path).create()
    for team in save.teams:
        project_count = len(save.team_development[team.id].active_projects)
        assert 2 <= project_count <= 3
        assert team.car_state is not None
