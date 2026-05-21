"""Engine for academy trust and relationship management."""

from __future__ import annotations

from typing import Literal

from app.models.academy import Academy
from app.models.race import RaceResult
from app.models.save_game import AcademyState, ChampionshipState, NewsItem, SaveGame


# Trust thresholds
TRUST_CRITICAL = 25
TRUST_WARNING = 40
TRUST_NEUTRAL = 55
TRUST_GOOD = 70
TRUST_EXCELLENT = 85

# Position expectations by trust level
EXPECTED_POSITIONS = {
    "excellent": 3,  # Expected to fight for podiums
    "good": 6,  # Expected top 6
    "neutral": 10,  # Expected points
    "warning": 15,  # Just finish reasonably
    "critical": 20,  # Anything helps
}


TrustLevel = Literal["excellent", "good", "neutral", "warning", "critical"]


def get_trust_level(trust: int) -> TrustLevel:
    """Get the trust level category from a trust value."""
    if trust >= TRUST_EXCELLENT:
        return "excellent"
    if trust >= TRUST_GOOD:
        return "good"
    if trust >= TRUST_NEUTRAL:
        return "neutral"
    if trust >= TRUST_WARNING:
        return "warning"
    return "critical"


def calculate_race_trust_change(
    save: SaveGame,
    race_result: RaceResult,
    is_feature: bool = True,
) -> tuple[int, str]:
    """
    Calculate trust change based on race result.

    Returns (trust_change, reason_text)
    """
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None or player.academy_id is None:
        return 0, ""

    academy = next((a for a in save.academies if a.id == player.academy_id), None)
    if academy is None or academy.style == "independent":
        return 0, ""

    academy_state = next(
        (s for s in save.academy_states if s.academy_id == player.academy_id), None
    )
    if academy_state is None:
        return 0, ""

    # Find player's position
    player_result = next(
        (r for r in race_result.classification if r.driver_id == player.id), None
    )
    if player_result is None:
        return 0, ""

    position = player_result.position
    is_dnf = player_result.status == "dnf"
    trust_level = get_trust_level(academy_state.trust)

    # Base trust change calculation
    expected_position = EXPECTED_POSITIONS[trust_level]

    # Scale factor based on race type (feature race matters more)
    race_weight = 1.5 if is_feature else 1.0

    # Academy patience affects magnitude (low patience = bigger swings)
    patience_factor = (100 - academy.patience) / 50  # 0.4 to 1.32

    if is_dnf:
        # DNF penalty depends on academy pressure
        pressure_factor = academy.pressure / 100
        change = int(-8 * pressure_factor * race_weight)
        reason = "DNF hurts your standing with the academy"
    elif position <= 3:
        # Podium bonus
        change = int((6 - position) * 3 * race_weight * patience_factor)
        reason = f"P{position} podium impresses the academy"
    elif position <= expected_position:
        # Met or exceeded expectations
        exceeded_by = expected_position - position
        change = int((2 + exceeded_by) * race_weight * patience_factor)
        if exceeded_by > 3:
            reason = f"P{position} far exceeds expectations"
        else:
            reason = f"P{position} meets academy expectations"
    elif position <= expected_position + 3:
        # Slightly below expectations
        change = int(-2 * race_weight * patience_factor)
        reason = f"P{position} is below what the academy expects"
    else:
        # Well below expectations
        below_by = position - expected_position
        pressure_factor = academy.pressure / 100
        change = int(-below_by * pressure_factor * race_weight * patience_factor)
        reason = f"P{position} disappoints the academy"

    # Cap changes
    change = max(-15, min(15, change))

    return change, reason


def calculate_championship_trust_modifier(
    save: SaveGame,
    standings: ChampionshipState,
) -> tuple[int, str]:
    """
    Calculate trust modifier based on championship position.

    Called at season checkpoints (every 4-5 races).
    """
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None or player.academy_id is None:
        return 0, ""

    academy = next((a for a in save.academies if a.id == player.academy_id), None)
    if academy is None or academy.style == "independent":
        return 0, ""

    # Find player's championship position
    sorted_standings = sorted(
        standings.driver_standings, key=lambda x: x.points, reverse=True
    )
    player_position = next(
        (i + 1 for i, s in enumerate(sorted_standings) if s.driver_id == player.id),
        None,
    )
    if player_position is None:
        return 0, ""

    # Calculate trust change based on championship position
    if player_position <= 3:
        change = 8 - player_position * 2  # +6, +4, +2
        reason = f"P{player_position} in championship strengthens your position"
    elif player_position <= 6:
        change = 1
        reason = "Solid championship position noted by academy"
    elif player_position <= 10:
        change = 0
        reason = ""
    elif player_position <= 15:
        change = -2
        reason = "Championship position below expectations"
    else:
        change = -5
        reason = "Poor championship standing concerns the academy"

    return change, reason


def generate_academy_feedback(
    save: SaveGame,
    trust_change: int,
    reason: str,
) -> NewsItem | None:
    """Generate a news item for significant academy trust changes."""
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None or player.academy_id is None:
        return None

    academy = next((a for a in save.academies if a.id == player.academy_id), None)
    if academy is None or academy.style == "independent":
        return None

    academy_state = next(
        (s for s in save.academy_states if s.academy_id == player.academy_id), None
    )
    if academy_state is None:
        return None

    trust_level = get_trust_level(academy_state.trust)

    # Only generate news for significant changes or critical trust
    if abs(trust_change) < 5 and trust_level not in ("warning", "critical"):
        return None

    import uuid

    if trust_change >= 5:
        headline = f"{academy.name} pleased with {player.name}'s progress"
        body = f"{reason}. The academy is watching closely as you continue to develop."
        importance = 3
    elif trust_change <= -5:
        headline = f"{academy.name} concerned about {player.name}'s recent form"
        body = f"{reason}. Management is reviewing your progress."
        importance = 4
    elif trust_level == "critical":
        headline = f"{player.name}'s academy seat under threat"
        body = f"Sources suggest {academy.name} is considering other options for next season."
        importance = 5
    elif trust_level == "warning":
        headline = f"{academy.name} expects improvement from {player.name}"
        body = "Consistent results are needed to secure future support."
        importance = 3
    else:
        return None

    return NewsItem(
        id=f"academy_feedback_{uuid.uuid4().hex[:8]}",
        date=save.current_date,
        category="academy",
        headline=headline,
        body=body,
        linked_driver_ids=[player.id],
        importance=importance,
    )


def get_academy_status(save: SaveGame) -> dict | None:
    """
    Get comprehensive academy status for the player.

    Returns dict with trust info, expectations, and warnings.
    """
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None or player.academy_id is None:
        return None

    academy = next((a for a in save.academies if a.id == player.academy_id), None)
    if academy is None:
        return None

    if academy.style == "independent":
        return {
            "academy_name": "Independent",
            "trust": None,
            "trust_level": None,
            "expected_position": None,
            "seat_security": "stable",
            "f1_pathway": "open",
            "warnings": [],
            "opportunities": ["Freedom to negotiate with any F1 team"],
        }

    academy_state = next(
        (s for s in save.academy_states if s.academy_id == player.academy_id), None
    )
    if academy_state is None:
        return None

    trust_level = get_trust_level(academy_state.trust)
    expected_position = EXPECTED_POSITIONS[trust_level]

    # Determine seat security
    if trust_level == "critical":
        seat_security = "at_risk"
    elif trust_level == "warning":
        seat_security = "uncertain"
    elif trust_level in ("neutral", "good"):
        seat_security = "stable"
    else:
        seat_security = "strong"

    # Determine F1 pathway status
    if academy.f1_team_id:
        if trust_level == "excellent":
            f1_pathway = "promising"
        elif trust_level == "good":
            f1_pathway = "possible"
        elif trust_level == "neutral":
            f1_pathway = "needs_work"
        else:
            f1_pathway = "unlikely"
    else:
        f1_pathway = "none"

    # Generate warnings
    warnings = []
    if trust_level == "critical":
        warnings.append("Your academy seat is under serious threat")
        warnings.append("Major improvement needed immediately")
    elif trust_level == "warning":
        warnings.append("The academy is monitoring your performance closely")
        warnings.append("Consistent results required to maintain support")

    # Generate opportunities
    opportunities = []
    if trust_level == "excellent":
        opportunities.append("F1 test opportunities may be available")
        opportunities.append("Academy support at maximum level")
    elif trust_level == "good":
        opportunities.append("On track for continued academy support")
    if academy.testing_opportunities >= 75:
        opportunities.append("Access to F1 simulator sessions")

    # Check for junior competition
    if academy_state.junior_depth and len(academy_state.junior_depth) > 2:
        warnings.append(f"{len(academy_state.junior_depth)} other juniors competing for attention")

    return {
        "academy_name": academy.name,
        "academy_style": academy.style,
        "trust": academy_state.trust,
        "trust_level": trust_level,
        "expected_position": expected_position,
        "seat_security": seat_security,
        "f1_pathway": f1_pathway,
        "f1_team": academy.f1_team_id,
        "warnings": warnings,
        "opportunities": opportunities,
        "pressure": academy.pressure,
        "patience": academy.patience,
        "support_level": academy.support_level,
    }


def apply_race_trust_change(
    save: SaveGame,
    race_result: RaceResult,
    is_feature: bool = True,
) -> tuple[SaveGame, NewsItem | None]:
    """
    Apply trust change from a race result and generate feedback if needed.

    Returns (updated_save, optional_news_item)
    """
    trust_change, reason = calculate_race_trust_change(save, race_result, is_feature)

    if trust_change == 0:
        return save, None

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None or player.academy_id is None:
        return save, None

    # Update academy state
    new_academy_states = []
    for state in save.academy_states:
        if state.academy_id == player.academy_id:
            new_trust = max(0, min(100, state.trust + trust_change))
            new_academy_states.append(state.model_copy(update={"trust": new_trust}))
        else:
            new_academy_states.append(state)

    updated_save = save.model_copy(update={"academy_states": new_academy_states})

    # Generate feedback news
    news_item = generate_academy_feedback(updated_save, trust_change, reason)

    return updated_save, news_item


def check_season_milestone(
    save: SaveGame,
    completed_rounds: int,
) -> tuple[SaveGame, list[NewsItem]]:
    """
    Check for season milestones and apply championship-based trust changes.

    Called after each race weekend completion.
    Returns (updated_save, news_items)
    """
    news_items = []

    # Check milestones at rounds 4, 8, 12 (approximately quarterly)
    milestone_rounds = {4, 8, 12}
    if completed_rounds not in milestone_rounds:
        return save, news_items

    trust_change, reason = calculate_championship_trust_modifier(save, save.standings)

    if trust_change == 0:
        return save, news_items

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None or player.academy_id is None:
        return save, news_items

    # Update academy state
    new_academy_states = []
    for state in save.academy_states:
        if state.academy_id == player.academy_id:
            new_trust = max(0, min(100, state.trust + trust_change))
            new_academy_states.append(state.model_copy(update={"trust": new_trust}))
        else:
            new_academy_states.append(state)

    updated_save = save.model_copy(update={"academy_states": new_academy_states})

    # Generate milestone news
    if reason:
        import uuid

        academy = next((a for a in save.academies if a.id == player.academy_id), None)
        academy_name = academy.name if academy else "Academy"

        news_items.append(
            NewsItem(
                id=f"academy_milestone_{uuid.uuid4().hex[:8]}",
                date=save.current_date,
                category="academy",
                headline=f"Season review: {academy_name} assesses {player.name}",
                body=reason,
                linked_driver_ids=[player.id],
                importance=3,
            )
        )

    return updated_save, news_items
