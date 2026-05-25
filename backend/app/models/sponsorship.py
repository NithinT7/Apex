"""Models for the sponsorship system tied to marketability."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


# Sponsor tier based on marketability threshold
SponsorTier = Literal["local", "regional", "national", "global", "elite"]


# Marketability thresholds for each tier
MARKETABILITY_THRESHOLDS: dict[SponsorTier, int] = {
    "local": 0,      # Available to everyone
    "regional": 45,  # Low-medium marketability
    "national": 60,  # Medium marketability
    "global": 75,    # High marketability
    "elite": 90,     # Star marketability
}


# Tier display names
TIER_NAMES: dict[SponsorTier, str] = {
    "local": "Local",
    "regional": "Regional",
    "national": "National",
    "global": "Global",
    "elite": "Elite",
}


class SponsorActivityEffects(AppModel):
    """Effects from completing a sponsor activity."""

    # XP gains
    media_xp: int = 0

    # Attribute effects
    marketability: int = 0
    sponsor_value: int = 0
    reputation: int = 0

    # Relationship effects
    team_interest: int = 0  # Increases team's interest in signing/keeping player
    academy_trust: int = 0

    # Special bonuses
    development_funding_bonus: float = 0.0  # Multiplier for next dev point purchase
    contract_value_bonus: float = 0.0  # Increases contract negotiation leverage

    # Narrative/pressure effects
    pressure_increase: int = 0  # Can increase pressure if sponsorship underdelivers


class SponsorActivityRisk(AppModel):
    """Risk effects for sponsor activities."""

    chance: int = 0  # Percentage chance of negative outcome

    # Penalties if risk triggers
    marketability_penalty: int = 0
    reputation_penalty: int = 0
    pressure_increase: int = 0

    # Narrative for when things go wrong
    failure_narrative: str = ""


class SponsorActivity(AppModel):
    """A sponsor activity that can be unlocked based on marketability."""

    id: str
    name: str
    tier: SponsorTier
    description: str

    # Requirements
    min_marketability: int  # Threshold to unlock
    min_sponsor_value: int = 0  # Optional additional requirement

    # Effects when completed
    effects: SponsorActivityEffects

    # Risk of negative outcome
    risk: SponsorActivityRisk | None = None

    # Duration in days
    duration_days: int = 1

    # Narrative flavor
    flavor_text: str = ""
    success_headline: str = ""  # News headline on success
    success_body: str = ""  # News body on success

    # Team/academy affinity (optional - some sponsors align better with certain teams)
    preferred_team_ids: list[str] = Field(default_factory=list)
    preferred_academy_ids: list[str] = Field(default_factory=list)

    # Whether this generates a major news story
    is_major_event: bool = False


class SponsorshipState(AppModel):
    """Tracks player's sponsorship status."""

    # Current sponsor tier based on marketability
    current_tier: SponsorTier = "local"

    # Total sponsor value accumulated
    total_sponsor_earnings: int = 0

    # Activities completed this season
    activities_completed: list[str] = Field(default_factory=list)

    # Active sponsor partnerships (for narrative)
    active_partners: list[str] = Field(default_factory=list)

    # Pending development funding bonus (applied to next purchase)
    pending_dev_bonus: float = 0.0


def get_sponsor_tier(marketability: int) -> SponsorTier:
    """Determine sponsor tier based on marketability rating."""
    if marketability >= MARKETABILITY_THRESHOLDS["elite"]:
        return "elite"
    elif marketability >= MARKETABILITY_THRESHOLDS["global"]:
        return "global"
    elif marketability >= MARKETABILITY_THRESHOLDS["national"]:
        return "national"
    elif marketability >= MARKETABILITY_THRESHOLDS["regional"]:
        return "regional"
    return "local"


def get_tier_name(tier: SponsorTier) -> str:
    """Get display name for a tier."""
    return TIER_NAMES.get(tier, tier.capitalize())


def get_next_tier_threshold(current_marketability: int) -> tuple[SponsorTier, int] | None:
    """Get the next tier and its threshold, or None if at max."""
    current_tier = get_sponsor_tier(current_marketability)

    tier_order: list[SponsorTier] = ["local", "regional", "national", "global", "elite"]
    current_idx = tier_order.index(current_tier)

    if current_idx >= len(tier_order) - 1:
        return None

    next_tier = tier_order[current_idx + 1]
    return next_tier, MARKETABILITY_THRESHOLDS[next_tier]
