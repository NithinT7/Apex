"""Engine for between-race activities."""

from __future__ import annotations

import random
from datetime import datetime

from app.models.activity import (
    Activity,
    ActivityEffect,
    ActivityOutcome,
    AvailableActivities,
)
from app.models.save_game import SaveGame
from app.models.weekly_focus import FocusOutcome


# Define all available activities
ACTIVITIES: list[Activity] = [
    Activity(
        id="rest",
        name="Rest & Recovery",
        type="rest",
        description="Take time off to recover from the physical and mental demands of racing. Reduces fatigue significantly.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=-25, morale=5),
    ),
    Activity(
        id="simulator_basic",
        name="Simulator Session",
        type="simulator",
        description="Practice on the team's simulator to prepare for the next track and refine your racecraft.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=10, form=8),
        requirements={"fatigue": 70},  # Can't do if too tired
    ),
    Activity(
        id="simulator_intensive",
        name="Intensive Simulator Program",
        type="simulator",
        description="An extended simulator session focusing on specific weaknesses. Higher reward but more tiring.",
        duration_days=2,
        base_effects=ActivityEffect(fatigue=25, form=15, morale=-5),
        requirements={"fatigue": 50},
    ),
    Activity(
        id="physical_training",
        name="Physical Training",
        type="physical_training",
        description="Hit the gym and work on your physical conditioning. Builds long-term performance.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=15, form=5, morale=5),
        requirements={"fatigue": 60},
    ),
    Activity(
        id="media_interview",
        name="Media Interview",
        type="media_appearance",
        description="Sit down with journalists for interviews. Boosts your public profile but can be draining.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=10, reputation=5, sponsor_value=3),
        risk_chance=0.15,
        risk_effects=ActivityEffect(morale=-10, reputation=-5),  # Bad interview
    ),
    Activity(
        id="sponsor_meeting",
        name="Sponsor Event",
        type="sponsor_event",
        description="Attend a sponsor event to maintain relationships and secure future funding.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=15, sponsor_value=8, morale=-5),
    ),
    Activity(
        id="team_debrief",
        name="Team Technical Debrief",
        type="team_debrief",
        description="Meet with engineers to analyze data from the last race and plan improvements.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=5, form=10),
    ),
    Activity(
        id="academy_visit",
        name="Academy Headquarters Visit",
        type="academy_meeting",
        description="Visit your academy's headquarters to strengthen relationships with key figures.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=10, academy_trust=8, morale=5),
        risk_chance=0.1,
        risk_effects=ActivityEffect(academy_trust=-5, morale=-10),  # Awkward meeting
    ),
    Activity(
        id="fan_meet",
        name="Fan Meet & Greet",
        type="fan_engagement",
        description="Meet fans and sign autographs. Great for morale and public image.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=10, morale=15, reputation=3, sponsor_value=2),
    ),
    Activity(
        id="mental_coach",
        name="Mental Performance Session",
        type="mental_coaching",
        description="Work with a sports psychologist to improve mental resilience and focus.",
        duration_days=1,
        base_effects=ActivityEffect(fatigue=5, morale=10, form=5),
    ),
    Activity(
        id="full_rest",
        name="Extended Break",
        type="rest",
        description="Take multiple days completely off. Maximum recovery but you might lose some sharpness.",
        duration_days=2,
        base_effects=ActivityEffect(fatigue=-40, morale=15, form=-5),
    ),
]

ACTIVITY_MAP = {a.id: a for a in ACTIVITIES}


def get_available_activities(save: SaveGame) -> AvailableActivities:
    """Get activities available to the player based on current state."""
    # Calculate days until next race
    next_round = next((r for r in save.calendar if not r.completed), None)
    if next_round is None:
        # Season over
        return AvailableActivities(days_until_next_race=0, activities=[])

    # Parse dates to calculate days
    current = datetime.strptime(save.current_date, "%Y-%m-%d")
    next_start = datetime.strptime(next_round.start_date, "%Y-%m-%d")
    days_until = (next_start - current).days

    # Get player driver
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        return AvailableActivities(days_until_next_race=days_until, activities=[])

    # Filter activities based on requirements and time
    available = []
    for activity in ACTIVITIES:
        # Check duration fits
        if activity.duration_days > days_until:
            continue

        # Check requirements
        meets_requirements = True
        for req_key, req_max in activity.requirements.items():
            if req_key == "fatigue" and player.fatigue > req_max:
                meets_requirements = False
                break

        if meets_requirements:
            available.append(activity)

    # Get completed activities from event flags
    completed = [
        flag.replace("activity_completed_", "")
        for flag in save.event_flags
        if flag.startswith("activity_completed_") and save.event_flags[flag]
    ]

    return AvailableActivities(
        days_until_next_race=days_until,
        activities=available,
        completed_activities=completed,
    )


def perform_activity(save: SaveGame, activity_id: str, seed: int | None = None) -> tuple[SaveGame, ActivityOutcome]:
    """
    Perform an activity and return updated save + outcome.

    Args:
        save: Current save game state
        activity_id: ID of activity to perform
        seed: Optional random seed for deterministic outcomes

    Returns:
        Tuple of (updated save, activity outcome)
    """
    rng = random.Random(seed if seed is not None else save.random_seed)

    activity = ACTIVITY_MAP.get(activity_id)
    if activity is None:
        raise ValueError(f"Unknown activity: {activity_id}")

    # Get player driver
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        raise ValueError("No player driver found")

    # Check if activity can be performed
    available = get_available_activities(save)
    if activity_id not in [a.id for a in available.activities]:
        raise ValueError(f"Activity {activity_id} is not available")

    # Determine if risk triggers
    risk_triggered = activity.risk_chance > 0 and rng.random() < activity.risk_chance
    effects = activity.risk_effects if risk_triggered and activity.risk_effects else activity.base_effects

    # Apply effects to player
    new_fatigue = max(0, min(100, player.fatigue + effects.fatigue))
    new_morale = max(0, min(100, player.morale + effects.morale))
    new_form = max(0, min(100, player.current_form + effects.form))

    # Update player attributes if needed
    new_attributes = player.attributes
    if effects.reputation != 0:
        new_rep = max(0, min(100, player.attributes.reputation + effects.reputation))
        new_attributes = player.attributes.model_copy(update={"reputation": new_rep})
    if effects.sponsor_value != 0:
        new_sv = max(0, min(100, player.attributes.sponsor_value + effects.sponsor_value))
        new_attributes = new_attributes.model_copy(update={"sponsor_value": new_sv})

    updated_player = player.model_copy(
        update={
            "fatigue": new_fatigue,
            "morale": new_morale,
            "current_form": new_form,
            "attributes": new_attributes,
        }
    )

    # Update drivers list
    new_drivers = [updated_player if d.id == player.id else d for d in save.drivers]

    # Update academy trust if applicable
    new_academy_states = save.academy_states
    if effects.academy_trust != 0 and player.academy_id:
        new_academy_states = []
        for state in save.academy_states:
            if state.academy_id == player.academy_id:
                new_trust = max(0, min(100, state.trust + effects.academy_trust))
                new_academy_states.append(state.model_copy(update={"trust": new_trust}))
            else:
                new_academy_states.append(state)

    # Advance date
    current = datetime.strptime(save.current_date, "%Y-%m-%d")
    from datetime import timedelta

    new_date = (current + timedelta(days=activity.duration_days)).strftime("%Y-%m-%d")

    # Mark activity as completed
    new_flags = {**save.event_flags, f"activity_completed_{activity_id}": True}

    # Generate narrative
    narrative = _generate_narrative(activity, risk_triggered, effects, player.name)

    outcome = ActivityOutcome(
        activity_id=activity_id,
        activity_name=activity.name,
        success=not risk_triggered,
        narrative=narrative,
        effects_applied=effects,
    )

    updated_save = save.model_copy(
        update={
            "drivers": new_drivers,
            "academy_states": new_academy_states,
            "current_date": new_date,
            "event_flags": new_flags,
        }
    )

    return updated_save, outcome


def advance_to_race_week(save: SaveGame) -> SaveGame:
    """
    Advance time to the next race week, applying natural recovery and weekly focus.

    Used when player wants to skip remaining between-race activities.
    """
    # Import here to avoid circular dependency
    from app.engine.weekly_focus_engine import apply_focus_and_advance, clear_focus_completions

    next_round = next((r for r in save.calendar if not r.completed), None)
    if next_round is None:
        return save

    # Get player driver
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        return save

    # Apply weekly focus if one is active
    focus_outcome: FocusOutcome | None = None
    if save.development_profile and save.development_profile.active_focus_id:
        save, focus_outcome = apply_focus_and_advance(save)
        # Re-fetch player after focus application
        player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
        if player is None:
            return save

    # Calculate days skipped
    current = datetime.strptime(save.current_date, "%Y-%m-%d")
    next_start = datetime.strptime(next_round.start_date, "%Y-%m-%d")
    days_skipped = (next_start - current).days

    # Apply passive recovery (less effective than active rest)
    fatigue_recovery = min(days_skipped * 5, 30)  # 5 fatigue per day, max 30
    new_fatigue = max(0, player.fatigue - fatigue_recovery)

    # Small morale drift toward neutral
    morale_drift = 2 if player.morale < 50 else -2 if player.morale > 50 else 0
    new_morale = max(0, min(100, player.morale + morale_drift * days_skipped))

    updated_player = player.model_copy(
        update={
            "fatigue": new_fatigue,
            "morale": new_morale,
        }
    )

    new_drivers = [updated_player if d.id == player.id else d for d in save.drivers]

    # Clear activity and focus completion flags for new break period
    new_flags = {
        k: v for k, v in save.event_flags.items()
        if not k.startswith("activity_completed_") and not k.startswith("focus_completed_")
    }

    updated_save = save.model_copy(
        update={
            "drivers": new_drivers,
            "current_date": next_round.start_date,
            "phase": "race_week",
            "event_flags": new_flags,
        }
    )

    return updated_save


def _generate_narrative(
    activity: Activity, risk_triggered: bool, effects: ActivityEffect, driver_name: str
) -> str:
    """Generate a narrative description of the activity outcome."""
    if activity.type == "rest":
        if risk_triggered:
            return f"{driver_name} tried to rest but couldn't fully switch off from racing thoughts."
        return f"{driver_name} enjoyed some well-deserved rest and feels refreshed."

    if activity.type == "simulator":
        if risk_triggered:
            return f"{driver_name}'s simulator session was cut short due to technical issues."
        if effects.form >= 10:
            return f"{driver_name} had an excellent simulator session, finding significant time in key sectors."
        return f"{driver_name} put in solid work on the simulator, building confidence for the next race."

    if activity.type == "physical_training":
        return f"{driver_name} completed a rigorous training session, maintaining peak physical condition."

    if activity.type == "media_appearance":
        if risk_triggered:
            return f"{driver_name}'s interview took an awkward turn when pressed about team politics."
        return f"{driver_name} handled the media with confidence, delivering some great soundbites."

    if activity.type == "sponsor_event":
        return f"{driver_name} represented the team professionally at the sponsor event."

    if activity.type == "team_debrief":
        return f"{driver_name} spent quality time with the engineers, analyzing data and planning setup changes."

    if activity.type == "academy_meeting":
        if risk_triggered:
            return f"{driver_name}'s academy meeting was tense, with questions raised about recent performance."
        return f"{driver_name} had productive discussions with academy management about the path forward."

    if activity.type == "fan_engagement":
        return f"{driver_name} met with fans and signed autographs, enjoying the support from the paddock."

    if activity.type == "mental_coaching":
        return f"{driver_name} worked on mental preparation techniques, feeling more focused and resilient."

    return f"{driver_name} completed the {activity.name}."
