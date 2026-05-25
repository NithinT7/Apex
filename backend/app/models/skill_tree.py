"""Skill tree node and configuration models."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel
from app.models.development_profile import DevelopmentBranch


class SkillNodeEffect(AppModel):
    """Effects applied when a skill node is unlocked."""

    # Attribute bonuses (permanent)
    attribute_bonuses: dict[str, int] = Field(default_factory=dict)

    # XP bonuses (one-time or passive)
    xp_bonuses: dict[str, int] = Field(default_factory=dict)

    # Special flags/modifiers
    special_effects: list[str] = Field(default_factory=list)


class SkillTreeNode(AppModel):
    """A single node in the skill tree."""

    id: str
    branch: DevelopmentBranch
    name: str
    description: str

    # Costs
    cost: int  # Development points required
    xp_required: int  # Branch XP threshold required

    # Prerequisites
    required_node_ids: list[str] = Field(default_factory=list)
    required_traits: list[str] = Field(default_factory=list)
    required_achievements: list[str] = Field(default_factory=list)

    # Effects when unlocked
    effects: SkillNodeEffect = Field(default_factory=SkillNodeEffect)

    # Trait unlock (optional - for major nodes)
    unlocks_trait_id: str | None = None

    # Node classification
    is_major_node: bool = False
    tier: int = 1  # 1-4, higher = more powerful

    # Visual/UI hints
    icon: str | None = None
    position_x: int = 0  # For tree layout
    position_y: int = 0


class SkillTreeBranch(AppModel):
    """A branch of the skill tree containing multiple nodes."""

    id: DevelopmentBranch
    name: str
    description: str
    icon: str | None = None
    color: str | None = None  # Hex color for UI
    nodes: list[SkillTreeNode] = Field(default_factory=list)


class SkillTreeConfig(AppModel):
    """Complete skill tree configuration."""

    version: str = "1.0.0"
    branches: list[SkillTreeBranch] = Field(default_factory=list)

    def get_node(self, node_id: str) -> SkillTreeNode | None:
        """Find a node by ID across all branches."""
        for branch in self.branches:
            for node in branch.nodes:
                if node.id == node_id:
                    return node
        return None

    def get_branch(self, branch_id: DevelopmentBranch) -> SkillTreeBranch | None:
        """Find a branch by ID."""
        return next((b for b in self.branches if b.id == branch_id), None)

    def get_nodes_for_branch(self, branch_id: DevelopmentBranch) -> list[SkillTreeNode]:
        """Get all nodes for a specific branch."""
        branch = self.get_branch(branch_id)
        return branch.nodes if branch else []

    def validate_prerequisites(
        self,
        node_id: str,
        unlocked_nodes: list[str],
        unlocked_traits: list[str],
        achievements: list[str],
    ) -> tuple[bool, str]:
        """
        Check if a node's prerequisites are met.

        Returns (is_valid, error_message).
        """
        node = self.get_node(node_id)
        if not node:
            return False, f"Node {node_id} not found"

        # Check required nodes
        for req_node in node.required_node_ids:
            if req_node not in unlocked_nodes:
                return False, f"Requires node: {req_node}"

        # Check required traits
        for req_trait in node.required_traits:
            if req_trait not in unlocked_traits:
                return False, f"Requires trait: {req_trait}"

        # Check required achievements
        for req_achievement in node.required_achievements:
            if req_achievement not in achievements:
                return False, f"Requires achievement: {req_achievement}"

        return True, ""


def validate_skill_tree_config(config: SkillTreeConfig) -> list[str]:
    """
    Validate a skill tree configuration for consistency.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    all_node_ids: set[str] = set()

    for branch in config.branches:
        for node in branch.nodes:
            # Check for duplicate IDs
            if node.id in all_node_ids:
                errors.append(f"Duplicate node ID: {node.id}")
            all_node_ids.add(node.id)

            # Check branch matches
            if node.branch != branch.id:
                errors.append(f"Node {node.id} branch mismatch: {node.branch} vs {branch.id}")

            # Check tier is valid
            if not 1 <= node.tier <= 4:
                errors.append(f"Node {node.id} has invalid tier: {node.tier}")

            # Check cost is positive
            if node.cost < 0:
                errors.append(f"Node {node.id} has negative cost: {node.cost}")

            # Check XP required is non-negative
            if node.xp_required < 0:
                errors.append(f"Node {node.id} has negative xp_required: {node.xp_required}")

    # Validate prerequisites reference existing nodes
    for branch in config.branches:
        for node in branch.nodes:
            for req_node in node.required_node_ids:
                if req_node not in all_node_ids:
                    errors.append(f"Node {node.id} requires non-existent node: {req_node}")

    return errors
