"""Tests for between-race activity routes."""

from fastapi.testclient import TestClient

from app.api import activity_routes, career_routes, weekend_routes
from app.main import app
from app.save.save_manager import SaveManager


def _create_career_and_complete_race(client: TestClient, manager: SaveManager) -> str:
    """Create a career and complete a race to get to between_races phase."""
    # Create career
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
    save_id = response.json()["saveId"]

    # Simulate a weekend to get to between_races phase
    client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

    return save_id


def test_get_activities_requires_between_races_phase(tmp_path) -> None:
    """Test that activities are only available in between_races phase."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    # Create career (starts in race_week phase)
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
    save_id = response.json()["saveId"]

    # Try to get activities in race_week phase
    response = client.get(f"/career/{save_id}/activities")
    assert response.status_code == 400
    assert "between_races" in response.json()["detail"].lower()


def test_get_activities_returns_list(tmp_path) -> None:
    """Test that available activities are returned."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    response = client.get(f"/career/{save_id}/activities")
    assert response.status_code == 200
    body = response.json()

    assert "activities" in body
    assert "daysUntilNextRace" in body
    assert len(body["activities"]) > 0
    # Check activity structure
    activity = body["activities"][0]
    assert "id" in activity
    assert "name" in activity
    assert "description" in activity
    assert "baseEffects" in activity


def test_perform_activity_updates_driver_stats(tmp_path) -> None:
    """Test that performing an activity updates driver stats."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    # Get initial status
    status_before = client.get(f"/career/{save_id}/activities/status").json()

    # Perform simulator activity (should increase fatigue and form)
    response = client.post(f"/career/{save_id}/activities/simulator_basic")
    assert response.status_code == 200
    outcome = response.json()

    assert outcome["activityId"] == "simulator_basic"
    assert outcome["activityName"] == "Simulator Session"
    assert "narrative" in outcome
    assert "effectsApplied" in outcome
    assert outcome["effectsApplied"]["fatigue"] > 0  # Simulator increases fatigue
    assert outcome["effectsApplied"]["form"] > 0  # Simulator increases form

    # Check status after
    status_after = client.get(f"/career/{save_id}/activities/status").json()
    assert status_after["fatigue"] > status_before["fatigue"]
    assert status_after["form"] > status_before["form"]


def test_perform_activity_advances_date(tmp_path) -> None:
    """Test that performing an activity advances the game date."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    # Get available activities
    activities_before = client.get(f"/career/{save_id}/activities").json()
    days_before = activities_before["daysUntilNextRace"]

    # Perform an activity that takes 1 day
    client.post(f"/career/{save_id}/activities/rest")

    # Check days remaining
    activities_after = client.get(f"/career/{save_id}/activities").json()
    days_after = activities_after["daysUntilNextRace"]

    assert days_after == days_before - 1


def test_skip_to_race_week_transitions_phase(tmp_path) -> None:
    """Test that skipping to race week transitions the phase."""
    from app.api import save_routes

    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    save_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    # Verify we're in between_races via status endpoint
    status = client.get(f"/career/{save_id}/activities/status").json()
    assert status["phase"] == "between_races"

    # Skip to race week
    response = client.post(f"/career/{save_id}/activities/skip")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.json()}"
    body = response.json()

    assert body["phase"] == "race_week"


def test_development_points_can_be_spent_between_races(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    weekend_routes.manager = manager
    activity_routes.manager = manager
    client = TestClient(app)

    save = client.post(
        "/career/new",
        json={
            "name": "Dev Driver",
            "nationality": "British",
            "age": 18,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    ).json()

    raced = client.post(f"/career/{save['saveId']}/weekend/next/simulate").json()
    assert raced["development"]["availablePoints"] >= 1

    status = client.get(f"/career/{save['saveId']}/activities/development")
    assert status.status_code == 200
    body = status.json()
    assert body["availablePoints"] == raced["development"]["availablePoints"]
    assert any(skill["id"] == "starts_1" for skill in body["skills"])
    assert all("maxRank" in skill for skill in body["skills"])

    before_starts = next(d for d in raced["drivers"] if d["id"] == "player_driver")["attributes"]["starts"]
    spend = client.post(f"/career/{save['saveId']}/activities/development/starts_1")
    assert spend.status_code == 200
    after = spend.json()
    after_starts = next(d for d in after["drivers"] if d["id"] == "player_driver")["attributes"]["starts"]
    assert after_starts == before_starts + 1
    assert after["development"]["spentPoints"]["starts_1"] == 1


def test_get_player_status_returns_stats(tmp_path) -> None:
    """Test that player status endpoint returns driver stats."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    response = client.get(f"/career/{save_id}/activities/status")
    assert response.status_code == 200
    body = response.json()

    # Status endpoint returns snake_case (not a Pydantic model response)
    assert "fatigue" in body
    assert "morale" in body
    assert "form" in body
    assert "reputation" in body
    assert "days_until_race" in body
    assert "phase" in body
    assert body["phase"] == "between_races"


def test_activity_with_risk_has_risk_chance(tmp_path) -> None:
    """Test that activities with risk chance have the proper risk_chance field."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    # Get available activities
    response = client.get(f"/career/{save_id}/activities")
    assert response.status_code == 200
    activities = response.json()["activities"]

    # Find media_interview and verify it has a risk chance
    media_interview = next((a for a in activities if a["id"] == "media_interview"), None)
    assert media_interview is not None
    assert media_interview["riskChance"] > 0  # Should have a risk chance

    # Perform the activity - just verify it works
    response = client.post(f"/career/{save_id}/activities/media_interview")
    assert response.status_code == 200
    outcome = response.json()
    # The outcome can be success or failure, both are valid
    assert "success" in outcome
    assert "narrative" in outcome


def test_activity_requirements_filter_options(tmp_path) -> None:
    """Test that activities with unmet requirements are filtered out."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    # Get player status
    status = client.get(f"/career/{save_id}/activities/status").json()

    # Get available activities
    activities = client.get(f"/career/{save_id}/activities").json()
    activity_ids = [a["id"] for a in activities["activities"]]

    # If fatigue is high, intensive simulator should not be available
    if status["fatigue"] > 50:
        assert "simulator_intensive" not in activity_ids


def test_cannot_perform_unavailable_activity(tmp_path) -> None:
    """Test that unavailable activities cannot be performed."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

    save_id = _create_career_and_complete_race(client, manager)

    # Try to perform a non-existent activity
    response = client.post(f"/career/{save_id}/activities/fake_activity")
    assert response.status_code == 400
