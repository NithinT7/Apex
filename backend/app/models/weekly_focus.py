"""Weekly focus model for the new development system."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel
from app.models.development_profile import DevelopmentBranch


FocusCategory = Literal[
    "driving",       # Pure driving skill focuses
    "physical",      # Fitness and physical preparation
    "technical",     # Technical/engineering focuses
    "mental",        # Mental preparation
    "media",         # Media and sponsor activities
    "academy",       # Academy-related activities
    "strategic",     # Race strategy and analysis
    "recovery",      # Rest and recovery
]


class FocusUnlockRequirements(AppModel):
    """Requirements to have a focus option available."""

    # Minimum attribute values
    min_attributes: dict[str, int] = Field(default_factory=dict)

    # Minimum branch XP levels
    min_branch_xp: dict[str, int] = Field(default_factory=dict)

    # Required traits
    required_traits: list[str] = Field(default_factory=list)

    # Required skill nodes
    required_nodes: list[str] = Field(default_factory=list)

    # Phase requirements (e.g., only available in certain career phases)
    required_phase: list[str] = Field(default_factory=list)

    # Other conditions
    conditions: list[str] = Field(default_factory=list)


class FocusRiskEffect(AppModel):
    """Effects that can occur if a focus has negative outcomes."""

    # Chance of risk occurring (0-100)
    chance: int = 0

    # XP penalties (negative values)
    xp_penalties: dict[str, int] = Field(default_factory=dict)

    # Attribute penalties
    attribute_penalties: dict[str, int] = Field(default_factory=dict)

    # Relationship penalties
    relationship_penalties: dict[str, int] = Field(default_factory=dict)

    # Narrative description of what went wrong
    risk_narrative: str = ""


class WeeklyFocus(AppModel):
    """A weekly focus option that players can choose between races."""

    id: str
    name: str
    category: FocusCategory
    description: str

    # Primary XP gain branch
    primary_xp_branch: DevelopmentBranch

    # Secondary XP branches (smaller gains)
    secondary_xp_branches: list[DevelopmentBranch] = Field(default_factory=list)

    # XP amounts gained
    primary_xp_amount: int = 15  # Base XP for primary branch
    secondary_xp_amount: int = 5  # Base XP for secondary branches

    # Attribute effects (temporary or permanent modifiers)
    attribute_xp_effects: dict[str, int] = Field(default_factory=dict)

    # Relationship effects
    relationship_effects: dict[str, int] = Field(default_factory=dict)

    # Marketability effects
    marketability_effects: int = 0

    # Academy effects
    academy_effects: int = 0

    # Unlock requirements
    unlock_requirements: FocusUnlockRequirements = Field(default_factory=FocusUnlockRequirements)

    # Risk effects (optional)
    risk_effects: FocusRiskEffect | None = None

    # Duration in days (affects how many focuses can be done between races)
    duration_days: int = 2

    # Flavor/narrative
    flavor_text: str | None = None
    icon: str | None = None

    # Whether this focus can be repeated in the same between-race period
    repeatable: bool = False

    # Whether this focus is mutually exclusive with others
    exclusive_with: list[str] = Field(default_factory=list)


class FocusOutcome(AppModel):
    """Result of completing a weekly focus."""

    focus_id: str
    focus_name: str
    success: bool

    # XP gained
    xp_gained: dict[str, int] = Field(default_factory=dict)

    # Other effects applied
    attribute_changes: dict[str, int] = Field(default_factory=dict)
    relationship_changes: dict[str, int] = Field(default_factory=dict)
    marketability_change: int = 0
    academy_change: int = 0

    # Narrative description
    narrative: str = ""

    # If a trait was unlocked
    trait_unlocked: str | None = None


class WeeklyFocusConfig(AppModel):
    """Complete weekly focus configuration."""

    version: str = "1.0.0"
    focuses: list[WeeklyFocus] = Field(default_factory=list)

    def get_focus(self, focus_id: str) -> WeeklyFocus | None:
        """Find a focus by ID."""
        return next((f for f in self.focuses if f.id == focus_id), None)

    def get_focuses_by_category(self, category: FocusCategory) -> list[WeeklyFocus]:
        """Get all focuses in a category."""
        return [f for f in self.focuses if f.category == category]


def validate_weekly_focus_config(config: WeeklyFocusConfig) -> list[str]:
    """
    Validate a weekly focus configuration for consistency.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    all_focus_ids: set[str] = set()

    for focus in config.focuses:
        # Check for duplicate IDs
        if focus.id in all_focus_ids:
            errors.append(f"Duplicate focus ID: {focus.id}")
        all_focus_ids.add(focus.id)

        # Check duration is positive
        if focus.duration_days < 1:
            errors.append(f"Focus {focus.id} has invalid duration: {focus.duration_days}")

        # Check primary XP amount is positive
        if focus.primary_xp_amount < 0:
            errors.append(f"Focus {focus.id} has negative primary_xp_amount")

        # Check secondary XP amount is non-negative
        if focus.secondary_xp_amount < 0:
            errors.append(f"Focus {focus.id} has negative secondary_xp_amount")

        # Check risk chance is valid
        if focus.risk_effects and not 0 <= focus.risk_effects.chance <= 100:
            errors.append(f"Focus {focus.id} has invalid risk chance: {focus.risk_effects.chance}")

    # Validate exclusive_with references
    for focus in config.focuses:
        for exclusive_id in focus.exclusive_with:
            if exclusive_id not in all_focus_ids:
                errors.append(f"Focus {focus.id} references non-existent exclusive focus: {exclusive_id}")

    return errors


def check_focus_availability(
    focus: WeeklyFocus,
    attributes: dict[str, int],
    branch_xp: dict[str, int],
    unlocked_traits: list[str],
    unlocked_nodes: list[str],
    current_phase: str,
) -> tuple[bool, list[str]]:
    """
    Check if a focus is available to the player.

    Returns (is_available, list_of_unmet_requirements).
    """
    unmet: list[str] = []
    reqs = focus.unlock_requirements

    # Check minimum attributes
    for attr, min_val in reqs.min_attributes.items():
        current_val = attributes.get(attr, 0)
        if current_val < min_val:
            unmet.append(f"Need {attr} >= {min_val} (have {current_val})")

    # Check minimum branch XP
    for branch, min_xp in reqs.min_branch_xp.items():
        current_xp = branch_xp.get(branch, 0)
        if current_xp < min_xp:
            unmet.append(f"Need {min_xp} XP in {branch} (have {current_xp})")

    # Check required traits
    for trait_id in reqs.required_traits:
        if trait_id not in unlocked_traits:
            unmet.append(f"Need trait: {trait_id}")

    # Check required nodes
    for node_id in reqs.required_nodes:
        if node_id not in unlocked_nodes:
            unmet.append(f"Need skill: {node_id}")

    # Check phase requirements
    if reqs.required_phase and current_phase not in reqs.required_phase:
        unmet.append(f"Only available in phases: {', '.join(reqs.required_phase)}")

    return len(unmet) == 0, unmet
