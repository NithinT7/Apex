"""Engine for the weekly focus development system."""

from __future__ import annotations

import random
from datetime import datetime

from app.data.loaders import get_weekly_focus_config
from app.models.development_profile import (
    DevelopmentHistoryEntry,
    DevelopmentProfile,
    create_player_starting_profile,
)
from app.models.driver import Driver
from app.models.save_game import SaveGame
from app.models.weekly_focus import (
    FocusOutcome,
    WeeklyFocus,
    check_focus_availability,
)


class AvailableFocusInfo:
    """Information about an available focus option."""

    def __init__(
        self,
        focus: WeeklyFocus,
        is_available: bool,
        unmet_requirements: list[str],
        is_recommended: bool = False,
        recommendation_reason: str = "",
    ):
        self.focus = focus
        self.is_available = is_available
        self.unmet_requirements = unmet_requirements
        self.is_recommended = is_recommended
        self.recommendation_reason = recommendation_reason

    def to_dict(self) -> dict:
        return {
            "focus": self.focus.model_dump(by_alias=True),
            "isAvailable": self.is_available,
            "unmetRequirements": self.unmet_requirements,
            "isRecommended": self.is_recommended,
            "recommendationReason": self.recommendation_reason,
        }


class FocusSelectionResult:
    """Result of available focus query."""

    def __init__(
        self,
        available_focuses: list[AvailableFocusInfo],
        days_until_next_race: int,
        focus_slots_available: int,
        active_focus_id: str | None,
        completed_focus_ids: list[str],
    ):
        self.available_focuses = available_focuses
        self.days_until_next_race = days_until_next_race
        self.focus_slots_available = focus_slots_available
        self.active_focus_id = active_focus_id
        self.completed_focus_ids = completed_focus_ids

    def to_dict(self) -> dict:
        return {
            "availableFocuses": [f.to_dict() for f in self.available_focuses],
            "daysUntilNextRace": self.days_until_next_race,
            "focusSlotsAvailable": self.focus_slots_available,
            "activeFocusId": self.active_focus_id,
            "completedFocusIds": self.completed_focus_ids,
        }


def get_available_focuses(save: SaveGame) -> FocusSelectionResult:
    """
    Get all focus options with availability status for the player.

    Returns both available and locked focuses with information about requirements.
    """
    config = get_weekly_focus_config()
    player = _get_player(save)
    profile = _ensure_profile(save, player)

    # Calculate days and slots
    days_until_race = _calculate_days_until_next_race(save)
    focus_slots = _calculate_focus_slots(days_until_race, save)

    # Get completed focuses this break
    completed_ids = _get_completed_focus_ids(save)

    # Check availability for each focus
    focus_infos: list[AvailableFocusInfo] = []
    player_attrs = _get_player_attributes_dict(player)
    branch_xp = profile.branch_xp

    # Find rival for rival-related checks
    has_active_rival = _has_active_rival(save)
    has_academy = player.academy_id is not None

    for focus in config.focuses:
        # Check base availability
        is_available, unmet = check_focus_availability(
            focus=focus,
            attributes=player_attrs,
            branch_xp=branch_xp,
            unlocked_traits=profile.unlocked_trait_ids,
            unlocked_nodes=profile.unlocked_node_ids,
            current_phase=save.phase,
        )

        # Check special conditions
        if "has_academy" in focus.unlock_requirements.conditions:
            if not has_academy:
                is_available = False
                unmet.append("Requires academy membership")

        if "has_active_rival" in focus.unlock_requirements.conditions:
            if not has_active_rival:
                is_available = False
                unmet.append("Requires an active rivalry")

        # Check if already completed and not repeatable
        if focus.id in completed_ids and not focus.repeatable:
            is_available = False
            unmet.append("Already completed this break")

        # Check exclusivity
        for exclusive_id in focus.exclusive_with:
            if exclusive_id in completed_ids:
                is_available = False
                unmet.append(f"Cannot combine with {exclusive_id}")

        # Check if focus fits in remaining time
        if focus.duration_days > days_until_race:
            is_available = False
            unmet.append(f"Not enough time ({focus.duration_days} days needed)")

        # Determine if recommended
        is_recommended, reason = _should_recommend_focus(focus, player, profile, save)

        focus_infos.append(AvailableFocusInfo(
            focus=focus,
            is_available=is_available,
            unmet_requirements=unmet,
            is_recommended=is_recommended and is_available,
            recommendation_reason=reason if is_available else "",
        ))

    # Sort: available first, then recommended first, then by category
    focus_infos.sort(key=lambda f: (
        not f.is_available,
        not f.is_recommended,
        f.focus.category,
    ))

    return FocusSelectionResult(
        available_focuses=focus_infos,
        days_until_next_race=days_until_race,
        focus_slots_available=focus_slots - len(completed_ids),
        active_focus_id=profile.active_focus_id,
        completed_focus_ids=completed_ids,
    )


def choose_focus(save: SaveGame, focus_id: str) -> SaveGame:
    """
    Set the player's active weekly focus.

    This doesn't immediately apply effects - effects are applied when
    advancing to the next weekend.
    """
    config = get_weekly_focus_config()
    focus = config.get_focus(focus_id)

    if focus is None:
        raise ValueError(f"Unknown focus: {focus_id}")

    player = _get_player(save)
    profile = _ensure_profile(save, player)

    # Verify focus is available
    player_attrs = _get_player_attributes_dict(player)
    is_available, unmet = check_focus_availability(
        focus=focus,
        attributes=player_attrs,
        branch_xp=profile.branch_xp,
        unlocked_traits=profile.unlocked_trait_ids,
        unlocked_nodes=profile.unlocked_node_ids,
        current_phase=save.phase,
    )

    # Check special conditions
    if "has_academy" in focus.unlock_requirements.conditions:
        if player.academy_id is None:
            is_available = False
            unmet.append("Requires academy membership")

    if "has_active_rival" in focus.unlock_requirements.conditions:
        if not _has_active_rival(save):
            is_available = False
            unmet.append("Requires an active rivalry")

    # Check completed/exclusive
    completed_ids = _get_completed_focus_ids(save)
    if focus_id in completed_ids and not focus.repeatable:
        raise ValueError(f"Focus {focus_id} already completed this break")

    for exclusive_id in focus.exclusive_with:
        if exclusive_id in completed_ids:
            raise ValueError(f"Focus {focus_id} cannot be combined with {exclusive_id}")

    if not is_available:
        raise ValueError(f"Focus {focus_id} is not available: {', '.join(unmet)}")

    # Set the active focus
    updated_profile = profile.model_copy(update={"active_focus_id": focus_id})

    return save.model_copy(update={"development_profile": updated_profile})


def apply_focus_and_advance(
    save: SaveGame,
    seed: int | None = None,
) -> tuple[SaveGame, FocusOutcome | None]:
    """
    Apply the active focus effects and advance time to race week.

    This is called when transitioning from between_races to race_week.
    Returns the updated save and the focus outcome (if a focus was active).
    """
    player = _get_player(save)
    profile = _ensure_profile(save, player)

    # If no active focus, just return
    if profile.active_focus_id is None:
        return save, None

    config = get_weekly_focus_config()
    focus = config.get_focus(profile.active_focus_id)
    if focus is None:
        # Clear invalid focus and return
        updated_profile = profile.model_copy(update={"active_focus_id": None})
        return save.model_copy(update={"development_profile": updated_profile}), None

    rng = random.Random(seed if seed is not None else save.random_seed)

    # Check for risk
    risk_triggered = False
    if focus.risk_effects and focus.risk_effects.chance > 0:
        risk_triggered = rng.randint(1, 100) <= focus.risk_effects.chance

    # Calculate XP gains
    xp_gained: dict[str, int] = {}
    if not risk_triggered:
        # Primary branch XP
        xp_gained[focus.primary_xp_branch] = focus.primary_xp_amount

        # Secondary branch XP
        for branch in focus.secondary_xp_branches:
            xp_gained[branch] = focus.secondary_xp_amount
    else:
        # Risk penalties if present
        if focus.risk_effects and focus.risk_effects.xp_penalties:
            for branch, penalty in focus.risk_effects.xp_penalties.items():
                xp_gained[branch] = penalty

    # Apply XP to profile
    new_branch_xp = profile.branch_xp.copy()
    for branch, amount in xp_gained.items():
        current = new_branch_xp.get(branch, 0)
        new_branch_xp[branch] = max(0, current + amount)

    # Apply attribute effects
    attribute_changes: dict[str, int] = {}
    new_attributes = player.attributes

    effects_to_apply = focus.attribute_xp_effects
    if risk_triggered and focus.risk_effects:
        effects_to_apply = focus.risk_effects.attribute_penalties

    for attr, change in effects_to_apply.items():
        current = getattr(new_attributes, attr, None)
        if current is not None:
            new_val = max(0, min(100, current + change))
            new_attributes = new_attributes.model_copy(update={attr: new_val})
            attribute_changes[attr] = change

    # Apply relationship effects
    relationship_changes: dict[str, int] = {}
    if focus.relationship_effects and not risk_triggered:
        for rel, change in focus.relationship_effects.items():
            relationship_changes[rel] = change

    # Apply academy effects
    academy_change = 0
    new_academy_states = save.academy_states
    if focus.academy_effects != 0 and player.academy_id and not risk_triggered:
        academy_change = focus.academy_effects
        new_academy_states = []
        for state in save.academy_states:
            if state.academy_id == player.academy_id:
                new_trust = max(0, min(100, state.trust + academy_change))
                new_academy_states.append(state.model_copy(update={"trust": new_trust}))
            else:
                new_academy_states.append(state)

    # Apply marketability effects
    marketability_change = 0
    if focus.marketability_effects != 0 and not risk_triggered:
        marketability_change = focus.marketability_effects
        new_mk = max(0, min(100, new_attributes.marketability + marketability_change))
        new_attributes = new_attributes.model_copy(update={"marketability": new_mk})
        attribute_changes["marketability"] = attribute_changes.get("marketability", 0) + marketability_change

    # Generate narrative
    narrative = _generate_focus_narrative(focus, risk_triggered, player.name)

    # Create history entry
    history_entry = DevelopmentHistoryEntry(
        date=save.current_date,
        round_id=_get_current_round_id(save),
        source="weekly_focus",
        xp_gained=xp_gained,
        summary=narrative,
    )

    # Update profile
    new_history = profile.history + [history_entry]
    if len(new_history) > 50:
        new_history = new_history[-50:]

    updated_profile = profile.model_copy(
        update={
            "branch_xp": new_branch_xp,
            "active_focus_id": None,  # Clear active focus
            "history": new_history,
        }
    )

    # Update player
    updated_player = player.model_copy(update={"attributes": new_attributes})
    new_drivers = [updated_player if d.id == player.id else d for d in save.drivers]

    # Mark focus as completed
    completed_key = f"focus_completed_{focus.id}"
    new_flags = {**save.event_flags, completed_key: True}

    # Create outcome
    outcome = FocusOutcome(
        focus_id=focus.id,
        focus_name=focus.name,
        success=not risk_triggered,
        xp_gained=xp_gained,
        attribute_changes=attribute_changes,
        relationship_changes=relationship_changes,
        marketability_change=marketability_change,
        academy_change=academy_change,
        narrative=narrative,
    )

    updated_save = save.model_copy(
        update={
            "drivers": new_drivers,
            "academy_states": new_academy_states,
            "development_profile": updated_profile,
            "event_flags": new_flags,
        }
    )

    return updated_save, outcome


def clear_focus_completions(save: SaveGame) -> SaveGame:
    """Clear focus completion flags for a new between-race period."""
    new_flags = {
        k: v for k, v in save.event_flags.items()
        if not k.startswith("focus_completed_")
    }
    return save.model_copy(update={"event_flags": new_flags})


def get_development_profile_summary(save: SaveGame) -> dict:
    """Get a summary of the player's development profile for the frontend."""
    player = _get_player(save)
    profile = _ensure_profile(save, player)

    # Calculate totals
    total_branch_xp = sum(profile.branch_xp.values())

    # Get recent history
    recent_history = profile.history[-10:] if profile.history else []

    return {
        "currentPoints": profile.current_points,
        "totalPointsEarned": profile.total_points_earned,
        "branchXp": profile.branch_xp,
        "totalBranchXp": total_branch_xp,
        "unlockedNodeIds": profile.unlocked_node_ids,
        "unlockedTraitIds": profile.unlocked_trait_ids,
        "activeFocusId": profile.active_focus_id,
        "recentHistory": [
            {
                "date": h.date,
                "source": h.source,
                "xpGained": h.xp_gained,
                "summary": h.summary,
                "nodeUnlocked": h.node_unlocked,
                "traitUnlocked": h.trait_unlocked,
            }
            for h in reversed(recent_history)
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
    """Ensure the save has a development profile, creating one if needed."""
    if save.development_profile is not None:
        return save.development_profile
    return create_player_starting_profile(player.hidden.potential)


def _calculate_days_until_next_race(save: SaveGame) -> int:
    """Calculate days until the next race weekend."""
    next_round = next((r for r in save.calendar if not r.completed), None)
    if next_round is None:
        return 0

    current = datetime.strptime(save.current_date, "%Y-%m-%d")
    next_start = datetime.strptime(next_round.start_date, "%Y-%m-%d")
    return max(0, (next_start - current).days)


def _calculate_focus_slots(days_until_race: int, save: SaveGame) -> int:
    """
    Calculate how many focus slots are available.

    Standard breaks: 1 slot
    Long breaks (7+ days): 2 slots
    """
    if days_until_race >= 7:
        return 2
    return 1


def _get_completed_focus_ids(save: SaveGame) -> list[str]:
    """Get IDs of focuses completed this break."""
    return [
        flag.replace("focus_completed_", "")
        for flag in save.event_flags
        if flag.startswith("focus_completed_") and save.event_flags[flag]
    ]


def _get_player_attributes_dict(player: Driver) -> dict[str, int]:
    """Convert player attributes to a flat dict for checking."""
    return {
        "pace": player.attributes.pace,
        "qualifying": player.attributes.qualifying,
        "racecraft": player.attributes.racecraft,
        "tire_management": player.attributes.tire_management,
        "wet_weather": player.attributes.wet_weather,
        "consistency": player.attributes.consistency,
        "starts": player.attributes.starts,
        "awareness": player.attributes.awareness,
        "adaptability": player.attributes.adaptability,
        "technical_feedback": player.attributes.technical_feedback,
        "pressure": player.attributes.pressure,
        "confidence": player.attributes.confidence,
        "composure": player.attributes.composure,
        "aggression": player.attributes.aggression,
        "discipline": player.attributes.discipline,
        "focus": player.attributes.focus,
        "reputation": player.attributes.reputation,
        "marketability": player.attributes.marketability,
        "sponsor_value": player.attributes.sponsor_value,
    }


def _has_active_rival(save: SaveGame) -> bool:
    """Check if player has an active rivalry."""
    player_id = save.player_driver_id
    return any(
        r.intensity >= 30 and (
            (hasattr(r, 'driver_id') and r.driver_id == player_id) or
            (hasattr(r, 'opponent_id') and r.opponent_id == player_id)
        )
        for r in save.rivalries
    )


def _should_recommend_focus(
    focus: WeeklyFocus,
    player: Driver,
    profile: DevelopmentProfile,
    save: SaveGame,
) -> tuple[bool, str]:
    """
    Determine if a focus should be recommended based on player state.

    Returns (should_recommend, reason).
    """
    # Recommend academy focus if trust is dropping
    if focus.id == "academy_session" and player.academy_id:
        academy_state = next(
            (s for s in save.academy_states if s.academy_id == player.academy_id),
            None
        )
        if academy_state and academy_state.trust < 50:
            return True, "Your academy relationship needs attention"

    # Recommend simulator if low form or new to racing
    if focus.id == "simulator_work":
        if profile.branch_xp.get("raw_pace", 0) < 30:
            return True, "Build your pace fundamentals"

    # Recommend racecraft training if struggled with overtakes
    if focus.id == "racecraft_training":
        if player.attributes.racecraft < 75:
            return True, "Sharpen your wheel-to-wheel skills"

    # Recommend media if marketability is low but sponsor value potential
    if focus.id == "media_day":
        if player.attributes.marketability < 60 and player.attributes.reputation >= 60:
            return True, "Build your public profile"

    # Recommend technical debrief for technical drivers
    if focus.id == "technical_debrief":
        if player.attributes.technical_feedback >= 70:
            return True, "Leverage your technical strengths"

    return False, ""


def _get_current_round_id(save: SaveGame) -> str | None:
    """Get the current round ID."""
    next_round = next((r for r in save.calendar if not r.completed), None)
    return next_round.id if next_round else None


def _generate_focus_narrative(
    focus: WeeklyFocus,
    risk_triggered: bool,
    driver_name: str,
) -> str:
    """Generate a narrative for the focus outcome."""
    if risk_triggered and focus.risk_effects:
        return focus.risk_effects.risk_narrative or f"{driver_name}'s {focus.name} didn't go as planned."

    narratives = {
        "simulator_work": f"{driver_name} put in dedicated hours on the simulator, finding valuable insights for the upcoming race.",
        "racecraft_training": f"{driver_name} worked on overtaking strategies with the team, feeling sharper in wheel-to-wheel scenarios.",
        "tire_management_program": f"{driver_name} analyzed tire data with the strategy team, developing a better feel for tire preservation.",
        "starts_and_reactions": f"{driver_name} drilled race starts until the reactions became second nature.",
        "fitness_consistency": f"{driver_name} completed an intensive physical training block, building endurance for race distances.",
        "technical_debrief": f"{driver_name} spent quality time with the engineers, translating data into setup improvements.",
        "academy_session": f"{driver_name} met with academy leadership, discussing progress and F1 pathway opportunities.",
        "media_day": f"{driver_name} handled press duties professionally, raising their public profile.",
        "sponsor_activation": f"{driver_name} attended sponsor events, strengthening commercial relationships.",
        "rival_study": f"{driver_name} studied rival driving patterns, identifying potential weaknesses to exploit.",
        "mental_reset": f"{driver_name} took time to recharge mentally, returning with a fresh perspective.",
    }

    return narratives.get(
        focus.id,
        focus.flavor_text or f"{driver_name} completed {focus.name}."
    )
