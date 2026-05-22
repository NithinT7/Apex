"""Tests for interactive race decision routes."""

from fastapi.testclient import TestClient

from app.api import career_routes, decision_routes, weekend_routes
from app.data.loaders import get_f1_calendar, get_f1_drivers, get_f1_teams, get_f2_drivers
from app.engine.decision_engine import _load_internal_state
from app.main import app
from app.models.save_game import ChampionshipEntry, ChampionshipState
from app.save.save_manager import SaveManager


def _create_career(client: TestClient) -> str:
    """Create a career and return the save ID."""
    response = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 18,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    )
    return response.json()["saveId"]


def _promote_save_to_f1(manager: SaveManager, save_id: str) -> None:
    """Move the player into an F1 seat and switch the active calendar."""
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
                "active_race": None,
            }
        )
    )


def test_prepare_weekend_returns_practice_and_qualifying(tmp_path) -> None:
    """Test that prepare_weekend returns practice and qualifying results."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")

    assert response.status_code == 200
    body = response.json()

    assert body["roundId"] == "f2_2026_round_01"
    assert "practice" in body
    assert "qualifying" in body
    assert "sprintGrid" in body
    assert "featureGrid" in body
    assert body["hasSprint"] is True
    assert len(body["qualifying"]["classification"]) == 22
    assert len(body["sprintGrid"]) == 22
    assert len(body["featureGrid"]) == 22
    qualifying_order = [row["driverId"] for row in body["qualifying"]["classification"]]
    assert body["sprintGrid"] == list(reversed(qualifying_order[:10])) + qualifying_order[10:]


def test_start_race_returns_active_race_state(tmp_path) -> None:
    """Test that starting a race returns an ActiveRaceState."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare weekend first
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")

    # Start sprint race
    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")

    assert response.status_code == 200
    body = response.json()

    # API uses camelCase aliases
    assert body["saveId"] == save_id
    assert body["roundId"] == "f2_2026_round_01"
    assert body["raceType"] == "sprint"
    assert body["currentLap"] == 0
    assert 20 <= body["totalLaps"] <= 32
    assert body["isComplete"] is False
    assert "lapSnapshots" in body
    assert "pendingDecision" in body


def test_start_race_requires_prepare(tmp_path) -> None:
    """Test that starting a race without preparing fails."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")

    assert response.status_code == 400
    assert "not prepared" in response.json()["detail"].lower()


def test_simulate_advances_one_lap(tmp_path) -> None:
    """Test that the interactive simulate endpoint advances a single lap."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare and start
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")
    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")

    # Simulate
    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/simulate")

    assert response.status_code == 200
    body = response.json()

    assert body["currentLap"] == 1
    assert len(body["lapSnapshots"]) == 1
    leader = body["lapSnapshots"][0]["runningOrder"][0]
    assert leader["currentLapTime"] is not None
    assert leader["bestLapTime"] is not None
    assert leader["previousLapTime"] is None


def test_player_push_decision_only_affects_next_lap(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")
    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")
    state = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/simulate").json()
    assert state["pendingDecision"] is not None

    decision_id = state["pendingDecision"]["prompt"]["id"]
    response = client.post(
        f"/career/{save_id}/race/f2_2026_round_01/sprint/decide",
        json={"decisionId": decision_id, "choiceIndex": 2},
    )
    assert response.status_code == 200
    save = manager.get(save_id)
    internal_state = _load_internal_state(save, "f2_2026_round_01", "sprint")
    player = next(runner for runner in internal_state.runners if runner.driver.id == save.player_driver_id)
    assert player.modifier_laps_remaining == 1

    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/simulate")
    internal_state = _load_internal_state(save, "f2_2026_round_01", "sprint")
    player = next(runner for runner in internal_state.runners if runner.driver.id == save.player_driver_id)
    assert player.modifier_laps_remaining == 0
    assert player.pace_modifier == 0


def test_submit_decision_clears_pending_decision(tmp_path) -> None:
    """Test that submitting a decision clears the pending decision."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare and start
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")
    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")

    # Simulate until we get a decision or complete (camelCase)
    sim_response = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/simulate")
    state = sim_response.json()

    # If there's a pending decision, submit it
    if state["pendingDecision"]:
        decision_id = state["pendingDecision"]["prompt"]["id"]
        response = client.post(
            f"/career/{save_id}/race/f2_2026_round_01/sprint/decide",
            json={"decisionId": decision_id, "choiceIndex": 0},
        )

        assert response.status_code == 200
        body = response.json()
        # After submission, the race should have progressed
        assert body["currentLap"] >= state["currentLap"]


def test_auto_complete_finishes_race(tmp_path) -> None:
    """Test that auto_complete finishes the race immediately."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare and start
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")
    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")

    # Auto-complete
    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/auto-complete")

    assert response.status_code == 200
    body = response.json()

    # RaceResult uses camelCase
    assert body["sessionType"] == "sprint"
    assert 20 <= body["totalLaps"] <= 32
    assert len(body["classification"]) == 22
    assert "lapLog" in body


def test_finalize_weekend_updates_standings(tmp_path) -> None:
    """Test that finalizing a weekend updates standings."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")

    # Start and auto-complete sprint
    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")
    sprint_result = client.post(
        f"/career/{save_id}/race/f2_2026_round_01/sprint/auto-complete"
    ).json()

    # Start and auto-complete feature
    client.post(f"/career/{save_id}/race/f2_2026_round_01/feature/start")
    feature_result = client.post(
        f"/career/{save_id}/race/f2_2026_round_01/feature/auto-complete"
    ).json()

    # Finalize
    response = client.post(
        f"/career/{save_id}/race/f2_2026_round_01/finalize",
        json={"sprint": sprint_result, "feature": feature_result},
    )

    assert response.status_code == 200
    body = response.json()

    # SaveGame response uses camelCase
    assert body["phase"] == "between_races"
    assert body["calendar"][0]["completed"] is True
    assert len(body["weekendResults"]) == 1
    assert sum(entry["points"] for entry in body["standings"]["driverStandings"]) > 0


def test_invalid_race_type_rejected(tmp_path) -> None:
    """Test that invalid race_type is rejected."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare
    client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")

    # Try to start with invalid race type
    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/invalid/start")

    assert response.status_code == 400
    assert "race_type" in response.json()["detail"].lower()


def test_prepare_already_completed_weekend_fails(tmp_path) -> None:
    """Test that preparing an already completed weekend fails."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # First, simulate the weekend the old way to complete it
    client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

    # Now try to prepare it for interactive mode - this round is now complete
    # so the next playable round is round 02
    response = client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare")

    # The response will be 409 because round 01 is completed and next is round 02
    assert response.status_code == 409


def test_full_interactive_race_flow(tmp_path) -> None:
    """Test complete interactive race flow with decisions."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)

    # Prepare weekend
    prep = client.post(f"/career/{save_id}/race/f2_2026_round_01/prepare").json()
    assert prep["roundId"] == "f2_2026_round_01"

    # Sprint race
    client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/start")

    # Loop: simulate -> decide (if needed) -> repeat until complete
    sprint_decisions = 0
    for _ in range(50):  # Safety limit
        state = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/simulate").json()

        if state["isComplete"]:
            break

        if state["pendingDecision"]:
            sprint_decisions += 1
            decision_id = state["pendingDecision"]["prompt"]["id"]
            client.post(
                f"/career/{save_id}/race/f2_2026_round_01/sprint/decide",
                json={"decisionId": decision_id, "choiceIndex": 1},  # Pick middle option
            )

    # Complete the sprint
    sprint_result = client.post(f"/career/{save_id}/race/f2_2026_round_01/sprint/complete").json()
    assert sprint_result["sessionType"] == "sprint"

    # Feature race
    client.post(f"/career/{save_id}/race/f2_2026_round_01/feature/start")

    feature_decisions = 0
    for _ in range(100):  # Safety limit
        state = client.post(f"/career/{save_id}/race/f2_2026_round_01/feature/simulate").json()

        if state["isComplete"]:
            break

        if state["pendingDecision"]:
            feature_decisions += 1
            decision_id = state["pendingDecision"]["prompt"]["id"]
            client.post(
                f"/career/{save_id}/race/f2_2026_round_01/feature/decide",
                json={"decisionId": decision_id, "choiceIndex": 0},  # Pick first option
            )

    # Complete the feature
    feature_result = client.post(f"/career/{save_id}/race/f2_2026_round_01/feature/complete").json()
    assert feature_result["sessionType"] == "feature"

    # Finalize weekend
    final = client.post(
        f"/career/{save_id}/race/f2_2026_round_01/finalize",
        json={"sprint": sprint_result, "feature": feature_result},
    ).json()

    assert final["calendar"][0]["completed"] is True
    assert len(final["weekendResults"]) == 1
    assert sprint_decisions >= 1 or feature_decisions >= 1  # Should have at least some decisions


def test_interactive_f1_weekend_uses_f1_field_and_points(tmp_path) -> None:
    """Interactive race endpoints should follow the active F1 calendar/field."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)
    _promote_save_to_f1(manager, save_id)

    prep = client.post(f"/career/{save_id}/race/f1_2026_round_01/prepare")
    assert prep.status_code == 200
    prep_body = prep.json()
    expected_f1_field_size = len(get_f1_drivers())
    f2_driver_ids = {driver.id for driver in get_f2_drivers()}

    assert len(prep_body["qualifying"]["classification"]) == expected_f1_field_size
    assert prep_body["hasSprint"] is False
    assert prep_body["sprintGrid"] == []

    sprint_start = client.post(f"/career/{save_id}/race/f1_2026_round_01/sprint/start")
    assert sprint_start.status_code == 400
    assert "does not have a sprint" in sprint_start.json()["detail"].lower()

    feature_start = client.post(f"/career/{save_id}/race/f1_2026_round_01/feature/start")
    assert feature_start.status_code == 200
    assert 45 <= feature_start.json()["totalLaps"] <= 78

    feature_result = client.post(
        f"/career/{save_id}/race/f1_2026_round_01/feature/auto-complete"
    )
    assert feature_result.status_code == 200
    feature_body = feature_result.json()

    assert feature_body["classification"][0]["points"] == 25
    assert len(feature_body["classification"]) == expected_f1_field_size
    assert not any(row["driverId"] in f2_driver_ids for row in feature_body["classification"])
    assert all(row["pitStops"] >= 1 for row in feature_body["classification"] if row["status"] == "running")

    track_id = prep_body["practice"]["trackId"]
    sprint_body = {
        "raceId": f"{track_id}_sprint",
        "sessionType": "sprint",
        "trackId": track_id,
        "totalLaps": 0,
        "startingGrid": [],
        "classification": [],
        "lapLog": [],
        "decisionPrompts": [],
        "safetyCarLaps": [],
        "dnfs": [],
    }

    final = client.post(
        f"/career/{save_id}/race/f1_2026_round_01/finalize",
        json={"sprint": sprint_body, "feature": feature_body},
    )
    assert final.status_code == 200
    final_body = final.json()
    assert final_body["calendar"][0]["series"] == "F1"
    assert final_body["calendar"][0]["completed"] is True
    assert all(team_id.startswith("f1_") for team_id in final_body["standings"]["teamStandings"])


def test_interactive_f1_sprint_round_uses_non_reversed_grid(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    decision_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career(client)
    _promote_save_to_f1(manager, save_id)
    save = manager.get(save_id)
    assert save is not None
    updated_calendar = [
        calendar_round.model_copy(update={"completed": calendar_round.id == "f1_2026_round_01"})
        for calendar_round in save.calendar
    ]
    manager.save(save.model_copy(update={"calendar": updated_calendar}))

    prep = client.post(f"/career/{save_id}/race/f1_2026_round_02/prepare")
    assert prep.status_code == 200
    prep_body = prep.json()
    qualifying_order = [row["driverId"] for row in prep_body["qualifying"]["classification"]]

    assert prep_body["hasSprint"] is True
    assert prep_body["sprintGrid"] == qualifying_order

    sprint_start = client.post(f"/career/{save_id}/race/f1_2026_round_02/sprint/start")
    assert sprint_start.status_code == 200
    assert 18 <= sprint_start.json()["totalLaps"] <= 28
