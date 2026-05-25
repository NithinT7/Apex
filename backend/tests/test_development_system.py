"""Tests for the new development system foundation (skill tree, weekly focus, traits)."""

import json
from pathlib import Path

import pytest

from app.data.loaders import (
    get_skill_tree_config,
    get_trait_config,
    get_weekly_focus_config,
    validate_development_configs,
)
from app.models.development_profile import (
    ALL_BRANCHES,
    DevelopmentHistoryEntry,
    DevelopmentProfile,
    create_default_development_profile,
    create_player_starting_profile,
)
from app.models.driver_trait import DriverTrait, TraitConfig
from app.models.save_game import SaveGame
from app.models.skill_tree import SkillTreeConfig
from app.models.weekly_focus import WeeklyFocus, WeeklyFocusConfig
from app.save.save_manager import SaveManager


class TestSkillTreeConfig:
    """Tests for skill tree configuration loading and validation."""

    def test_skill_tree_config_loads(self) -> None:
        config = get_skill_tree_config()
        assert isinstance(config, SkillTreeConfig)
        assert config.version == "1.0.0"

    def test_skill_tree_has_all_branches(self) -> None:
        config = get_skill_tree_config()
        branch_ids = {branch.id for branch in config.branches}
        expected_branches = set(ALL_BRANCHES)
        assert branch_ids == expected_branches

    def test_skill_tree_nodes_have_valid_structure(self) -> None:
        config = get_skill_tree_config()
        for branch in config.branches:
            assert len(branch.nodes) >= 5, f"Branch {branch.id} has too few nodes"
            for node in branch.nodes:
                assert node.id, "Node must have an ID"
                assert node.name, "Node must have a name"
                assert 1 <= node.tier <= 4, f"Node {node.id} has invalid tier {node.tier}"
                assert node.cost >= 0, f"Node {node.id} has negative cost"
                assert node.xp_required >= 0, f"Node {node.id} has negative XP requirement"

    def test_skill_tree_prerequisites_exist(self) -> None:
        config = get_skill_tree_config()
        all_node_ids = {node.id for branch in config.branches for node in branch.nodes}

        for branch in config.branches:
            for node in branch.nodes:
                for prereq in node.required_node_ids:
                    assert prereq in all_node_ids, (
                        f"Node {node.id} has non-existent prerequisite {prereq}"
                    )

    def test_skill_tree_has_entry_point_nodes(self) -> None:
        """Each branch should have at least one node with no prerequisites (entry point)."""
        config = get_skill_tree_config()
        for branch in config.branches:
            entry_nodes = [node for node in branch.nodes if not node.required_node_ids]
            assert entry_nodes, (
                f"Branch {branch.id} has no entry point nodes (nodes with no prerequisites)"
            )


class TestWeeklyFocusConfig:
    """Tests for weekly focus configuration loading and validation."""

    def test_weekly_focus_config_loads(self) -> None:
        config = get_weekly_focus_config()
        assert isinstance(config, WeeklyFocusConfig)
        assert config.version == "1.0.0"

    def test_weekly_focus_has_options(self) -> None:
        config = get_weekly_focus_config()
        assert len(config.focuses) >= 10, "Should have at least 10 focus options"

    def test_weekly_focus_references_valid_branches(self) -> None:
        config = get_weekly_focus_config()
        valid_branches = set(ALL_BRANCHES)

        for focus in config.focuses:
            assert focus.primary_xp_branch in valid_branches, (
                f"Focus {focus.id} has invalid primary branch {focus.primary_xp_branch}"
            )
            for secondary in focus.secondary_xp_branches:
                assert secondary in valid_branches, (
                    f"Focus {focus.id} has invalid secondary branch {secondary}"
                )

    def test_weekly_focus_has_valid_xp_amounts(self) -> None:
        config = get_weekly_focus_config()
        for focus in config.focuses:
            assert focus.primary_xp_amount >= 0, f"Focus {focus.id} has negative primary XP"
            assert focus.secondary_xp_amount >= 0, f"Focus {focus.id} has negative secondary XP"
            assert focus.duration_days >= 1, f"Focus {focus.id} has invalid duration"


class TestTraitConfig:
    """Tests for driver trait configuration loading and validation."""

    def test_trait_config_loads(self) -> None:
        config = get_trait_config()
        assert isinstance(config, TraitConfig)
        assert config.version == "1.0.0"

    def test_traits_have_valid_structure(self) -> None:
        config = get_trait_config()
        assert len(config.traits) >= 10, "Should have at least 10 traits"

        for trait in config.traits:
            assert trait.id, "Trait must have an ID"
            assert trait.name, "Trait must have a name"
            assert trait.category, "Trait must have a category"
            assert trait.description, "Trait must have a description"
            assert trait.rarity in ("common", "uncommon", "rare", "legendary")

    def test_trait_incompatibilities_are_symmetric(self) -> None:
        config = get_trait_config()
        trait_ids = {trait.id for trait in config.traits}

        for trait in config.traits:
            for incompatible in trait.incompatible_traits:
                assert incompatible in trait_ids, (
                    f"Trait {trait.id} references non-existent incompatible trait {incompatible}"
                )


class TestCrossValidation:
    """Tests for cross-validation between configs."""

    def test_all_development_configs_validate(self) -> None:
        errors = validate_development_configs()
        assert errors == [], f"Validation errors: {errors}"

    def test_skill_tree_trait_unlocks_exist(self) -> None:
        skill_tree = get_skill_tree_config()
        traits = get_trait_config()
        trait_ids = {trait.id for trait in traits.traits}

        for branch in skill_tree.branches:
            for node in branch.nodes:
                if node.unlocks_trait_id:
                    assert node.unlocks_trait_id in trait_ids, (
                        f"Node {node.id} unlocks non-existent trait {node.unlocks_trait_id}"
                    )


class TestDevelopmentProfile:
    """Tests for development profile model."""

    def test_default_profile_has_all_branches(self) -> None:
        profile = create_default_development_profile()
        assert set(profile.branch_xp.keys()) == set(ALL_BRANCHES)

    def test_default_profile_starts_at_zero(self) -> None:
        profile = create_default_development_profile()
        assert profile.current_points == 0
        assert profile.total_points_earned == 0
        assert all(xp == 0 for xp in profile.branch_xp.values())
        assert profile.unlocked_node_ids == []
        assert profile.unlocked_trait_ids == []

    def test_player_starting_profile_has_initial_xp(self) -> None:
        profile = create_player_starting_profile(potential=85)
        assert profile.current_points == 3
        assert profile.total_points_earned == 3
        assert profile.branch_xp["raw_pace"] > 0
        assert len(profile.history) == 1

    def test_player_profile_scales_with_potential(self) -> None:
        low_potential = create_player_starting_profile(potential=70)
        high_potential = create_player_starting_profile(potential=95)

        assert high_potential.branch_xp["raw_pace"] > low_potential.branch_xp["raw_pace"]

    def test_profile_xp_methods(self) -> None:
        profile = create_default_development_profile()
        profile.add_branch_xp("raw_pace", 50)
        assert profile.get_branch_xp("raw_pace") == 50
        profile.add_branch_xp("raw_pace", 25)
        assert profile.get_branch_xp("raw_pace") == 75

    def test_profile_unlock_tracking(self) -> None:
        profile = create_default_development_profile()
        assert not profile.has_unlocked_node("test_node")
        assert not profile.has_unlocked_trait("test_trait")

        profile.unlocked_node_ids.append("test_node")
        profile.unlocked_trait_ids.append("test_trait")

        assert profile.has_unlocked_node("test_node")
        assert profile.has_unlocked_trait("test_trait")

    def test_history_entry_limits(self) -> None:
        profile = create_default_development_profile()
        for i in range(60):
            profile.add_history_entry(
                DevelopmentHistoryEntry(
                    date=f"2026-0{(i % 9) + 1}-01",
                    source="race_result",
                    summary=f"Entry {i}",
                )
            )
        assert len(profile.history) == 50


class TestSaveGameCompatibility:
    """Tests for save game compatibility with new development system."""

    def test_save_game_accepts_none_development_profile(self) -> None:
        """Ensure existing saves without development_profile still load."""
        from app.models.save_game import SaveGame

        # Minimal save data without development_profile
        minimal_data = {
            "save_id": "test-save",
            "name": "Test Save",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "current_date": "2026-03-01",
            "season": 2026,
            "phase": "preseason",
            "drivers": [],
            "teams": [],
            "academies": [],
            "academy_states": [],
            "calendar": [],
            "standings": {"driver_standings": [], "team_standings": {}},
            "random_seed": 12345,
        }

        # Should not raise
        save = SaveGame.model_validate(minimal_data)
        assert save.development_profile is None

    def test_save_game_accepts_development_profile(self) -> None:
        """Ensure saves with development_profile load correctly."""
        from app.models.save_game import SaveGame

        profile_data = {
            "current_points": 5,
            "total_points_earned": 10,
            "branch_xp": {branch: 20 for branch in ALL_BRANCHES},
            "unlocked_node_ids": ["test_node"],
            "unlocked_trait_ids": [],
            "active_focus_id": None,
            "history": [],
            "trait_bonuses": {},
        }

        save_data = {
            "save_id": "test-save",
            "name": "Test Save",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "current_date": "2026-03-01",
            "season": 2026,
            "phase": "preseason",
            "drivers": [],
            "teams": [],
            "academies": [],
            "academy_states": [],
            "calendar": [],
            "standings": {"driver_standings": [], "team_standings": {}},
            "random_seed": 12345,
            "development_profile": profile_data,
        }

        save = SaveGame.model_validate(save_data)
        assert save.development_profile is not None
        assert save.development_profile.current_points == 5
        assert save.development_profile.has_unlocked_node("test_node")

    def test_development_profile_serialization_roundtrip(self) -> None:
        """Ensure profile serializes and deserializes correctly."""
        original = create_player_starting_profile(potential=88)
        original.add_branch_xp("racecraft", 50)
        original.unlocked_node_ids.append("late_braker")
        original.unlocked_trait_ids.append("cold_blooded")

        json_str = original.model_dump_json(by_alias=True)
        restored = DevelopmentProfile.model_validate_json(json_str)

        assert restored.current_points == original.current_points
        assert restored.branch_xp == original.branch_xp
        assert restored.unlocked_node_ids == original.unlocked_node_ids
        assert restored.unlocked_trait_ids == original.unlocked_trait_ids
