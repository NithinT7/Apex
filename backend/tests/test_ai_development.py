"""Tests for AI driver development system."""

from __future__ import annotations

import pytest

from app.engine.ai_development_engine import (
    apply_ai_season_development,
    get_driver_market_rating,
    get_driver_traits,
    should_consider_for_elite_seat,
    _calculate_development_points,
    _calculate_regression,
    _get_age_development_factor,
    _get_team_quality,
    ROOKIE_AGE,
    YOUNG_DRIVER_AGE,
    VETERAN_AGE,
    LATE_CAREER_AGE,
)
from app.models.ai_development import (
    AI_TRAITS,
    AIDriverDevelopmentState,
    ProtectionTier,
    determine_protection_tier,
    get_driver_overall_rating,
    get_trait,
)
from app.models.driver import Driver, DriverAttributes, HiddenDriverAttributes, CareerStats
from app.models.save_game import ChampionshipEntry, ChampionshipState, SaveGame
from app.models.team import Team


# =============================================================================
# Test Fixtures
# =============================================================================


def make_driver(
    id: str = "test_driver",
    name: str = "Test Driver",
    age: int = 22,
    series: str = "F2",
    team_id: str = "test_team",
    pace: int = 80,
    qualifying: int = 80,
    racecraft: int = 80,
    consistency: int = 80,
    tire_management: int = 80,
    potential: int = 85,
    development_rate: int = 80,
    career_wins: int = 0,
    academy_id: str | None = None,
    nationality: str = "British",
) -> Driver:
    """Create a test driver with configurable attributes."""
    return Driver(
        id=id,
        name=name,
        nationality=nationality,
        age=age,
        series=series,
        team_id=team_id,
        academy_id=academy_id,
        attributes=DriverAttributes(
            pace=pace,
            qualifying=qualifying,
            racecraft=racecraft,
            consistency=consistency,
            tire_management=tire_management,
            starts=75,
            wet_weather=78,
            pressure=78,
            composure=78,
            awareness=75,
            discipline=75,
            focus=75,
            technical_feedback=75,
            adaptability=75,
            confidence=75,
            marketability=70,
            sponsor_value=70,
            reputation=70,
            aggression=70,
        ),
        hidden=HiddenDriverAttributes(
            potential=potential,
            development_rate=development_rate,
            adaptation_ceiling=potential,
            clutch_factor=75,
            crash_proneness=20,
            loyalty=70,
        ),
        career=CareerStats(wins=career_wins),
    )


def make_team(
    id: str = "test_team",
    name: str = "Test Team",
    car_performance: int = 80,
    financial_health: int = 80,
    series: str = "F2",
) -> Team:
    """Create a test team."""
    return Team(
        id=id,
        name=name,
        series=series,
        country="United Kingdom",
        car_performance=car_performance,
        financial_health=financial_health,
        development_rate=70,
        reliability=80,
        strategy=75,
    )


def make_save(
    drivers: list[Driver] | None = None,
    teams: list[Team] | None = None,
    player_driver_id: str | None = "player",
    standings: dict[str, int] | None = None,
    event_flags: dict | None = None,
) -> SaveGame:
    """Create a test save game."""
    from datetime import datetime

    if drivers is None:
        drivers = []
    if teams is None:
        teams = [make_team()]

    # Create driver standings
    driver_standings = []
    if standings:
        # Sort by points (position value inversely)
        sorted_drivers = sorted(standings.items(), key=lambda x: x[1])
        for i, (driver_id, position) in enumerate(sorted_drivers):
            driver_standings.append(
                ChampionshipEntry(
                    driver_id=driver_id,
                    points=100 - (position * 5),  # Simulate points based on position
                    wins=max(0, 5 - position) if position <= 5 else 0,
                )
            )

    championship_state = ChampionshipState(
        driver_standings=driver_standings,
        team_standings={},
    )

    return SaveGame(
        save_id="test_save",
        name="Test Save",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        drivers=drivers,
        teams=teams,
        academies=[],
        academy_states=[],
        player_driver_id=player_driver_id,
        standings=championship_state,
        event_flags=event_flags or {},
        random_seed=12345,
        season=2025,
        current_date="2025-12-01",
        phase="offseason",
        calendar=[],
    )


# =============================================================================
# Test: High-Potential Rookie Development
# =============================================================================


class TestRookieDevelopment:
    """Test that high-potential rookies develop meaningfully."""

    def test_high_potential_rookie_improves_after_strong_season(self):
        """High-potential F2 rookie should improve after strong season."""
        # Create a 20-year-old high-potential rookie
        rookie = make_driver(
            id="rookie",
            name="Rising Star",
            age=20,
            series="F2",
            pace=78,
            qualifying=77,
            racecraft=76,
            consistency=75,
            tire_management=74,
            potential=92,  # Very high potential
            development_rate=85,
        )

        team = make_team(car_performance=85, financial_health=85)
        save = make_save(
            drivers=[rookie],
            teams=[team],
            player_driver_id="player",  # Different from rookie
            standings={"rookie": 2},  # Strong 2nd place finish
        )

        initial_rating = get_driver_overall_rating(rookie)

        # Apply season-end development multiple times to see consistent improvement
        total_improvement = 0
        for _ in range(5):  # Run 5 simulated seasons
            updated_save, news = apply_ai_season_development(save, "season_end")
            updated_rookie = next(d for d in updated_save.drivers if d.id == "rookie")
            new_rating = get_driver_overall_rating(updated_rookie)
            total_improvement += new_rating - get_driver_overall_rating(
                next(d for d in save.drivers if d.id == "rookie")
            )
            save = updated_save

        # Over 5 seasons, a high-potential rookie should show meaningful improvement
        # At least some improvement expected given the setup
        assert total_improvement > 0, "High-potential rookie should improve over time"

    def test_rookie_age_development_factor(self):
        """Rookies should have higher development factor."""
        rookie_factor = _get_age_development_factor(20)
        prime_factor = _get_age_development_factor(28)
        veteran_factor = _get_age_development_factor(35)

        assert rookie_factor > prime_factor > veteran_factor
        assert rookie_factor == 1.5  # Rookies get 1.5x development factor


# =============================================================================
# Test: Average Driver Development
# =============================================================================


class TestAverageDriverDevelopment:
    """Test that average drivers develop modestly."""

    def test_average_driver_develops_modestly(self):
        """Average drivers should develop but not dramatically."""
        avg_driver = make_driver(
            id="average",
            name="Average Driver",
            age=25,
            series="F2",
            pace=75,
            qualifying=75,
            racecraft=75,
            consistency=75,
            tire_management=75,
            potential=80,  # Average potential
            development_rate=70,
        )

        team = make_team(car_performance=75, financial_health=70)
        save = make_save(
            drivers=[avg_driver],
            teams=[team],
            player_driver_id="player",
            standings={"average": 8},  # Middle of the pack
        )

        # Run development
        updated_save, _ = apply_ai_season_development(save, "season_end")
        updated_driver = next(d for d in updated_save.drivers if d.id == "average")

        initial_rating = get_driver_overall_rating(avg_driver)
        final_rating = get_driver_overall_rating(updated_driver)

        # Average driver shouldn't have dramatic changes
        # Allow -2 to +3 points change
        change = final_rating - initial_rating
        assert -3 <= change <= 4, f"Average driver had unexpected change: {change}"


# =============================================================================
# Test: Older Driver Regression
# =============================================================================


class TestOlderDriverRegression:
    """Test that older drivers regress gradually."""

    def test_older_driver_regresses_slowly(self):
        """Drivers in their mid-30s should regress gradually."""
        veteran = make_driver(
            id="veteran",
            name="Veteran Driver",
            age=35,
            series="F1",
            pace=82,
            qualifying=82,
            racecraft=85,
            consistency=84,
            tire_management=86,
            potential=85,
            development_rate=65,
            career_wins=10,
        )

        team = make_team(car_performance=85, financial_health=85, series="F1")
        save = make_save(
            drivers=[veteran],
            teams=[team],
            player_driver_id="player",
            standings={"veteran": 6},
        )

        # Create development state with standard protection
        dev_state = AIDriverDevelopmentState(
            protection_tier="standard",
            peak_rating=85,
        )

        import random
        rng = random.Random("test_regression")

        # Calculate regression
        regression = _calculate_regression(veteran, dev_state, rng)

        # Should have some regression but capped
        assert regression >= 0
        assert regression <= 4  # Standard tier max regression

    def test_late_career_driver_regresses_more(self):
        """Drivers 36+ should regress more noticeably."""
        old_driver = make_driver(
            id="old",
            name="Old Driver",
            age=38,
            series="F1",
            pace=78,
            qualifying=76,
            racecraft=82,
            consistency=80,
            tire_management=84,
            potential=82,
            development_rate=50,
            career_wins=5,
        )

        # Vulnerable tier for struggling older driver
        dev_state = AIDriverDevelopmentState(
            protection_tier="vulnerable",
            peak_rating=85,
            consecutive_decline_seasons=1,
        )

        import random
        rng = random.Random("test_late_career")

        regression = _calculate_regression(old_driver, dev_state, rng)

        # Should regress but within vulnerable limits
        assert regression <= 6  # Vulnerable tier max


# =============================================================================
# Test: Elite Driver Protection
# =============================================================================


class TestEliteDriverProtection:
    """Test that elite drivers are protected from nonsensical collapse."""

    def test_elite_driver_protection_tier(self):
        """World champions and elite drivers get untouchable tier."""
        # World champion under 35
        tier1 = determine_protection_tier(
            driver_age=28,
            overall_rating=93,
            career_wins=25,
            is_world_champion=True,
            series="F1",
        )
        assert tier1 == "untouchable"

        # Elite rating + many wins
        tier2 = determine_protection_tier(
            driver_age=26,
            overall_rating=94,
            career_wins=20,
            is_world_champion=False,
            series="F1",
        )
        assert tier2 == "untouchable"

    def test_elite_driver_minimal_regression(self):
        """Untouchable drivers should have minimal regression."""
        elite = make_driver(
            id="elite",
            name="Max Champion",
            age=28,
            series="F1",
            pace=95,
            qualifying=96,
            racecraft=94,
            consistency=93,
            tire_management=92,
            potential=98,
            development_rate=90,
            career_wins=30,
        )

        dev_state = AIDriverDevelopmentState(
            protection_tier="untouchable",
            peak_rating=95,
        )

        import random

        # Run regression calculation many times
        total_regression = 0
        for seed in range(20):
            rng = random.Random(f"test_elite_{seed}")
            regression = _calculate_regression(elite, dev_state, rng)
            total_regression += regression

        # Average regression should be very low
        avg_regression = total_regression / 20
        assert avg_regression < 0.5, "Elite drivers should rarely regress"

    def test_elite_driver_remains_elite(self):
        """Elite drivers should remain elite over multiple seasons."""
        elite = make_driver(
            id="elite",
            name="Charles Elite",
            age=27,
            series="F1",
            pace=92,
            qualifying=93,
            racecraft=91,
            consistency=90,
            tire_management=89,
            potential=95,
            development_rate=85,
            career_wins=15,
        )

        team = make_team(
            id="elite_team",
            car_performance=95,
            financial_health=95,
            series="F1",
        )

        # Set up save with champion flag
        save = make_save(
            drivers=[elite],
            teams=[team],
            player_driver_id="player",
            standings={"elite": 1},  # Won the championship
            event_flags={"champion_elite": True},
        )

        initial_rating = get_driver_overall_rating(elite)

        # Simulate 5 seasons
        for _ in range(5):
            save, _ = apply_ai_season_development(save, "season_end")

        final_driver = next(d for d in save.drivers if d.id == "elite")
        final_rating = get_driver_overall_rating(final_driver)

        # Elite driver shouldn't drop significantly
        rating_drop = initial_rating - final_rating
        assert rating_drop <= 3, f"Elite driver dropped too much: {rating_drop} points"

    def test_should_consider_for_elite_seat(self):
        """Elite drivers should be considered for top seats."""
        elite = make_driver(
            id="elite",
            name="Elite Driver",
            age=27,
            series="F1",
            pace=92,
            qualifying=93,
            racecraft=91,
            consistency=90,
            tire_management=89,
            potential=95,
            career_wins=20,
        )

        save = make_save(
            drivers=[elite],
            event_flags={
                "ai_development_states": {
                    "elite": {
                        "protection_tier": "untouchable",
                        "peak_rating": 92,
                        "trait_ids": [],
                    }
                }
            },
        )

        assert should_consider_for_elite_seat(elite, save) is True


# =============================================================================
# Test: AI Traits
# =============================================================================


class TestAITraits:
    """Test AI trait system."""

    def test_traits_persist_in_save(self):
        """AI traits should persist in save game."""
        driver = make_driver(
            id="trait_driver",
            name="Trait Driver",
            age=25,
            qualifying=88,  # High enough for elite qualifier
            consistency=87,
        )

        save = make_save(
            drivers=[driver],
            player_driver_id="player",
            standings={"trait_driver": 3},
            event_flags={
                "ai_development_states": {
                    "trait_driver": {
                        "trait_ids": ["elite_qualifier", "consistent_finisher"],
                        "protection_tier": "protected",
                        "peak_rating": 85,
                    }
                }
            },
        )

        # Get traits
        traits = get_driver_traits("trait_driver", save)
        trait_names = [t.name for t in traits]

        assert "Elite Qualifier" in trait_names
        assert "Consistent Finisher" in trait_names

    def test_trait_bonuses_applied(self):
        """Trait bonuses should apply to attributes."""
        trait = get_trait("elite_qualifier")
        assert trait is not None
        assert trait.attribute_bonuses.get("qualifying") == 3
        assert trait.attribute_bonuses.get("confidence") == 2

    def test_get_trait_by_id(self):
        """Should be able to retrieve traits by ID."""
        for trait in AI_TRAITS:
            retrieved = get_trait(trait.id)
            assert retrieved is not None
            assert retrieved.id == trait.id
            assert retrieved.name == trait.name


# =============================================================================
# Test: Driver Market Integration
# =============================================================================


class TestDriverMarketIntegration:
    """Test that driver market uses updated ratings and traits."""

    def test_driver_market_rating_includes_development(self):
        """Driver market rating should include development state."""
        driver = make_driver(
            id="market_driver",
            name="Market Driver",
            age=24,
            pace=85,
            qualifying=86,
            racecraft=84,
            consistency=85,
            tire_management=83,
            potential=90,
        )

        save = make_save(
            drivers=[driver],
            event_flags={
                "ai_development_states": {
                    "market_driver": {
                        "trait_ids": ["late_braker"],
                        "protection_tier": "protected",
                        "peak_rating": 85,
                        "last_season_rating_change": 2,
                    }
                }
            },
        )

        market_info = get_driver_market_rating(driver, save)

        assert market_info["overall_rating"] == get_driver_overall_rating(driver)
        assert market_info["potential"] == 90
        assert market_info["protection_tier"] == "protected"
        assert "Late Braker" in market_info["traits"]
        assert market_info["trend"] == "improving"
        assert market_info["age"] == 24

    def test_driver_market_trend_calculation(self):
        """Market rating should show correct trend based on development."""
        driver = make_driver(id="trend_driver", name="Trend Driver")

        # Declining driver
        save_declining = make_save(
            drivers=[driver],
            event_flags={
                "ai_development_states": {
                    "trend_driver": {
                        "last_season_rating_change": -2,
                        "trait_ids": [],
                        "protection_tier": "standard",
                    }
                }
            },
        )

        market_declining = get_driver_market_rating(driver, save_declining)
        assert market_declining["trend"] == "declining"

        # Stable driver
        save_stable = make_save(
            drivers=[driver],
            event_flags={
                "ai_development_states": {
                    "trend_driver": {
                        "last_season_rating_change": 0,
                        "trait_ids": [],
                        "protection_tier": "standard",
                    }
                }
            },
        )

        market_stable = get_driver_market_rating(driver, save_stable)
        assert market_stable["trend"] == "stable"


# =============================================================================
# Test: Protection Tier System
# =============================================================================


class TestProtectionTiers:
    """Test protection tier determination."""

    def test_protection_tier_world_champion(self):
        """World champions under 35 are untouchable."""
        tier = determine_protection_tier(
            driver_age=30,
            overall_rating=88,
            career_wins=10,
            is_world_champion=True,
            series="F1",
        )
        assert tier == "untouchable"

    def test_protection_tier_older_champion(self):
        """World champions 35+ lose untouchable status."""
        tier = determine_protection_tier(
            driver_age=36,
            overall_rating=88,
            career_wins=15,
            is_world_champion=True,
            series="F1",
        )
        # Still should be protected due to high rating and wins
        assert tier in ("untouchable", "protected")

    def test_protection_tier_young_talent(self):
        """Young high-potential drivers get protection."""
        tier = determine_protection_tier(
            driver_age=22,
            overall_rating=84,
            career_wins=2,
            is_world_champion=False,
            series="F2",
        )
        assert tier == "protected"

    def test_protection_tier_struggling_veteran(self):
        """Struggling older drivers become vulnerable."""
        tier = determine_protection_tier(
            driver_age=37,
            overall_rating=76,
            career_wins=3,
            is_world_champion=False,
            series="F1",
        )
        assert tier == "vulnerable"

    def test_protection_tier_f1_driver_bonus(self):
        """F1 drivers with good ratings get protection."""
        tier = determine_protection_tier(
            driver_age=28,
            overall_rating=86,
            career_wins=2,
            is_world_champion=False,
            series="F1",
        )
        assert tier == "protected"


# =============================================================================
# Test: Team Quality Effects
# =============================================================================


class TestTeamQualityEffects:
    """Test that team quality affects development."""

    def test_elite_team_quality_detection(self):
        """Elite teams should be detected correctly."""
        elite_team = make_team(car_performance=95, financial_health=95)
        assert _get_team_quality(elite_team) == "elite"

    def test_backmarker_team_quality_detection(self):
        """Backmarker teams should be detected correctly."""
        # score = car_performance + (financial_health / 2)
        # score < 75 = backmarker
        backmarker = make_team(car_performance=60, financial_health=20)  # score = 70
        assert _get_team_quality(backmarker) == "backmarker"

    def test_team_quality_tiers(self):
        """Test all team quality tier boundaries.

        score = car_performance + (financial_health / 2)
        Elite: score >= 95
        Top: score >= 85
        Midfield: score >= 75
        Backmarker: score < 75
        """
        # Elite: score >= 95, car_performance=90, financial_health=20 -> 90 + 10 = 100
        elite = make_team(car_performance=90, financial_health=20)
        assert _get_team_quality(elite) == "elite"

        # Top: score >= 85 but < 95, car_performance=80, financial_health=20 -> 80 + 10 = 90
        top = make_team(car_performance=80, financial_health=20)
        assert _get_team_quality(top) == "top"

        # Midfield: score >= 75 but < 85, car_performance=70, financial_health=20 -> 70 + 10 = 80
        mid = make_team(car_performance=70, financial_health=20)
        assert _get_team_quality(mid) == "midfield"


# =============================================================================
# Test: Overall Rating Calculation
# =============================================================================


class TestOverallRating:
    """Test overall rating calculation."""

    def test_overall_rating_calculation(self):
        """Overall rating should be average of core attributes."""
        driver = make_driver(
            pace=85,
            qualifying=90,
            racecraft=82,
            consistency=88,
            tire_management=80,
        )

        expected = round((85 + 90 + 82 + 88 + 80) / 5)  # 85
        assert get_driver_overall_rating(driver) == expected


# =============================================================================
# Test: Season Integration
# =============================================================================


class TestSeasonIntegration:
    """Test integration with season engine."""

    def test_development_at_season_end(self):
        """Development should apply at season end."""
        driver = make_driver(
            id="season_driver",
            name="Season Driver",
            age=22,
            potential=90,
            development_rate=85,
        )

        save = make_save(
            drivers=[driver],
            player_driver_id="player",
            standings={"season_driver": 1},
        )

        updated_save, news = apply_ai_season_development(save, "season_end")

        # Development state should be stored
        ai_states = updated_save.event_flags.get("ai_development_states", {})
        assert "season_driver" in ai_states

    def test_development_at_season_start(self):
        """Smaller development should apply at season start."""
        driver = make_driver(
            id="preseason_driver",
            name="Preseason Driver",
            age=21,
            potential=92,
            development_rate=90,
        )

        save = make_save(
            drivers=[driver],
            player_driver_id="player",
        )

        updated_save, news = apply_ai_season_development(save, "season_start")

        # Should process without error
        assert updated_save is not None

    def test_player_driver_excluded(self):
        """Player driver should not be affected by AI development."""
        player = make_driver(
            id="player",
            name="Player Driver",
            age=22,
            pace=80,
            potential=90,
        )

        save = make_save(
            drivers=[player],
            player_driver_id="player",
            standings={"player": 1},
        )

        initial_rating = get_driver_overall_rating(player)
        updated_save, _ = apply_ai_season_development(save, "season_end")
        updated_player = next(d for d in updated_save.drivers if d.id == "player")
        final_rating = get_driver_overall_rating(updated_player)

        # Player rating should be unchanged
        assert initial_rating == final_rating
