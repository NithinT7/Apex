"""Tests for the post-race interview system."""

import pytest
from fastapi.testclient import TestClient

from app.engine.interview_engine import (
    apply_interview_response,
    detect_triggers,
    generate_interview,
    generate_interviews_for_weekend,
    select_question_for_trigger,
)
from app.main import app
from app.models.interview import InterviewState
from app.save.save_manager import SaveManager


client = TestClient(app)


@pytest.fixture
def manager():
    """Create a SaveManager instance."""
    return SaveManager()


@pytest.fixture
def save_with_player(manager: SaveManager):
    """Create a save with a player."""
    response = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 20,
            "driverNumber": 99,
            "backgroundId": "karting_prodigy",
            "archetypeId": "smooth_operator",
            "teamId": "f2_prema",
            "difficulty": "realistic_prospect",
        },
    )
    assert response.status_code == 201
    return manager.get(response.json()["saveId"])


class TestTriggerDetection:
    """Tests for interview trigger detection."""

    def test_detect_race_win(self, save_with_player):
        """Test that race win is detected."""
        weekend_data = {"feature_position": 1}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "race_win" in triggers

    def test_detect_podium(self, save_with_player):
        """Test that podium finish is detected."""
        weekend_data = {"feature_position": 2}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "podium" in triggers

        weekend_data = {"feature_position": 3}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "podium" in triggers

    def test_detect_pole_position(self, save_with_player):
        """Test that pole position is detected."""
        weekend_data = {"qualifying_position": 1}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "pole_position" in triggers

    def test_detect_big_recovery(self, save_with_player):
        """Test that big recovery is detected."""
        weekend_data = {
            "qualifying_position": 15,
            "feature_position": 5,
            "positions_gained": 10,
        }
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "big_recovery" in triggers

    def test_detect_underperformance(self, save_with_player):
        """Test that underperformance is detected."""
        weekend_data = {
            "qualifying_position": 3,
            "feature_position": 15,
            "positions_gained": -12,
        }
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "underperformance" in triggers

    def test_detect_penalty(self, save_with_player):
        """Test that penalty is detected."""
        weekend_data = {"feature_position": 8, "penalties": 1}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "penalty_received" in triggers

    def test_detect_crash(self, save_with_player):
        """Test that major crash is detected."""
        weekend_data = {"dnf_reason": "crash"}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "major_crash" in triggers

    def test_detect_mechanical_dnf(self, save_with_player):
        """Test that mechanical DNF is detected."""
        weekend_data = {"dnf_reason": "engine"}
        triggers = detect_triggers(save_with_player, weekend_data)
        assert "dnf_mechanical" in triggers

    def test_no_triggers_for_normal_result(self, save_with_player):
        """Test that no special triggers for mid-pack finish."""
        weekend_data = {
            "qualifying_position": 10,
            "feature_position": 10,
            "positions_gained": 0,
        }
        triggers = detect_triggers(save_with_player, weekend_data)
        # Should not have win/podium/recovery triggers
        assert "race_win" not in triggers
        assert "podium" not in triggers
        assert "big_recovery" not in triggers


class TestQuestionSelection:
    """Tests for interview question selection."""

    def test_select_question_for_win(self, save_with_player):
        """Test selecting a question for race win trigger."""
        question = select_question_for_trigger(save_with_player, "race_win")
        assert question is not None
        assert question.trigger == "race_win"
        assert len(question.choices) >= 2

    def test_select_question_for_podium(self, save_with_player):
        """Test selecting a question for podium trigger."""
        question = select_question_for_trigger(save_with_player, "podium")
        assert question is not None
        assert question.trigger == "podium"

    def test_select_question_for_strategy(self, save_with_player):
        """Test selecting a question for strategy controversy."""
        question = select_question_for_trigger(save_with_player, "strategy_controversy")
        assert question is not None
        assert question.trigger == "strategy_controversy"

    def test_no_question_for_invalid_trigger(self, save_with_player):
        """Test that no question is returned for invalid trigger."""
        question = select_question_for_trigger(save_with_player, "invalid_trigger")  # type: ignore
        assert question is None


class TestInterviewGeneration:
    """Tests for interview generation."""

    def test_generate_interview_for_win(self, save_with_player):
        """Test generating an interview for race win."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None
        assert interview.trigger == "race_win"
        assert interview.round_id == "round_1"
        assert interview.question is not None
        assert len(interview.question.choices) >= 2

    def test_generate_interviews_for_weekend(self, save_with_player):
        """Test generating interviews based on weekend results."""
        weekend_data = {"feature_position": 1}
        interviews = generate_interviews_for_weekend(
            save_with_player, "round_1", weekend_data, max_interviews=1
        )
        assert len(interviews) >= 1
        assert interviews[0].trigger == "race_win"

    def test_cooldown_prevents_duplicate(self, save_with_player):
        """Test that cooldown prevents duplicate interviews."""
        # Generate first interview
        interview1 = generate_interview(save_with_player, "race_win", "round_1")
        assert interview1 is not None

        # Update save with the interview
        from app.engine.interview_engine import add_pending_interview
        updated_save = add_pending_interview(save_with_player, interview1)

        # Update last trigger round
        updated_state = updated_save.interview_state.model_copy(
            update={"last_trigger_round": {"race_win": "round_1"}}
        )
        updated_save = updated_save.model_copy(update={"interview_state": updated_state})

        # Try to generate another interview for same trigger and round
        interview2 = generate_interview(updated_save, "race_win", "round_1")
        assert interview2 is None


class TestInterviewResponse:
    """Tests for interview response processing."""

    def test_apply_interview_response(self, save_with_player):
        """Test applying an interview response."""
        # Generate an interview
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        # Add to pending
        from app.engine.interview_engine import add_pending_interview
        save_with_interview = add_pending_interview(save_with_player, interview)

        # Respond to interview
        choice_id = interview.question.choices[0].id
        updated_save, response, news = apply_interview_response(
            save_with_interview, interview.id, choice_id
        )

        assert response is not None
        assert response.choice_id == choice_id
        assert news is not None
        assert len(news.headline) > 0

        # Check interview moved to history
        assert len(updated_save.interview_state.pending_interviews) == 0
        assert len(updated_save.interview_state.interview_history) == 1

    def test_effects_applied_correctly(self, save_with_player):
        """Test that effects are applied to player."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        from app.engine.interview_engine import add_pending_interview
        save_with_interview = add_pending_interview(save_with_player, interview)

        # Find a choice with positive team trust
        positive_choice = next(
            (c for c in interview.question.choices if c.effects.team_trust > 0),
            interview.question.choices[0],
        )

        updated_save, response, news = apply_interview_response(
            save_with_interview, interview.id, positive_choice.id
        )

        # Check effects were recorded
        assert response is not None
        assert response.effects_applied.team_trust == positive_choice.effects.team_trust


class TestAPIEndpoints:
    """Tests for the interview API endpoints."""

    def test_get_pending_interviews_empty(self, save_with_player):
        """Test getting pending interviews when none exist."""
        response = client.get(f"/career/{save_with_player.save_id}/interview/pending")
        assert response.status_code == 200

        data = response.json()
        assert data["hasPending"] is False
        assert data["interviews"] == []

    def test_get_pending_interviews_with_interview(self, save_with_player, manager):
        """Test getting pending interviews when one exists."""
        # Generate and add an interview
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        from app.engine.interview_engine import add_pending_interview
        updated_save = add_pending_interview(save_with_player, interview)
        manager.save(updated_save)

        response = client.get(f"/career/{updated_save.save_id}/interview/pending")
        assert response.status_code == 200

        data = response.json()
        assert data["hasPending"] is True
        assert len(data["interviews"]) == 1
        assert data["interviews"][0]["id"] == interview.id

    def test_respond_to_interview(self, save_with_player, manager):
        """Test responding to an interview."""
        # Generate and add an interview
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        from app.engine.interview_engine import add_pending_interview
        updated_save = add_pending_interview(save_with_player, interview)
        manager.save(updated_save)

        # Respond to interview
        choice_id = interview.question.choices[0].id
        response = client.post(
            f"/career/{updated_save.save_id}/interview/respond",
            json={"interview_id": interview.id, "choice_id": choice_id},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["response"]["choiceId"] == choice_id
        assert "effects" in data
        assert "news" in data

    def test_respond_to_invalid_interview(self, save_with_player):
        """Test responding to a non-existent interview."""
        response = client.post(
            f"/career/{save_with_player.save_id}/interview/respond",
            json={"interview_id": "invalid_id", "choice_id": "some_choice"},
        )
        assert response.status_code == 404

    def test_respond_with_invalid_choice(self, save_with_player, manager):
        """Test responding with an invalid choice."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        from app.engine.interview_engine import add_pending_interview
        updated_save = add_pending_interview(save_with_player, interview)
        manager.save(updated_save)

        response = client.post(
            f"/career/{updated_save.save_id}/interview/respond",
            json={"interview_id": interview.id, "choice_id": "invalid_choice"},
        )
        assert response.status_code == 400

    def test_get_interview_history(self, save_with_player):
        """Test getting interview history."""
        response = client.get(f"/career/{save_with_player.save_id}/interview/history")
        assert response.status_code == 200

        data = response.json()
        assert "totalInterviews" in data
        assert "history" in data

    def test_get_interview_stats(self, save_with_player):
        """Test getting interview statistics."""
        response = client.get(f"/career/{save_with_player.save_id}/interview/stats")
        assert response.status_code == 200

        data = response.json()
        assert "totalInterviews" in data
        assert "totalMediaXp" in data
        assert "toneDistribution" in data

    def test_dismiss_interview(self, save_with_player, manager):
        """Test dismissing an interview."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        from app.engine.interview_engine import add_pending_interview
        updated_save = add_pending_interview(save_with_player, interview)
        manager.save(updated_save)

        response = client.delete(
            f"/career/{updated_save.save_id}/interview/pending/{interview.id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True

        # Verify interview is gone
        check_response = client.get(f"/career/{updated_save.save_id}/interview/pending")
        assert check_response.json()["hasPending"] is False


class TestInterviewEffects:
    """Tests for specific interview effects."""

    def test_media_xp_awarded(self, save_with_player, manager):
        """Test that media XP is awarded from interview."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        # Ensure development profile exists
        from app.models.development_profile import DevelopmentProfile
        if save_with_player.development_profile is None:
            save_with_player = save_with_player.model_copy(
                update={"development_profile": DevelopmentProfile()}
            )

        from app.engine.interview_engine import add_pending_interview
        save_with_interview = add_pending_interview(save_with_player, interview)

        # Find choice with media XP
        choice_with_xp = max(
            interview.question.choices,
            key=lambda c: c.effects.media_xp,
        )

        initial_xp = save_with_interview.development_profile.branch_xp.get(
            "media_marketability", 0
        )

        updated_save, response, news = apply_interview_response(
            save_with_interview, interview.id, choice_with_xp.id
        )

        if choice_with_xp.effects.media_xp > 0 and updated_save.development_profile:
            final_xp = updated_save.development_profile.branch_xp.get(
                "media_marketability", 0
            )
            assert final_xp == initial_xp + choice_with_xp.effects.media_xp

    def test_news_item_generated(self, save_with_player):
        """Test that a news item is generated from interview."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        from app.engine.interview_engine import add_pending_interview
        save_with_interview = add_pending_interview(save_with_player, interview)

        initial_news_count = len(save_with_interview.news)

        updated_save, response, news = apply_interview_response(
            save_with_interview, interview.id, interview.question.choices[0].id
        )

        assert len(updated_save.news) == initial_news_count + 1
        assert updated_save.news[-1].category == "media"

    def test_perception_tags_added(self, save_with_player):
        """Test that perception tags are recorded."""
        interview = generate_interview(save_with_player, "race_win", "round_1")
        assert interview is not None

        # Find choice with perception tags
        choice_with_tags = next(
            (c for c in interview.question.choices if c.effects.perception_tags),
            interview.question.choices[0],
        )

        from app.engine.interview_engine import add_pending_interview
        save_with_interview = add_pending_interview(save_with_player, interview)

        updated_save, response, news = apply_interview_response(
            save_with_interview, interview.id, choice_with_tags.id
        )

        # Check perception tags were stored in event flags
        last_effects = updated_save.event_flags.get("last_interview_effects", {})
        if choice_with_tags.effects.perception_tags:
            assert last_effects.get("perception_tags") == choice_with_tags.effects.perception_tags
