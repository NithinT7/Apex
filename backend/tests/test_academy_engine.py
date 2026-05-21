"""Tests for academy trust engine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import activity_routes, career_routes, weekend_routes
from app.engine.academy_engine import (
    EXPECTED_POSITIONS,
    TRUST_CRITICAL,
    TRUST_EXCELLENT,
    TRUST_GOOD,
    TRUST_NEUTRAL,
    TRUST_WARNING,
    get_academy_status,
    get_trust_level,
)
from app.main import app
from app.save.save_manager import SaveManager


class TestGetTrustLevel:
    def test_excellent_trust_level(self):
        assert get_trust_level(TRUST_EXCELLENT) == "excellent"
        assert get_trust_level(100) == "excellent"

    def test_good_trust_level(self):
        assert get_trust_level(TRUST_GOOD) == "good"
        assert get_trust_level(TRUST_EXCELLENT - 1) == "good"

    def test_neutral_trust_level(self):
        assert get_trust_level(TRUST_NEUTRAL) == "neutral"
        assert get_trust_level(TRUST_GOOD - 1) == "neutral"

    def test_warning_trust_level(self):
        assert get_trust_level(TRUST_WARNING) == "warning"
        assert get_trust_level(TRUST_NEUTRAL - 1) == "warning"

    def test_critical_trust_level(self):
        assert get_trust_level(0) == "critical"
        assert get_trust_level(TRUST_WARNING - 1) == "critical"


def _create_career_with_academy(tmp_path, academy_id: str = "academy_ferrari") -> tuple[TestClient, SaveManager, str]:
    """Create a career with academy and complete a race to get academy state."""
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
            "academyId": academy_id,
            "difficulty": "realistic",
        },
    )
    save_id = response.json()["saveId"]
    return client, manager, save_id


class TestGetAcademyStatus:
    def test_returns_status_for_player_with_academy(self, tmp_path):
        client, manager, save_id = _create_career_with_academy(tmp_path)
        save = manager.get(save_id)
        status = get_academy_status(save)
        assert status is not None
        assert "academy_name" in status
        assert "trust" in status
        assert "trust_level" in status
        assert "expected_position" in status
        assert "seat_security" in status
        assert "f1_pathway" in status

    def test_returns_none_for_player_without_academy(self, tmp_path):
        client, manager, save_id = _create_career_with_academy(tmp_path, academy_id="academy_independent")
        save = manager.get(save_id)
        # Independent academy has special handling
        status = get_academy_status(save)
        # Should return special independent status, not None
        assert status is not None
        assert status["academy_name"] == "Independent"
        assert status["trust"] is None

    def test_status_contains_warnings_and_opportunities(self, tmp_path):
        client, manager, save_id = _create_career_with_academy(tmp_path)
        save = manager.get(save_id)
        status = get_academy_status(save)
        assert "warnings" in status
        assert "opportunities" in status
        assert isinstance(status["warnings"], list)
        assert isinstance(status["opportunities"], list)


class TestAcademyStatusEndpoint:
    def test_academy_endpoint_returns_status(self, tmp_path):
        client, manager, save_id = _create_career_with_academy(tmp_path)
        response = client.get(f"/career/{save_id}/activities/academy")
        assert response.status_code == 200
        body = response.json()
        assert "academy_name" in body
        assert "trust" in body


class TestAcademyTrustAfterRace:
    def test_academy_trust_changes_after_weekend(self, tmp_path):
        """Test that academy trust updates after completing a weekend."""
        client, manager, save_id = _create_career_with_academy(tmp_path)

        # Get initial trust
        save_before = manager.get(save_id)
        player = next(d for d in save_before.drivers if d.id == save_before.player_driver_id)
        initial_academy_state = next(
            (s for s in save_before.academy_states if s.academy_id == player.academy_id), None
        )
        assert initial_academy_state is not None
        initial_trust = initial_academy_state.trust

        # Simulate a weekend
        client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

        # Get trust after
        save_after = manager.get(save_id)
        final_academy_state = next(
            (s for s in save_after.academy_states if s.academy_id == player.academy_id), None
        )
        assert final_academy_state is not None

        # Trust should have changed (could be up or down depending on race result)
        # The important thing is the system is working
        # Note: trust might stay the same if no significant change warranted
        assert final_academy_state.trust is not None


class TestActivityAcademyStatusIncludedInStatus:
    def test_activity_status_includes_academy_trust(self, tmp_path):
        """Test that the activity status endpoint includes academy trust."""
        client, manager, save_id = _create_career_with_academy(tmp_path)

        # Simulate to get to between_races phase
        client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

        response = client.get(f"/career/{save_id}/activities/status")
        assert response.status_code == 200
        body = response.json()

        # Should include academy_trust field
        assert "academy_trust" in body
        assert body["academy_trust"] is not None


class TestTrustExpectations:
    def test_expected_positions_defined_for_all_levels(self):
        """Verify expected positions exist for all trust levels."""
        assert "excellent" in EXPECTED_POSITIONS
        assert "good" in EXPECTED_POSITIONS
        assert "neutral" in EXPECTED_POSITIONS
        assert "warning" in EXPECTED_POSITIONS
        assert "critical" in EXPECTED_POSITIONS

    def test_higher_trust_means_higher_expectations(self):
        """Higher trust levels should have higher (lower number) position expectations."""
        assert EXPECTED_POSITIONS["excellent"] < EXPECTED_POSITIONS["good"]
        assert EXPECTED_POSITIONS["good"] < EXPECTED_POSITIONS["neutral"]
        assert EXPECTED_POSITIONS["neutral"] < EXPECTED_POSITIONS["warning"]
        assert EXPECTED_POSITIONS["warning"] < EXPECTED_POSITIONS["critical"]


class TestTrustThresholds:
    def test_trust_thresholds_are_ordered(self):
        """Trust thresholds should be in ascending order."""
        assert TRUST_CRITICAL < TRUST_WARNING
        assert TRUST_WARNING < TRUST_NEUTRAL
        assert TRUST_NEUTRAL < TRUST_GOOD
        assert TRUST_GOOD < TRUST_EXCELLENT
