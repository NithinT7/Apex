"""API routes for between-race activities."""

from fastapi import APIRouter, HTTPException, status

from app.engine.academy_engine import get_academy_status
from app.engine.rivalry_engine import get_rivalry_status
from app.engine.activity_engine import (
    advance_to_race_week,
    get_available_activities,
    perform_activity,
)
from app.models.activity import ActivityOutcome, AvailableActivities
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/activities", tags=["activities"])
manager = SaveManager()


@router.get("", response_model=AvailableActivities)
def list_activities(save_id: str) -> AvailableActivities:
    """
    Get available activities for the current between-race period.

    Returns list of activities the player can perform, filtered by:
    - Time until next race
    - Player's current fatigue level
    - Other requirements
    """
    save = _get_save(save_id)

    if save.phase != "between_races":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Activities only available during between_races phase, current phase is {save.phase}",
        )

    return get_available_activities(save)


@router.get("/status")
def get_activity_status(save_id: str) -> dict:
    """
    Get current player status relevant to activities.

    Returns fatigue, morale, form, and days until next race.
    """
    save = _get_save(save_id)

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if player is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Player driver not found")

    available = get_available_activities(save)

    # Get academy trust if applicable
    academy_trust = None
    if player.academy_id:
        academy_state = next(
            (s for s in save.academy_states if s.academy_id == player.academy_id), None
        )
        if academy_state:
            academy_trust = academy_state.trust

    return {
        "fatigue": player.fatigue,
        "morale": player.morale,
        "form": player.current_form,
        "reputation": player.attributes.reputation,
        "sponsor_value": player.attributes.sponsor_value,
        "academy_trust": academy_trust,
        "days_until_race": available.days_until_next_race,
        "phase": save.phase,
    }


@router.get("/academy")
def get_academy(save_id: str) -> dict:
    """
    Get comprehensive academy status for the player.

    Returns trust info, expectations, warnings, and F1 pathway status.
    """
    save = _get_save(save_id)

    academy_status = get_academy_status(save)
    if academy_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player has no academy affiliation",
        )

    return academy_status


@router.get("/rivalries")
def get_rivalries(save_id: str) -> dict:
    """
    Get current rivalry status for the player.

    Returns active rivalries with their intensity and type.
    """
    save = _get_save(save_id)

    rivalry_status = get_rivalry_status(save)
    return {
        "rivalries": [
            {
                "id": r.id,
                "opponentId": r.opponent_id,
                "opponentName": next(
                    (d.name for d in save.drivers if d.id == r.opponent_id), "Unknown"
                ),
                "rivalryType": r.rivalry_type,
                "intensity": r.intensity,
                "intensityLevel": _get_intensity_label(r.intensity),
                "respect": r.respect,
                "recentEvents": [
                    {"description": e.description, "intensityChange": e.intensity_change}
                    for e in r.recent_events[:3]
                ],
            }
            for r in rivalry_status.rivalries
        ],
        "mostIntenseId": rivalry_status.most_intense.id if rivalry_status.most_intense else None,
        "teammateRivalryId": rivalry_status.teammate_rivalry.id if rivalry_status.teammate_rivalry else None,
    }


def _get_intensity_label(intensity: int) -> str:
    """Get human-readable intensity label."""
    if intensity >= 90:
        return "bitter"
    if intensity >= 75:
        return "intense"
    if intensity >= 50:
        return "moderate"
    return "mild"


@router.post("/skip", response_model=SaveGame)
def skip_to_race(save_id: str) -> SaveGame:
    """
    Skip remaining activities and advance to race week.

    Applies passive recovery based on days skipped.
    """
    save = _get_save(save_id)

    if save.phase != "between_races":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only skip during between_races phase, current phase is {save.phase}",
        )

    updated_save = advance_to_race_week(save)
    return manager.save(updated_save)


@router.post("/{activity_id}", response_model=ActivityOutcome)
def do_activity(save_id: str, activity_id: str) -> ActivityOutcome:
    """
    Perform an activity.

    Updates driver stats (fatigue, morale, form, etc.) and advances time.
    Returns the outcome including narrative and effects applied.
    """
    save = _get_save(save_id)

    if save.phase != "between_races":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Activities only available during between_races phase, current phase is {save.phase}",
        )

    try:
        updated_save, outcome = perform_activity(save, activity_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # Check if we should transition to race_week
    available = get_available_activities(updated_save)
    if available.days_until_next_race <= 0:
        updated_save = updated_save.model_copy(update={"phase": "race_week"})

    manager.save(updated_save)

    return outcome


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save
