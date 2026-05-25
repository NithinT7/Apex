"""
Player balance and difficulty configuration.

This module defines the difficulty presets that determine how powerful
a created player can become over their career.

Philosophy:
- The player is a promising/prodigy driver
- They SHOULD be able to become elite (94-99 OVR) with good development
- Different presets offer different starting points and growth rates
- Soft caps can be broken through with traits and achievements
- F1 rookie adaptation makes the transition hard, not the player's ceiling
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.base import AppModel


# =============================================================================
# Difficulty Preset Types
# =============================================================================

DifficultyPreset = Literal["prodigy", "realistic_prospect", "underdog", "brutal_realism"]


@dataclass
class DifficultyConfig:
    """Configuration for a difficulty preset."""

    id: DifficultyPreset
    name: str
    description: str
    flavor_text: str

    # Starting overall rating range (average of core attributes)
    starting_ovr_min: int
    starting_ovr_max: int

    # Hidden potential range (max attribute ceiling without breakthroughs)
    potential_min: int
    potential_max: int

    # Development rate range (affects AI development speed too)
    development_rate_min: int
    development_rate_max: int

    # Development point multiplier (1.0 = normal)
    dev_point_multiplier: float

    # XP gain multiplier
    xp_multiplier: float

    # Soft cap before needing traits/achievements to break through
    soft_cap: int

    # Hard cap (absolute maximum, requires special traits)
    hard_cap: int

    # Starting development points bonus
    starting_dev_points: int

    # Starting branch XP bonus (applied to all branches)
    starting_branch_xp_bonus: int


# =============================================================================
# Difficulty Presets
# =============================================================================

DIFFICULTY_PRESETS: dict[DifficultyPreset, DifficultyConfig] = {
    "prodigy": DifficultyConfig(
        id="prodigy",
        name="Prodigy",
        description="Generational talent destined for greatness",
        flavor_text="You are the next big thing. Everyone knows it. Now prove it.",
        starting_ovr_min=76,
        starting_ovr_max=82,
        potential_min=96,
        potential_max=99,
        development_rate_min=78,
        development_rate_max=88,
        dev_point_multiplier=1.3,
        xp_multiplier=1.25,
        soft_cap=94,
        hard_cap=99,
        starting_dev_points=5,
        starting_branch_xp_bonus=25,
    ),
    "realistic_prospect": DifficultyConfig(
        id="realistic_prospect",
        name="Realistic Prospect",
        description="Strong junior destined for F1, but must earn elite status",
        flavor_text="You have the talent to make it. How far you go is up to you.",
        starting_ovr_min=72,
        starting_ovr_max=78,
        potential_min=92,
        potential_max=97,
        development_rate_min=70,
        development_rate_max=82,
        dev_point_multiplier=1.0,
        xp_multiplier=1.0,
        soft_cap=92,
        hard_cap=98,
        starting_dev_points=3,
        starting_branch_xp_bonus=10,
    ),
    "underdog": DifficultyConfig(
        id="underdog",
        name="Underdog",
        description="Late bloomer with hidden potential",
        flavor_text="Nobody expects much. You'll show them.",
        starting_ovr_min=66,
        starting_ovr_max=73,
        potential_min=86,
        potential_max=94,
        development_rate_min=64,
        development_rate_max=76,
        dev_point_multiplier=0.85,
        xp_multiplier=0.9,
        soft_cap=88,
        hard_cap=96,
        starting_dev_points=2,
        starting_branch_xp_bonus=5,
    ),
    "brutal_realism": DifficultyConfig(
        id="brutal_realism",
        name="Brutal Realism",
        description="Harsh simulation - every point must be earned",
        flavor_text="The odds are against you. Most don't make it. Will you?",
        starting_ovr_min=60,
        starting_ovr_max=70,
        potential_min=82,
        potential_max=90,
        development_rate_min=55,
        development_rate_max=68,
        dev_point_multiplier=0.7,
        xp_multiplier=0.75,
        soft_cap=84,
        hard_cap=92,
        starting_dev_points=1,
        starting_branch_xp_bonus=0,
    ),
}

# Default difficulty for new careers
DEFAULT_DIFFICULTY: DifficultyPreset = "realistic_prospect"


def get_difficulty_config(preset: DifficultyPreset | str) -> DifficultyConfig:
    """Get the configuration for a difficulty preset."""
    if preset not in DIFFICULTY_PRESETS:
        # Fall back to default if unknown
        preset = DEFAULT_DIFFICULTY
    return DIFFICULTY_PRESETS[preset]


def get_all_difficulty_options() -> list[dict]:
    """Get all difficulty options for the frontend."""
    return [
        {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "flavorText": config.flavor_text,
            "startingOvrRange": f"{config.starting_ovr_min}-{config.starting_ovr_max}",
            "potentialRange": f"{config.potential_min}-{config.potential_max}",
            "developmentSpeed": _dev_speed_label(config.dev_point_multiplier),
            "recommended": config.id == "realistic_prospect",
        }
        for config in DIFFICULTY_PRESETS.values()
    ]


def _dev_speed_label(multiplier: float) -> str:
    """Convert multiplier to human-readable label."""
    if multiplier >= 1.2:
        return "Fast"
    elif multiplier >= 1.0:
        return "Medium-Fast"
    elif multiplier >= 0.8:
        return "Medium"
    else:
        return "Slow"


# =============================================================================
# F1 Rookie Adaptation System
# =============================================================================


@dataclass
class F1AdaptationState:
    """Tracks a driver's F1 rookie adaptation progress."""

    f1_races_completed: int = 0
    adaptation_progress: float = 0.0  # 0-100
    current_penalty: float = 0.0  # Effective rating penalty
    fully_adapted: bool = False


# F1 Adaptation constants
F1_ADAPTATION_RACES_MIN = 6  # Minimum races before full adaptation possible
F1_ADAPTATION_RACES_MAX = 12  # Maximum races (guaranteed full adaptation)
F1_ADAPTATION_BASE_PENALTY = 8  # Maximum penalty at start
F1_ADAPTATION_MIN_PENALTY = 0  # Minimum penalty when fully adapted


def calculate_f1_adaptation_penalty(
    f1_races: int,
    adaptability: int,
    confidence: int,
    recent_results_avg: float | None = None,
) -> float:
    """
    Calculate the F1 rookie adaptation penalty.

    The penalty decreases with:
    - More F1 races completed
    - Higher adaptability attribute
    - Higher confidence
    - Better recent race results

    Args:
        f1_races: Number of F1 races completed
        adaptability: Driver's adaptability attribute (1-100)
        confidence: Driver's confidence attribute (1-100)
        recent_results_avg: Average finishing position in last 3 races (lower = better)

    Returns:
        Effective rating penalty (0-8 typically)
    """
    if f1_races >= F1_ADAPTATION_RACES_MAX:
        return 0.0

    # Base progress from races completed
    race_progress = min(100, (f1_races / F1_ADAPTATION_RACES_MIN) * 80)

    # Adaptability bonus (high adaptability adapts faster)
    adaptability_bonus = max(0, (adaptability - 70) / 30) * 15

    # Confidence bonus
    confidence_bonus = max(0, (confidence - 60) / 40) * 10

    # Results bonus (good results speed up adaptation)
    results_bonus = 0
    if recent_results_avg is not None:
        if recent_results_avg <= 5:
            results_bonus = 15  # Podium contender
        elif recent_results_avg <= 10:
            results_bonus = 10  # Points finisher
        elif recent_results_avg <= 15:
            results_bonus = 5   # Midfield

    total_progress = min(100, race_progress + adaptability_bonus + confidence_bonus + results_bonus)

    # Calculate remaining penalty
    penalty_factor = 1.0 - (total_progress / 100)
    penalty = F1_ADAPTATION_BASE_PENALTY * penalty_factor

    return round(max(0, penalty), 1)


def get_f1_adaptation_state(
    save,
    player_id: str,
) -> F1AdaptationState:
    """Get the current F1 adaptation state for a player."""
    from app.models.save_game import SaveGame

    if not isinstance(save, SaveGame):
        return F1AdaptationState()

    player = next((d for d in save.drivers if d.id == player_id), None)
    if player is None or player.series != "F1":
        return F1AdaptationState(fully_adapted=True)

    # Count F1 races completed
    f1_races = 0
    for weekend in save.weekend_results:
        if weekend.feature:
            player_result = next(
                (r for r in weekend.feature.classification if r.driver_id == player_id),
                None,
            )
            if player_result:
                f1_races += 1

    # Get recent results average
    recent_positions = []
    for weekend in reversed(save.weekend_results[-5:]):
        if weekend.feature:
            player_result = next(
                (r for r in weekend.feature.classification if r.driver_id == player_id),
                None,
            )
            if player_result:
                recent_positions.append(player_result.position)

    recent_avg = sum(recent_positions) / len(recent_positions) if recent_positions else None

    penalty = calculate_f1_adaptation_penalty(
        f1_races=f1_races,
        adaptability=player.attributes.adaptability,
        confidence=player.attributes.confidence,
        recent_results_avg=recent_avg,
    )

    return F1AdaptationState(
        f1_races_completed=f1_races,
        adaptation_progress=100 - (penalty / F1_ADAPTATION_BASE_PENALTY * 100),
        current_penalty=penalty,
        fully_adapted=penalty == 0,
    )


# =============================================================================
# Soft Cap System
# =============================================================================


def get_effective_cap(
    base_potential: int,
    difficulty: DifficultyPreset | str,
    unlocked_traits: list[str],
    achievements: list[str],
) -> int:
    """
    Calculate the effective attribute cap for a player.

    Soft caps can be broken through with:
    - Certain trait unlocks
    - Career achievements (championships, podiums, etc.)

    Args:
        base_potential: The driver's hidden potential
        difficulty: The difficulty preset
        unlocked_traits: List of unlocked trait IDs
        achievements: List of achievement IDs earned

    Returns:
        The effective maximum attribute value
    """
    config = get_difficulty_config(difficulty)

    # Start with the soft cap
    cap = config.soft_cap

    # Trait bonuses
    cap_breaking_traits = {
        "one_lap_monster": 2,
        "tire_whisperer": 2,
        "rain_god": 2,
        "clutch_performer": 2,
        "future_champion": 3,
        "generational_talent": 4,
        "complete_driver": 3,
    }

    for trait in unlocked_traits:
        if trait in cap_breaking_traits:
            cap += cap_breaking_traits[trait]

    # Achievement bonuses
    achievement_bonuses = {
        "f2_champion": 2,
        "f2_race_winner": 1,
        "f1_podium": 2,
        "f1_race_winner": 3,
        "f1_pole": 1,
        "f1_champion": 4,
        "multiple_f1_wins": 2,
    }

    for achievement in achievements:
        if achievement in achievement_bonuses:
            cap += achievement_bonuses[achievement]

    # Can't exceed hard cap
    cap = min(cap, config.hard_cap)

    # Also limited by potential (but potential can exceed soft cap)
    return min(cap, max(base_potential, config.soft_cap))


def calculate_attribute_with_caps(
    base_value: int,
    potential: int,
    difficulty: DifficultyPreset | str,
    unlocked_traits: list[str] | None = None,
    achievements: list[str] | None = None,
    f1_adaptation_penalty: float = 0,
) -> int:
    """
    Calculate an attribute's effective value with all modifiers.

    Args:
        base_value: The raw attribute value
        potential: The driver's potential
        difficulty: The difficulty preset
        unlocked_traits: List of unlocked traits
        achievements: List of achievements
        f1_adaptation_penalty: Current F1 rookie penalty

    Returns:
        The effective attribute value after all modifiers
    """
    cap = get_effective_cap(
        potential,
        difficulty,
        unlocked_traits or [],
        achievements or [],
    )

    # Apply cap
    capped = min(base_value, cap)

    # Apply F1 adaptation penalty
    effective = capped - f1_adaptation_penalty

    return max(1, int(effective))


# =============================================================================
# Development Point Multipliers
# =============================================================================


def get_dev_point_multiplier(
    difficulty: DifficultyPreset | str,
    player_form: int = 50,
    championship_position: int | None = None,
) -> float:
    """
    Calculate the development point multiplier for point awards.

    Args:
        difficulty: The difficulty preset
        player_form: Current form (0-100)
        championship_position: Current championship standing (1 = leader)

    Returns:
        Multiplier to apply to development point gains
    """
    config = get_difficulty_config(difficulty)
    multiplier = config.dev_point_multiplier

    # Form bonus (high form = slightly faster development)
    if player_form >= 80:
        multiplier *= 1.1
    elif player_form >= 60:
        multiplier *= 1.05

    # Championship position bonus (fighting at front = more development)
    if championship_position is not None:
        if championship_position <= 3:
            multiplier *= 1.15
        elif championship_position <= 6:
            multiplier *= 1.08

    return multiplier


def get_xp_multiplier(difficulty: DifficultyPreset | str) -> float:
    """Get the XP gain multiplier for a difficulty preset."""
    return get_difficulty_config(difficulty).xp_multiplier


# =============================================================================
# Starting Attribute Generation
# =============================================================================


def generate_starting_attributes(
    difficulty: DifficultyPreset | str,
    background_effects: dict[str, int],
    archetype_effects: dict[str, int],
    seed: int,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Generate starting attributes and hidden stats for a new player.

    Args:
        difficulty: The difficulty preset
        background_effects: Attribute modifiers from background
        archetype_effects: Attribute modifiers from archetype
        seed: Random seed for deterministic generation

    Returns:
        Tuple of (visible_attributes, hidden_attributes)
    """
    import random

    rng = random.Random(seed)
    config = get_difficulty_config(difficulty)

    # Target OVR range
    target_ovr = rng.randint(config.starting_ovr_min, config.starting_ovr_max)

    # Core attributes that define OVR
    core_attrs = ["pace", "qualifying", "racecraft", "consistency", "tire_management", "pressure"]

    # Generate base attributes around target OVR
    attributes: dict[str, int] = {}

    # Core attributes cluster around target OVR with variance
    for attr in core_attrs:
        variance = rng.randint(-4, 4)
        base = target_ovr + variance
        attributes[attr] = _clamp(base)

    # Secondary attributes slightly lower
    secondary_attrs = {
        "wet_weather": target_ovr - 4,
        "starts": target_ovr - 2,
        "awareness": target_ovr - 3,
        "adaptability": target_ovr,
        "technical_feedback": target_ovr - 5,
        "composure": target_ovr - 2,
        "focus": target_ovr - 2,
        "discipline": target_ovr - 3,
    }

    for attr, base in secondary_attrs.items():
        variance = rng.randint(-3, 3)
        attributes[attr] = _clamp(base + variance)

    # Mental/confidence starts lower for rookies
    attributes["confidence"] = _clamp(target_ovr - 8 + rng.randint(-3, 3))
    attributes["aggression"] = _clamp(65 + rng.randint(-5, 10))

    # Reputation/marketability starts low
    attributes["reputation"] = _clamp(55 + rng.randint(-5, 10))
    attributes["marketability"] = _clamp(50 + rng.randint(-5, 10))
    attributes["sponsor_value"] = _clamp(40 + rng.randint(-5, 10))

    # Apply background and archetype effects
    for effects in [background_effects, archetype_effects]:
        for key, value in effects.items():
            snake_key = _camel_to_snake(key)
            if snake_key in attributes:
                attributes[snake_key] = _clamp(attributes[snake_key] + value)

    # Generate hidden attributes
    potential = rng.randint(config.potential_min, config.potential_max)
    development_rate = rng.randint(config.development_rate_min, config.development_rate_max)

    hidden: dict[str, int] = {
        "potential": potential,
        "development_rate": development_rate,
        "clutch_factor": _clamp(target_ovr - 5 + rng.randint(-5, 10)),
        "crash_proneness": _clamp(40 - (target_ovr - 70) // 3 + rng.randint(-5, 5)),
        "loyalty": _clamp(60 + rng.randint(-10, 10)),
        "adaptation_ceiling": _clamp(potential - rng.randint(0, 5)),
        "retirement_chance": 0,
    }

    return attributes, hidden


def _clamp(value: int) -> int:
    """Clamp value to 1-100 range."""
    return max(1, min(100, value))


def _camel_to_snake(value: str) -> str:
    """Convert camelCase to snake_case."""
    result = []
    for char in value:
        if char.isupper():
            result.append("_")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result).lstrip("_")
