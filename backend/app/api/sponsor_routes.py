"""API routes for the sponsorship system."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.engine.sponsor_engine import (
    clear_sponsor_completions,
    complete_sponsor_activity,
    get_available_sponsor_activities,
)
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/sponsor", tags=["sponsor"])
manager = SaveManager()


class CompleteSponsorActivityRequest(BaseModel):
    """Request body for completing a sponsor activity."""

    activity_id: str


@router.get("/activities")
def get_sponsor_activities(save_id: str) -> dict:
    """
    Get all sponsor activities with availability status.

    Returns both available and locked activities based on the player's
    current marketability and sponsor value ratings.

    Available activities can be completed during between-race periods.
    Locked activities show what marketability threshold is needed to unlock them.
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    result = get_available_sponsor_activities(save)
    return result.to_dict()


@router.post("/complete")
def complete_activity(save_id: str, request: CompleteSponsorActivityRequest) -> dict:
    """
    Complete a sponsor activity and apply its effects.

    The activity must be available (player meets marketability and sponsor
    value requirements) and not already completed this break.

    Effects applied on success:
    - Media/marketability XP
    - Marketability attribute increase
    - Sponsor value increase
    - Team interest boost
    - Academy trust (if applicable)
    - Development funding bonus (for certain activities)
    - Contract value bonus (for major activities)

    Some activities have risk that can trigger negative effects:
    - Marketability penalty
    - Reputation penalty
    - Increased pressure
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    try:
        updated_save, outcome = complete_sponsor_activity(
            save, request.activity_id
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # Save the updated state
    manager.save(updated_save)

    return {
        "success": True,
        "outcome": outcome.to_dict(),
        "updatedState": get_available_sponsor_activities(updated_save).to_dict(),
    }


@router.get("/status")
def get_sponsor_status(save_id: str) -> dict:
    """
    Get the player's current sponsorship status.

    Returns:
    - Current marketability tier
    - Marketability and sponsor value ratings
    - Progress to next tier
    - Total sponsor earnings this season
    - Activities completed this season
    - Pending development funding bonus
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    result = get_available_sponsor_activities(save)

    # Calculate progress to next tier
    progress_to_next = 0.0
    if result.next_tier_threshold:
        current_mk = result.marketability
        # Find current tier threshold
        tier_order = ["local", "regional", "national", "global", "elite"]
        from app.models.sponsorship import MARKETABILITY_THRESHOLDS

        current_threshold = 0
        for tier in tier_order:
            t = MARKETABILITY_THRESHOLDS[tier]
            if current_mk >= t:
                current_threshold = t
            else:
                break

        range_size = result.next_tier_threshold - current_threshold
        if range_size > 0:
            progress_to_next = (current_mk - current_threshold) / range_size

    return {
        "currentTier": result.current_tier,
        "currentTierName": result.current_tier_name,
        "marketability": result.marketability,
        "sponsorValue": result.sponsor_value,
        "nextTierThreshold": result.next_tier_threshold,
        "progressToNextTier": progress_to_next,
        "activitiesCompletedThisSeason": result.sponsorship_state.activities_completed,
        "totalSponsorEarnings": result.sponsorship_state.total_sponsor_earnings,
        "pendingDevBonus": result.sponsorship_state.pending_dev_bonus,
        "activePartners": result.sponsorship_state.active_partners,
    }


@router.post("/clear-completions")
def clear_completions(save_id: str) -> dict:
    """
    Clear sponsor activity completions for a new between-race period.

    This is called automatically when transitioning to a new between-race
    period, but can be called manually for testing purposes.
    """
    save = _get_save(save_id)

    updated_save = clear_sponsor_completions(save)
    manager.save(updated_save)

    return {
        "success": True,
        "message": "Sponsor activity completions cleared",
    }


@router.get("/team-interest-preview")
def preview_team_interest(save_id: str) -> dict:
    """
    Preview how sponsor value affects team interest calculations.

    Shows how the player's sponsor value influences interest from
    different tiers of teams:
    - Backmarker teams: High influence (up to 16% bonus)
    - Midfield teams: Medium influence (up to 12% bonus)
    - Top teams: Low influence (up to 6% bonus)
    - Elite teams: Minimal influence (up to 3% bonus)
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player driver not found",
        )

    sponsor_value = player.attributes.sponsor_value

    from app.engine.sponsor_engine import get_team_interest_modifier

    return {
        "sponsorValue": sponsor_value,
        "teamInterestModifiers": {
            "backmarker": {
                "modifier": get_team_interest_modifier(sponsor_value, "backmarker"),
                "description": "Teams at the back of the grid heavily value sponsor value",
            },
            "midfield": {
                "modifier": get_team_interest_modifier(sponsor_value, "midfield"),
                "description": "Midfield teams balance performance and commercial value",
            },
            "top_team": {
                "modifier": get_team_interest_modifier(sponsor_value, "top_team"),
                "description": "Top teams focus on performance but appreciate marketability",
            },
            "elite_team": {
                "modifier": get_team_interest_modifier(sponsor_value, "elite_team"),
                "description": "Elite teams prioritize raw talent over commercial factors",
            },
        },
    }


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save
