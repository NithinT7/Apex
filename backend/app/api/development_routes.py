"""API routes for the weekly focus development system."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.engine.skill_tree_engine import (
    get_node_preview,
    get_skill_tree_state,
    unlock_node,
)
from app.engine.weekly_focus_engine import (
    apply_focus_and_advance,
    choose_focus,
    get_available_focuses,
    get_development_profile_summary,
)
from app.models.save_game import SaveGame
from app.models.weekly_focus import FocusOutcome
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/development", tags=["development"])
manager = SaveManager()


class ChooseFocusRequest(BaseModel):
    """Request body for choosing a weekly focus."""
    focus_id: str


class UnlockNodeRequest(BaseModel):
    """Request body for unlocking a skill tree node."""
    node_id: str


class FocusListResponse(BaseModel):
    """Response model for available focuses."""

    class FocusInfo(BaseModel):
        focus: dict
        is_available: bool
        unmet_requirements: list[str]
        is_recommended: bool
        recommendation_reason: str

        class Config:
            # Allow arbitrary dict for focus
            arbitrary_types_allowed = True

    available_focuses: list[dict]
    days_until_next_race: int
    focus_slots_available: int
    active_focus_id: str | None
    completed_focus_ids: list[str]


class DevelopmentProfileResponse(BaseModel):
    """Response model for development profile."""

    current_points: int
    total_points_earned: int
    branch_xp: dict[str, int]
    total_branch_xp: int
    unlocked_node_ids: list[str]
    unlocked_trait_ids: list[str]
    active_focus_id: str | None
    recent_history: list[dict]


@router.get("/focuses")
def list_available_focuses(save_id: str) -> dict:
    """
    Get available weekly focuses for the current player state.

    Returns all focus options with availability status, unlock requirements,
    and recommendations based on player state.
    """
    save = _get_save(save_id)

    if save.phase not in ("between_races", "preseason"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Weekly focus selection only available during between_races or preseason phase (current: {save.phase})",
        )

    result = get_available_focuses(save)
    return result.to_dict()


@router.post("/focus")
def select_focus(save_id: str, request: ChooseFocusRequest) -> dict:
    """
    Choose a weekly focus for the current between-race period.

    The focus effects will be applied when advancing to the next race week.
    """
    save = _get_save(save_id)

    if save.phase not in ("between_races", "preseason"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Weekly focus selection only available during between_races or preseason phase (current: {save.phase})",
        )

    try:
        updated_save = choose_focus(save, request.focus_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    saved = manager.save(updated_save)

    return {
        "success": True,
        "activeFocusId": saved.development_profile.active_focus_id if saved.development_profile else None,
        "message": f"Focus set to {request.focus_id}",
    }


@router.post("/focus/apply")
def apply_focus(save_id: str) -> dict:
    """
    Apply the current active focus and get the outcome.

    This is typically called when transitioning to race week, but can also
    be called explicitly to see the focus results.
    """
    save = _get_save(save_id)

    if save.development_profile is None or save.development_profile.active_focus_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active focus to apply",
        )

    updated_save, outcome = apply_focus_and_advance(save)
    saved = manager.save(updated_save)

    if outcome is None:
        return {"success": False, "message": "No focus was applied"}

    return {
        "success": True,
        "outcome": outcome.model_dump(by_alias=True),
    }


@router.delete("/focus")
def clear_focus(save_id: str) -> dict:
    """Clear the active focus without applying it."""
    save = _get_save(save_id)

    if save.development_profile is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No development profile found",
        )

    updated_profile = save.development_profile.model_copy(update={"active_focus_id": None})
    updated_save = save.model_copy(update={"development_profile": updated_profile})
    manager.save(updated_save)

    return {"success": True, "message": "Focus cleared"}


@router.get("/profile")
def get_profile(save_id: str) -> dict:
    """
    Get the player's development profile summary.

    Returns XP progress, unlocked skills/traits, and recent development history.
    """
    save = _get_save(save_id)

    if save.player_driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    return get_development_profile_summary(save)


@router.get("/history")
def get_development_history(save_id: str, limit: int = 20) -> dict:
    """
    Get the player's development history.

    Returns recent development events including focus completions,
    race XP gains, and skill unlocks.
    """
    save = _get_save(save_id)

    if save.development_profile is None:
        return {"history": []}

    history = save.development_profile.history[-limit:]

    return {
        "history": [
            {
                "date": h.date,
                "roundId": h.round_id,
                "source": h.source,
                "xpGained": h.xp_gained,
                "developmentPointsGained": h.development_points_gained,
                "nodeUnlocked": h.node_unlocked,
                "traitUnlocked": h.trait_unlocked,
                "summary": h.summary,
            }
            for h in reversed(history)
        ]
    }


@router.get("/skill-tree")
def get_skill_tree(save_id: str) -> dict:
    """
    Get the complete skill tree state for the player.

    Returns all branches with nodes in their current state (locked/available/unlocked),
    XP progress, unlocked traits, and recommendations.
    """
    save = _get_save(save_id)

    if save.player_driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    state = get_skill_tree_state(save)
    return state.to_dict()


@router.post("/unlock-node")
def unlock_skill_node(save_id: str, request: UnlockNodeRequest) -> dict:
    """
    Attempt to unlock a skill tree node.

    Validates XP requirements, development points, and prerequisites.
    If successful, applies the node's effects and saves the game.
    """
    save = _get_save(save_id)

    if save.player_driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    updated_save, result = unlock_node(save, request.node_id)

    if result.success:
        manager.save(updated_save)

    return result.to_dict()


@router.get("/skill-tree/node/{node_id}")
def get_node_details(save_id: str, node_id: str) -> dict:
    """
    Get detailed preview information about a specific skill tree node.

    Returns full information about requirements, effects, and unlock status.
    """
    save = _get_save(save_id)

    if save.player_driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    return get_node_preview(save, node_id)


@router.get("/weekend-summary")
def get_weekend_development_summary(save_id: str) -> dict:
    """
    Get the development summary from the last completed weekend.

    Returns XP gained by branch, development points earned, new nodes
    available, and a human-readable breakdown of what was achieved.
    """
    save = _get_save(save_id)

    # Check event flags for the stored summary
    summary = save.event_flags.get("last_weekend_development")

    if summary is None:
        return {
            "available": False,
            "message": "No weekend development summary available",
        }

    return {
        "available": True,
        **summary,
    }


@router.delete("/weekend-summary")
def clear_weekend_development_summary(save_id: str) -> dict:
    """
    Clear the weekend development summary after it has been viewed.

    Called by the frontend after displaying the summary to the player.
    """
    save = _get_save(save_id)

    # Remove the summary from event flags
    updated_flags = {k: v for k, v in save.event_flags.items() if k != "last_weekend_development"}
    updated_save = save.model_copy(update={"event_flags": updated_flags})
    manager.save(updated_save)

    return {"success": True, "message": "Summary cleared"}


@router.get("/f1-adaptation")
def get_f1_adaptation_status(save_id: str) -> dict:
    """
    Get the player's F1 rookie adaptation status.

    Returns adaptation progress, current penalty, and estimated remaining adjustment.
    """
    from app.engine.player_balance import get_f1_adaptation_state

    save = _get_save(save_id)

    if save.player_driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player driver not found",
        )

    # Get adaptation state
    state = get_f1_adaptation_state(save, save.player_driver_id)

    return {
        "isInF1": player.series == "F1",
        "f1RacesCompleted": state.f1_races_completed,
        "adaptationProgress": round(state.adaptation_progress, 1),
        "currentPenalty": state.current_penalty,
        "fullyAdapted": state.fully_adapted,
        "estimatedRacesRemaining": max(0, 10 - state.f1_races_completed) if not state.fully_adapted else 0,
    }


@router.get("/difficulty-info")
def get_difficulty_info(save_id: str) -> dict:
    """
    Get information about the save's difficulty settings.

    Returns the difficulty preset and its effects on development.
    """
    from app.engine.player_balance import get_difficulty_config

    save = _get_save(save_id)
    config = get_difficulty_config(save.difficulty)

    return {
        "difficulty": save.difficulty,
        "name": config.name,
        "description": config.description,
        "potentialRange": f"{config.potential_min}-{config.potential_max}",
        "softCap": config.soft_cap,
        "hardCap": config.hard_cap,
        "devPointMultiplier": config.dev_point_multiplier,
        "xpMultiplier": config.xp_multiplier,
        "canReachElite": config.hard_cap >= 94,
    }


@router.get("/player-achievements")
def get_player_achievements(save_id: str) -> dict:
    """
    Get the player's career achievements that affect development caps.
    """
    save = _get_save(save_id)

    if save.player_driver_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    # Calculate achievements from save data
    achievements = _calculate_achievements(save)

    return {
        "achievements": achievements,
        "capBreakingAchievements": [
            a for a in achievements
            if a["id"] in {"f2_champion", "f1_podium", "f1_race_winner", "f1_champion", "f1_pole"}
        ],
        "totalCapBonus": sum(a.get("capBonus", 0) for a in achievements),
    }


def _calculate_achievements(save) -> list[dict]:
    """Calculate achievements from save data."""
    from app.models.save_game import SaveGame

    achievements = []
    player_id = save.player_driver_id

    if not player_id:
        return achievements

    # Check F2 championship
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
        if player_standing:
            # Check for F2 wins
            if player_standing.wins > 0:
                achievements.append({
                    "id": "f2_race_winner",
                    "name": "F2 Race Winner",
                    "description": f"Won {player_standing.wins} F2 race(s)",
                    "capBonus": 1,
                })

            # Check if F2 champion (would need to check previous seasons)
            if sorted_standings[0].driver_id == player_id and player_standing.wins >= 3:
                achievements.append({
                    "id": "f2_champion",
                    "name": "F2 Champion",
                    "description": "Won the F2 Championship",
                    "capBonus": 2,
                })

    # Check for F1 achievements from weekend results
    player = next((d for d in save.drivers if d.id == player_id), None)
    if player and player.series == "F1":
        f1_wins = 0
        f1_podiums = 0
        f1_poles = 0

        for weekend in save.weekend_results:
            # Check feature race
            if weekend.feature:
                player_result = next(
                    (r for r in weekend.feature.classification if r.driver_id == player_id),
                    None,
                )
                if player_result:
                    if player_result.position == 1:
                        f1_wins += 1
                    if player_result.position <= 3:
                        f1_podiums += 1

            # Check qualifying for poles
            if weekend.qualifying:
                player_quali = next(
                    (r for r in weekend.qualifying.classification if r.driver_id == player_id),
                    None,
                )
                if player_quali and player_quali.position == 1:
                    f1_poles += 1

        if f1_poles > 0:
            achievements.append({
                "id": "f1_pole",
                "name": "F1 Pole Position",
                "description": f"Took {f1_poles} pole position(s) in F1",
                "capBonus": 1,
            })

        if f1_podiums > 0:
            achievements.append({
                "id": "f1_podium",
                "name": "F1 Podium",
                "description": f"Achieved {f1_podiums} podium(s) in F1",
                "capBonus": 2,
            })

        if f1_wins > 0:
            achievements.append({
                "id": "f1_race_winner",
                "name": "F1 Race Winner",
                "description": f"Won {f1_wins} F1 race(s)",
                "capBonus": 3,
            })

        if f1_wins >= 3:
            achievements.append({
                "id": "multiple_f1_wins",
                "name": "Multiple F1 Winner",
                "description": "Won 3+ F1 races",
                "capBonus": 2,
            })

    return achievements


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save
