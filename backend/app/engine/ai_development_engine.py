"""
AI Driver Development Engine

Implements simplified but realistic development for AI drivers based on:
- Age and potential
- Previous season performance
- Team quality and resources
- Academy support
- Random growth variance

Key design principles:
- High-potential rookies develop meaningfully
- Elite drivers (Max/Lando/Leclerc tier) are protected from nonsensical collapse
- Older drivers regress gradually, but stars are protected
- Development feeds into driver market logic
"""

from __future__ import annotations

import random
import uuid
from typing import TYPE_CHECKING

from app.models.ai_development import (
    AI_TRAITS,
    AIDriverDevelopmentState,
    AITrait,
    DEVELOPMENT_CATEGORIES,
    DriverDevelopmentProfile,
    ProtectionTier,
    determine_protection_tier,
    get_driver_overall_rating,
    get_trait,
)
from app.models.driver import Driver
from app.models.save_game import NewsItem, SaveGame

if TYPE_CHECKING:
    pass


# =============================================================================
# Constants and Configuration
# =============================================================================

# Age thresholds
ROOKIE_AGE = 22
YOUNG_DRIVER_AGE = 25
PRIME_START_AGE = 24
PRIME_END_AGE = 30
VETERAN_AGE = 33
LATE_CAREER_AGE = 36

# Development rate modifiers
BASE_DEVELOPMENT_CHANCE = 60  # Base % chance to develop each season

# Regression rates by protection tier (points per season)
REGRESSION_RATES: dict[ProtectionTier, dict[str, float]] = {
    "untouchable": {
        "base_rate": 0.0,  # No natural regression
        "age_penalty_start": 38,  # Only start aging at 38
        "max_regression": 1,  # Max 1 point per season
    },
    "protected": {
        "base_rate": 0.0,
        "age_penalty_start": 34,
        "max_regression": 2,
    },
    "standard": {
        "base_rate": 0.1,  # Small base regression
        "age_penalty_start": 32,
        "max_regression": 4,
    },
    "vulnerable": {
        "base_rate": 0.3,
        "age_penalty_start": 30,
        "max_regression": 6,
    },
}

# Team quality tiers (affects development support)
TEAM_QUALITY_TIERS = {
    "elite": {"development_bonus": 15, "resource_multiplier": 1.3},
    "top": {"development_bonus": 10, "resource_multiplier": 1.15},
    "midfield": {"development_bonus": 5, "resource_multiplier": 1.0},
    "backmarker": {"development_bonus": 0, "resource_multiplier": 0.85},
}


# =============================================================================
# Core Development Functions
# =============================================================================


def apply_ai_season_development(
    save: SaveGame,
    checkpoint: str = "season_end",
) -> tuple[SaveGame, list[NewsItem]]:
    """
    Apply AI driver development at season checkpoints.

    Checkpoints:
    - season_start: Pre-season development based on off-season work
    - mid_season: Mid-season adjustments (optional)
    - season_end: End of season development and regression

    Returns updated save and any news items generated.
    """
    rng = random.Random(f"{save.random_seed}:{save.season}:ai_dev:{checkpoint}")
    news_items: list[NewsItem] = []
    updated_drivers: list[Driver] = []

    # Get AI development states
    ai_dev_states = save.event_flags.get("ai_development_states", {})
    if not isinstance(ai_dev_states, dict):
        ai_dev_states = {}

    # Get performance data from standings
    standings_map = _get_standings_map(save)

    for driver in save.drivers:
        # Skip player
        if driver.id == save.player_driver_id:
            updated_drivers.append(driver)
            continue

        # Get or create development state
        dev_state = _get_or_create_dev_state(driver, ai_dev_states)

        # Update protection tier
        dev_state = _update_protection_tier(driver, save, dev_state)

        # Calculate development
        if checkpoint == "season_end":
            driver, dev_state, dev_news = _apply_season_end_development(
                driver, save, dev_state, standings_map, rng
            )
            news_items.extend(dev_news)
        else:
            driver, dev_state, dev_news = _apply_season_start_development(
                driver, save, dev_state, standings_map, rng
            )
            news_items.extend(dev_news)

        # Try to unlock traits
        driver, dev_state, trait_news = _try_unlock_traits(driver, dev_state, rng)
        news_items.extend(trait_news)

        # Note: Driver aging is handled in season_engine.prepare_next_season()
        # to avoid double-aging (both player and AI drivers age there)

        updated_drivers.append(driver)

        # Save state back
        ai_dev_states[driver.id] = dev_state.model_dump()

    # Update save
    new_flags = {**save.event_flags, "ai_development_states": ai_dev_states}
    updated_save = save.model_copy(
        update={
            "drivers": updated_drivers,
            "event_flags": new_flags,
        }
    )

    return updated_save, news_items


def _apply_season_end_development(
    driver: Driver,
    save: SaveGame,
    dev_state: AIDriverDevelopmentState,
    standings_map: dict[str, int],
    rng: random.Random,
) -> tuple[Driver, AIDriverDevelopmentState, list[NewsItem]]:
    """Apply end-of-season development/regression."""
    news_items: list[NewsItem] = []

    # Get performance context
    champ_position = standings_map.get(driver.id)
    team = next((t for t in save.teams if t.id == driver.team_id), None)
    team_quality = _get_team_quality(team) if team else "midfield"

    # Calculate base development points
    dev_points = _calculate_development_points(
        driver=driver,
        champ_position=champ_position,
        team_quality=team_quality,
        dev_state=dev_state,
        rng=rng,
    )

    # Calculate regression
    regression_points = _calculate_regression(
        driver=driver,
        dev_state=dev_state,
        rng=rng,
    )

    # Net change
    net_change = dev_points - regression_points

    # Apply development/regression
    if net_change != 0:
        driver, applied_changes = _apply_attribute_changes(
            driver=driver,
            points=net_change,
            dev_state=dev_state,
            rng=rng,
        )

        # Update state
        new_rating = get_driver_overall_rating(driver)
        dev_state = dev_state.model_copy(
            update={
                "last_season_rating_change": net_change,
                "total_career_growth": dev_state.total_career_growth + max(0, net_change),
                "peak_rating": max(dev_state.peak_rating, new_rating),
                "consecutive_decline_seasons": (
                    dev_state.consecutive_decline_seasons + 1 if net_change < 0 else 0
                ),
            }
        )

        # Generate news for significant changes
        if abs(net_change) >= 3:
            news = _generate_development_news(driver, net_change, save.current_date)
            if news:
                news_items.append(news)

    return driver, dev_state, news_items


def _apply_season_start_development(
    driver: Driver,
    save: SaveGame,
    dev_state: AIDriverDevelopmentState,
    standings_map: dict[str, int],
    rng: random.Random,
) -> tuple[Driver, AIDriverDevelopmentState, list[NewsItem]]:
    """Apply pre-season development (smaller bonuses)."""
    news_items: list[NewsItem] = []

    # Pre-season development is smaller (1-2 points max for high potential)
    age_factor = _get_age_development_factor(driver.age)
    potential_factor = (driver.hidden.potential - 70) / 30  # 0-1 scale

    if rng.random() < (age_factor * potential_factor * 0.5):
        # Small pre-season boost
        points = rng.choice([1, 1, 2])
        driver, _ = _apply_attribute_changes(driver, points, dev_state, rng)

    return driver, dev_state, news_items


# =============================================================================
# Development Calculation
# =============================================================================


def _calculate_development_points(
    driver: Driver,
    champ_position: int | None,
    team_quality: str,
    dev_state: AIDriverDevelopmentState,
    rng: random.Random,
) -> int:
    """
    Calculate development points for a driver.

    Based on:
    - Age (young drivers develop faster)
    - Potential (high potential = faster development)
    - Development rate (intrinsic growth speed)
    - Performance (good results = more development)
    - Team quality (better teams = more development resources)
    - Academy support (academy drivers get bonuses)
    - Random variance
    """
    points = 0

    # 1. AGE FACTOR (major)
    age_factor = _get_age_development_factor(driver.age)

    # 2. POTENTIAL FACTOR
    # High potential drivers grow more
    potential_factor = max(0.5, (driver.hidden.potential - 65) / 30)  # 0.5-1.2

    # 3. DEVELOPMENT RATE
    # Natural development speed
    dev_rate_factor = driver.hidden.development_rate / 80  # ~0.6-1.25

    # 4. PERFORMANCE FACTOR
    performance_factor = _get_performance_factor(champ_position, driver.series)

    # 5. TEAM QUALITY BONUS
    team_config = TEAM_QUALITY_TIERS.get(team_quality, TEAM_QUALITY_TIERS["midfield"])
    team_bonus = team_config["development_bonus"]

    # 6. HEADROOM CHECK
    # Don't develop if already at/near ceiling
    current_rating = get_driver_overall_rating(driver)
    ceiling = min(99, driver.hidden.potential + 5)
    headroom = max(0, ceiling - current_rating)
    if headroom <= 0:
        return 0

    headroom_factor = min(1.0, headroom / 15)  # Full factor if 15+ points of headroom

    # Calculate base development chance
    base_chance = (
        BASE_DEVELOPMENT_CHANCE
        * age_factor
        * potential_factor
        * dev_rate_factor
        * performance_factor
        * headroom_factor
    )

    # Random check
    if rng.randint(1, 100) <= base_chance:
        # Calculate points
        base_points = 1

        # Young + high potential = more points
        if driver.age <= YOUNG_DRIVER_AGE and driver.hidden.potential >= 85:
            base_points += rng.choice([1, 2, 2, 3])
        elif driver.age <= ROOKIE_AGE:
            base_points += rng.choice([1, 1, 2])
        elif driver.age <= PRIME_END_AGE:
            base_points += rng.choice([0, 1, 1])

        # Performance bonus
        if champ_position and champ_position <= 3:
            base_points += 1
        elif champ_position and champ_position <= 6:
            base_points += rng.choice([0, 1])

        # Team bonus
        base_points = int(base_points * team_config["resource_multiplier"])

        # Academy bonus for young drivers
        if driver.academy_id and driver.age <= 24:
            base_points += 1

        # Random variance
        variance = rng.choice([-1, 0, 0, 1, 1])
        points = max(0, base_points + variance)

    return min(points, headroom)  # Cap at headroom


def _calculate_regression(
    driver: Driver,
    dev_state: AIDriverDevelopmentState,
    rng: random.Random,
) -> int:
    """
    Calculate regression points for a driver.

    Regression is based on:
    - Protection tier (elite drivers are protected)
    - Age (older drivers regress more)
    - Recent decline (compounding decline)
    """
    tier = dev_state.protection_tier
    config = REGRESSION_RATES.get(tier, REGRESSION_RATES["standard"])

    # Base regression
    regression = 0

    # Age-based regression
    if driver.age >= config["age_penalty_start"]:
        years_over = driver.age - config["age_penalty_start"]
        # Exponential-ish scaling
        age_regression = config["base_rate"] + (years_over * 0.3)

        # Random check
        if rng.random() < age_regression:
            regression += 1

        # Additional regression for very old
        if driver.age >= LATE_CAREER_AGE:
            if rng.random() < 0.4:
                regression += 1
            if driver.age >= 40 and rng.random() < 0.5:
                regression += 1

    # Compounding decline
    if dev_state.consecutive_decline_seasons >= 2:
        if rng.random() < 0.3:
            regression += 1

    # Cap regression
    regression = min(regression, config["max_regression"])

    # Protected drivers have a chance to resist regression
    if tier in ("untouchable", "protected") and regression > 0:
        resist_chance = 0.7 if tier == "untouchable" else 0.4
        if rng.random() < resist_chance:
            regression = max(0, regression - 1)

    return regression


def _apply_attribute_changes(
    driver: Driver,
    points: int,
    dev_state: AIDriverDevelopmentState,
    rng: random.Random,
) -> tuple[Driver, dict[str, int]]:
    """Apply attribute changes to a driver."""
    if points == 0:
        return driver, {}

    changes: dict[str, int] = {}
    updated_attrs = driver.attributes

    if points > 0:
        # Development: prioritize weakest core attributes
        candidates = _get_development_candidates(driver, dev_state)

        for _ in range(points):
            if not candidates:
                break

            # Weighted random selection (favor weaker attributes)
            attr = _weighted_select(candidates, rng)
            current = getattr(updated_attrs, attr)
            cap = min(99, driver.hidden.potential + 3)

            if current < cap:
                updated_attrs = updated_attrs.model_copy(
                    update={attr: current + 1}
                )
                changes[attr] = changes.get(attr, 0) + 1
                candidates = _get_development_candidates(
                    driver.model_copy(update={"attributes": updated_attrs}),
                    dev_state,
                )
    else:
        # Regression: affect strongest attributes first (preserves style)
        regression_attrs = _get_regression_candidates(driver)

        for _ in range(abs(points)):
            if not regression_attrs:
                break

            attr = rng.choice(regression_attrs)
            current = getattr(updated_attrs, attr)

            if current > 60:  # Don't regress below 60
                updated_attrs = updated_attrs.model_copy(
                    update={attr: current - 1}
                )
                changes[attr] = changes.get(attr, 0) - 1

    return driver.model_copy(update={"attributes": updated_attrs}), changes


# =============================================================================
# Trait System
# =============================================================================


def _try_unlock_traits(
    driver: Driver,
    dev_state: AIDriverDevelopmentState,
    rng: random.Random,
) -> tuple[Driver, AIDriverDevelopmentState, list[NewsItem]]:
    """Try to unlock new traits for a driver."""
    news_items: list[NewsItem] = []

    # Limit total traits
    if len(dev_state.trait_ids) >= 3:
        return driver, dev_state, news_items

    # Get available traits
    available = _get_available_traits(driver, dev_state)
    if not available:
        return driver, dev_state, news_items

    # Chance to unlock (based on age and performance)
    unlock_chance = 15 if driver.age <= YOUNG_DRIVER_AGE else 8 if driver.age <= PRIME_END_AGE else 3

    if rng.randint(1, 100) <= unlock_chance:
        # Weight by trait unlock_weight
        weights = [t.unlock_weight for t in available]
        total = sum(weights)
        r = rng.uniform(0, total)
        cumulative = 0
        selected = available[0]

        for trait in available:
            cumulative += trait.unlock_weight
            if r <= cumulative:
                selected = trait
                break

        # Unlock the trait
        new_trait_ids = dev_state.trait_ids + [selected.id]
        dev_state = dev_state.model_copy(update={"trait_ids": new_trait_ids})

        # Apply trait bonuses
        updated_attrs = driver.attributes
        for attr, bonus in selected.attribute_bonuses.items():
            current = getattr(updated_attrs, attr, None)
            if current is not None:
                updated_attrs = updated_attrs.model_copy(
                    update={attr: min(99, current + bonus)}
                )

        driver = driver.model_copy(update={"attributes": updated_attrs})

    return driver, dev_state, news_items


def _get_available_traits(
    driver: Driver,
    dev_state: AIDriverDevelopmentState,
) -> list[AITrait]:
    """Get traits a driver could potentially unlock."""
    available = []

    for trait in AI_TRAITS:
        # Skip if already has trait
        if trait.id in dev_state.trait_ids:
            continue

        # Check primary attribute requirement
        primary_attr = _get_trait_primary_attribute(trait)
        if primary_attr:
            current = getattr(driver.attributes, primary_attr, 0)
            if current < trait.min_primary_attribute:
                continue

        available.append(trait)

    return available


def _get_trait_primary_attribute(trait: AITrait) -> str | None:
    """Get the primary attribute for a trait category."""
    category_attrs = {
        "pace": "qualifying",
        "racecraft": "racecraft",
        "mental": "consistency",
        "technical": "tire_management",
        "media": "marketability",
    }
    return category_attrs.get(trait.category)


def get_driver_traits(driver_id: str, save: SaveGame) -> list[AITrait]:
    """Get the unlocked traits for a driver."""
    ai_dev_states = save.event_flags.get("ai_development_states", {})
    if not isinstance(ai_dev_states, dict):
        return []

    state_data = ai_dev_states.get(driver_id, {})
    if not state_data:
        return []

    trait_ids = state_data.get("trait_ids", [])
    return [t for t in AI_TRAITS if t.id in trait_ids]


# =============================================================================
# Helper Functions
# =============================================================================


def _get_or_create_dev_state(
    driver: Driver,
    ai_dev_states: dict,
) -> AIDriverDevelopmentState:
    """Get or create development state for a driver."""
    if driver.id in ai_dev_states:
        return AIDriverDevelopmentState.model_validate(ai_dev_states[driver.id])

    # Create new state
    current_rating = get_driver_overall_rating(driver)
    return AIDriverDevelopmentState(
        peak_rating=current_rating,
    )


def _update_protection_tier(
    driver: Driver,
    save: SaveGame,
    dev_state: AIDriverDevelopmentState,
) -> AIDriverDevelopmentState:
    """Update the driver's protection tier."""
    # Check if world champion
    is_champion = save.event_flags.get(f"champion_{driver.id}", False)

    tier = determine_protection_tier(
        driver_age=driver.age,
        overall_rating=get_driver_overall_rating(driver),
        career_wins=driver.career.wins,
        is_world_champion=bool(is_champion),
        series=driver.series,
    )

    return dev_state.model_copy(update={"protection_tier": tier})


def _get_standings_map(save: SaveGame) -> dict[str, int]:
    """Get championship positions for all drivers."""
    result = {}

    # F2 standings
    if save.standings and save.standings.driver_standings:
        sorted_f2 = sorted(
            save.standings.driver_standings,
            key=lambda x: x.points,
            reverse=True,
        )
        for i, entry in enumerate(sorted_f2, 1):
            result[entry.driver_id] = i

    # F1 standings
    if save.f1_standings and save.f1_standings.driver_standings:
        sorted_f1 = sorted(
            save.f1_standings.driver_standings,
            key=lambda x: x.points,
            reverse=True,
        )
        for i, entry in enumerate(sorted_f1, 1):
            result[entry.driver_id] = i

    return result


def _get_team_quality(team) -> str:
    """Determine team quality tier."""
    # Based on car performance and financial health
    score = team.car_performance + (team.financial_health / 2)

    if score >= 95:
        return "elite"
    elif score >= 85:
        return "top"
    elif score >= 75:
        return "midfield"
    return "backmarker"


def _get_age_development_factor(age: int) -> float:
    """Get development factor based on age."""
    if age <= ROOKIE_AGE:
        return 1.5  # Rookies develop fastest
    elif age <= YOUNG_DRIVER_AGE:
        return 1.3
    elif age <= PRIME_START_AGE:
        return 1.1
    elif age <= PRIME_END_AGE:
        return 0.9
    elif age <= VETERAN_AGE:
        return 0.5
    else:
        return 0.2  # Late career - minimal development


def _get_performance_factor(position: int | None, series: str) -> float:
    """Get development factor based on performance."""
    if position is None:
        return 0.8

    # Scale by series
    if series == "F1":
        if position <= 3:
            return 1.3
        elif position <= 6:
            return 1.15
        elif position <= 10:
            return 1.0
        else:
            return 0.9
    else:  # F2
        if position <= 3:
            return 1.2
        elif position <= 5:
            return 1.1
        elif position <= 10:
            return 1.0
        elif position <= 15:
            return 0.9
        else:
            return 0.8


def _get_development_candidates(
    driver: Driver,
    dev_state: AIDriverDevelopmentState,
) -> list[str]:
    """Get attributes that can be developed."""
    core_attrs = [
        "pace", "qualifying", "racecraft", "consistency",
        "tire_management", "wet_weather", "pressure",
    ]

    candidates = []
    for attr in core_attrs:
        current = getattr(driver.attributes, attr)
        cap = min(99, driver.hidden.potential + 3)
        if current < cap:
            candidates.append(attr)

    return candidates


def _get_regression_candidates(driver: Driver) -> list[str]:
    """Get attributes that can regress."""
    physical_attrs = ["pace", "qualifying", "consistency", "starts"]
    mental_attrs = ["pressure", "composure"]

    # Physical attributes regress first for older drivers
    candidates = physical_attrs if driver.age >= VETERAN_AGE else physical_attrs + mental_attrs

    return [
        attr for attr in candidates
        if getattr(driver.attributes, attr) > 60
    ]


def _weighted_select(candidates: list[str], rng: random.Random) -> str:
    """Select from candidates with weighting toward lower values."""
    if not candidates:
        return candidates[0]

    # Lower value = higher weight
    weights = [1.0 for _ in candidates]  # Start with equal weights
    r = rng.random() * sum(weights)

    cumulative = 0
    for i, w in enumerate(weights):
        cumulative += w
        if r <= cumulative:
            return candidates[i]

    return candidates[-1]


def _generate_development_news(
    driver: Driver,
    net_change: int,
    date: str,
) -> NewsItem | None:
    """Generate news for significant development changes."""
    if abs(net_change) < 3:
        return None

    if net_change >= 5:
        headline = f"{driver.name} shows exceptional development"
        body = f"{driver.name} has made remarkable progress this season, cementing their position as one of the most improved drivers on the grid."
        category = "system"
    elif net_change >= 3:
        headline = f"{driver.name} continues to develop"
        body = f"{driver.name} has shown solid improvement over the season, developing their skills further."
        category = "system"
    elif net_change <= -4:
        headline = f"Concerns over {driver.name}'s form"
        body = f"Questions are being asked about {driver.name}'s recent decline in performance. The driver will be looking to bounce back next season."
        category = "rumor"
    else:  # -3
        headline = f"{driver.name} faces challenging season"
        body = f"{driver.name} has struggled to maintain their previous level this season."
        category = "system"

    return NewsItem(
        id=f"ai_dev_{uuid.uuid4().hex[:8]}",
        date=date,
        category=category,
        headline=headline,
        body=body,
        linked_driver_ids=[driver.id],
        importance=3 if abs(net_change) >= 4 else 2,
    )


# =============================================================================
# Integration with Driver Market
# =============================================================================


def get_driver_market_rating(driver: Driver, save: SaveGame) -> dict:
    """
    Get a driver's market rating including AI development factors.

    Used by the silly season engine for transfer decisions.
    """
    ai_dev_states = save.event_flags.get("ai_development_states", {})
    state_data = ai_dev_states.get(driver.id, {}) if isinstance(ai_dev_states, dict) else {}

    dev_state = (
        AIDriverDevelopmentState.model_validate(state_data)
        if state_data
        else AIDriverDevelopmentState()
    )

    overall = get_driver_overall_rating(driver)
    traits = [get_trait(tid) for tid in dev_state.trait_ids]
    traits = [t for t in traits if t is not None]

    return {
        "overall_rating": overall,
        "potential": driver.hidden.potential,
        "protection_tier": dev_state.protection_tier,
        "traits": [t.name for t in traits],
        "trend": (
            "improving" if dev_state.last_season_rating_change > 0
            else "declining" if dev_state.last_season_rating_change < 0
            else "stable"
        ),
        "peak_rating": dev_state.peak_rating,
        "age": driver.age,
        "marketability": driver.attributes.marketability,
    }


def should_consider_for_elite_seat(driver: Driver, save: SaveGame) -> bool:
    """
    Check if a driver should be considered for a top team seat.

    Elite drivers should not be replaced by significantly weaker drivers.
    """
    market = get_driver_market_rating(driver, save)

    # Untouchable drivers always keep consideration
    if market["protection_tier"] == "untouchable":
        return True

    # Protected drivers need significant drop to lose consideration
    if market["protection_tier"] == "protected":
        if market["overall_rating"] >= 85:
            return True
        if market["peak_rating"] - market["overall_rating"] <= 5:
            return True

    # Check raw talent
    if market["overall_rating"] >= 88:
        return True

    # Check potential for young drivers
    if driver.age <= 25 and market["potential"] >= 90:
        return True

    return False
