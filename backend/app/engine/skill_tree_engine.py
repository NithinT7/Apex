"""Engine for the skill tree unlock system."""

from __future__ import annotations

from typing import Literal

from app.data.loaders import get_skill_tree_config, get_trait_config
from app.models.development_profile import (
    DevelopmentHistoryEntry,
    DevelopmentProfile,
    create_player_starting_profile,
)
from app.models.driver import Driver
from app.models.driver_trait import DriverTrait
from app.models.save_game import SaveGame
from app.models.skill_tree import SkillTreeConfig, SkillTreeNode


# Node states for the frontend
NodeState = Literal["locked", "available", "unlocked"]


class SkillNodeInfo:
    """Information about a skill tree node with its current state."""

    def __init__(
        self,
        node: SkillTreeNode,
        state: NodeState,
        unmet_requirements: list[str],
        can_afford: bool,
        trait_info: dict | None = None,
    ):
        self.node = node
        self.state = state
        self.unmet_requirements = unmet_requirements
        self.can_afford = can_afford
        self.trait_info = trait_info  # Info about unlockable trait if any

    def to_dict(self) -> dict:
        return {
            "node": self.node.model_dump(by_alias=True),
            "state": self.state,
            "unmetRequirements": self.unmet_requirements,
            "canAfford": self.can_afford,
            "traitInfo": self.trait_info,
        }


class SkillBranchInfo:
    """Information about a skill tree branch."""

    def __init__(
        self,
        branch_id: str,
        name: str,
        description: str,
        icon: str | None,
        color: str | None,
        current_xp: int,
        nodes: list[SkillNodeInfo],
    ):
        self.branch_id = branch_id
        self.name = name
        self.description = description
        self.icon = icon
        self.color = color
        self.current_xp = current_xp
        self.nodes = nodes

    def to_dict(self) -> dict:
        return {
            "branchId": self.branch_id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "color": self.color,
            "currentXp": self.current_xp,
            "nodes": [n.to_dict() for n in self.nodes],
            "unlockedCount": sum(1 for n in self.nodes if n.state == "unlocked"),
            "availableCount": sum(1 for n in self.nodes if n.state == "available"),
            "totalCount": len(self.nodes),
        }


class SkillTreeState:
    """Complete skill tree state for the player."""

    def __init__(
        self,
        branches: list[SkillBranchInfo],
        current_points: int,
        total_points_earned: int,
        unlocked_traits: list[dict],
        recommended_nodes: list[str],
    ):
        self.branches = branches
        self.current_points = current_points
        self.total_points_earned = total_points_earned
        self.unlocked_traits = unlocked_traits
        self.recommended_nodes = recommended_nodes

    def to_dict(self) -> dict:
        return {
            "branches": [b.to_dict() for b in self.branches],
            "currentPoints": self.current_points,
            "totalPointsEarned": self.total_points_earned,
            "unlockedTraits": self.unlocked_traits,
            "recommendedNodes": self.recommended_nodes,
            "totalUnlocked": sum(b.to_dict()["unlockedCount"] for b in self.branches),
            "totalAvailable": sum(b.to_dict()["availableCount"] for b in self.branches),
        }


class UnlockResult:
    """Result of attempting to unlock a node."""

    def __init__(
        self,
        success: bool,
        message: str,
        node_id: str | None = None,
        trait_unlocked: str | None = None,
        attribute_changes: dict[str, int] | None = None,
        special_effects: list[str] | None = None,
    ):
        self.success = success
        self.message = message
        self.node_id = node_id
        self.trait_unlocked = trait_unlocked
        self.attribute_changes = attribute_changes or {}
        self.special_effects = special_effects or []

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "nodeId": self.node_id,
            "traitUnlocked": self.trait_unlocked,
            "attributeChanges": self.attribute_changes,
            "specialEffects": self.special_effects,
        }


def get_skill_tree_state(save: SaveGame) -> SkillTreeState:
    """
    Get the complete skill tree state for the player.

    Returns all branches with node states (locked/available/unlocked),
    XP progress, and recommendations.
    """
    config = get_skill_tree_config()
    trait_config = get_trait_config()
    player = _get_player(save)
    profile = _ensure_profile(save, player)

    branches: list[SkillBranchInfo] = []

    for branch in config.branches:
        branch_xp = profile.get_branch_xp(branch.id)
        nodes: list[SkillNodeInfo] = []

        for node in branch.nodes:
            state, unmet = _get_node_state(
                node=node,
                profile=profile,
                config=config,
                save=save,
            )

            can_afford = profile.current_points >= node.cost and state == "available"

            # Get trait info if this node unlocks a trait
            trait_info = None
            if node.unlocks_trait_id:
                trait = trait_config.get_trait(node.unlocks_trait_id)
                if trait:
                    trait_info = {
                        "id": trait.id,
                        "name": trait.name,
                        "category": trait.category,
                        "description": trait.description,
                        "rarity": trait.rarity,
                    }

            nodes.append(SkillNodeInfo(
                node=node,
                state=state,
                unmet_requirements=unmet,
                can_afford=can_afford,
                trait_info=trait_info,
            ))

        branches.append(SkillBranchInfo(
            branch_id=branch.id,
            name=branch.name,
            description=branch.description,
            icon=branch.icon,
            color=branch.color,
            current_xp=branch_xp,
            nodes=nodes,
        ))

    # Get unlocked traits info
    unlocked_traits = []
    for trait_id in profile.unlocked_trait_ids:
        trait = trait_config.get_trait(trait_id)
        if trait:
            unlocked_traits.append({
                "id": trait.id,
                "name": trait.name,
                "category": trait.category,
                "description": trait.description,
                "rarity": trait.rarity,
                "icon": trait.icon,
            })

    # Calculate recommended nodes
    recommended = _get_recommended_nodes(branches, profile, player)

    return SkillTreeState(
        branches=branches,
        current_points=profile.current_points,
        total_points_earned=profile.total_points_earned,
        unlocked_traits=unlocked_traits,
        recommended_nodes=recommended,
    )


def unlock_node(save: SaveGame, node_id: str) -> tuple[SaveGame, UnlockResult]:
    """
    Attempt to unlock a skill tree node.

    Validates requirements, deducts points, applies effects, and saves.
    """
    config = get_skill_tree_config()
    trait_config = get_trait_config()
    player = _get_player(save)
    profile = _ensure_profile(save, player)

    # Get the node
    node = config.get_node(node_id)
    if node is None:
        return save, UnlockResult(False, f"Node '{node_id}' not found")

    # Check if already unlocked
    if node_id in profile.unlocked_node_ids:
        return save, UnlockResult(False, f"Node '{node.name}' is already unlocked")

    # Check requirements
    state, unmet = _get_node_state(node, profile, config, save)

    if state == "locked":
        return save, UnlockResult(
            False,
            f"Cannot unlock '{node.name}': {'; '.join(unmet)}",
        )

    # Check can afford
    if profile.current_points < node.cost:
        return save, UnlockResult(
            False,
            f"Not enough development points. Need {node.cost}, have {profile.current_points}",
        )

    # Apply the unlock!
    new_profile = _apply_node_unlock(profile, node, save.current_date)
    new_player = _apply_node_effects(player, node)

    # Check for trait unlock
    trait_unlocked = None
    if node.unlocks_trait_id and node.unlocks_trait_id not in profile.unlocked_trait_ids:
        trait = trait_config.get_trait(node.unlocks_trait_id)
        if trait:
            new_profile.unlocked_trait_ids.append(node.unlocks_trait_id)
            trait_unlocked = trait.name
            # Apply trait effects
            new_player = _apply_trait_effects(new_player, trait)

    # Update save
    new_drivers = [new_player if d.id == player.id else d for d in save.drivers]
    updated_save = save.model_copy(
        update={
            "drivers": new_drivers,
            "development_profile": new_profile,
        }
    )

    return updated_save, UnlockResult(
        success=True,
        message=f"Unlocked '{node.name}'!" + (f" Earned trait: {trait_unlocked}" if trait_unlocked else ""),
        node_id=node_id,
        trait_unlocked=node.unlocks_trait_id if trait_unlocked else None,
        attribute_changes=node.effects.attribute_bonuses,
        special_effects=node.effects.special_effects,
    )


def get_node_preview(save: SaveGame, node_id: str) -> dict:
    """
    Get a preview of what unlocking a node would do.

    Returns detailed information about effects, requirements, and costs.
    """
    config = get_skill_tree_config()
    trait_config = get_trait_config()
    player = _get_player(save)
    profile = _ensure_profile(save, player)

    node = config.get_node(node_id)
    if node is None:
        return {"error": f"Node '{node_id}' not found"}

    state, unmet = _get_node_state(node, profile, config, save)

    # Get trait preview if applicable
    trait_preview = None
    if node.unlocks_trait_id:
        trait = trait_config.get_trait(node.unlocks_trait_id)
        if trait:
            trait_preview = {
                "id": trait.id,
                "name": trait.name,
                "category": trait.category,
                "description": trait.description,
                "rarity": trait.rarity,
                "positiveEffects": trait.positive_effects.model_dump(by_alias=True),
                "drawbacks": trait.drawbacks.model_dump(by_alias=True),
                "flavorText": trait.flavor_text,
            }

    return {
        "nodeId": node.id,
        "name": node.name,
        "description": node.description,
        "branch": node.branch,
        "tier": node.tier,
        "state": state,
        "unmetRequirements": unmet,
        "cost": node.cost,
        "currentPoints": profile.current_points,
        "canAfford": profile.current_points >= node.cost,
        "xpRequired": node.xp_required,
        "currentBranchXp": profile.get_branch_xp(node.branch),
        "hasEnoughXp": profile.get_branch_xp(node.branch) >= node.xp_required,
        "effects": {
            "attributeBonuses": node.effects.attribute_bonuses,
            "xpBonuses": node.effects.xp_bonuses,
            "specialEffects": node.effects.special_effects,
        },
        "traitUnlock": trait_preview,
        "isMajorNode": node.is_major_node,
        "prerequisites": node.required_node_ids,
        "unlockedPrerequisites": [
            n for n in node.required_node_ids if n in profile.unlocked_node_ids
        ],
    }


# --- Private helpers ---


def _get_player(save: SaveGame) -> Driver:
    """Get the player driver."""
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        raise ValueError("No player driver found")
    return player


def _ensure_profile(save: SaveGame, player: Driver) -> DevelopmentProfile:
    """Ensure the save has a development profile."""
    if save.development_profile is not None:
        return save.development_profile
    return create_player_starting_profile(player.hidden.potential)


def _get_node_state(
    node: SkillTreeNode,
    profile: DevelopmentProfile,
    config: SkillTreeConfig,
    save: SaveGame,
) -> tuple[NodeState, list[str]]:
    """
    Determine the state of a node and any unmet requirements.

    Returns (state, list_of_unmet_requirements).
    """
    # Already unlocked?
    if node.id in profile.unlocked_node_ids:
        return "unlocked", []

    unmet: list[str] = []

    # Check XP requirement
    branch_xp = profile.get_branch_xp(node.branch)
    if branch_xp < node.xp_required:
        unmet.append(f"Need {node.xp_required} {node.branch} XP (have {branch_xp})")

    # Check prerequisite nodes
    for prereq_id in node.required_node_ids:
        if prereq_id not in profile.unlocked_node_ids:
            prereq_node = config.get_node(prereq_id)
            prereq_name = prereq_node.name if prereq_node else prereq_id
            unmet.append(f"Requires: {prereq_name}")

    # Check required traits
    for trait_id in node.required_traits:
        if trait_id not in profile.unlocked_trait_ids:
            unmet.append(f"Requires trait: {trait_id}")

    # Check required achievements
    achievements = _get_player_achievements(save)
    for achievement in node.required_achievements:
        if achievement not in achievements:
            unmet.append(f"Requires achievement: {_format_achievement(achievement)}")

    if unmet:
        return "locked", unmet

    return "available", []


def _get_player_achievements(save: SaveGame) -> list[str]:
    """
    Get list of achievements the player has earned.

    Derives achievements from career stats and standings.
    """
    achievements: list[str] = []
    player_id = save.player_driver_id
    if not player_id:
        return achievements

    # Find player in standings
    standings = save.standings
    player_entry = next(
        (e for e in standings.driver_standings if e.driver_id == player_id),
        None
    )

    if player_entry:
        # Race wins
        if player_entry.wins >= 1:
            achievements.append("first_win")
        if player_entry.wins >= 3:
            achievements.append("triple_winner")
        if player_entry.wins >= 5:
            achievements.append("serial_winner")

        # Podiums
        if player_entry.podiums >= 1:
            achievements.append("first_podium")
        if player_entry.podiums >= 5:
            achievements.append("podium_regular")

        # Poles
        if player_entry.poles >= 1:
            achievements.append("first_pole")
        if player_entry.poles >= 3:
            achievements.append("qualifying_star")

        # Fastest laps
        if player_entry.fastest_laps >= 1:
            achievements.append("first_fastest_lap")

        # Championship position
        sorted_standings = sorted(
            standings.driver_standings,
            key=lambda x: x.points,
            reverse=True,
        )
        player_position = next(
            (i + 1 for i, e in enumerate(sorted_standings) if e.driver_id == player_id),
            None
        )

        if player_position:
            if player_position == 1:
                achievements.append("championship_leader")
            if player_position <= 3:
                achievements.append("title_contender")
            if player_position <= 5:
                achievements.append("top_5_championship")

    # Check event flags for special achievements
    event_flags = save.event_flags
    if event_flags.get("rain_master_performance"):
        achievements.append("rain_master_performance")
    if event_flags.get("comeback_drive"):
        achievements.append("comeback_drive")
    if event_flags.get("perfect_weekend"):
        achievements.append("perfect_weekend")

    return achievements


def _format_achievement(achievement_id: str) -> str:
    """Format achievement ID for display."""
    labels = {
        "first_win": "Win a race",
        "triple_winner": "Win 3 races",
        "serial_winner": "Win 5 races",
        "first_podium": "Finish on the podium",
        "podium_regular": "5 podium finishes",
        "first_pole": "Take pole position",
        "qualifying_star": "3 pole positions",
        "first_fastest_lap": "Set a fastest lap",
        "championship_leader": "Lead the championship",
        "title_contender": "Finish top 3 in championship",
        "top_5_championship": "Finish top 5 in championship",
        "rain_master_performance": "Excel in wet conditions",
        "comeback_drive": "Recover 5+ positions in a race",
        "perfect_weekend": "Pole, fastest lap, and win",
    }
    return labels.get(achievement_id, achievement_id.replace("_", " ").title())


def _apply_node_unlock(
    profile: DevelopmentProfile,
    node: SkillTreeNode,
    current_date: str,
) -> DevelopmentProfile:
    """
    Apply a node unlock to the profile.

    Deducts points, adds node to unlocked list, creates history entry.
    """
    # Create new profile with modifications
    new_unlocked = profile.unlocked_node_ids + [node.id]
    new_points = profile.current_points - node.cost

    # Add history entry
    history_entry = DevelopmentHistoryEntry(
        date=current_date,
        source="skill_unlock",
        development_points_gained=-node.cost,
        node_unlocked=node.id,
        summary=f"Unlocked skill: {node.name}",
    )

    new_history = profile.history + [history_entry]
    if len(new_history) > 50:
        new_history = new_history[-50:]

    return profile.model_copy(
        update={
            "current_points": new_points,
            "unlocked_node_ids": new_unlocked,
            "history": new_history,
        }
    )


def _apply_node_effects(player: Driver, node: SkillTreeNode) -> Driver:
    """
    Apply a node's effects to the player's attributes.

    Returns updated driver.
    """
    effects = node.effects
    if not effects.attribute_bonuses:
        return player

    # Apply attribute bonuses
    new_attrs = player.attributes
    for attr, bonus in effects.attribute_bonuses.items():
        current = getattr(new_attrs, attr, None)
        if current is not None:
            new_val = max(0, min(99, current + bonus))
            new_attrs = new_attrs.model_copy(update={attr: new_val})

    return player.model_copy(update={"attributes": new_attrs})


def _apply_trait_effects(player: Driver, trait: DriverTrait) -> Driver:
    """
    Apply a trait's effects to the player's attributes.

    Returns updated driver.
    """
    effects = trait.positive_effects.attribute_modifiers
    if not effects:
        return player

    new_attrs = player.attributes
    for attr, bonus in effects.items():
        current = getattr(new_attrs, attr, None)
        if current is not None:
            new_val = max(0, min(99, current + bonus))
            new_attrs = new_attrs.model_copy(update={attr: new_val})

    # Also apply any drawback attribute modifiers
    drawbacks = trait.drawbacks.attribute_modifiers
    for attr, penalty in drawbacks.items():
        current = getattr(new_attrs, attr, None)
        if current is not None:
            new_val = max(0, min(99, current + penalty))
            new_attrs = new_attrs.model_copy(update={attr: new_val})

    return player.model_copy(update={"attributes": new_attrs})


def _get_recommended_nodes(
    branches: list[SkillBranchInfo],
    profile: DevelopmentProfile,
    player: Driver,
) -> list[str]:
    """
    Get recommended nodes based on player state and affordability.

    Returns list of node IDs.
    """
    recommended: list[str] = []

    # Find all available nodes the player can afford
    affordable_available = []
    for branch in branches:
        for node_info in branch.nodes:
            if node_info.state == "available" and node_info.can_afford:
                affordable_available.append((node_info, branch.branch_id))

    if not affordable_available:
        return recommended

    # Prioritize by:
    # 1. Major nodes (trait unlocks)
    # 2. Nodes in branches with high XP
    # 3. Lower tier nodes first (build foundation)

    sorted_nodes = sorted(
        affordable_available,
        key=lambda x: (
            not x[0].node.is_major_node,  # Major nodes first
            -profile.get_branch_xp(x[1]),  # Higher XP branches first
            x[0].node.tier,  # Lower tiers first
        ),
    )

    # Return top 3 recommendations
    return [n[0].node.id for n in sorted_nodes[:3]]
