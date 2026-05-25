"""Tests for the player balance and difficulty system."""

import pytest
from fastapi.testclient import TestClient

from app.engine.player_balance import (
    DEFAULT_DIFFICULTY,
    DIFFICULTY_PRESETS,
    DifficultyPreset,
    calculate_f1_adaptation_penalty,
    generate_starting_attributes,
    get_all_difficulty_options,
    get_dev_point_multiplier,
    get_difficulty_config,
    get_effective_cap,
    get_xp_multiplier,
    F1_ADAPTATION_BASE_PENALTY,
    F1_ADAPTATION_RACES_MAX,
)
from app.main import app
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


client = TestClient(app)


@pytest.fixture
def manager():
    """Create a SaveManager instance."""
    return SaveManager()


class TestDifficultyPresets:
    """Tests for difficulty preset configuration."""

    def test_all_presets_exist(self):
        """Test that all expected presets are defined."""
        expected = ["prodigy", "realistic_prospect", "underdog", "brutal_realism"]
        for preset in expected:
            assert preset in DIFFICULTY_PRESETS

    def test_prodigy_has_highest_potential(self):
        """Test that prodigy has the highest potential range."""
        prodigy = get_difficulty_config("prodigy")
        realistic = get_difficulty_config("realistic_prospect")
        underdog = get_difficulty_config("underdog")
        brutal = get_difficulty_config("brutal_realism")

        assert prodigy.potential_max > realistic.potential_max
        assert realistic.potential_max > underdog.potential_max
        assert underdog.potential_max > brutal.potential_max

    def test_prodigy_has_highest_starting_ovr(self):
        """Test that prodigy has the highest starting OVR range."""
        prodigy = get_difficulty_config("prodigy")
        brutal = get_difficulty_config("brutal_realism")

        assert prodigy.starting_ovr_min > brutal.starting_ovr_min
        assert prodigy.starting_ovr_max > brutal.starting_ovr_max

    def test_prodigy_can_reach_elite(self):
        """Test that prodigy preset can reach elite (94+) ratings."""
        prodigy = get_difficulty_config("prodigy")
        assert prodigy.hard_cap >= 94
        assert prodigy.soft_cap >= 92

    def test_realistic_prospect_can_reach_elite_with_achievements(self):
        """Test that realistic prospect can reach elite with achievements."""
        config = get_difficulty_config("realistic_prospect")
        # Base soft cap + achievement bonuses should allow elite
        assert config.soft_cap + 6 >= 94  # +6 from achievements

    def test_dev_multipliers_scale_with_difficulty(self):
        """Test that development multipliers scale correctly."""
        prodigy = get_difficulty_config("prodigy")
        realistic = get_difficulty_config("realistic_prospect")
        brutal = get_difficulty_config("brutal_realism")

        assert prodigy.dev_point_multiplier > realistic.dev_point_multiplier
        assert realistic.dev_point_multiplier > brutal.dev_point_multiplier

    def test_default_difficulty_is_realistic_prospect(self):
        """Test that default difficulty is realistic prospect."""
        assert DEFAULT_DIFFICULTY == "realistic_prospect"


class TestPlayerCreation:
    """Tests for player creation with different difficulties."""

    def test_create_prodigy_player(self, manager: SaveManager):
        """Test creating a player with prodigy difficulty."""
        response = client.post(
            "/career/new",
            json={
                "name": "Max Talent",
                "nationality": "Dutch",
                "age": 18,
                "driverNumber": 33,
                "backgroundId": "karting_prodigy",
                "archetypeId": "one_lap_monster",
                "teamId": "f2_prema",
                "difficulty": "prodigy",
            },
        )
        assert response.status_code == 201

        save_id = response.json()["saveId"]
        save = manager.get(save_id)

        # Check difficulty is stored
        assert save.difficulty == "prodigy"

        # Check player has high potential
        player = next(d for d in save.drivers if d.id == save.player_driver_id)
        assert player.hidden.potential >= 96

        # Check starting points are higher
        assert save.development_profile.current_points >= 5

    def test_create_brutal_realism_player(self, manager: SaveManager):
        """Test creating a player with brutal realism difficulty."""
        # Use technical_driver background (no potential bonus) for accurate test
        response = client.post(
            "/career/new",
            json={
                "name": "Hard Mode",
                "nationality": "German",
                "age": 22,
                "driverNumber": 42,
                "backgroundId": "technical_driver",  # No potential bonus
                "archetypeId": "smooth_operator",
                "teamId": "f2_prema",
                "difficulty": "brutal_realism",
            },
        )
        assert response.status_code == 201

        save_id = response.json()["saveId"]
        save = manager.get(save_id)

        # Check difficulty is stored
        assert save.difficulty == "brutal_realism"

        # Check player has lower potential (brutal realism range is 82-90)
        player = next(d for d in save.drivers if d.id == save.player_driver_id)
        assert 82 <= player.hidden.potential <= 90

        # Check starting points are lower
        assert save.development_profile.current_points <= 2

    def test_realistic_prospect_is_default(self, manager: SaveManager):
        """Test that realistic prospect is the default difficulty."""
        response = client.post(
            "/career/new",
            json={
                "name": "Default Difficulty",
                "nationality": "British",
                "age": 20,
                "driverNumber": 99,
                "backgroundId": "karting_prodigy",
                "archetypeId": "smooth_operator",
                "teamId": "f2_prema",
                # No difficulty specified
            },
        )
        assert response.status_code == 201

        save_id = response.json()["saveId"]
        save = manager.get(save_id)

        assert save.difficulty == "realistic_prospect"

    def test_difficulty_affects_starting_attributes(self):
        """Test that difficulty affects starting attribute range."""
        # Generate attributes for different difficulties
        prodigy_attrs, prodigy_hidden = generate_starting_attributes(
            "prodigy", {}, {}, seed=12345
        )
        brutal_attrs, brutal_hidden = generate_starting_attributes(
            "brutal_realism", {}, {}, seed=12345
        )

        # Prodigy should have higher average attributes
        prodigy_avg = sum(prodigy_attrs.get(a, 0) for a in ["pace", "qualifying", "racecraft"]) / 3
        brutal_avg = sum(brutal_attrs.get(a, 0) for a in ["pace", "qualifying", "racecraft"]) / 3

        assert prodigy_avg > brutal_avg

        # Prodigy should have higher potential
        assert prodigy_hidden["potential"] > brutal_hidden["potential"]


class TestF1Adaptation:
    """Tests for F1 rookie adaptation system."""

    def test_adaptation_penalty_at_start(self):
        """Test that new F1 drivers have a penalty."""
        penalty = calculate_f1_adaptation_penalty(
            f1_races=0,
            adaptability=70,
            confidence=70,
            recent_results_avg=None,
        )
        assert penalty > 0
        assert penalty <= F1_ADAPTATION_BASE_PENALTY

    def test_adaptation_penalty_decreases_with_races(self):
        """Test that penalty decreases with more races."""
        penalty_0 = calculate_f1_adaptation_penalty(0, 70, 70, None)
        penalty_5 = calculate_f1_adaptation_penalty(5, 70, 70, None)
        penalty_10 = calculate_f1_adaptation_penalty(10, 70, 70, None)

        assert penalty_5 < penalty_0
        assert penalty_10 < penalty_5

    def test_full_adaptation_after_max_races(self):
        """Test that penalty is zero after max races."""
        penalty = calculate_f1_adaptation_penalty(
            f1_races=F1_ADAPTATION_RACES_MAX,
            adaptability=70,
            confidence=70,
            recent_results_avg=None,
        )
        assert penalty == 0

    def test_high_adaptability_adapts_faster(self):
        """Test that high adaptability reduces penalty faster."""
        low_adapt = calculate_f1_adaptation_penalty(5, 60, 70, None)
        high_adapt = calculate_f1_adaptation_penalty(5, 90, 70, None)

        assert high_adapt < low_adapt

    def test_good_results_speed_up_adaptation(self):
        """Test that good results reduce penalty faster."""
        bad_results = calculate_f1_adaptation_penalty(5, 70, 70, recent_results_avg=18)
        good_results = calculate_f1_adaptation_penalty(5, 70, 70, recent_results_avg=5)

        assert good_results < bad_results


class TestSoftCaps:
    """Tests for the soft cap system."""

    def test_base_soft_cap(self):
        """Test that soft cap is applied without traits."""
        cap = get_effective_cap(
            base_potential=95,
            difficulty="realistic_prospect",
            unlocked_traits=[],
            achievements=[],
        )
        config = get_difficulty_config("realistic_prospect")
        assert cap == config.soft_cap

    def test_traits_increase_cap(self):
        """Test that cap-breaking traits increase the cap."""
        base_cap = get_effective_cap(95, "realistic_prospect", [], [])
        with_trait = get_effective_cap(
            95, "realistic_prospect",
            unlocked_traits=["one_lap_monster"],
            achievements=[],
        )

        assert with_trait > base_cap

    def test_achievements_increase_cap(self):
        """Test that achievements increase the cap."""
        base_cap = get_effective_cap(95, "realistic_prospect", [], [])
        with_achievement = get_effective_cap(
            95, "realistic_prospect",
            unlocked_traits=[],
            achievements=["f1_race_winner"],
        )

        assert with_achievement > base_cap

    def test_cap_cannot_exceed_hard_cap(self):
        """Test that cap cannot exceed hard cap."""
        config = get_difficulty_config("realistic_prospect")
        max_cap = get_effective_cap(
            99, "realistic_prospect",
            unlocked_traits=["one_lap_monster", "future_champion", "generational_talent"],
            achievements=["f1_champion", "multiple_f1_wins", "f1_race_winner"],
        )

        assert max_cap <= config.hard_cap

    def test_prodigy_can_reach_99(self):
        """Test that prodigy can reach 99 with achievements."""
        cap = get_effective_cap(
            99, "prodigy",
            unlocked_traits=["future_champion"],
            achievements=["f1_champion"],
        )

        assert cap >= 99


class TestDevelopmentMultipliers:
    """Tests for development point multipliers."""

    def test_prodigy_gets_bonus(self):
        """Test that prodigy gets development bonus."""
        prodigy_mult = get_dev_point_multiplier("prodigy")
        realistic_mult = get_dev_point_multiplier("realistic_prospect")

        assert prodigy_mult > realistic_mult

    def test_form_affects_multiplier(self):
        """Test that high form increases multiplier."""
        low_form = get_dev_point_multiplier("realistic_prospect", player_form=30)
        high_form = get_dev_point_multiplier("realistic_prospect", player_form=85)

        assert high_form > low_form

    def test_championship_position_affects_multiplier(self):
        """Test that fighting at front increases multiplier."""
        midfield = get_dev_point_multiplier("realistic_prospect", championship_position=10)
        leader = get_dev_point_multiplier("realistic_prospect", championship_position=1)

        assert leader > midfield

    def test_xp_multiplier_scales_with_difficulty(self):
        """Test that XP multiplier scales correctly."""
        prodigy_xp = get_xp_multiplier("prodigy")
        brutal_xp = get_xp_multiplier("brutal_realism")

        assert prodigy_xp > brutal_xp


class TestAPIEndpoints:
    """Tests for the new API endpoints."""

    @pytest.fixture
    def save_with_player(self, manager: SaveManager) -> SaveGame:
        """Create a save with a player."""
        response = client.post(
            "/career/new",
            json={
                "name": "Test Player",
                "nationality": "British",
                "age": 20,
                "driverNumber": 99,
                "backgroundId": "karting_prodigy",
                "archetypeId": "smooth_operator",
                "teamId": "f2_prema",
                "difficulty": "prodigy",
            },
        )
        assert response.status_code == 201
        return manager.get(response.json()["saveId"])

    def test_get_difficulty_info(self, save_with_player: SaveGame):
        """Test the difficulty info endpoint."""
        response = client.get(f"/career/{save_with_player.save_id}/development/difficulty-info")
        assert response.status_code == 200

        data = response.json()
        assert data["difficulty"] == "prodigy"
        assert data["name"] == "Prodigy"
        assert data["canReachElite"] is True

    def test_get_f1_adaptation(self, save_with_player: SaveGame):
        """Test the F1 adaptation endpoint."""
        response = client.get(f"/career/{save_with_player.save_id}/development/f1-adaptation")
        assert response.status_code == 200

        data = response.json()
        assert "isInF1" in data
        assert "f1RacesCompleted" in data
        assert "adaptationProgress" in data

    def test_get_player_achievements(self, save_with_player: SaveGame):
        """Test the player achievements endpoint."""
        response = client.get(f"/career/{save_with_player.save_id}/development/player-achievements")
        assert response.status_code == 200

        data = response.json()
        assert "achievements" in data
        assert "totalCapBonus" in data

    def test_career_options_includes_difficulty_presets(self):
        """Test that career options include difficulty presets."""
        response = client.get("/career/new/options")
        assert response.status_code == 200

        data = response.json()
        assert "difficultyPresets" in data
        assert len(data["difficultyPresets"]) == 4

        # Check structure
        preset = data["difficultyPresets"][0]
        assert "id" in preset
        assert "name" in preset
        assert "description" in preset
        assert "startingOvrRange" in preset
        assert "potentialRange" in preset


class TestDifficultyPersistence:
    """Tests that difficulty settings persist correctly."""

    def test_difficulty_persists_in_save(self, manager: SaveManager):
        """Test that difficulty setting persists through save/load."""
        response = client.post(
            "/career/new",
            json={
                "name": "Persistence Test",
                "nationality": "Finnish",
                "age": 19,
                "driverNumber": 77,
                "backgroundId": "karting_prodigy",
                "archetypeId": "smooth_operator",
                "teamId": "f2_prema",
                "difficulty": "underdog",
            },
        )
        assert response.status_code == 201

        save_id = response.json()["saveId"]

        # Reload the save
        reloaded = manager.get(save_id)
        assert reloaded.difficulty == "underdog"

    def test_existing_saves_get_default_difficulty(self, manager: SaveManager):
        """Test that saves without difficulty get the default."""
        # Create a save
        response = client.post(
            "/career/new",
            json={
                "name": "Legacy Save",
                "nationality": "Spanish",
                "age": 21,
                "driverNumber": 55,
                "backgroundId": "karting_prodigy",
                "archetypeId": "smooth_operator",
                "teamId": "f2_prema",
            },
        )
        assert response.status_code == 201

        save = manager.get(response.json()["saveId"])
        # Should have default difficulty
        assert save.difficulty == "realistic_prospect"
