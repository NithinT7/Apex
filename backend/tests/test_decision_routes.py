"""Tests for interactive race decision routes."""

from fastapi.testclient import TestClient

from app.api import career_routes, decision_routes, weekend_routes
from app.main import app
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

    assert body["round_id"] == "f2_2026_round_01"
    assert "practice" in body
    assert "qualifying" in body
    assert "sprint_grid" in body
    assert "feature_grid" in body
    assert len(body["qualifying"]["classification"]) == 22
    assert len(body["sprint_grid"]) == 22
    assert len(body["feature_grid"]) == 22


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
    assert body["totalLaps"] == 12
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


def test_simulate_to_decision_advances_race(tmp_path) -> None:
    """Test that simulate_to_decision advances the race until a decision or completion."""
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

    # Should either have a pending decision or be complete (camelCase)
    assert body["currentLap"] > 0 or body["isComplete"] or body["pendingDecision"] is not None
    assert len(body["lapSnapshots"]) > 0


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
    assert body["totalLaps"] == 12
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
    assert prep["round_id"] == "f2_2026_round_01"

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
