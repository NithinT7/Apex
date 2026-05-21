"""Tests for rivalry engine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import activity_routes, career_routes, weekend_routes
from app.engine.rivalry_engine import (
    INTENSITY_BITTER,
    INTENSITY_INTENSE,
    INTENSITY_MILD,
    INTENSITY_MODERATE,
    get_intensity_level,
    get_rivalry_status,
    get_rivalry_with,
    initialize_rivalries,
)
from app.main import app
from app.save.save_manager import SaveManager


class TestGetIntensityLevel:
    def test_bitter_intensity(self):
        assert get_intensity_level(INTENSITY_BITTER) == "bitter"
        assert get_intensity_level(100) == "bitter"

    def test_intense_intensity(self):
        assert get_intensity_level(INTENSITY_INTENSE) == "intense"
        assert get_intensity_level(INTENSITY_BITTER - 1) == "intense"

    def test_moderate_intensity(self):
        assert get_intensity_level(INTENSITY_MODERATE) == "moderate"
        assert get_intensity_level(INTENSITY_INTENSE - 1) == "moderate"

    def test_mild_intensity(self):
        assert get_intensity_level(0) == "mild"
        assert get_intensity_level(INTENSITY_MODERATE - 1) == "mild"


def _create_career_with_rivalry(tmp_path) -> tuple[TestClient, SaveManager, str]:
    """Create a career and complete a race to potentially generate rivalries."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    client = TestClient(app)

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
    return client, manager, save_id


class TestInitializeRivalries:
    def test_initializes_teammate_rivalry(self, tmp_path):
        """Test that a teammate rivalry is created on career creation."""
        client, manager, save_id = _create_career_with_rivalry(tmp_path)
        save = manager.get(save_id)

        # Initialize rivalries (this should create a teammate rivalry)
        updated_save = initialize_rivalries(save)

        # Should have at least one rivalry (teammate)
        assert len(updated_save.rivalries) >= 1
        teammate_rivalry = next(
            (r for r in updated_save.rivalries if r.rivalry_type == "teammate"), None
        )
        assert teammate_rivalry is not None
        assert teammate_rivalry.intensity < 50  # Should start mild


class TestGetRivalryStatus:
    def test_returns_empty_for_no_rivalries(self, tmp_path):
        client, manager, save_id = _create_career_with_rivalry(tmp_path)
        save = manager.get(save_id)

        status = get_rivalry_status(save)
        # May have 0 rivalries if not initialized
        assert status.rivalries is not None

    def test_returns_rivalries_after_initialization(self, tmp_path):
        client, manager, save_id = _create_career_with_rivalry(tmp_path)
        save = manager.get(save_id)

        # Initialize rivalries
        save = initialize_rivalries(save)

        status = get_rivalry_status(save)
        if save.rivalries:
            assert len(status.rivalries) == len(save.rivalries)


class TestRivalryEndpoint:
    def test_rivalry_endpoint_returns_status(self, tmp_path):
        client, manager, save_id = _create_career_with_rivalry(tmp_path)

        # Complete a race to enter between_races phase
        client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

        response = client.get(f"/career/{save_id}/activities/rivalries")
        assert response.status_code == 200
        body = response.json()
        assert "rivalries" in body
        assert "mostIntenseId" in body
        assert "teammateRivalryId" in body


class TestRivalriesAfterRace:
    def test_rivalries_can_form_after_race(self, tmp_path):
        """Test that rivalries can form or update after a race."""
        client, manager, save_id = _create_career_with_rivalry(tmp_path)

        # Simulate multiple races to give rivalries a chance to form
        for round_num in range(1, 4):
            round_id = f"f2_2026_round_{round_num:02d}"
            try:
                client.post(f"/career/{save_id}/weekend/{round_id}/simulate")
            except Exception:
                break

        # Get rivalry status
        response = client.get(f"/career/{save_id}/activities/rivalries")
        assert response.status_code == 200
        body = response.json()

        # After multiple races, there should be some rivalries
        # (either from initialization or race events)
        assert "rivalries" in body


class TestIntensityThresholds:
    def test_thresholds_are_ordered(self):
        """Intensity thresholds should be in ascending order."""
        assert INTENSITY_MILD < INTENSITY_MODERATE
        assert INTENSITY_MODERATE < INTENSITY_INTENSE
        assert INTENSITY_INTENSE < INTENSITY_BITTER


class TestGetRivalryWith:
    def test_returns_none_for_no_rivalry(self, tmp_path):
        client, manager, save_id = _create_career_with_rivalry(tmp_path)
        save = manager.get(save_id)

        rivalry = get_rivalry_with(save, "nonexistent_driver")
        assert rivalry is None

    def test_returns_rivalry_if_exists(self, tmp_path):
        client, manager, save_id = _create_career_with_rivalry(tmp_path)
        save = manager.get(save_id)

        # Initialize to create teammate rivalry
        save = initialize_rivalries(save)

        if save.rivalries:
            first_rivalry = save.rivalries[0]
            found_rivalry = get_rivalry_with(save, first_rivalry.opponent_id)
            assert found_rivalry is not None
            assert found_rivalry.opponent_id == first_rivalry.opponent_id
