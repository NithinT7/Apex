"""Development profile model for the new skill tree and weekly focus system."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


# Development branches for XP tracking
DevelopmentBranch = Literal[
    "raw_pace",
    "racecraft",
    "tire_strategy",
    "mentality_pressure",
    "technical_feedback",
    "starts_execution",
    "media_marketability",
    "academy_path",
]

ALL_BRANCHES: list[DevelopmentBranch] = [
    "raw_pace",
    "racecraft",
    "tire_strategy",
    "mentality_pressure",
    "technical_feedback",
    "starts_execution",
    "media_marketability",
    "academy_path",
]


class DevelopmentHistoryEntry(AppModel):
    """A single entry in the development history log."""

    date: str  # ISO date or round identifier
    round_id: str | None = None
    source: Literal[
        "race_result",
        "weekly_focus",
        "skill_unlock",
        "trait_unlock",
        "season_start",
        "milestone",
        "interview",
        "sponsor_activity",
        "special_event",
    ]
    xp_gained: dict[str, int] = Field(default_factory=dict)  # branch -> XP
    development_points_gained: int = 0
    node_unlocked: str | None = None
    trait_unlocked: str | None = None
    summary: str = ""


class DevelopmentProfile(AppModel):
    """
    Tracks a driver's skill tree progression, XP, and development history.

    This replaces the old DevelopmentState for players while maintaining
    backwards compatibility. AI drivers may have simplified or no profiles.
    """

    # Development points (currency for unlocking nodes)
    current_points: int = 0
    total_points_earned: int = 0

    # XP by branch (progress toward unlocking higher-tier nodes)
    branch_xp: dict[str, int] = Field(default_factory=lambda: {
        "raw_pace": 0,
        "racecraft": 0,
        "tire_strategy": 0,
        "mentality_pressure": 0,
        "technical_feedback": 0,
        "starts_execution": 0,
        "media_marketability": 0,
        "academy_path": 0,
    })

    # Unlocked skill tree nodes
    unlocked_node_ids: list[str] = Field(default_factory=list)

    # Unlocked driver traits
    unlocked_trait_ids: list[str] = Field(default_factory=list)

    # Currently active weekly focus (None if not set)
    active_focus_id: str | None = None

    # Development history log
    history: list[DevelopmentHistoryEntry] = Field(default_factory=list)

    # Cached trait bonuses (recalculated when traits change)
    trait_bonuses: dict[str, int] = Field(default_factory=dict)

    def get_branch_xp(self, branch: DevelopmentBranch) -> int:
        """Get XP for a specific branch."""
        return self.branch_xp.get(branch, 0)

    def add_branch_xp(self, branch: DevelopmentBranch, amount: int) -> None:
        """Add XP to a specific branch."""
        current = self.branch_xp.get(branch, 0)
        self.branch_xp[branch] = current + amount

    def has_unlocked_node(self, node_id: str) -> bool:
        """Check if a skill tree node is unlocked."""
        return node_id in self.unlocked_node_ids

    def has_unlocked_trait(self, trait_id: str) -> bool:
        """Check if a trait is unlocked."""
        return trait_id in self.unlocked_trait_ids

    def add_history_entry(self, entry: DevelopmentHistoryEntry) -> None:
        """Add an entry to the development history."""
        self.history.append(entry)
        # Keep only last 50 entries to avoid bloat
        if len(self.history) > 50:
            self.history = self.history[-50:]


def create_default_development_profile() -> DevelopmentProfile:
    """Create a default development profile for new drivers or migration."""
    return DevelopmentProfile(
        current_points=0,
        total_points_earned=0,
        branch_xp={branch: 0 for branch in ALL_BRANCHES},
        unlocked_node_ids=[],
        unlocked_trait_ids=[],
        active_focus_id=None,
        history=[],
        trait_bonuses={},
    )


def create_player_starting_profile(
    potential: int = 85,
    starting_points: int = 3,
    branch_xp_bonus: int = 0,
) -> DevelopmentProfile:
    """
    Create a starting development profile for a new player.

    Args:
        potential: The driver's hidden potential (affects base XP)
        starting_points: Development points to start with (varies by difficulty)
        branch_xp_bonus: Bonus XP to add to all branches (varies by difficulty)

    Player starts with some initial XP based on their prodigy status and difficulty.
    """
    # Players start with some XP to represent their talent
    base_xp = max(0, (potential - 70) * 2) + branch_xp_bonus

    return DevelopmentProfile(
        current_points=starting_points,
        total_points_earned=starting_points,
        branch_xp={
            "raw_pace": base_xp + 10,
            "racecraft": base_xp + 5,
            "tire_strategy": base_xp,
            "mentality_pressure": base_xp,
            "technical_feedback": base_xp,
            "starts_execution": base_xp + 5,
            "media_marketability": branch_xp_bonus,
            "academy_path": 10 + branch_xp_bonus,
        },
        unlocked_node_ids=[],
        unlocked_trait_ids=[],
        active_focus_id=None,
        history=[
            DevelopmentHistoryEntry(
                date="career_start",
                source="season_start",
                development_points_gained=starting_points,
                summary="Career begins with natural talent foundation.",
            )
        ],
        trait_bonuses={},
    )
