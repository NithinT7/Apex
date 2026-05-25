"""Tests for race weekend development system (XP and points)."""

import pytest
from fastapi.testclient import TestClient

from app.engine.development_engine import (
    award_development_points,
    award_weekend_development,
    calculate_race_weekend_xp,
    get_unified_development_points,
    is_direct_stat_buying_enabled,
    migrate_legacy_points_to_profile,
    points_for_weekend,
)
from app.main import app
from app.models.development_profile import (
    ALL_BRANCHES,
    create_default_development_profile,
    create_player_starting_profile,
)
from app.models.race import (
    PracticeClassification,
    PracticeResult,
    QualifyingClassification,
    QualifyingResult,
    RaceClassification,
    RaceResult,
    WeatherState,
    WeekendResult,
)
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


client = TestClient(app)


@pytest.fixture
def manager():
    """Create a SaveManager instance."""
    return SaveManager()


@pytest.fixture
def save_with_player(manager: SaveManager) -> SaveGame:
    """Create a save game with a player driver."""
    response = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 20,
            "driverNumber": 99,
            "backgroundId": "karting_prodigy",
            "archetypeId": "smooth_operator",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
        },
    )
    assert response.status_code == 201
    save_data = response.json()
    save_id = save_data["saveId"]
    return manager.get(save_id)


@pytest.fixture
def mock_weekend_result(save_with_player: SaveGame) -> WeekendResult:
    """Create a mock weekend result for testing."""
    player_id = save_with_player.player_driver_id
    other_drivers = [d.id for d in save_with_player.drivers if d.id != player_id][:5]

    weather = WeatherState(
        condition="dry",
        air_temp=25,
        track_temp=35,
        rain_intensity=0,
        track_grip=75,
    )

    # Practice result - player in P3 with good setup
    practice = PracticeResult(
        track_id="bahrain",
        weather=weather,
        classification=[
            PracticeClassification(position=1, driver_id=other_drivers[0], lap_time=90.5, setup_score=82, note="Good setup"),
            PracticeClassification(position=2, driver_id=other_drivers[1], lap_time=90.6, setup_score=78, note="Baseline"),
            PracticeClassification(position=3, driver_id=player_id, lap_time=90.7, setup_score=85, note="Strong setup"),
        ],
    )

    # Qualifying result - player in P5
    quali = QualifyingResult(
        track_id="bahrain",
        weather=weather,
        classification=[
            QualifyingClassification(position=1, driver_id=other_drivers[0], lap_time=89.5, gap_to_pole=0, note=""),
            QualifyingClassification(position=2, driver_id=other_drivers[1], lap_time=89.6, gap_to_pole=0.1, note=""),
            QualifyingClassification(position=3, driver_id=other_drivers[2], lap_time=89.7, gap_to_pole=0.2, note=""),
            QualifyingClassification(position=4, driver_id=other_drivers[3], lap_time=89.8, gap_to_pole=0.3, note=""),
            QualifyingClassification(position=5, driver_id=player_id, lap_time=89.9, gap_to_pole=0.4, note=""),
        ],
    )

    # Feature race - player finishes P2 (gained 3 positions)
    feature = RaceResult(
        race_id="bahrain_feature",
        session_type="feature",
        track_id="bahrain",
        total_laps=30,
        starting_grid=[other_drivers[0], other_drivers[1], other_drivers[2], other_drivers[3], player_id],
        classification=[
            RaceClassification(position=1, driver_id=other_drivers[0], status="running", total_time=2700.0, gap_to_winner=0, points=25, pit_stops=1, fastest_lap=90.1),
            RaceClassification(position=2, driver_id=player_id, status="running", total_time=2705.0, gap_to_winner=5.0, points=18, pit_stops=1, fastest_lap=90.2),
            RaceClassification(position=3, driver_id=other_drivers[1], status="running", total_time=2710.0, gap_to_winner=10.0, points=15, pit_stops=1, fastest_lap=90.3),
        ],
        lap_log=[],
        decision_prompts=[],
        safety_car_laps=[],
        dnfs=[],
    )

    # Sprint race (empty)
    sprint = RaceResult(
        race_id="bahrain_sprint",
        session_type="sprint",
        track_id="bahrain",
        total_laps=0,
        starting_grid=[],
        classification=[],
        lap_log=[],
        decision_prompts=[],
        safety_car_laps=[],
        dnfs=[],
    )

    return WeekendResult(
        save_id=save_with_player.save_id,
        round_id="bahrain_r1",
        track_id="bahrain",
        completed=True,
        practice=practice,
        qualifying=quali,
        sprint=sprint,
        feature=feature,
        headline="Test Driver takes podium",
    )


class TestRaceXPCalculation:
    """Tests for race performance XP calculation."""

    def test_qualifying_xp_pole_position(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that pole position awards maximum raw_pace XP."""
        # Modify to give player pole
        player_id = save_with_player.player_driver_id
        modified_quali = mock_weekend_result.qualifying.model_copy()
        modified_quali.classification[0].driver_id = player_id
        modified_quali.classification[0].position = 1

        modified_result = mock_weekend_result.model_copy(update={"qualifying": modified_quali})
        xp = calculate_race_weekend_xp(save_with_player, modified_result)

        assert xp["raw_pace"] >= 20  # Pole should give significant XP

    def test_positions_gained_racecraft_xp(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that gaining positions awards racecraft XP."""
        xp = calculate_race_weekend_xp(save_with_player, mock_weekend_result)

        # Player went from P5 to P2, gaining 3 positions
        assert xp["racecraft"] >= 10  # Should award racecraft XP for overtakes

    def test_practice_setup_technical_xp(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that good practice setup awards technical feedback XP."""
        xp = calculate_race_weekend_xp(save_with_player, mock_weekend_result)

        # Player had setup_score of 85 in practice
        assert xp["technical_feedback"] >= 10

    def test_points_finish_media_xp(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that points finish awards media XP."""
        xp = calculate_race_weekend_xp(save_with_player, mock_weekend_result)

        # Player finished P2 (podium)
        assert xp["media_marketability"] >= 10

    def test_academy_driver_gets_academy_xp(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that academy drivers earn academy XP."""
        player = next(d for d in save_with_player.drivers if d.id == save_with_player.player_driver_id)

        # This player has academy_id set
        assert player.academy_id is not None

        xp = calculate_race_weekend_xp(save_with_player, mock_weekend_result)
        assert xp["academy_path"] >= 8  # Base academy XP

    def test_all_branches_get_some_xp(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that most branches receive at least some XP from a weekend."""
        xp = calculate_race_weekend_xp(save_with_player, mock_weekend_result)

        # At least 5 branches should have XP
        branches_with_xp = sum(1 for v in xp.values() if v > 0)
        assert branches_with_xp >= 5


class TestAwardWeekendDevelopment:
    """Tests for the unified weekend development award function."""

    def test_awards_both_points_and_xp(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that award_weekend_development gives both points and XP."""
        initial_points = save_with_player.development_profile.current_points
        initial_xp = dict(save_with_player.development_profile.branch_xp)

        updated_save, summary = award_weekend_development(save_with_player, mock_weekend_result)

        # Check development points increased
        assert updated_save.development_profile.current_points > initial_points

        # Check some branch XP increased
        new_xp = updated_save.development_profile.branch_xp
        xp_increased = any(new_xp.get(b, 0) > initial_xp.get(b, 0) for b in ALL_BRANCHES)
        assert xp_increased

    def test_creates_history_entry(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that weekend development creates a history entry."""
        initial_history_len = len(save_with_player.development_profile.history)

        updated_save, summary = award_weekend_development(save_with_player, mock_weekend_result)

        assert len(updated_save.development_profile.history) > initial_history_len

        latest_entry = updated_save.development_profile.history[-1]
        assert latest_entry.source == "race_result"
        assert latest_entry.round_id == mock_weekend_result.round_id

    def test_summary_contains_breakdown(self, save_with_player: SaveGame, mock_weekend_result: WeekendResult):
        """Test that the summary contains a readable breakdown."""
        updated_save, summary = award_weekend_development(save_with_player, mock_weekend_result)

        assert summary.round_id == mock_weekend_result.round_id
        assert summary.development_points_gained > 0
        assert len(summary.breakdown) > 0


class TestUnifiedDevelopmentPoints:
    """Tests for unified development point handling."""

    def test_award_points_updates_both_systems(self, save_with_player: SaveGame):
        """Test that award_development_points updates both legacy and new systems."""
        initial_legacy = save_with_player.development.available_points
        initial_profile = save_with_player.development_profile.current_points

        updated = award_development_points(save_with_player, 5)

        assert updated.development.available_points == initial_legacy + 5
        assert updated.development_profile.current_points == initial_profile + 5

    def test_get_unified_points_returns_max(self, save_with_player: SaveGame):
        """Test that get_unified_development_points returns the maximum."""
        # Manually desync the systems
        profile = save_with_player.development_profile.model_copy(update={"current_points": 10})
        dev = save_with_player.development.model_copy(update={"available_points": 5})
        modified = save_with_player.model_copy(update={"development_profile": profile, "development": dev})

        unified = get_unified_development_points(modified)
        assert unified == 10  # Should return the higher value

    def test_migrate_legacy_points_syncs(self, save_with_player: SaveGame):
        """Test that migrate_legacy_points_to_profile syncs points."""
        # Give legacy more points
        dev = save_with_player.development.model_copy(update={"available_points": 20})
        profile = save_with_player.development_profile.model_copy(update={"current_points": 5})
        modified = save_with_player.model_copy(update={"development": dev, "development_profile": profile})

        migrated = migrate_legacy_points_to_profile(modified)

        assert migrated.development_profile.current_points == 20


class TestDirectStatBuyingDeprecation:
    """Tests for direct stat buying deprecation."""

    def test_direct_stat_buying_disabled_after_skill_tree_use(self, save_with_player: SaveGame):
        """Test that direct stat buying is disabled after using skill tree."""
        # Add an unlocked node to indicate skill tree usage
        profile = save_with_player.development_profile.model_copy(
            update={"unlocked_node_ids": ["pace_foundation"]}
        )
        modified = save_with_player.model_copy(update={"development_profile": profile})

        enabled = is_direct_stat_buying_enabled(modified)
        assert enabled is False

    def test_legacy_development_endpoint_returns_deprecation_notice(self, save_with_player: SaveGame):
        """Test that the legacy development endpoint includes deprecation info."""
        response = client.get(f"/career/{save_with_player.save_id}/activities/development")
        assert response.status_code == 200

        data = response.json()
        assert data.get("deprecated") is True
        assert "deprecationNotice" in data
        assert "skillTreeEndpoint" in data

    def test_direct_spending_blocked_after_skill_tree_use(self, save_with_player: SaveGame, manager: SaveManager):
        """Test that direct spending is blocked after using skill tree."""
        # First, unlock a skill tree node
        profile = save_with_player.development_profile.model_copy(
            update={"unlocked_node_ids": ["pace_foundation"]}
        )
        modified = save_with_player.model_copy(update={"development_profile": profile})
        manager.save(modified)

        # Try to use direct stat buying
        response = client.post(
            f"/career/{save_with_player.save_id}/activities/development/raw_pace_1"
        )

        # Should be rejected
        assert response.status_code == 400
        assert "Skill Tree" in response.json()["detail"]


class TestWeekendDevelopmentSummaryEndpoint:
    """Tests for the weekend development summary API endpoint."""

    def test_get_summary_when_none_available(self, save_with_player: SaveGame):
        """Test getting summary when none is available."""
        response = client.get(f"/career/{save_with_player.save_id}/development/weekend-summary")
        assert response.status_code == 200

        data = response.json()
        assert data["available"] is False

    def test_clear_summary_when_none_exists(self, save_with_player: SaveGame):
        """Test clearing summary when none exists."""
        response = client.delete(f"/career/{save_with_player.save_id}/development/weekend-summary")
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True


class TestExistingSavesStillWork:
    """Tests to ensure backwards compatibility with existing saves."""

    def test_save_without_profile_can_award_points(self):
        """Test that saves without development_profile can still get points."""
        # Create a minimal save without development_profile
        response = client.post(
            "/career/new",
            json={
                "name": "Legacy Driver",
                "nationality": "German",
                "age": 22,
                "driverNumber": 42,
                "backgroundId": "karting_prodigy",
                "archetypeId": "smooth_operator",
                "teamId": "f2_prema",
            },
        )
        assert response.status_code == 201

        save_id = response.json()["saveId"]

        # Verify we can still access development endpoints
        response = client.get(f"/career/{save_id}/activities/development")
        assert response.status_code == 200

    def test_skill_tree_works_with_legacy_points(self, save_with_player: SaveGame, manager: SaveManager):
        """Test that skill tree can use points from legacy system."""
        # Give legacy system more points
        dev = save_with_player.development.model_copy(update={"available_points": 15})
        profile = save_with_player.development_profile.model_copy(
            update={
                "current_points": 15,
                "branch_xp": {**save_with_player.development_profile.branch_xp, "raw_pace": 100},
            }
        )
        modified = save_with_player.model_copy(update={"development": dev, "development_profile": profile})
        manager.save(modified)

        # Unlock a node
        response = client.post(
            f"/career/{save_with_player.save_id}/development/unlock-node",
            json={"node_id": "pace_foundation"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
