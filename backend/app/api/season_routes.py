"""API routes for season progression."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.engine.season_engine import (
    advance_to_next_season,
    get_season_summary,
    is_season_complete,
)
from app.engine.silly_season_engine import (
    evaluate_player_f1_offers,
    generate_silly_season_rumors_news,
    process_player_f1_decision,
    simulate_silly_season,
)
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/season", tags=["season"])
manager = SaveManager()


class F1DecisionRequest(BaseModel):
    accept: bool
    teamId: str | None = None


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


@router.get("/f1-offers")
def get_f1_offers(save_id: str) -> dict:
    """
    Get F1 offers available to the player.

    Only available during offseason phase.
    Returns list of potential F1 seats with likelihood info.
    """
    save = _get_save(save_id)

    if save.phase != "offseason":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="F1 offers only available during offseason",
        )

    offers = evaluate_player_f1_offers(save)

    return {
        "offers": offers,
        "hasOffers": len(offers) > 0,
        "bestOffer": offers[0] if offers else None,
    }


@router.post("/f1-decision", response_model=SaveGame)
def make_f1_decision(save_id: str, request: F1DecisionRequest) -> SaveGame:
    """
    Accept or decline F1 offers.

    If accepting, specify the teamId to join.
    """
    save = _get_save(save_id)

    if save.phase != "offseason":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="F1 decisions only available during offseason",
        )

    updated_save, _ = process_player_f1_decision(
        save, request.accept, request.teamId
    )

    return manager.save(updated_save)


@router.get("/rumors")
def get_transfer_rumors(save_id: str) -> dict:
    """
    Get current transfer rumors for the silly season.

    Returns news items about potential driver moves.
    """
    save = _get_save(save_id)

    if save.phase != "offseason":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer rumors only available during offseason",
        )

    rumors = generate_silly_season_rumors_news(save)

    return {
        "rumors": [
            {
                "id": r.id,
                "headline": r.headline,
                "body": r.body,
                "linkedDriverIds": r.linked_driver_ids,
                "importance": r.importance,
            }
            for r in rumors
        ],
    }


@router.post("/simulate-market", response_model=SaveGame)
def simulate_driver_market(save_id: str) -> SaveGame:
    """
    Simulate the driver market (AI moves).

    Processes AI driver transfers and contract changes.
    """
    save = _get_save(save_id)

    if save.phase != "offseason":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Market simulation only available during offseason",
        )

    updated_save, news = simulate_silly_season(save)
    updated_save = updated_save.model_copy(
        update={"news": [*updated_save.news, *news]}
    )

    return manager.save(updated_save)


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save
