"""Models for simplified AI driver development."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


# AI trait categories
AITraitCategory = Literal["pace", "racecraft", "mental", "technical", "media"]

# Protection tiers for elite drivers
ProtectionTier = Literal["untouchable", "protected", "standard", "vulnerable"]


class AITrait(AppModel):
    """A simplified trait that AI drivers can unlock."""

    id: str
    name: str
    description: str
    category: AITraitCategory

    # Attribute bonuses when trait is active
    attribute_bonuses: dict[str, int] = Field(default_factory=dict)

    # Minimum rating in primary attribute to unlock
    min_primary_attribute: int = 80

    # Weight for trait unlock chance (higher = more common)
    unlock_weight: int = 10


# Predefined AI traits
AI_TRAITS: list[AITrait] = [
    # Pace traits
    AITrait(
        id="elite_qualifier",
        name="Elite Qualifier",
        description="Exceptional one-lap pace and qualifying consistency.",
        category="pace",
        attribute_bonuses={"qualifying": 3, "confidence": 2},
        min_primary_attribute=85,
        unlock_weight=8,
    ),
    AITrait(
        id="late_braker",
        name="Late Braker",
        description="Brakes later than most, gaining time in braking zones.",
        category="pace",
        attribute_bonuses={"pace": 2, "racecraft": 1},
        min_primary_attribute=82,
        unlock_weight=10,
    ),

    # Racecraft traits
    AITrait(
        id="reckless_attacker",
        name="Reckless Attacker",
        description="Aggressive overtaker who takes risks.",
        category="racecraft",
        attribute_bonuses={"racecraft": 2, "aggression": 3},
        min_primary_attribute=78,
        unlock_weight=12,
    ),
    AITrait(
        id="defensive_master",
        name="Defensive Master",
        description="Expert at defending position under pressure.",
        category="racecraft",
        attribute_bonuses={"racecraft": 2, "awareness": 2},
        min_primary_attribute=82,
        unlock_weight=8,
    ),
    AITrait(
        id="strong_starter",
        name="Strong Starter",
        description="Consistently gains positions on race starts.",
        category="racecraft",
        attribute_bonuses={"starts": 4, "awareness": 1},
        min_primary_attribute=80,
        unlock_weight=10,
    ),

    # Mental traits
    AITrait(
        id="consistent_finisher",
        name="Consistent Finisher",
        description="Rarely makes mistakes, always extracts maximum points.",
        category="mental",
        attribute_bonuses={"consistency": 3, "discipline": 2},
        min_primary_attribute=85,
        unlock_weight=8,
    ),
    AITrait(
        id="pressure_performer",
        name="Pressure Performer",
        description="Performs best in high-pressure situations.",
        category="mental",
        attribute_bonuses={"pressure": 3, "composure": 2},
        min_primary_attribute=85,
        unlock_weight=6,
    ),
    AITrait(
        id="comeback_king",
        name="Comeback King",
        description="Known for remarkable recovery drives.",
        category="mental",
        attribute_bonuses={"racecraft": 2, "focus": 2, "composure": 1},
        min_primary_attribute=80,
        unlock_weight=8,
    ),

    # Technical traits
    AITrait(
        id="tire_whisperer",
        name="Tire Whisperer",
        description="Exceptional tire management skills.",
        category="technical",
        attribute_bonuses={"tire_management": 4, "adaptability": 1},
        min_primary_attribute=85,
        unlock_weight=8,
    ),
    AITrait(
        id="wet_specialist",
        name="Wet Specialist",
        description="Comes alive in wet and changing conditions.",
        category="technical",
        attribute_bonuses={"wet_weather": 4, "adaptability": 2},
        min_primary_attribute=82,
        unlock_weight=10,
    ),
    AITrait(
        id="technical_leader",
        name="Technical Leader",
        description="Excellent technical feedback drives car development.",
        category="technical",
        attribute_bonuses={"technical_feedback": 3, "adaptability": 1},
        min_primary_attribute=80,
        unlock_weight=10,
    ),

    # Media traits
    AITrait(
        id="media_star",
        name="Media Star",
        description="Natural media presence, highly marketable.",
        category="media",
        attribute_bonuses={"marketability": 4, "sponsor_value": 3},
        min_primary_attribute=75,
        unlock_weight=12,
    ),
    AITrait(
        id="fan_favorite",
        name="Fan Favorite",
        description="Beloved by fans for personality and racing style.",
        category="media",
        attribute_bonuses={"marketability": 3, "reputation": 2},
        min_primary_attribute=70,
        unlock_weight=15,
    ),
]

AI_TRAIT_MAP: dict[str, AITrait] = {trait.id: trait for trait in AI_TRAITS}


class AIDriverDevelopmentState(AppModel):
    """Tracks AI driver's development state."""

    # Unlocked traits
    trait_ids: list[str] = Field(default_factory=list)

    # Protection tier (determined by driver's elite status)
    protection_tier: ProtectionTier = "standard"

    # Regression tracking
    consecutive_decline_seasons: int = 0
    peak_rating: int = 0  # Highest overall rating achieved

    # Development history
    last_season_rating_change: int = 0
    total_career_growth: int = 0


class DriverDevelopmentProfile(AppModel):
    """
    Complete development profile for a driver.

    This is what gets stored in the save game for each AI driver.
    """

    driver_id: str
    state: AIDriverDevelopmentState = Field(default_factory=AIDriverDevelopmentState)


def get_trait(trait_id: str) -> AITrait | None:
    """Get a trait by ID."""
    return AI_TRAIT_MAP.get(trait_id)


def get_traits_by_category(category: AITraitCategory) -> list[AITrait]:
    """Get all traits in a category."""
    return [t for t in AI_TRAITS if t.category == category]


def determine_protection_tier(
    driver_age: int,
    overall_rating: int,
    career_wins: int,
    is_world_champion: bool,
    series: str,
) -> ProtectionTier:
    """
    Determine a driver's protection tier based on their status.

    Protection affects how much a driver can regress:
    - untouchable: Max/Lando/Leclerc tier - minimal regression
    - protected: Established top drivers - slow regression
    - standard: Normal drivers - standard regression
    - vulnerable: Struggling/older drivers - faster regression
    """
    # World champions under 35 are untouchable
    if is_world_champion and driver_age < 35:
        return "untouchable"

    # Elite rating + significant wins = untouchable
    if overall_rating >= 92 and career_wins >= 15:
        return "untouchable"

    # High rating + wins OR being a top F1 driver = protected
    if overall_rating >= 88 and career_wins >= 5:
        return "protected"

    if series == "F1" and overall_rating >= 85:
        return "protected"

    # Young high-potential drivers get some protection
    if driver_age <= 25 and overall_rating >= 82:
        return "protected"

    # Older drivers with declining performance are vulnerable
    if driver_age >= 35 and overall_rating < 80:
        return "vulnerable"

    if driver_age >= 38:
        return "vulnerable"

    return "standard"


# Development category weights for different driver profiles
DEVELOPMENT_CATEGORIES = {
    "pace": ["pace", "qualifying"],
    "racecraft": ["racecraft", "starts", "awareness"],
    "consistency": ["consistency", "discipline", "focus"],
    "technical": ["tire_management", "wet_weather", "technical_feedback", "adaptability"],
    "mental": ["pressure", "composure", "confidence"],
    "media": ["marketability", "sponsor_value", "reputation"],
}


def get_driver_overall_rating(driver) -> int:
    """Calculate a driver's overall rating from attributes."""
    attrs = driver.attributes
    core_attrs = [
        attrs.pace,
        attrs.qualifying,
        attrs.racecraft,
        attrs.consistency,
        attrs.tire_management,
    ]
    return round(sum(core_attrs) / len(core_attrs))
