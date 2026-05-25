"""Engine for sponsor activities tied to marketability."""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

from app.models.development_profile import DevelopmentHistoryEntry
from app.models.driver import Driver
from app.models.save_game import NewsItem, SaveGame
from app.models.sponsorship import (
    SponsorActivity,
    SponsorActivityEffects,
    SponsorActivityRisk,
    SponsorshipState,
    SponsorTier,
    get_sponsor_tier,
    get_tier_name,
    MARKETABILITY_THRESHOLDS,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class SponsorActivityConfig:
    """Configuration for sponsor activities."""

    def __init__(
        self,
        activities: list[SponsorActivity],
        tier_bonuses: dict[SponsorTier, dict[str, float]],
        team_interest_weights: dict[str, float],
    ):
        self.activities = activities
        self.tier_bonuses = tier_bonuses
        self.team_interest_weights = team_interest_weights
        self._activity_map = {a.id: a for a in activities}

    def get_activity(self, activity_id: str) -> SponsorActivity | None:
        return self._activity_map.get(activity_id)

    def get_activities_for_tier(self, tier: SponsorTier) -> list[SponsorActivity]:
        return [a for a in self.activities if a.tier == tier]


@lru_cache
def get_sponsor_config() -> SponsorActivityConfig:
    """Load the sponsor activity configuration."""
    path = DATA_DIR / "sponsor_activities.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    activities = []
    for item in data["activities"]:
        effects = SponsorActivityEffects.model_validate(item["effects"])
        risk = None
        if item.get("risk"):
            risk = SponsorActivityRisk.model_validate(item["risk"])

        activity = SponsorActivity(
            id=item["id"],
            name=item["name"],
            tier=item["tier"],
            description=item["description"],
            min_marketability=item["min_marketability"],
            min_sponsor_value=item.get("min_sponsor_value", 0),
            effects=effects,
            risk=risk,
            duration_days=item.get("duration_days", 1),
            flavor_text=item.get("flavor_text", ""),
            success_headline=item.get("success_headline", ""),
            success_body=item.get("success_body", ""),
            preferred_team_ids=item.get("preferred_team_ids", []),
            preferred_academy_ids=item.get("preferred_academy_ids", []),
            is_major_event=item.get("is_major_event", False),
        )
        activities.append(activity)

    return SponsorActivityConfig(
        activities=activities,
        tier_bonuses=data.get("tier_bonuses", {}),
        team_interest_weights=data.get("team_interest_weights", {}),
    )


class SponsorActivityInfo:
    """Information about a sponsor activity with availability status."""

    def __init__(
        self,
        activity: SponsorActivity,
        is_available: bool,
        unmet_requirements: list[str],
        tier_name: str,
        is_locked: bool = False,
        unlock_progress: float = 0.0,
    ):
        self.activity = activity
        self.is_available = is_available
        self.unmet_requirements = unmet_requirements
        self.tier_name = tier_name
        self.is_locked = is_locked
        self.unlock_progress = unlock_progress

    def to_dict(self) -> dict:
        return {
            "activity": {
                "id": self.activity.id,
                "name": self.activity.name,
                "tier": self.activity.tier,
                "tierName": self.tier_name,
                "description": self.activity.description,
                "minMarketability": self.activity.min_marketability,
                "minSponsorValue": self.activity.min_sponsor_value,
                "durationDays": self.activity.duration_days,
                "flavorText": self.activity.flavor_text,
                "isMajorEvent": self.activity.is_major_event,
                "effects": {
                    "mediaXp": self.activity.effects.media_xp,
                    "marketability": self.activity.effects.marketability,
                    "sponsorValue": self.activity.effects.sponsor_value,
                    "reputation": self.activity.effects.reputation,
                    "teamInterest": self.activity.effects.team_interest,
                    "academyTrust": self.activity.effects.academy_trust,
                    "developmentFundingBonus": self.activity.effects.development_funding_bonus,
                    "contractValueBonus": self.activity.effects.contract_value_bonus,
                    "pressureIncrease": self.activity.effects.pressure_increase,
                },
                "risk": {
                    "chance": self.activity.risk.chance,
                    "failureNarrative": self.activity.risk.failure_narrative,
                } if self.activity.risk else None,
            },
            "isAvailable": self.is_available,
            "unmetRequirements": self.unmet_requirements,
            "isLocked": self.is_locked,
            "unlockProgress": self.unlock_progress,
        }


class SponsorActivityResult:
    """Result of getting available sponsor activities."""

    def __init__(
        self,
        available_activities: list[SponsorActivityInfo],
        locked_activities: list[SponsorActivityInfo],
        current_tier: SponsorTier,
        current_tier_name: str,
        marketability: int,
        sponsor_value: int,
        next_tier_threshold: int | None,
        sponsorship_state: SponsorshipState,
    ):
        self.available_activities = available_activities
        self.locked_activities = locked_activities
        self.current_tier = current_tier
        self.current_tier_name = current_tier_name
        self.marketability = marketability
        self.sponsor_value = sponsor_value
        self.next_tier_threshold = next_tier_threshold
        self.sponsorship_state = sponsorship_state

    def to_dict(self) -> dict:
        return {
            "availableActivities": [a.to_dict() for a in self.available_activities],
            "lockedActivities": [a.to_dict() for a in self.locked_activities],
            "currentTier": self.current_tier,
            "currentTierName": self.current_tier_name,
            "marketability": self.marketability,
            "sponsorValue": self.sponsor_value,
            "nextTierThreshold": self.next_tier_threshold,
            "activitiesCompletedThisSeason": self.sponsorship_state.activities_completed,
            "totalSponsorEarnings": self.sponsorship_state.total_sponsor_earnings,
            "pendingDevBonus": self.sponsorship_state.pending_dev_bonus,
        }


def get_available_sponsor_activities(save: SaveGame) -> SponsorActivityResult:
    """Get all sponsor activities with availability status."""
    config = get_sponsor_config()
    player = _get_player(save)

    marketability = player.attributes.marketability
    sponsor_value = player.attributes.sponsor_value
    current_tier = get_sponsor_tier(marketability)

    # Get or create sponsorship state
    sponsorship_state = save.sponsorship_state or SponsorshipState()

    # Get completed activities this break
    completed_ids = _get_completed_sponsor_activities(save)

    available: list[SponsorActivityInfo] = []
    locked: list[SponsorActivityInfo] = []

    for activity in config.activities:
        tier_name = get_tier_name(activity.tier)
        unmet: list[str] = []

        # Check marketability requirement
        meets_marketability = marketability >= activity.min_marketability
        if not meets_marketability:
            unmet.append(f"Requires {activity.min_marketability} marketability (you have {marketability})")

        # Check sponsor value requirement
        meets_sponsor_value = sponsor_value >= activity.min_sponsor_value
        if not meets_sponsor_value and activity.min_sponsor_value > 0:
            unmet.append(f"Requires {activity.min_sponsor_value} sponsor value (you have {sponsor_value})")

        # Check if already completed this break
        if activity.id in completed_ids:
            unmet.append("Already completed this break")

        is_completed = activity.id in completed_ids
        is_available = meets_marketability and meets_sponsor_value and not is_completed
        is_locked = not meets_marketability or not meets_sponsor_value

        # Calculate unlock progress
        unlock_progress = 0.0
        if is_locked:
            mk_progress = min(1.0, marketability / max(1, activity.min_marketability))
            sv_progress = min(1.0, sponsor_value / max(1, activity.min_sponsor_value)) if activity.min_sponsor_value > 0 else 1.0
            unlock_progress = (mk_progress + sv_progress) / 2
        else:
            unlock_progress = 1.0

        info = SponsorActivityInfo(
            activity=activity,
            is_available=is_available,
            unmet_requirements=unmet,
            tier_name=tier_name,
            is_locked=is_locked,
            unlock_progress=unlock_progress,
        )

        # Only add to available if actually available (not completed, meets requirements)
        # Add to locked if requirements not met
        # Skip if completed (don't show in either list)
        if is_locked:
            locked.append(info)
        elif is_available:
            available.append(info)
        # Completed activities are not added to either list

    # Sort available by tier
    tier_order: dict[SponsorTier, int] = {
        "local": 0, "regional": 1, "national": 2, "global": 3, "elite": 4
    }
    available.sort(key=lambda x: tier_order.get(x.activity.tier, 0))
    locked.sort(key=lambda x: (tier_order.get(x.activity.tier, 0), x.activity.min_marketability))

    # Calculate next tier threshold
    next_threshold: int | None = None
    for tier in ["regional", "national", "global", "elite"]:
        threshold = MARKETABILITY_THRESHOLDS[tier]
        if marketability < threshold:
            next_threshold = threshold
            break

    return SponsorActivityResult(
        available_activities=available,
        locked_activities=locked,
        current_tier=current_tier,
        current_tier_name=get_tier_name(current_tier),
        marketability=marketability,
        sponsor_value=sponsor_value,
        next_tier_threshold=next_threshold,
        sponsorship_state=sponsorship_state,
    )


def complete_sponsor_activity(
    save: SaveGame,
    activity_id: str,
    seed: int | None = None,
) -> tuple[SaveGame, SponsorActivityOutcome]:
    """
    Complete a sponsor activity and apply its effects.

    Returns the updated save and the outcome.
    """
    config = get_sponsor_config()
    activity = config.get_activity(activity_id)

    if activity is None:
        raise ValueError(f"Unknown sponsor activity: {activity_id}")

    player = _get_player(save)
    marketability = player.attributes.marketability
    sponsor_value = player.attributes.sponsor_value

    # Verify activity is available
    if marketability < activity.min_marketability:
        raise ValueError(f"Activity {activity_id} requires {activity.min_marketability} marketability")
    if sponsor_value < activity.min_sponsor_value:
        raise ValueError(f"Activity {activity_id} requires {activity.min_sponsor_value} sponsor value")

    completed_ids = _get_completed_sponsor_activities(save)
    if activity_id in completed_ids:
        raise ValueError(f"Activity {activity_id} already completed this break")

    rng = random.Random(seed if seed is not None else save.random_seed)

    # Check for risk
    risk_triggered = False
    if activity.risk and activity.risk.chance > 0:
        risk_triggered = rng.randint(1, 100) <= activity.risk.chance

    # Apply effects
    effects = activity.effects
    effects_applied: dict[str, int | float] = {}

    new_attributes = player.attributes

    if not risk_triggered:
        # Apply positive effects
        if effects.marketability != 0:
            new_mk = max(0, min(100, new_attributes.marketability + effects.marketability))
            new_attributes = new_attributes.model_copy(update={"marketability": new_mk})
            effects_applied["marketability"] = effects.marketability

        if effects.sponsor_value != 0:
            new_sv = max(0, min(100, new_attributes.sponsor_value + effects.sponsor_value))
            new_attributes = new_attributes.model_copy(update={"sponsor_value": new_sv})
            effects_applied["sponsor_value"] = effects.sponsor_value

        if effects.reputation != 0:
            new_rep = max(0, min(100, new_attributes.reputation + effects.reputation))
            new_attributes = new_attributes.model_copy(update={"reputation": new_rep})
            effects_applied["reputation"] = effects.reputation

        effects_applied["media_xp"] = effects.media_xp
        effects_applied["team_interest"] = effects.team_interest
        effects_applied["academy_trust"] = effects.academy_trust
        effects_applied["development_funding_bonus"] = effects.development_funding_bonus
        effects_applied["contract_value_bonus"] = effects.contract_value_bonus
    else:
        # Apply risk penalties
        risk = activity.risk
        if risk.marketability_penalty != 0:
            new_mk = max(0, min(100, new_attributes.marketability + risk.marketability_penalty))
            new_attributes = new_attributes.model_copy(update={"marketability": new_mk})
            effects_applied["marketability"] = risk.marketability_penalty

        if risk.reputation_penalty != 0:
            new_rep = max(0, min(100, new_attributes.reputation + risk.reputation_penalty))
            new_attributes = new_attributes.model_copy(update={"reputation": new_rep})
            effects_applied["reputation"] = risk.reputation_penalty

        effects_applied["pressure_increase"] = risk.pressure_increase

    # Update player
    updated_player = player.model_copy(update={"attributes": new_attributes})
    new_drivers = [updated_player if d.id == player.id else d for d in save.drivers]

    # Update sponsorship state
    sponsorship_state = save.sponsorship_state or SponsorshipState()
    new_completed = sponsorship_state.activities_completed + [activity_id]
    new_earnings = sponsorship_state.total_sponsor_earnings + (effects.sponsor_value * 10000 if not risk_triggered else 0)
    new_dev_bonus = sponsorship_state.pending_dev_bonus
    if not risk_triggered and effects.development_funding_bonus > 0:
        new_dev_bonus += effects.development_funding_bonus

    updated_sponsorship = sponsorship_state.model_copy(
        update={
            "current_tier": get_sponsor_tier(new_attributes.marketability),
            "activities_completed": new_completed,
            "total_sponsor_earnings": new_earnings,
            "pending_dev_bonus": new_dev_bonus,
        }
    )

    # Add media XP to development profile
    profile = save.development_profile
    if profile and not risk_triggered and effects.media_xp > 0:
        new_branch_xp = profile.branch_xp.copy()
        current_xp = new_branch_xp.get("media_marketability", 0)
        new_branch_xp["media_marketability"] = current_xp + effects.media_xp

        # Create history entry
        history_entry = DevelopmentHistoryEntry(
            date=save.current_date,
            round_id=_get_current_round_id(save),
            source="sponsor_activity",
            xp_gained={"media_marketability": effects.media_xp},
            summary=f"Completed {activity.name}",
        )

        new_history = profile.history + [history_entry]
        if len(new_history) > 50:
            new_history = new_history[-50:]

        profile = profile.model_copy(
            update={
                "branch_xp": new_branch_xp,
                "history": new_history,
            }
        )

    # Update academy trust if applicable
    new_academy_states = save.academy_states
    if not risk_triggered and effects.academy_trust > 0 and player.academy_id:
        new_academy_states = []
        for state in save.academy_states:
            if state.academy_id == player.academy_id:
                new_trust = max(0, min(100, state.trust + effects.academy_trust))
                new_academy_states.append(state.model_copy(update={"trust": new_trust}))
            else:
                new_academy_states.append(state)

    # Generate news if major event
    news_item: NewsItem | None = None
    if activity.is_major_event:
        import uuid

        team = _get_player_team(save)
        team_name = team.name if team else "the team"

        headline = activity.success_headline.format(driver=player.name, team=team_name)
        body = activity.success_body.format(driver=player.name, team=team_name)

        if risk_triggered and activity.risk:
            headline = f"{player.name}'s sponsor event doesn't go as planned"
            body = activity.risk.failure_narrative

        news_item = NewsItem(
            id=f"sponsor_{uuid.uuid4().hex[:8]}",
            date=save.current_date,
            category="media",
            headline=headline,
            body=body,
            linked_driver_ids=[player.id],
            importance=3 if activity.is_major_event else 1,
        )

    # Mark activity as completed
    completed_key = f"sponsor_completed_{activity_id}"
    new_flags = {**save.event_flags, completed_key: True}

    # Create outcome
    outcome = SponsorActivityOutcome(
        activity_id=activity_id,
        activity_name=activity.name,
        success=not risk_triggered,
        effects_applied=effects_applied,
        narrative=activity.flavor_text if not risk_triggered else (activity.risk.failure_narrative if activity.risk else ""),
        news_item=news_item,
    )

    # Update save
    updates: dict = {
        "drivers": new_drivers,
        "academy_states": new_academy_states,
        "sponsorship_state": updated_sponsorship,
        "event_flags": new_flags,
    }
    if profile:
        updates["development_profile"] = profile

    if news_item:
        updates["news"] = save.news + [news_item]

    updated_save = save.model_copy(update=updates)

    return updated_save, outcome


class SponsorActivityOutcome:
    """Outcome of completing a sponsor activity."""

    def __init__(
        self,
        activity_id: str,
        activity_name: str,
        success: bool,
        effects_applied: dict[str, int | float],
        narrative: str,
        news_item: NewsItem | None = None,
    ):
        self.activity_id = activity_id
        self.activity_name = activity_name
        self.success = success
        self.effects_applied = effects_applied
        self.narrative = narrative
        self.news_item = news_item

    def to_dict(self) -> dict:
        return {
            "activityId": self.activity_id,
            "activityName": self.activity_name,
            "success": self.success,
            "effectsApplied": self.effects_applied,
            "narrative": self.narrative,
            "newsGenerated": self.news_item is not None,
        }


def clear_sponsor_completions(save: SaveGame) -> SaveGame:
    """Clear sponsor activity completion flags for a new between-race period."""
    new_flags = {
        k: v for k, v in save.event_flags.items()
        if not k.startswith("sponsor_completed_")
    }
    return save.model_copy(update={"event_flags": new_flags})


def get_team_interest_modifier(
    sponsor_value: int,
    team_tier: str,
) -> float:
    """
    Calculate how much sponsor value influences a team's interest.

    Backmarker teams care a lot about sponsor value.
    Midfield teams care somewhat.
    Top teams care less but it still matters.
    Elite teams care the least but won't ignore it.
    """
    config = get_sponsor_config()
    base_weight = config.team_interest_weights.get(team_tier, 0.5)

    # Normalize sponsor value (0-100) to a multiplier
    # High sponsor value = up to 20% boost for backmarkers
    sponsor_multiplier = (sponsor_value / 100) * base_weight * 0.2

    return 1.0 + sponsor_multiplier


def apply_sponsor_effects_to_team_interest(
    base_interest: int,
    sponsor_value: int,
    team_tier: str,
) -> int:
    """Apply sponsor value effects to team interest score."""
    modifier = get_team_interest_modifier(sponsor_value, team_tier)
    return int(base_interest * modifier)


# --- Private helpers ---


def _get_player(save: SaveGame) -> Driver:
    """Get the player driver."""
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        raise ValueError("No player driver found")
    return player


def _get_player_team(save: SaveGame):
    """Get the player's team."""
    player = _get_player(save)
    return next((t for t in save.teams if t.id == player.team_id), None)


def _get_completed_sponsor_activities(save: SaveGame) -> list[str]:
    """Get IDs of sponsor activities completed this break."""
    return [
        flag.replace("sponsor_completed_", "")
        for flag in save.event_flags
        if flag.startswith("sponsor_completed_") and save.event_flags[flag]
    ]


def _get_current_round_id(save: SaveGame) -> str | None:
    """Get the current round ID."""
    next_round = next((r for r in save.calendar if not r.completed), None)
    return next_round.id if next_round else None
