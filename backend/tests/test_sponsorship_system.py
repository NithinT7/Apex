"""Tests for the sponsorship system."""

import pytest
from fastapi.testclient import TestClient

from app.engine.sponsor_engine import (
    apply_sponsor_effects_to_team_interest,
    clear_sponsor_completions,
    complete_sponsor_activity,
    get_available_sponsor_activities,
    get_sponsor_config,
    get_team_interest_modifier,
)
from app.main import app
from app.models.sponsorship import get_sponsor_tier, get_tier_name, MARKETABILITY_THRESHOLDS
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


class TestSponsorConfig:
    """Tests for sponsor configuration loading."""

    def test_load_sponsor_config(self):
        """Test loading sponsor config."""
        config = get_sponsor_config()
        assert len(config.activities) > 0
        assert "local" in config.tier_bonuses
        assert "backmarker" in config.team_interest_weights

    def test_activities_have_required_fields(self):
        """Test that all activities have required fields."""
        config = get_sponsor_config()
        for activity in config.activities:
            assert activity.id
            assert activity.name
            assert activity.tier in ["local", "regional", "national", "global", "elite"]
            assert activity.description
            assert activity.effects is not None

    def test_tiers_have_proper_thresholds(self):
        """Test that higher tiers require higher marketability."""
        config = get_sponsor_config()
        tier_min_marketability = {"local": 0, "regional": 45, "national": 60, "global": 75, "elite": 90}

        for activity in config.activities:
            expected_min = tier_min_marketability.get(activity.tier, 0)
            assert activity.min_marketability >= expected_min, (
                f"Activity {activity.id} in tier {activity.tier} has "
                f"min_marketability {activity.min_marketability} but tier requires {expected_min}"
            )


class TestSponsorTiers:
    """Tests for sponsor tier functions."""

    def test_get_sponsor_tier_local(self):
        """Test that low marketability returns local tier."""
        assert get_sponsor_tier(0) == "local"
        assert get_sponsor_tier(44) == "local"

    def test_get_sponsor_tier_regional(self):
        """Test that medium-low marketability returns regional tier."""
        assert get_sponsor_tier(45) == "regional"
        assert get_sponsor_tier(59) == "regional"

    def test_get_sponsor_tier_national(self):
        """Test that medium marketability returns national tier."""
        assert get_sponsor_tier(60) == "national"
        assert get_sponsor_tier(74) == "national"

    def test_get_sponsor_tier_global(self):
        """Test that high marketability returns global tier."""
        assert get_sponsor_tier(75) == "global"
        assert get_sponsor_tier(89) == "global"

    def test_get_sponsor_tier_elite(self):
        """Test that star marketability returns elite tier."""
        assert get_sponsor_tier(90) == "elite"
        assert get_sponsor_tier(100) == "elite"

    def test_get_tier_name(self):
        """Test tier name conversion."""
        assert get_tier_name("local") == "Local"
        assert get_tier_name("regional") == "Regional"
        assert get_tier_name("national") == "National"
        assert get_tier_name("global") == "Global"
        assert get_tier_name("elite") == "Elite"


class TestAvailableActivities:
    """Tests for getting available sponsor activities."""

    def test_activities_locked_at_low_marketability(self, save_with_player):
        """Test that higher-tier activities are locked at low marketability."""
        # Get player and set low marketability
        player = next(d for d in save_with_player.drivers if d.id == save_with_player.player_driver_id)
        player = player.model_copy(
            update={"attributes": player.attributes.model_copy(update={"marketability": 30})}
        )
        save = save_with_player.model_copy(
            update={"drivers": [player if d.id == player.id else d for d in save_with_player.drivers]}
        )

        result = get_available_sponsor_activities(save)

        # Local activities should be available
        local_available = [a for a in result.available_activities if a.activity.tier == "local"]
        assert len(local_available) > 0

        # National/global/elite should be locked
        locked_tiers = {a.activity.tier for a in result.locked_activities}
        assert "national" in locked_tiers or "global" in locked_tiers or "elite" in locked_tiers

    def test_activities_unlock_at_threshold(self, save_with_player):
        """Test that activities unlock when marketability reaches threshold."""
        # Set marketability to 60 (national tier threshold)
        player = next(d for d in save_with_player.drivers if d.id == save_with_player.player_driver_id)
        player = player.model_copy(
            update={"attributes": player.attributes.model_copy(
                update={"marketability": 60, "sponsor_value": 55}
            )}
        )
        save = save_with_player.model_copy(
            update={"drivers": [player if d.id == player.id else d for d in save_with_player.drivers]}
        )

        result = get_available_sponsor_activities(save)

        # National tier activities should now be available
        national_available = [a for a in result.available_activities if a.activity.tier == "national"]
        assert len(national_available) > 0

    def test_completed_activities_not_available(self, save_with_player):
        """Test that completed activities are not available again."""
        # Complete an activity
        config = get_sponsor_config()
        local_activity = next(a for a in config.activities if a.tier == "local")

        updated_save, outcome = complete_sponsor_activity(
            save_with_player, local_activity.id
        )

        # Try to get available activities - the completed one should not be available
        result = get_available_sponsor_activities(updated_save)

        available_ids = [a.activity.id for a in result.available_activities]
        assert local_activity.id not in available_ids


class TestCompleteSponsorActivity:
    """Tests for completing sponsor activities."""

    def test_complete_local_activity(self, save_with_player):
        """Test completing a local sponsor activity."""
        config = get_sponsor_config()
        local_activity = next(a for a in config.activities if a.tier == "local")

        updated_save, outcome = complete_sponsor_activity(
            save_with_player, local_activity.id
        )

        assert outcome.success is True
        assert outcome.activity_id == local_activity.id
        assert outcome.activity_name == local_activity.name

    def test_effects_applied_once(self, save_with_player, manager):
        """Test that effects are applied exactly once."""
        config = get_sponsor_config()
        local_activity = next(
            a for a in config.activities
            if a.tier == "local" and a.effects.marketability > 0
        )

        player_before = next(d for d in save_with_player.drivers if d.id == save_with_player.player_driver_id)
        initial_marketability = player_before.attributes.marketability

        # Complete the activity
        updated_save, outcome = complete_sponsor_activity(
            save_with_player, local_activity.id
        )

        player_after = next(d for d in updated_save.drivers if d.id == updated_save.player_driver_id)
        final_marketability = player_after.attributes.marketability

        # Verify effects applied once
        if outcome.success:
            assert final_marketability == initial_marketability + local_activity.effects.marketability

        # Try to complete again - should fail
        with pytest.raises(ValueError) as exc_info:
            complete_sponsor_activity(updated_save, local_activity.id)
        assert "already completed" in str(exc_info.value).lower()

    def test_cannot_complete_locked_activity(self, save_with_player):
        """Test that locked activities cannot be completed."""
        config = get_sponsor_config()
        elite_activity = next(a for a in config.activities if a.tier == "elite")

        # Player starts with low marketability, elite should be locked
        with pytest.raises(ValueError) as exc_info:
            complete_sponsor_activity(save_with_player, elite_activity.id)
        assert "requires" in str(exc_info.value).lower()

    def test_media_xp_awarded(self, save_with_player):
        """Test that media XP is awarded to development profile."""
        config = get_sponsor_config()
        local_activity = next(
            a for a in config.activities
            if a.tier == "local" and a.effects.media_xp > 0
        )

        # Ensure development profile exists
        from app.models.development_profile import DevelopmentProfile
        if save_with_player.development_profile is None:
            save_with_player = save_with_player.model_copy(
                update={"development_profile": DevelopmentProfile()}
            )

        initial_xp = save_with_player.development_profile.branch_xp.get("media_marketability", 0)

        updated_save, outcome = complete_sponsor_activity(
            save_with_player, local_activity.id
        )

        if outcome.success and updated_save.development_profile:
            final_xp = updated_save.development_profile.branch_xp.get("media_marketability", 0)
            assert final_xp == initial_xp + local_activity.effects.media_xp

    def test_news_generated_for_major_event(self, save_with_player):
        """Test that news is generated for major sponsor events."""
        # Set high marketability to unlock major events
        player = next(d for d in save_with_player.drivers if d.id == save_with_player.player_driver_id)
        player = player.model_copy(
            update={"attributes": player.attributes.model_copy(
                update={"marketability": 80, "sponsor_value": 70}
            )}
        )
        save = save_with_player.model_copy(
            update={"drivers": [player if d.id == player.id else d for d in save_with_player.drivers]}
        )

        config = get_sponsor_config()
        major_activity = next(
            (a for a in config.activities if a.is_major_event and a.min_marketability <= 80),
            None
        )

        if major_activity:
            initial_news_count = len(save.news)

            updated_save, outcome = complete_sponsor_activity(
                save, major_activity.id
            )

            # News should be generated for major events
            assert len(updated_save.news) > initial_news_count


class TestTeamInterestModifier:
    """Tests for team interest modifiers based on sponsor value."""

    def test_backmarker_high_modifier(self):
        """Test that backmarker teams have high sponsor value modifier."""
        # High sponsor value should give significant boost to backmarker interest
        modifier = get_team_interest_modifier(100, "backmarker")
        assert modifier > 1.1  # At least 10% boost

    def test_elite_team_low_modifier(self):
        """Test that elite teams have minimal sponsor value modifier."""
        # Elite teams should not care much about sponsor value
        modifier = get_team_interest_modifier(100, "elite_team")
        assert modifier < 1.05  # Less than 5% boost

    def test_midfield_moderate_modifier(self):
        """Test that midfield teams have moderate sponsor value modifier."""
        modifier = get_team_interest_modifier(100, "midfield")
        # Should be between backmarker and elite
        assert 1.05 < modifier < 1.15

    def test_zero_sponsor_value_no_boost(self):
        """Test that zero sponsor value gives no boost."""
        modifier = get_team_interest_modifier(0, "backmarker")
        assert modifier == 1.0

    def test_apply_to_base_interest(self):
        """Test applying modifier to base interest score."""
        base_interest = 50
        sponsor_value = 80

        modified = apply_sponsor_effects_to_team_interest(
            base_interest, sponsor_value, "backmarker"
        )

        # Should be higher than base
        assert modified > base_interest


class TestClearCompletions:
    """Tests for clearing sponsor activity completions."""

    def test_clear_sponsor_completions(self, save_with_player):
        """Test that sponsor completions can be cleared."""
        config = get_sponsor_config()
        local_activity = next(a for a in config.activities if a.tier == "local")

        # Complete an activity
        updated_save, _ = complete_sponsor_activity(
            save_with_player, local_activity.id
        )

        # Clear completions
        cleared_save = clear_sponsor_completions(updated_save)

        # Should be able to complete again
        result = get_available_sponsor_activities(cleared_save)
        available_ids = [a.activity.id for a in result.available_activities]
        assert local_activity.id in available_ids


class TestAPIEndpoints:
    """Tests for sponsor API endpoints."""

    def test_get_sponsor_activities(self, save_with_player):
        """Test getting sponsor activities via API."""
        response = client.get(f"/career/{save_with_player.save_id}/sponsor/activities")
        assert response.status_code == 200

        data = response.json()
        assert "availableActivities" in data
        assert "lockedActivities" in data
        assert "currentTier" in data
        assert "marketability" in data

    def test_get_sponsor_status(self, save_with_player):
        """Test getting sponsor status via API."""
        response = client.get(f"/career/{save_with_player.save_id}/sponsor/status")
        assert response.status_code == 200

        data = response.json()
        assert "currentTier" in data
        assert "currentTierName" in data
        assert "marketability" in data
        assert "sponsorValue" in data

    def test_complete_activity_via_api(self, save_with_player):
        """Test completing sponsor activity via API."""
        config = get_sponsor_config()
        local_activity = next(a for a in config.activities if a.tier == "local")

        response = client.post(
            f"/career/{save_with_player.save_id}/sponsor/complete",
            json={"activity_id": local_activity.id},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["success"] is True
        assert data["outcome"]["activityId"] == local_activity.id

    def test_complete_locked_activity_via_api(self, save_with_player):
        """Test that completing locked activity returns error."""
        config = get_sponsor_config()
        elite_activity = next(a for a in config.activities if a.tier == "elite")

        response = client.post(
            f"/career/{save_with_player.save_id}/sponsor/complete",
            json={"activity_id": elite_activity.id},
        )
        assert response.status_code == 400

    def test_team_interest_preview(self, save_with_player):
        """Test team interest preview endpoint."""
        response = client.get(
            f"/career/{save_with_player.save_id}/sponsor/team-interest-preview"
        )
        assert response.status_code == 200

        data = response.json()
        assert "sponsorValue" in data
        assert "teamInterestModifiers" in data
        assert "backmarker" in data["teamInterestModifiers"]
        assert "elite_team" in data["teamInterestModifiers"]
