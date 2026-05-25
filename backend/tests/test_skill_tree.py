"""Tests for the skill tree unlock system."""

import pytest
from fastapi.testclient import TestClient

from app.engine.skill_tree_engine import (
    get_skill_tree_state,
    unlock_node,
    get_node_preview,
)
from app.main import app
from app.models.development_profile import create_player_starting_profile
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


client = TestClient(app)


@pytest.fixture
def manager():
    """Create a SaveManager instance."""
    return SaveManager()


@pytest.fixture
def save_with_player(manager: SaveManager) -> SaveGame:
    """Create a save game with a player."""
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
def save_with_xp(save_with_player: SaveGame, manager: SaveManager) -> SaveGame:
    """Create a save with enough XP to unlock some nodes."""
    profile = save_with_player.development_profile
    if profile is None:
        profile = create_player_starting_profile(85)

    # Give enough XP and points to unlock some nodes
    profile = profile.model_copy(
        update={
            "current_points": 10,
            "total_points_earned": 10,
            "branch_xp": {
                "raw_pace": 100,
                "racecraft": 80,
                "tire_strategy": 60,
                "mentality_pressure": 40,
                "technical_feedback": 40,
                "starts_execution": 60,
                "media_marketability": 30,
                "academy_path": 50,
            },
        }
    )

    updated_save = save_with_player.model_copy(update={"development_profile": profile})
    return manager.save(updated_save)


class TestGetSkillTreeState:
    """Tests for getting skill tree state."""

    def test_returns_all_branches(self, save_with_player: SaveGame):
        """Test that skill tree state includes all 8 branches."""
        state = get_skill_tree_state(save_with_player)

        assert len(state.branches) == 8
        branch_ids = {b.branch_id for b in state.branches}
        expected = {
            "raw_pace", "racecraft", "tire_strategy", "mentality_pressure",
            "technical_feedback", "starts_execution", "media_marketability", "academy_path"
        }
        assert branch_ids == expected

    def test_nodes_have_correct_states(self, save_with_player: SaveGame):
        """Test that nodes show correct locked/available/unlocked states."""
        state = get_skill_tree_state(save_with_player)

        # Find raw_pace branch
        raw_pace = next(b for b in state.branches if b.branch_id == "raw_pace")

        # The foundation node should be available (tier 1, no prereqs)
        foundation = next(n for n in raw_pace.nodes if n.node.id == "pace_foundation")
        assert foundation.state == "available"

        # Higher tier nodes should be locked (need prerequisites)
        one_lap = next(n for n in raw_pace.nodes if n.node.id == "one_lap_monster")
        assert one_lap.state == "locked"
        assert len(one_lap.unmet_requirements) > 0

    def test_xp_progress_tracked(self, save_with_xp: SaveGame):
        """Test that XP progress is correctly tracked."""
        state = get_skill_tree_state(save_with_xp)

        raw_pace = next(b for b in state.branches if b.branch_id == "raw_pace")
        assert raw_pace.current_xp == 100

    def test_can_afford_calculation(self, save_with_xp: SaveGame):
        """Test that can_afford is calculated correctly."""
        state = get_skill_tree_state(save_with_xp)

        # With 10 points, should be able to afford cost-1 nodes
        raw_pace = next(b for b in state.branches if b.branch_id == "raw_pace")
        foundation = next(n for n in raw_pace.nodes if n.node.id == "pace_foundation")

        if foundation.state == "available":
            assert foundation.can_afford is True


class TestUnlockNode:
    """Tests for unlocking skill tree nodes."""

    def test_can_unlock_eligible_node(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that an eligible node can be unlocked."""
        initial_points = save_with_xp.development_profile.current_points

        updated_save, result = unlock_node(save_with_xp, "pace_foundation")

        assert result.success is True
        assert "pace_foundation" in updated_save.development_profile.unlocked_node_ids
        assert updated_save.development_profile.current_points < initial_points

    def test_cannot_unlock_without_xp(self, save_with_player: SaveGame, manager: SaveManager):
        """Test that nodes requiring more XP than available cannot be unlocked."""
        # one_lap_monster requires 100 XP in raw_pace
        # New player doesn't have that much
        _, result = unlock_node(save_with_player, "one_lap_monster")

        assert result.success is False
        assert "XP" in result.message or "Requires" in result.message

    def test_cannot_unlock_without_points(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that nodes cannot be unlocked without enough development points."""
        # Set points to 0
        profile = save_with_xp.development_profile.model_copy(update={"current_points": 0})
        save_no_points = save_with_xp.model_copy(update={"development_profile": profile})

        _, result = unlock_node(save_no_points, "pace_foundation")

        assert result.success is False
        assert "points" in result.message.lower()

    def test_cannot_unlock_without_prerequisite(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that nodes with unmet prerequisites cannot be unlocked."""
        # braking_precision requires pace_foundation
        _, result = unlock_node(save_with_xp, "braking_precision")

        assert result.success is False
        assert "Requires" in result.message

    def test_cannot_unlock_duplicate(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that already-unlocked nodes cannot be unlocked again."""
        # First unlock
        updated_save, result1 = unlock_node(save_with_xp, "pace_foundation")
        assert result1.success is True

        # Second unlock attempt
        _, result2 = unlock_node(updated_save, "pace_foundation")
        assert result2.success is False
        assert "already" in result2.message.lower()

    def test_unlock_applies_effects_once(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that unlocking applies attribute effects correctly."""
        # Get initial attributes
        player_before = next(
            d for d in save_with_xp.drivers if d.id == save_with_xp.player_driver_id
        )
        pace_before = player_before.attributes.pace

        # Unlock pace_foundation (+1 pace)
        updated_save, result = unlock_node(save_with_xp, "pace_foundation")
        assert result.success is True

        player_after = next(
            d for d in updated_save.drivers if d.id == updated_save.player_driver_id
        )
        pace_after = player_after.attributes.pace

        assert pace_after == pace_before + 1
        assert result.attribute_changes.get("pace") == 1

    def test_unlock_chain_works(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that unlocking a chain of nodes works correctly."""
        # Unlock foundation
        save1, result1 = unlock_node(save_with_xp, "pace_foundation")
        assert result1.success is True

        # Now unlock braking_precision (requires pace_foundation)
        save2, result2 = unlock_node(save1, "braking_precision")
        assert result2.success is True

        assert "pace_foundation" in save2.development_profile.unlocked_node_ids
        assert "braking_precision" in save2.development_profile.unlocked_node_ids

    def test_trait_unlock_works(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that unlocking a major node unlocks its trait."""
        # Give enough XP for one_lap_monster
        profile = save_with_xp.development_profile.model_copy(
            update={
                "current_points": 20,
                "branch_xp": {"raw_pace": 150, **{
                    k: v for k, v in save_with_xp.development_profile.branch_xp.items()
                    if k != "raw_pace"
                }},
                "unlocked_node_ids": [
                    "pace_foundation",
                    "braking_precision",
                    "corner_entry_speed",
                    "qualifying_specialist",
                ],
            }
        )
        save_ready = save_with_xp.model_copy(update={"development_profile": profile})

        # Unlock one_lap_monster
        updated_save, result = unlock_node(save_ready, "one_lap_monster")

        assert result.success is True
        assert result.trait_unlocked == "one_lap_monster"
        assert "one_lap_monster" in updated_save.development_profile.unlocked_trait_ids


class TestSkillTreeAPI:
    """Tests for skill tree API endpoints."""

    def test_get_skill_tree_endpoint(self, save_with_player: SaveGame):
        """Test GET /career/{save_id}/development/skill-tree endpoint."""
        response = client.get(f"/career/{save_with_player.save_id}/development/skill-tree")
        assert response.status_code == 200

        data = response.json()
        assert "branches" in data
        assert "currentPoints" in data
        assert "totalPointsEarned" in data
        assert "recommendedNodes" in data
        assert len(data["branches"]) == 8

    def test_unlock_node_endpoint(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test POST /career/{save_id}/development/unlock-node endpoint."""
        response = client.post(
            f"/career/{save_with_xp.save_id}/development/unlock-node",
            json={"node_id": "pace_foundation"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["nodeId"] == "pace_foundation"

        # Verify in save
        reloaded = manager.get(save_with_xp.save_id)
        assert "pace_foundation" in reloaded.development_profile.unlocked_node_ids

    def test_get_node_details_endpoint(self, save_with_xp: SaveGame):
        """Test GET /career/{save_id}/development/skill-tree/node/{node_id} endpoint."""
        response = client.get(
            f"/career/{save_with_xp.save_id}/development/skill-tree/node/pace_foundation"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["nodeId"] == "pace_foundation"
        assert "state" in data
        assert "cost" in data
        assert "effects" in data


class TestSaveLoadPersistence:
    """Tests for save/load with unlocked nodes."""

    def test_unlocked_nodes_persist(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that unlocked nodes persist through save/load."""
        # Unlock a node
        updated_save, result = unlock_node(save_with_xp, "pace_foundation")
        assert result.success is True

        # Save
        saved = manager.save(updated_save)

        # Reload
        reloaded = manager.get(saved.save_id)

        assert "pace_foundation" in reloaded.development_profile.unlocked_node_ids
        assert reloaded.development_profile.current_points == saved.development_profile.current_points

    def test_history_entry_persists(self, save_with_xp: SaveGame, manager: SaveManager):
        """Test that unlock history entries persist."""
        # Unlock a node
        updated_save, _ = unlock_node(save_with_xp, "pace_foundation")

        # Save and reload
        saved = manager.save(updated_save)
        reloaded = manager.get(saved.save_id)

        # Check history
        history = reloaded.development_profile.history
        unlock_entries = [h for h in history if h.source == "skill_unlock"]
        assert len(unlock_entries) > 0
        assert unlock_entries[-1].node_unlocked == "pace_foundation"


class TestNodePreview:
    """Tests for node preview functionality."""

    def test_preview_shows_requirements(self, save_with_player: SaveGame):
        """Test that preview shows unmet requirements."""
        preview = get_node_preview(save_with_player, "one_lap_monster")

        assert preview["state"] == "locked"
        assert len(preview["unmetRequirements"]) > 0
        assert preview["cost"] > 0

    def test_preview_shows_trait_info(self, save_with_xp: SaveGame):
        """Test that preview includes trait info for major nodes."""
        preview = get_node_preview(save_with_xp, "one_lap_monster")

        assert preview["traitUnlock"] is not None
        assert preview["traitUnlock"]["id"] == "one_lap_monster"
        assert preview["traitUnlock"]["name"] == "One-Lap Monster"
        assert preview["isMajorNode"] is True

    def test_preview_shows_effects(self, save_with_xp: SaveGame):
        """Test that preview shows node effects."""
        preview = get_node_preview(save_with_xp, "pace_foundation")

        assert "effects" in preview
        assert "attributeBonuses" in preview["effects"]
        assert preview["effects"]["attributeBonuses"].get("pace") == 1
