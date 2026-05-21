"""API routes for season progression."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.engine.season_engine import (
    advance_to_next_season,
    get_season_summary,
    is_season_complete,
)
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/season", tags=["season"])
manager = SaveManager()


@router.get("/summary")
def get_summary(save_id: str) -> dict:
    """
    Get the season summary including standings and player performance.

    Available after the season is complete (phase: offseason).
    """
    save = _get_save(save_id)

    if not is_season_complete(save):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Season is not complete yet",
        )

    return get_season_summary(save)


@router.get("/status")
def get_season_status(save_id: str) -> dict:
    """
    Get the current season status.

    Returns season number, completed rounds, and whether the season is complete.
    """
    save = _get_save(save_id)

    total_rounds = len(save.calendar)
    completed_rounds = sum(1 for r in save.calendar if r.completed)
    remaining_rounds = total_rounds - completed_rounds

    return {
        "season": save.season,
        "phase": save.phase,
        "totalRounds": total_rounds,
        "completedRounds": completed_rounds,
        "remainingRounds": remaining_rounds,
        "isSeasonComplete": is_season_complete(save),
        "nextRound": next(
            ({"id": r.id, "name": r.name, "roundNumber": r.round_number}
             for r in save.calendar if not r.completed),
            None
        ),
    }


@router.post("/advance", response_model=SaveGame)
def advance_season(save_id: str) -> SaveGame:
    """
    Advance to the next season.

    Only available during offseason phase.
    - Increments season number
    - Resets calendar and standings
    - Ages drivers
    - Transitions to preseason phase
    """
    save = _get_save(save_id)

    if save.phase != "offseason":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Can only advance season during offseason, current phase is {save.phase}",
        )

    updated_save, _ = advance_to_next_season(save)
    return manager.save(updated_save)


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save
