"""API routes for the post-race interview system."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.engine.interview_engine import (
    apply_interview_response,
    format_interview_for_display,
    get_pending_interviews,
    has_pending_interview,
)
from app.models.save_game import SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career/{save_id}/interview", tags=["interview"])
manager = SaveManager()


class RespondToInterviewRequest(BaseModel):
    """Request body for responding to an interview."""

    interview_id: str
    choice_id: str


class InterviewHistoryParams(BaseModel):
    """Query params for interview history."""

    limit: int = 20


@router.get("/pending")
def get_pending_interview(save_id: str) -> dict:
    """
    Get all pending interviews for the player.

    Returns pending interviews that need a response, formatted for display.
    Each interview includes the question, reporter name, and available choices.
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    pending = get_pending_interviews(save)

    if not pending:
        return {
            "hasPending": False,
            "interviews": [],
        }

    # Format interviews for display
    formatted = [format_interview_for_display(i, save) for i in pending]

    return {
        "hasPending": True,
        "interviews": formatted,
    }


@router.post("/respond")
def respond_to_interview(save_id: str, request: RespondToInterviewRequest) -> dict:
    """
    Respond to a pending interview with the selected choice.

    Applies the effects of the chosen response:
    - Updates player attributes (marketability, confidence, morale)
    - Updates relationships (team trust, academy trust, rivalry intensity)
    - Awards media XP to the development profile
    - Generates a news item based on the response

    Returns the applied effects and generated news item.
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    # Check if interview exists
    pending = next(
        (i for i in save.interview_state.pending_interviews if i.id == request.interview_id),
        None,
    )

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found or already answered",
        )

    # Check if choice exists
    choice = next(
        (c for c in pending.question.choices if c.id == request.choice_id),
        None,
    )

    if not choice:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid choice ID",
        )

    # Apply the response
    updated_save, response, news_item = apply_interview_response(
        save, request.interview_id, request.choice_id
    )

    if response is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to apply interview response",
        )

    # Save the updated state
    manager.save(updated_save)

    return {
        "success": True,
        "response": {
            "interviewId": response.interview_id,
            "trigger": response.trigger,
            "choiceId": response.choice_id,
            "choiceText": response.choice_text,
        },
        "effects": {
            "marketability": response.effects_applied.marketability,
            "reputation": response.effects_applied.reputation,
            "confidence": response.effects_applied.confidence,
            "morale": response.effects_applied.morale,
            "teamTrust": response.effects_applied.team_trust,
            "academyTrust": response.effects_applied.academy_trust,
            "fanSupport": response.effects_applied.fan_support,
            "rivalryIntensity": response.effects_applied.rivalry_intensity,
            "rumorIntensity": response.effects_applied.rumor_intensity,
            "mediaXp": response.effects_applied.media_xp,
            "perceptionTags": response.effects_applied.perception_tags,
            "narrativeTone": response.effects_applied.narrative_tone,
        },
        "news": {
            "headline": news_item.headline if news_item else "",
            "body": news_item.body if news_item else "",
            "category": news_item.category if news_item else "media",
        },
    }


@router.get("/history")
def get_interview_history(save_id: str, limit: int = 20) -> dict:
    """
    Get the player's interview response history.

    Returns recent interview responses including the question trigger,
    chosen response, applied effects, and generated news headlines.
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    history = save.interview_state.interview_history[-limit:]

    return {
        "totalInterviews": save.interview_state.total_interviews_completed,
        "history": [
            {
                "interviewId": h.interview_id,
                "roundId": h.round_id,
                "trigger": h.trigger,
                "questionId": h.question_id,
                "choiceId": h.choice_id,
                "choiceText": h.choice_text,
                "newsHeadline": h.news_headline,
                "responseDate": h.response_date,
                "effects": {
                    "marketability": h.effects_applied.marketability,
                    "teamTrust": h.effects_applied.team_trust,
                    "academyTrust": h.effects_applied.academy_trust,
                    "mediaXp": h.effects_applied.media_xp,
                    "perceptionTags": h.effects_applied.perception_tags,
                    "narrativeTone": h.effects_applied.narrative_tone,
                },
            }
            for h in reversed(history)
        ],
    }


@router.get("/stats")
def get_interview_stats(save_id: str) -> dict:
    """
    Get statistics about the player's interview history.

    Returns aggregated stats like total interviews completed,
    most common tones used, and media XP earned.
    """
    save = _get_save(save_id)

    if not save.player_driver_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No player driver found",
        )

    history = save.interview_state.interview_history

    # Calculate stats
    total_media_xp = sum(h.effects_applied.media_xp for h in history)
    total_team_trust = sum(h.effects_applied.team_trust for h in history)
    total_academy_trust = sum(h.effects_applied.academy_trust for h in history)
    total_marketability = sum(h.effects_applied.marketability for h in history)

    # Count narrative tones
    tone_counts: dict[str, int] = {}
    for h in history:
        tone = h.effects_applied.narrative_tone
        tone_counts[tone] = tone_counts.get(tone, 0) + 1

    # Count perception tags
    all_tags: dict[str, int] = {}
    for h in history:
        for tag in h.effects_applied.perception_tags:
            all_tags[tag] = all_tags.get(tag, 0) + 1

    # Sort tags by count
    top_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:5]

    return {
        "totalInterviews": save.interview_state.total_interviews_completed,
        "totalMediaXp": total_media_xp,
        "netTeamTrust": total_team_trust,
        "netAcademyTrust": total_academy_trust,
        "netMarketability": total_marketability,
        "toneDistribution": tone_counts,
        "topPerceptionTags": [{"tag": t, "count": c} for t, c in top_tags],
    }


@router.delete("/pending/{interview_id}")
def dismiss_interview(save_id: str, interview_id: str) -> dict:
    """
    Dismiss a pending interview without responding.

    Use this if the player wants to skip an interview. The interview
    will be removed from the pending list without applying any effects.
    """
    save = _get_save(save_id)

    pending = next(
        (i for i in save.interview_state.pending_interviews if i.id == interview_id),
        None,
    )

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview not found",
        )

    # Remove from pending list
    updated_pending = [
        i for i in save.interview_state.pending_interviews if i.id != interview_id
    ]

    updated_state = save.interview_state.model_copy(
        update={"pending_interviews": updated_pending}
    )

    updated_save = save.model_copy(update={"interview_state": updated_state})
    manager.save(updated_save)

    return {
        "success": True,
        "message": "Interview dismissed",
    }


def _get_save(save_id: str) -> SaveGame:
    """Get a save game by ID."""
    save = manager.get(save_id)
    if save is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Save not found")
    return save
