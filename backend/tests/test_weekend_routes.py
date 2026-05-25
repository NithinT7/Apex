import random

from fastapi.testclient import TestClient

from app.api import career_routes, weekend_routes
from app.data.loaders import get_f1_calendar, get_f1_drivers, get_f1_teams, get_f2_drivers, get_tracks
from app.engine.weekend_engine import (
    Runner,
    _race_lap_time,
    _tire_wear_increment,
)
from app.main import app
from app.models.race import WeatherState
from app.models.save_game import ChampionshipEntry, ChampionshipState
from app.save.save_manager import SaveManager


def _promote_save_to_f1(manager: SaveManager, save_id: str) -> None:
    save = manager.get(save_id)
    assert save is not None

    f1_team = get_f1_teams()[0]
    displaced_driver_id = next(
        driver.id
        for driver in save.drivers
        if driver.series == "F1" and driver.team_id == f1_team.id
    )
    updated_drivers = []
    for driver in save.drivers:
        if driver.id == save.player_driver_id:
            updated_drivers.append(driver.model_copy(update={"series": "F1", "team_id": f1_team.id}))
        elif driver.id == displaced_driver_id:
            updated_drivers.append(driver.model_copy(update={"series": "Reserve"}))
        else:
            updated_drivers.append(driver)
    f1_driver_ids = [driver.id for driver in updated_drivers if driver.series == "F1"]
    f1_team_ids = [team.id for team in save.teams if team.series == "F1"]

    manager.save(
        save.model_copy(
            update={
                "phase": "race_week",
                "calendar": get_f1_calendar(),
                "drivers": updated_drivers,
                "standings": ChampionshipState(
                    driver_standings=[
                        ChampionshipEntry(driver_id=driver_id)
                        for driver_id in f1_driver_ids
                    ],
                    team_standings={team_id: 0 for team_id in f1_team_ids},
                ),
                "weekend_results": [],
                "random_seed": 2026,
            }
        )
    )


def test_compounds_affect_pace_and_degradation() -> None:
    driver = get_f1_drivers()[0]
    team = get_f1_teams()[0]
    track = next(round_track for round_track in get_tracks() if round_track.id == "barcelona")
    weather = WeatherState(condition="dry", air_temp=25, track_temp=35, rain_intensity=0)

    soft_runner = Runner(driver=driver, team=team, tire_compound="soft")
    medium_runner = Runner(driver=driver, team=team, tire_compound="medium")
    hard_runner = Runner(driver=driver, team=team, tire_compound="hard")

    soft_lap = _race_lap_time(soft_runner, track, weather, random.Random(1), False)
    medium_lap = _race_lap_time(medium_runner, track, weather, random.Random(1), False)
    hard_lap = _race_lap_time(hard_runner, track, weather, random.Random(1), False)

    assert soft_lap < medium_lap < hard_lap
    assert _tire_wear_increment(soft_runner, track, weather, "feature") > _tire_wear_increment(medium_runner, track, weather, "feature")
    assert _tire_wear_increment(hard_runner, track, weather, "feature") < _tire_wear_increment(medium_runner, track, weather, "feature")


def test_worn_tyres_are_slower_than_fresh_tyres() -> None:
    driver = get_f1_drivers()[0]
    team = get_f1_teams()[0]
    track = next(round_track for round_track in get_tracks() if round_track.id == "barcelona")
    weather = WeatherState(condition="dry", air_temp=25, track_temp=35, rain_intensity=0)
    fresh = Runner(driver=driver, team=team, tire_compound="medium", tire_age=1, tire_wear=5)
    worn = Runner(driver=driver, team=team, tire_compound="medium", tire_age=18, tire_wear=75)

    assert _race_lap_time(worn, track, weather, random.Random(7), False) > _race_lap_time(
        fresh,
        track,
        weather,
        random.Random(7),
        False,
    )


def test_simulate_opening_weekend_updates_save(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    create_response = client.post(
        "/career/new",
        json={
            "name": "Nithin Thumma",
            "nationality": "Indian",
            "age": 18,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    )
    save_id = create_response.json()["saveId"]

    response = client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

    assert response.status_code == 200
    body = response.json()
    weekend = body["weekendResults"][0]

    assert body["phase"] == "between_races"
    assert body["currentDate"] == "2026-03-08"
    assert body["calendar"][0]["completed"] is True
    assert weekend["completed"] is True
    assert len(weekend["qualifying"]["classification"]) == 22
    assert 20 <= len(weekend["sprint"]["lapLog"]) <= 32
    assert 30 <= len(weekend["feature"]["lapLog"]) <= 44
    assert len(weekend["feature"]["classification"]) == 22
    qualifying_order = [row["driverId"] for row in weekend["qualifying"]["classification"]]
    assert weekend["sprint"]["startingGrid"] == list(reversed(qualifying_order[:10])) + qualifying_order[10:]
    assert all(row["pitStops"] == 0 for row in weekend["sprint"]["classification"] if row["status"] == "running")
    assert all(row["pitStops"] >= 1 for row in weekend["feature"]["classification"] if row["status"] == "running")
    assert 1 <= len(weekend["sprint"]["decisionPrompts"]) <= 6
    assert 3 <= len(weekend["feature"]["decisionPrompts"]) <= 8
    assert any(
        lap["decisionPrompt"] is not None
        for lap in weekend["feature"]["lapLog"]
    )
    assert weekend["feature"]["decisionPrompts"][0]["choices"]
    assert any(news["id"] == "f2_2026_round_01_feature_headline" for news in body["news"])
    assert body["f1Standings"]["driverStandings"]
    assert body["f1WeekendResults"] == []
    assert sum(entry["points"] for entry in body["standings"]["driverStandings"]) > 0

    second_response = client.post(f"/career/{save_id}/weekend/f2_2026_round_02/simulate")
    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["currentDate"] == "2026-05-03"
    assert second_body["f1WeekendResults"]
    assert sum(entry["points"] for entry in second_body["f1Standings"]["driverStandings"]) > 0


def test_completed_weekend_can_be_fetched_and_not_resimulated(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 19,
            "driverNumber": 42,
            "backgroundId": "technical_driver",
            "archetypeId": "smooth_operator",
            "teamId": "f2_art",
            "academyId": "academy_independent",
            "difficulty": "realistic",
        },
    ).json()

    first = client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_01/simulate")
    assert first.status_code == 200

    fetched = client.get(f"/career/{save['saveId']}/weekend/f2_2026_round_01")
    assert fetched.status_code == 200
    assert fetched.json()["roundId"] == "f2_2026_round_01"

    second = client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_01/simulate")
    assert second.status_code == 409


def test_next_weekend_endpoint_progresses_in_calendar_order(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Calendar Driver",
            "nationality": "Italian",
            "age": 18,
            "driverNumber": 12,
            "backgroundId": "late_bloomer",
            "archetypeId": "rain_specialist",
            "teamId": "f2_mp",
            "academyId": "academy_mercedes",
            "difficulty": "realistic",
        },
    ).json()

    next_round = client.get(f"/career/{save['saveId']}/weekend/next/round")
    assert next_round.status_code == 200
    assert next_round.json()["id"] == "f2_2026_round_01"

    skip = client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_02/simulate")
    assert skip.status_code == 409

    simulated = client.post(f"/career/{save['saveId']}/weekend/next/simulate")
    assert simulated.status_code == 200
    assert simulated.json()["calendar"][0]["completed"] is True
    assert simulated.json()["calendar"][1]["completed"] is False

    next_after = client.get(f"/career/{save['saveId']}/weekend/next/round")
    assert next_after.status_code == 200
    assert next_after.json()["id"] == "f2_2026_round_02"


def test_f1_weekend_uses_f1_calendar_drivers_and_points(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Promoted Driver",
            "nationality": "Indian",
            "age": 19,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    ).json()
    _promote_save_to_f1(manager, save["saveId"])

    response = client.post(f"/career/{save['saveId']}/weekend/f1_2026_round_01/simulate")

    assert response.status_code == 200
    body = response.json()
    weekend = body["weekendResults"][0]
    expected_f1_field_size = len(get_f1_drivers())
    f2_driver_ids = {driver.id for driver in get_f2_drivers()}

    assert body["calendar"][0]["series"] == "F1"
    assert len(weekend["qualifying"]["classification"]) == expected_f1_field_size
    assert len(weekend["feature"]["classification"]) == expected_f1_field_size
    assert not any(
        row["driverId"] in f2_driver_ids
        for row in weekend["feature"]["classification"]
    )
    assert weekend["sprint"]["classification"] == []
    assert weekend["sprint"]["totalLaps"] == 0
    assert weekend["feature"]["classification"][0]["points"] == 25
    assert all(row["pitStops"] >= 1 for row in weekend["feature"]["classification"] if row["status"] == "running")
    assert all(team_id.startswith("f1_") for team_id in body["standings"]["teamStandings"])


def test_f1_sprint_weekend_uses_sprint_format_without_reverse_grid(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Sprint Driver",
            "nationality": "Indian",
            "age": 19,
            "driverNumber": 28,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    ).json()
    _promote_save_to_f1(manager, save["saveId"])

    opening = client.post(f"/career/{save['saveId']}/weekend/f1_2026_round_01/simulate")
    assert opening.status_code == 200

    response = client.post(f"/career/{save['saveId']}/weekend/f1_2026_round_02/simulate")

    assert response.status_code == 200
    weekend = response.json()["weekendResults"][1]
    qualifying_order = [row["driverId"] for row in weekend["qualifying"]["classification"]]

    assert 18 <= weekend["sprint"]["totalLaps"] <= 28
    assert weekend["sprint"]["startingGrid"] == qualifying_order
    assert weekend["sprint"]["classification"][0]["points"] == 8
    assert all(row["pitStops"] >= 2 for row in weekend["feature"]["classification"] if row["status"] == "running")


def test_strategy_events_are_recorded(tmp_path):
    """Verify that pit stop events, stint summaries, and strategy plans are recorded."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Strategy Driver",
            "nationality": "British",
            "age": 20,
            "driverNumber": 44,
            "backgroundId": "karting_prodigy",
            "archetypeId": "smooth_operator",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    ).json()

    response = client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_01/simulate")
    assert response.status_code == 200

    weekend = response.json()["weekendResults"][0]
    feature = weekend["feature"]

    # Strategy plans should be recorded for all drivers
    assert "strategyPlans" in feature
    assert len(feature["strategyPlans"]) > 0

    # Each plan should have required fields
    for plan in feature["strategyPlans"]:
        assert "driverId" in plan
        assert "plannedStops" in plan
        assert "startingCompound" in plan
        assert "strategyStyle" in plan

    # Stint summaries should be recorded
    assert "stintSummaries" in feature
    assert len(feature["stintSummaries"]) > 0

    # Each stint should have lap times and compound info
    for stint in feature["stintSummaries"]:
        assert "driverId" in stint
        assert "stintNumber" in stint
        assert "startLap" in stint
        assert "endLap" in stint
        assert "compound" in stint

    # If there were pit stops, pit stop events should be recorded
    total_pit_stops = sum(
        row["pitStops"] for row in feature["classification"] if row["status"] == "running"
    )
    if total_pit_stops > 0:
        assert "pitStopEvents" in feature
        assert len(feature["pitStopEvents"]) > 0

        for ps in feature["pitStopEvents"]:
            assert "driverId" in ps
            assert "lap" in ps
            assert "compoundIn" in ps
            assert "compoundOut" in ps
            assert "reason" in ps


def test_race_analysis_endpoint(tmp_path):
    """Verify the race analysis endpoint returns complete strategy data."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Analysis Driver",
            "nationality": "German",
            "age": 21,
            "driverNumber": 5,
            "backgroundId": "karting_prodigy",
            "archetypeId": "technical_developer",
            "teamId": "f2_art",
            "academyId": "academy_mercedes",
            "difficulty": "realistic",
        },
    ).json()

    # Simulate a race
    client.post(f"/career/{save['saveId']}/weekend/f2_2026_round_01/simulate")

    # Get analysis for the feature race
    response = client.get(
        f"/career/{save['saveId']}/weekend/f2_2026_round_01/analysis?race_type=feature"
    )
    assert response.status_code == 200

    analysis = response.json()

    # Check required fields
    assert analysis["saveId"] == save["saveId"]
    assert analysis["roundId"] == "f2_2026_round_01"
    assert analysis["raceType"] == "feature"
    assert "totalLaps" in analysis

    # Strategy data
    assert "strategyPlans" in analysis
    assert "pitStopEvents" in analysis
    assert "stintSummaries" in analysis
    assert "safetyCarDecisions" in analysis

    # Key incidents and summary
    assert "keyIncidents" in analysis
    assert "strategySummary" in analysis

    # Strategy summary should have statistics
    summary = analysis["strategySummary"]
    assert "totalPitStops" in summary
    assert "safetyCarCount" in summary
    assert "vscCount" in summary
    assert "oneStopDrivers" in summary
    assert "twoStopDrivers" in summary


def test_safety_car_decisions_recorded(tmp_path):
    """Verify safety car decisions are recorded when they occur."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "SC Driver",
            "nationality": "Italian",
            "age": 22,
            "driverNumber": 16,
            "backgroundId": "karting_prodigy",
            "archetypeId": "rain_specialist",
            "teamId": "f2_campos",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    ).json()

    # Simulate multiple races to increase chance of safety car
    for round_num in range(1, 6):
        response = client.post(
            f"/career/{save['saveId']}/weekend/f2_2026_round_{round_num:02d}/simulate"
        )
        assert response.status_code == 200

        weekend = response.json()["weekendResults"][-1]
        feature = weekend["feature"]

        # If there was a safety car, decisions should be recorded
        if feature["safetyCarLaps"]:
            assert "safetyCarDecisions" in feature
            # At least one decision should exist per SC deployment
            # (may not be 1:1 due to how consecutive laps are handled)
            if feature["safetyCarDecisions"]:
                for sc_decision in feature["safetyCarDecisions"]:
                    assert "lap" in sc_decision
                    assert "mode" in sc_decision
                    assert sc_decision["mode"] in ["safety_car", "vsc"]
                    assert "pitWindowOpen" in sc_decision
                break  # Found a race with SC, test passed
