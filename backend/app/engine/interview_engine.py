"""Interview engine for post-race media interactions.

This engine handles:
- Detecting interview triggers from race/qualifying results
- Generating pending interviews based on triggers
- Processing player responses and applying effects
- Creating news items from interview choices
- Awarding media XP from interviews
"""

from __future__ import annotations

import json
import random
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.models.interview import (
    InterviewChoice,
    InterviewEffect,
    InterviewQuestion,
    InterviewResponse,
    InterviewTrigger,
    PendingInterview,
)
from app.models.save_game import NewsItem

if TYPE_CHECKING:
    from app.models.save_game import SaveGame


# Load interview questions from data file
_QUESTIONS_FILE = Path(__file__).parent.parent / "data" / "interview_questions.json"
_INTERVIEW_QUESTIONS: list[dict] | None = None


def _load_questions() -> list[dict]:
    """Load interview questions from JSON file."""
    global _INTERVIEW_QUESTIONS
    if _INTERVIEW_QUESTIONS is None:
        with open(_QUESTIONS_FILE) as f:
            _INTERVIEW_QUESTIONS = json.load(f)
    return _INTERVIEW_QUESTIONS


def _parse_question(data: dict) -> InterviewQuestion:
    """Parse a question dict into an InterviewQuestion model."""
    choices = []
    for choice_data in data.get("choices", []):
        effects_data = choice_data.get("effects", {})
        effects = InterviewEffect(
            marketability=effects_data.get("marketability", 0),
            reputation=effects_data.get("reputation", 0),
            confidence=effects_data.get("confidence", 0),
            morale=effects_data.get("morale", 0),
            team_trust=effects_data.get("teamTrust", 0),
            academy_trust=effects_data.get("academyTrust", 0),
            fan_support=effects_data.get("fanSupport", 0),
            rivalry_intensity=effects_data.get("rivalryIntensity", 0),
            rumor_intensity=effects_data.get("rumorIntensity", 0),
            sponsor_interest=effects_data.get("sponsorInterest", 0),
            media_xp=effects_data.get("mediaXp", 0),
            perception_tags=effects_data.get("perceptionTags", []),
            narrative_tone=effects_data.get("narrativeTone", "neutral"),
        )
        choice = InterviewChoice(
            id=choice_data["id"],
            text=choice_data["text"],
            tone=choice_data["tone"],
            effects=effects,
            risk_level=choice_data.get("riskLevel", "safe"),
            follow_up_headline=choice_data.get("followUpHeadline", ""),
            follow_up_body=choice_data.get("followUpBody", ""),
            hidden_effects_hint=choice_data.get("hiddenEffectsHint"),
        )
        choices.append(choice)

    return InterviewQuestion(
        id=data["id"],
        trigger=data["trigger"],
        reporter_name=data.get("reporter_name", "Sky Sports Reporter"),
        question=data["question"],
        context=data.get("context", ""),
        choices=choices,
        priority=data.get("priority", 1),
        requires_academy=data.get("requiresAcademy", False),
        requires_rival=data.get("requiresRival", False),
        requires_f1=data.get("requiresF1", False),
        requires_f2=data.get("requiresF2", False),
    )


def detect_triggers(save: SaveGame, weekend_result: dict | None = None) -> list[InterviewTrigger]:
    """Detect interview triggers from current save state and weekend result.

    Args:
        save: The current save game state
        weekend_result: Optional dict with weekend result data for trigger detection

    Returns:
        List of detected triggers
    """
    triggers: list[InterviewTrigger] = []
    player_id = save.player_driver_id

    if not player_id:
        return triggers

    player = next((d for d in save.drivers if d.id == player_id), None)
    if not player:
        return triggers

    is_f1 = player.series == "F1"
    is_f2 = player.series == "F2"
    has_academy = bool(player.academy_id)

    # Get active rivalry (rivalries are always between player and opponent)
    active_rival = None
    for rivalry in save.rivalries:
        if rivalry.is_active and rivalry.opponent_id:
            active_rival = rivalry.opponent_id
            break

    # If no weekend result provided, try to get from most recent
    if weekend_result is None and save.weekend_results:
        last_weekend = save.weekend_results[-1]
        weekend_result = _extract_weekend_data(save, last_weekend)

    if weekend_result:
        feature_pos = weekend_result.get("feature_position")
        quali_pos = weekend_result.get("qualifying_position")
        positions_gained = weekend_result.get("positions_gained", 0)
        dnf_reason = weekend_result.get("dnf_reason")
        penalties_received = weekend_result.get("penalties", 0)
        strategy_controversy = weekend_result.get("strategy_controversy", False)
        team_orders_given = weekend_result.get("team_orders", False)
        rival_incident = weekend_result.get("rival_incident", False)
        is_first_f1_race = weekend_result.get("is_first_f1_race", False)
        points_scored = weekend_result.get("points_scored", 0)
        first_f1_points = weekend_result.get("first_f1_points", False)
        close_teammate_battle = weekend_result.get("close_teammate_battle", False)

        # Race win
        if feature_pos == 1:
            triggers.append("race_win")
            # Check if first career win
            total_wins = sum(
                1 for w in save.weekend_results
                if w.feature and any(
                    r.driver_id == player_id and r.position == 1
                    for r in w.feature.classification
                )
            )
            if total_wins <= 1:
                triggers.append("first_career_win")

        # Podium (but not win, to avoid duplicate)
        elif feature_pos and 2 <= feature_pos <= 3:
            triggers.append("podium")
            # Check if first career podium
            total_podiums = sum(
                1 for w in save.weekend_results
                if w.feature and any(
                    r.driver_id == player_id and r.position <= 3
                    for r in w.feature.classification
                )
            )
            if total_podiums <= 1:
                triggers.append("first_career_podium")

        # Pole position
        if quali_pos == 1:
            triggers.append("pole_position")

        # Big recovery (gained 5+ positions)
        if positions_gained and positions_gained >= 5:
            triggers.append("big_recovery")

        # Underperformance (lost 5+ positions or finished well below expectations)
        if positions_gained and positions_gained <= -5:
            triggers.append("underperformance")

        # DNF scenarios
        if dnf_reason:
            if dnf_reason in ("mechanical", "engine", "gearbox", "hydraulics"):
                triggers.append("dnf_mechanical")
            elif dnf_reason in ("collision", "crash", "contact"):
                triggers.append("major_crash")
                triggers.append("dnf_collision")

        # Penalty received
        if penalties_received and penalties_received > 0:
            triggers.append("penalty_received")

        # Strategy controversy
        if strategy_controversy:
            triggers.append("strategy_controversy")

        # Team orders
        if team_orders_given:
            triggers.append("team_orders")

        # Rival incident
        if rival_incident and active_rival:
            triggers.append("rival_incident")

        # First F1 race
        if is_first_f1_race and is_f1:
            triggers.append("first_f1_race")

        # First F1 points
        if first_f1_points and is_f1:
            triggers.append("first_f1_points")

        # Teammate battle
        if close_teammate_battle:
            triggers.append("teammate_battle")

    # Championship standings based triggers
    if save.standings and save.standings.driver_standings:
        sorted_standings = sorted(
            save.standings.driver_standings,
            key=lambda s: s.points,
            reverse=True,
        )
        player_standing = next(
            (s for s in sorted_standings if s.driver_id == player_id),
            None,
        )
        if player_standing and sorted_standings and sorted_standings[0].driver_id == player_id:
            triggers.append("championship_leader")

    # F1 standings for F1 players
    if is_f1 and save.f1_standings and save.f1_standings.driver_standings:
        sorted_f1 = sorted(
            save.f1_standings.driver_standings,
            key=lambda s: s.points,
            reverse=True,
        )
        player_f1_standing = next(
            (s for s in sorted_f1 if s.driver_id == player_id),
            None,
        )
        if player_f1_standing and sorted_f1 and sorted_f1[0].driver_id == player_id:
            triggers.append("championship_leader")

    # Academy evaluation trigger (when player has academy and is in F2)
    if has_academy and is_f2 and weekend_result:
        # Trigger when in top 3 or important race
        if weekend_result.get("feature_position") and weekend_result["feature_position"] <= 5:
            triggers.append("academy_evaluation")

    # Remove duplicates
    return list(set(triggers))


def _extract_weekend_data(save: SaveGame, weekend) -> dict:
    """Extract trigger-relevant data from a weekend result."""
    player_id = save.player_driver_id
    if not player_id:
        return {}

    data = {}

    # Feature race data
    if weekend.feature:
        player_result = next(
            (r for r in weekend.feature.classification if r.driver_id == player_id),
            None,
        )
        if player_result:
            data["feature_position"] = player_result.position
            data["points_scored"] = player_result.points if hasattr(player_result, "points") else 0
            if hasattr(player_result, "dnf") and player_result.dnf:
                data["dnf_reason"] = getattr(player_result, "dnf_reason", "crash")

    # Qualifying data
    if weekend.qualifying:
        player_quali = next(
            (r for r in weekend.qualifying.classification if r.driver_id == player_id),
            None,
        )
        if player_quali:
            data["qualifying_position"] = player_quali.position
            if "feature_position" in data:
                data["positions_gained"] = player_quali.position - data["feature_position"]

    # Check for first F1 race
    player = next((d for d in save.drivers if d.id == player_id), None)
    if player and player.series == "F1":
        f1_race_count = len([
            w for w in save.weekend_results
            if w.feature and any(r.driver_id == player_id for r in w.feature.classification)
        ])
        data["is_first_f1_race"] = f1_race_count <= 1

        # Check first F1 points
        if data.get("points_scored", 0) > 0:
            previous_points = sum(
                r.points if hasattr(r, "points") else 0
                for w in save.weekend_results[:-1]
                if w.feature
                for r in w.feature.classification
                if r.driver_id == player_id
            )
            data["first_f1_points"] = previous_points == 0

    return data


def select_question_for_trigger(
    save: SaveGame,
    trigger: InterviewTrigger,
    context_data: dict | None = None,
) -> InterviewQuestion | None:
    """Select an appropriate interview question for a trigger.

    Args:
        save: The current save game state
        trigger: The trigger to find a question for
        context_data: Optional context data (rival name, etc.)

    Returns:
        Selected InterviewQuestion or None if no suitable question
    """
    questions = _load_questions()
    player_id = save.player_driver_id

    if not player_id:
        return None

    player = next((d for d in save.drivers if d.id == player_id), None)
    if not player:
        return None

    is_f1 = player.series == "F1"
    is_f2 = player.series == "F2"
    has_academy = bool(player.academy_id)
    has_rival = any(r.is_active and r.opponent_id for r in save.rivalries)

    # Filter questions matching the trigger
    matching = []
    for q_data in questions:
        if q_data.get("trigger") != trigger:
            continue

        # Check requirements
        if q_data.get("requiresF1") and not is_f1:
            continue
        if q_data.get("requiresF2") and not is_f2:
            continue
        if q_data.get("requiresAcademy") and not has_academy:
            continue
        if q_data.get("requiresRival") and not has_rival:
            continue

        matching.append(q_data)

    if not matching:
        return None

    # Sort by priority and pick the highest priority question
    matching.sort(key=lambda q: q.get("priority", 1), reverse=True)

    # If multiple with same priority, pick randomly
    top_priority = matching[0].get("priority", 1)
    top_questions = [q for q in matching if q.get("priority", 1) == top_priority]

    selected = random.choice(top_questions)
    return _parse_question(selected)


def generate_interview(
    save: SaveGame,
    trigger: InterviewTrigger,
    round_id: str,
    context_data: dict | None = None,
) -> PendingInterview | None:
    """Generate a pending interview for a trigger.

    Args:
        save: The current save game state
        trigger: The trigger type
        round_id: The round ID this interview is for
        context_data: Optional context (rival name, team name, etc.)

    Returns:
        PendingInterview or None if no suitable question found
    """
    # Check cooldown - don't trigger same type too frequently
    last_trigger_round = save.interview_state.last_trigger_round.get(trigger)
    if last_trigger_round == round_id:
        return None

    question = select_question_for_trigger(save, trigger, context_data)
    if not question:
        return None

    # Build context data with driver/team names
    ctx = context_data or {}

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player:
        ctx["driver"] = player.name
        ctx["driver_first"] = player.name.split()[0] if player.name else "Driver"

        team = next((t for t in save.teams if t.id == player.team_id), None)
        if team:
            ctx["team"] = team.name

    # Add rival name if present
    for rivalry in save.rivalries:
        if rivalry.is_active and rivalry.opponent_id:
            rival = next((d for d in save.drivers if d.id == rivalry.opponent_id), None)
            if rival:
                ctx["rival_name"] = rival.name
            break

    return PendingInterview(
        id=str(uuid.uuid4()),
        round_id=round_id,
        trigger=trigger,
        question=question,
        context_data=ctx,
        created_date=save.current_date,
    )


def generate_interviews_for_weekend(
    save: SaveGame,
    round_id: str,
    weekend_result: dict | None = None,
    max_interviews: int = 1,
) -> list[PendingInterview]:
    """Generate interviews based on weekend results.

    Args:
        save: The current save game state
        round_id: The round ID
        weekend_result: Optional weekend result data
        max_interviews: Maximum number of interviews to generate

    Returns:
        List of pending interviews
    """
    triggers = detect_triggers(save, weekend_result)

    if not triggers:
        return []

    # Sort triggers by priority (we want to ask about wins before podiums, etc.)
    trigger_priority = {
        "race_win": 100,
        "first_career_win": 99,
        "first_f1_race": 98,
        "first_f1_points": 97,
        "championship_clinch": 96,
        "first_career_podium": 95,
        "pole_position": 90,
        "podium": 85,
        "major_crash": 80,
        "rival_incident": 78,
        "strategy_controversy": 75,
        "team_orders": 72,
        "penalty_received": 70,
        "big_recovery": 65,
        "championship_leader": 60,
        "teammate_battle": 55,
        "academy_evaluation": 50,
        "underperformance": 40,
        "dnf_mechanical": 35,
        "dnf_collision": 35,
        "contract_speculation": 30,
    }

    sorted_triggers = sorted(
        triggers,
        key=lambda t: trigger_priority.get(t, 0),
        reverse=True,
    )

    interviews = []
    for trigger in sorted_triggers[:max_interviews]:
        interview = generate_interview(save, trigger, round_id)
        if interview:
            interviews.append(interview)

    return interviews


def apply_interview_response(
    save: SaveGame,
    interview_id: str,
    choice_id: str,
) -> tuple[SaveGame, InterviewResponse | None, NewsItem | None]:
    """Apply the effects of an interview response.

    Args:
        save: The current save game state
        interview_id: The pending interview ID
        choice_id: The selected choice ID

    Returns:
        Tuple of (updated save, response record, generated news item)
    """
    # Find the pending interview
    pending = next(
        (i for i in save.interview_state.pending_interviews if i.id == interview_id),
        None,
    )

    if not pending:
        return save, None, None

    # Find the selected choice
    choice = next(
        (c for c in pending.question.choices if c.id == choice_id),
        None,
    )

    if not choice:
        return save, None, None

    player_id = save.player_driver_id
    if not player_id:
        return save, None, None

    # Apply effects to player driver
    updated_drivers = list(save.drivers)
    player_idx = next(
        (i for i, d in enumerate(updated_drivers) if d.id == player_id),
        None,
    )

    if player_idx is not None:
        player = updated_drivers[player_idx]
        updated_attrs = dict(player.attributes)

        effects = choice.effects

        # Apply attribute changes
        if "marketability" in updated_attrs:
            updated_attrs["marketability"] = max(
                1, min(99, updated_attrs["marketability"] + effects.marketability)
            )
        else:
            updated_attrs["marketability"] = max(1, min(99, 50 + effects.marketability))

        # Apply confidence (it's in attributes, not hidden)
        if "confidence" in updated_attrs and effects.confidence != 0:
            updated_attrs["confidence"] = max(
                1, min(99, updated_attrs["confidence"] + effects.confidence)
            )

        # Apply reputation
        if "reputation" in updated_attrs and effects.reputation != 0:
            updated_attrs["reputation"] = max(
                1, min(99, updated_attrs["reputation"] + effects.reputation)
            )

        # Apply morale (it's a direct attribute on Driver)
        updated_morale = max(1, min(99, player.morale + effects.morale))

        # Update player
        updated_player = player.model_copy(
            update={
                "attributes": updated_attrs,
                "morale": updated_morale,
            }
        )
        updated_drivers[player_idx] = updated_player

    # Apply team trust changes
    updated_teams = list(save.teams)
    player = next((d for d in save.drivers if d.id == player_id), None)
    if player and player.team_id and choice.effects.team_trust != 0:
        team_idx = next(
            (i for i, t in enumerate(updated_teams) if t.id == player.team_id),
            None,
        )
        if team_idx is not None:
            team = updated_teams[team_idx]
            # Team trust is stored in performance_tier or we need to track it elsewhere
            # For now, store in event_flags

    # Apply academy trust changes
    updated_academy_states = list(save.academy_states)
    if player and player.academy_id and choice.effects.academy_trust != 0:
        academy_idx = next(
            (i for i, a in enumerate(updated_academy_states) if a.academy_id == player.academy_id),
            None,
        )
        if academy_idx is not None:
            academy = updated_academy_states[academy_idx]
            updated_trust = max(0, min(100, academy.trust + choice.effects.academy_trust))
            updated_academy_states[academy_idx] = academy.model_copy(
                update={"trust": updated_trust}
            )

    # Apply rivalry intensity changes
    updated_rivalries = list(save.rivalries)
    if choice.effects.rivalry_intensity != 0:
        for i, rivalry in enumerate(updated_rivalries):
            if rivalry.is_active and rivalry.opponent_id:
                new_intensity = max(0, min(100, rivalry.intensity + choice.effects.rivalry_intensity))
                updated_rivalries[i] = rivalry.model_copy(update={"intensity": new_intensity})
                break

    # Generate news headline/body with context substitution
    context = pending.context_data
    headline = choice.follow_up_headline
    body = choice.follow_up_body

    for key, value in context.items():
        headline = headline.replace(f"{{{key}}}", str(value))
        body = body.replace(f"{{{key}}}", str(value))

    # Create news item
    news_item = NewsItem(
        id=str(uuid.uuid4()),
        date=save.current_date,
        category="media",
        headline=headline,
        body=body,
        linked_driver_ids=[player_id],
        importance=2 if choice.effects.narrative_tone == "controversial" else 1,
    )

    # Create interview response record
    response = InterviewResponse(
        interview_id=interview_id,
        round_id=pending.round_id,
        trigger=pending.trigger,
        question_id=pending.question.id,
        choice_id=choice_id,
        choice_text=choice.text,
        effects_applied=choice.effects,
        news_headline=headline,
        news_body=body,
        response_date=save.current_date,
    )

    # Update interview state
    updated_pending = [i for i in save.interview_state.pending_interviews if i.id != interview_id]
    updated_history = list(save.interview_state.interview_history) + [response]
    updated_trigger_rounds = dict(save.interview_state.last_trigger_round)
    updated_trigger_rounds[pending.trigger] = pending.round_id

    updated_interview_state = save.interview_state.model_copy(
        update={
            "pending_interviews": updated_pending,
            "interview_history": updated_history,
            "total_interviews_completed": save.interview_state.total_interviews_completed + 1,
            "last_trigger_round": updated_trigger_rounds,
        }
    )

    # Add media XP to development profile
    updated_profile = save.development_profile
    if updated_profile and choice.effects.media_xp > 0:
        updated_branch_xp = dict(updated_profile.branch_xp)
        updated_branch_xp["media_marketability"] = (
            updated_branch_xp.get("media_marketability", 0) + choice.effects.media_xp
        )
        updated_profile = updated_profile.model_copy(
            update={"branch_xp": updated_branch_xp}
        )

    # Add news to save
    updated_news = list(save.news) + [news_item]

    # Store effects in event flags for reference
    updated_flags = dict(save.event_flags)
    updated_flags["last_interview_effects"] = {
        "team_trust": choice.effects.team_trust,
        "academy_trust": choice.effects.academy_trust,
        "fan_support": choice.effects.fan_support,
        "rivalry_intensity": choice.effects.rivalry_intensity,
        "rumor_intensity": choice.effects.rumor_intensity,
        "perception_tags": choice.effects.perception_tags,
    }

    # Build updated save
    updated_save = save.model_copy(
        update={
            "drivers": updated_drivers,
            "teams": updated_teams,
            "academy_states": updated_academy_states,
            "rivalries": updated_rivalries,
            "interview_state": updated_interview_state,
            "development_profile": updated_profile,
            "news": updated_news,
            "event_flags": updated_flags,
        }
    )

    return updated_save, response, news_item


def add_pending_interview(save: SaveGame, interview: PendingInterview) -> SaveGame:
    """Add a pending interview to the save state.

    Args:
        save: The current save game state
        interview: The pending interview to add

    Returns:
        Updated save game
    """
    updated_pending = list(save.interview_state.pending_interviews) + [interview]
    updated_state = save.interview_state.model_copy(
        update={"pending_interviews": updated_pending}
    )

    return save.model_copy(update={"interview_state": updated_state})


def get_pending_interviews(save: SaveGame) -> list[PendingInterview]:
    """Get all pending interviews for the player.

    Args:
        save: The current save game state

    Returns:
        List of pending interviews
    """
    return list(save.interview_state.pending_interviews)


def has_pending_interview(save: SaveGame) -> bool:
    """Check if the player has any pending interviews.

    Args:
        save: The current save game state

    Returns:
        True if there are pending interviews
    """
    return len(save.interview_state.pending_interviews) > 0


def clear_expired_interviews(save: SaveGame) -> SaveGame:
    """Remove expired interviews from the pending list.

    Args:
        save: The current save game state

    Returns:
        Updated save game
    """
    current_round = None
    if save.calendar:
        current = next((r for r in save.calendar if r.status == "current"), None)
        if current:
            current_round = current.id

    if not current_round:
        return save

    # Filter out expired interviews
    updated_pending = [
        i for i in save.interview_state.pending_interviews
        if not i.expires_after_round or i.expires_after_round >= current_round
    ]

    if len(updated_pending) == len(save.interview_state.pending_interviews):
        return save

    updated_state = save.interview_state.model_copy(
        update={"pending_interviews": updated_pending}
    )

    return save.model_copy(update={"interview_state": updated_state})


def format_interview_for_display(
    interview: PendingInterview,
    save: SaveGame,
) -> dict:
    """Format a pending interview for frontend display.

    Args:
        interview: The pending interview
        save: The current save game state

    Returns:
        Dict formatted for frontend consumption
    """
    context = interview.context_data

    # Substitute context in question text
    question_text = interview.question.question
    for key, value in context.items():
        question_text = question_text.replace(f"{{{key}}}", str(value))

    # Format choices
    formatted_choices = []
    for choice in interview.question.choices:
        choice_text = choice.text
        for key, value in context.items():
            choice_text = choice_text.replace(f"{{{key}}}", str(value))

        formatted_choices.append({
            "id": choice.id,
            "text": choice_text,
            "tone": choice.tone,
            "riskLevel": choice.risk_level,
            "hiddenEffectsHint": choice.hidden_effects_hint,
        })

    return {
        "id": interview.id,
        "roundId": interview.round_id,
        "trigger": interview.trigger,
        "reporterName": interview.question.reporter_name,
        "question": question_text,
        "context": interview.question.context,
        "choices": formatted_choices,
        "createdDate": interview.created_date,
    }
