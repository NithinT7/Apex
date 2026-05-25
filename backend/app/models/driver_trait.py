"""Driver trait model for the new development system."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


TraitCategory = Literal[
    "driving",       # Pure driving skill traits
    "mental",        # Mental/psychological traits
    "technical",     # Technical/engineering traits
    "media",         # Media/marketability traits
    "strategic",     # Race strategy traits
    "physical",      # Physical traits
    "situational",   # Context-specific traits
]

TraitRarity = Literal[
    "common",        # Easy to unlock, modest effects
    "uncommon",      # Moderate requirements, solid effects
    "rare",          # Difficult to unlock, powerful effects
    "legendary",     # Very rare, game-changing effects
]


class TraitEffect(AppModel):
    """Effects a trait has on driver performance or career."""

    # Attribute modifiers (can be positive or negative)
    attribute_modifiers: dict[str, int] = Field(default_factory=dict)

    # Situational bonuses (applied in specific conditions)
    situational_bonuses: dict[str, int] = Field(default_factory=dict)

    # Special flags/behaviors
    special_flags: list[str] = Field(default_factory=list)

    # Narrative/perception effects
    perception_modifiers: dict[str, int] = Field(default_factory=dict)


class TraitUnlockRequirements(AppModel):
    """Requirements to unlock a trait."""

    # Minimum branch XP levels
    branch_xp: dict[str, int] = Field(default_factory=dict)

    # Required skill nodes to be unlocked
    required_nodes: list[str] = Field(default_factory=list)

    # Required other traits
    required_traits: list[str] = Field(default_factory=list)

    # Required achievements (race wins, podiums, etc.)
    achievements: list[str] = Field(default_factory=list)

    # Minimum attribute values
    min_attributes: dict[str, int] = Field(default_factory=dict)

    # Other conditions (e.g., "championship_position <= 3")
    conditions: list[str] = Field(default_factory=list)


class DriverTrait(AppModel):
    """A trait that can be unlocked by a driver."""

    id: str
    name: str
    category: TraitCategory
    description: str

    # Effects when trait is active
    positive_effects: TraitEffect = Field(default_factory=TraitEffect)
    drawbacks: TraitEffect = Field(default_factory=TraitEffect)

    # Unlock requirements
    unlock_requirements: TraitUnlockRequirements = Field(default_factory=TraitUnlockRequirements)

    # Rarity classification
    rarity: TraitRarity = "common"

    # Flavor/narrative
    flavor_text: str | None = None
    icon: str | None = None

    # Mutually exclusive traits (can't have both)
    incompatible_traits: list[str] = Field(default_factory=list)

    # Whether this trait can be lost/degraded
    is_permanent: bool = True


class TraitConfig(AppModel):
    """Complete trait configuration."""

    version: str = "1.0.0"
    traits: list[DriverTrait] = Field(default_factory=list)

    def get_trait(self, trait_id: str) -> DriverTrait | None:
        """Find a trait by ID."""
        return next((t for t in self.traits if t.id == trait_id), None)

    def get_traits_by_category(self, category: TraitCategory) -> list[DriverTrait]:
        """Get all traits in a category."""
        return [t for t in self.traits if t.category == category]

    def get_traits_by_rarity(self, rarity: TraitRarity) -> list[DriverTrait]:
        """Get all traits of a rarity level."""
        return [t for t in self.traits if t.rarity == rarity]


def validate_trait_config(config: TraitConfig) -> list[str]:
    """
    Validate a trait configuration for consistency.

    Returns a list of error messages (empty if valid).
    """
    errors: list[str] = []
    all_trait_ids: set[str] = set()

    for trait in config.traits:
        # Check for duplicate IDs
        if trait.id in all_trait_ids:
            errors.append(f"Duplicate trait ID: {trait.id}")
        all_trait_ids.add(trait.id)

        # Check incompatible traits reference existing traits
        for incompat in trait.incompatible_traits:
            if incompat == trait.id:
                errors.append(f"Trait {trait.id} is incompatible with itself")

    # Validate incompatible traits exist (second pass)
    for trait in config.traits:
        for incompat in trait.incompatible_traits:
            if incompat not in all_trait_ids:
                errors.append(f"Trait {trait.id} references non-existent incompatible trait: {incompat}")

        # Validate required traits exist
        for req_trait in trait.unlock_requirements.required_traits:
            if req_trait not in all_trait_ids:
                errors.append(f"Trait {trait.id} requires non-existent trait: {req_trait}")

    return errors


def check_trait_unlock_requirements(
    trait: DriverTrait,
    branch_xp: dict[str, int],
    unlocked_nodes: list[str],
    unlocked_traits: list[str],
    achievements: list[str],
    attributes: dict[str, int],
) -> tuple[bool, list[str]]:
    """
    Check if a trait's unlock requirements are met.

    Returns (is_unlockable, list_of_unmet_requirements).
    """
    unmet: list[str] = []
    reqs = trait.unlock_requirements

    # Check branch XP
    for branch, required_xp in reqs.branch_xp.items():
        current_xp = branch_xp.get(branch, 0)
        if current_xp < required_xp:
            unmet.append(f"Need {required_xp} XP in {branch} (have {current_xp})")

    # Check required nodes
    for node_id in reqs.required_nodes:
        if node_id not in unlocked_nodes:
            unmet.append(f"Need skill: {node_id}")

    # Check required traits
    for trait_id in reqs.required_traits:
        if trait_id not in unlocked_traits:
            unmet.append(f"Need trait: {trait_id}")

    # Check achievements
    for achievement in reqs.achievements:
        if achievement not in achievements:
            unmet.append(f"Need achievement: {achievement}")

    # Check minimum attributes
    for attr, min_val in reqs.min_attributes.items():
        current_val = attributes.get(attr, 0)
        if current_val < min_val:
            unmet.append(f"Need {attr} >= {min_val} (have {current_val})")

    return len(unmet) == 0, unmet
