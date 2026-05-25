from __future__ import annotations

from app.data.loaders import get_tracks
from app.engine.car_performance_engine import (
    car_tier,
    performance_composite,
    race_car_score,
    track_car_fit,
    track_demand_profile,
)
from app.engine.weekend_engine import simulate_weekend
from app.models.car import CarPerformanceProfile
from app.models.race import WeatherState
from app.models.team import Team
from app.save.save_manager import SaveManager


DRY_WEATHER = WeatherState(condition="dry", air_temp=24, track_temp=32, rain_intensity=0, track_grip=78)


def _legacy_team(team_id: str, series: str, performance: int, driver_support: int = 78) -> Team:
    return Team(
        id=team_id,
        name=team_id,
        series=series,  # type: ignore[arg-type]
        country="Test",
        car_performance=performance,
        reliability=driver_support,
        strategy=driver_support,
        development_rate=driver_support,
        financial_health=driver_support,
    )


def test_legacy_team_derives_full_car_profile_with_financial_health():
    strong_budget = _legacy_team("funded", "F1", 80, driver_support=88).effective_car_profile()
    weak_budget = _legacy_team("lean", "F1", 80, driver_support=68).model_copy(update={"financial_health": 55}).effective_car_profile()

    assert strong_budget.overall_performance == 80
    assert strong_budget.aero_efficiency > weak_budget.aero_efficiency
    assert strong_budget.upgrade_potential > weak_budget.upgrade_potential


def test_track_demand_exposes_requested_tire_deg_alias():
    monaco = next(track for track in get_tracks() if track.id == "monaco")
    demand = track_demand_profile(monaco).model_dump(by_alias=True)

    assert "tireDegImportance" in demand
    assert "tireDegradationImportance" not in demand
    assert demand["lowSpeedImportance"] > demand["straightLineImportance"]


def test_f1_top_cars_usually_beat_backmarkers_across_calendar():
    top_team = _legacy_team("front_runner", "F1", 91, 88)
    backmarker = _legacy_team("backmarker", "F1", 67, 72)
    tracks = get_tracks()[:24]

    top_wins = sum(
        race_car_score(top_team, track, DRY_WEATHER) > race_car_score(backmarker, track, DRY_WEATHER)
        for track in tracks
    )

    assert top_wins >= 22
    assert car_tier(top_team.effective_car_profile()) == "Front Runner"
    assert car_tier(backmarker.effective_car_profile()) == "Backmarker"


def test_f2_strong_driver_can_more_often_overcome_car_gap_than_f1_driver():
    f1_gap = performance_composite(series="F1", car_score=68, driver_score=94, setup_score=82, context_score=82) - performance_composite(
        series="F1", car_score=84, driver_score=78, setup_score=78, context_score=78
    )
    f2_gap = performance_composite(series="F2", car_score=68, driver_score=94, setup_score=82, context_score=82) - performance_composite(
        series="F2", car_score=84, driver_score=78, setup_score=78, context_score=78
    )

    assert f1_gap < 0
    assert f2_gap > f1_gap
    assert f2_gap >= 0


def test_track_fit_changes_expected_team_performance():
    tracks = {track.id: track for track in get_tracks()}
    monaco_car = CarPerformanceProfile(
        overall_performance=82,
        low_speed_cornering=95,
        traction=94,
        tire_warmup=91,
        setup_window=90,
        straight_line_speed=70,
    )
    monza_car = CarPerformanceProfile(
        overall_performance=82,
        straight_line_speed=96,
        aero_efficiency=90,
        high_speed_cornering=88,
        low_speed_cornering=72,
        traction=74,
    )

    assert track_car_fit(monaco_car, tracks["monaco"]) > track_car_fit(monza_car, tracks["monaco"])
    assert track_car_fit(monza_car, tracks["monza"]) > track_car_fit(monaco_car, tracks["monza"])


def test_weekend_simulation_is_deterministic_with_same_seed(tmp_path):
    save = SaveManager(tmp_path).create()
    first = simulate_weekend(save, "f2_2026_round_01").model_dump()
    second = simulate_weekend(save, "f2_2026_round_01").model_dump()

    assert first == second
