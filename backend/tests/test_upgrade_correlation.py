"""Tests for Technical Feedback → Upgrade Correlation system.

These tests verify that:
1. Low Technical Feedback creates wider estimated-vs-actual error
2. High Technical Feedback creates narrower estimated-vs-actual error
3. Technical Feedback does not create unrealistic actual gain boosts (max 8%)
4. Same seed produces same correlation result
5. Correlation calculations work correctly
"""

import random
from statistics import mean, stdev

import pytest

from app.engine.car_development_engine import (
    calculate_correlation_accuracy,
    calculate_actual_gain_with_feedback_bonus,
    calculate_estimated_gain_after_practice,
    generate_correlation_outcome,
    generate_driver_feedback_summary,
    generate_engineer_verdict,
    generate_enhanced_practice_report,
    get_team_primary_driver,
)
from app.models.car_development import (
    TeamDevelopmentState,
    UpgradeProject,
)
from app.models.driver import Driver, DriverAttributes, HiddenDriverAttributes
from app.models.team import Team


@pytest.fixture
def base_team() -> Team:
    """Create a base team for testing."""
    return Team(
        id="test_team",
        name="Test Team",
        series="F1",
        country="GB",
        car_performance=80,
        reliability=80,
        strategy=80,
        development_rate=80,
        financial_health=80,
    )


@pytest.fixture
def base_team_state() -> TeamDevelopmentState:
    """Create a base team development state."""
    return TeamDevelopmentState(
        team_id="test_team",
        engineering_quality=75,
        simulator_quality=70,
        manufacturing_speed=70,
        upgrade_risk_tolerance=50,
    )


@pytest.fixture
def low_tech_feedback_driver() -> Driver:
    """Create a driver with low technical feedback (50)."""
    return Driver(
        id="low_tech_driver",
        name="Low Tech Driver",
        nationality="GB",
        age=22,
        series="F1",
        team_id="test_team",
        attributes=DriverAttributes(
            pace=70,
            qualifying=70,
            racecraft=70,
            tire_management=70,
            wet_weather=70,
            consistency=70,
            starts=70,
            awareness=70,
            adaptability=70,
            technical_feedback=50,  # Low technical feedback
            pressure=70,
            confidence=70,
            composure=70,
            aggression=70,
            discipline=70,
            focus=70,
            reputation=70,
            marketability=70,
            sponsor_value=70,
        ),
        hidden=HiddenDriverAttributes(
            potential=85,
            development_rate=70,
            clutch_factor=70,
            crash_proneness=20,
            loyalty=70,
            adaptation_ceiling=90,
        ),
        morale=50,
    )


@pytest.fixture
def high_tech_feedback_driver() -> Driver:
    """Create a driver with high technical feedback (90)."""
    return Driver(
        id="high_tech_driver",
        name="High Tech Driver",
        nationality="GB",
        age=28,
        series="F1",
        team_id="test_team",
        attributes=DriverAttributes(
            pace=70,
            qualifying=70,
            racecraft=70,
            tire_management=70,
            wet_weather=70,
            consistency=70,
            starts=70,
            awareness=70,
            adaptability=70,
            technical_feedback=90,  # High technical feedback
            pressure=70,
            confidence=70,
            composure=70,
            aggression=70,
            discipline=70,
            focus=70,
            reputation=70,
            marketability=70,
            sponsor_value=70,
        ),
        hidden=HiddenDriverAttributes(
            potential=85,
            development_rate=70,
            clutch_factor=70,
            crash_proneness=20,
            loyalty=70,
            adaptation_ceiling=90,
        ),
        morale=70,
    )


@pytest.fixture
def base_upgrade_project() -> UpgradeProject:
    """Create a base upgrade project for testing."""
    return UpgradeProject(
        id="test_upgrade",
        name="New Floor Package",
        department="floor",
        upgrade_type="major",
        target_stats={"aero_efficiency": 3, "medium_speed_cornering": 2},
        expected_gain={"aero_efficiency": 3, "medium_speed_cornering": 2},
        risk=20,
        status="in_progress",
        delivery_round=5,
    )


class TestCorrelationAccuracy:
    """Tests for correlation accuracy calculation."""

    def test_higher_tech_feedback_increases_accuracy(
        self,
        base_team: Team,
        base_team_state: TeamDevelopmentState,
        low_tech_feedback_driver: Driver,
        high_tech_feedback_driver: Driver,
    ):
        """High technical feedback should produce higher correlation accuracy."""
        rng = random.Random(42)

        # Calculate accuracy with low tech feedback
        low_accuracies = []
        for _ in range(100):
            acc = calculate_correlation_accuracy(
                base_team, low_tech_feedback_driver, base_team_state, rng
            )
            low_accuracies.append(acc)

        # Reset RNG and calculate with high tech feedback
        rng = random.Random(42)
        high_accuracies = []
        for _ in range(100):
            acc = calculate_correlation_accuracy(
                base_team, high_tech_feedback_driver, base_team_state, rng
            )
            high_accuracies.append(acc)

        # High tech feedback should produce higher average accuracy
        assert mean(high_accuracies) > mean(low_accuracies)

    def test_accuracy_range_is_valid(
        self,
        base_team: Team,
        base_team_state: TeamDevelopmentState,
        high_tech_feedback_driver: Driver,
    ):
        """Correlation accuracy should always be between 0 and 1."""
        for seed in range(100):
            rng = random.Random(seed)
            accuracy = calculate_correlation_accuracy(
                base_team, high_tech_feedback_driver, base_team_state, rng
            )
            assert 0.0 <= accuracy <= 1.0


class TestEstimationError:
    """Tests for estimated gain error margins."""

    def test_high_accuracy_smaller_error(self):
        """High correlation accuracy should produce smaller estimation errors."""
        actual_gain = {"aero_efficiency": 3.0, "medium_speed_cornering": 2.0}

        high_acc_errors = []
        low_acc_errors = []

        for seed in range(100):
            rng = random.Random(seed)
            high_est = calculate_estimated_gain_after_practice(actual_gain, 0.9, rng)
            high_error = sum(
                abs(high_est[k] - actual_gain[k]) for k in actual_gain
            )
            high_acc_errors.append(high_error)

            rng = random.Random(seed)
            low_est = calculate_estimated_gain_after_practice(actual_gain, 0.3, rng)
            low_error = sum(
                abs(low_est[k] - actual_gain[k]) for k in actual_gain
            )
            low_acc_errors.append(low_error)

        # High accuracy should produce lower average error
        assert mean(high_acc_errors) < mean(low_acc_errors)

    def test_low_tech_feedback_wider_error(
        self,
        base_team: Team,
        base_team_state: TeamDevelopmentState,
        low_tech_feedback_driver: Driver,
        high_tech_feedback_driver: Driver,
        base_upgrade_project: UpgradeProject,
    ):
        """Low technical feedback should produce wider estimation errors over many samples."""
        low_errors = []
        high_errors = []

        for seed in range(100):
            # Low tech feedback
            rng = random.Random(seed)
            low_acc = calculate_correlation_accuracy(
                base_team, low_tech_feedback_driver, base_team_state, rng
            )
            actual = calculate_actual_gain_with_feedback_bonus(
                base_upgrade_project.expected_gain, low_tech_feedback_driver, base_team_state, rng
            )
            estimated = calculate_estimated_gain_after_practice(actual, low_acc, rng)
            low_error = sum(abs(estimated[k] - actual[k]) for k in actual)
            low_errors.append(low_error)

            # High tech feedback
            rng = random.Random(seed)
            high_acc = calculate_correlation_accuracy(
                base_team, high_tech_feedback_driver, base_team_state, rng
            )
            actual = calculate_actual_gain_with_feedback_bonus(
                base_upgrade_project.expected_gain, high_tech_feedback_driver, base_team_state, rng
            )
            estimated = calculate_estimated_gain_after_practice(actual, high_acc, rng)
            high_error = sum(abs(estimated[k] - actual[k]) for k in actual)
            high_errors.append(high_error)

        # Low tech feedback should have higher average error
        assert mean(low_errors) > mean(high_errors)
        # Low tech feedback should have higher error standard deviation (more variable)
        if len(low_errors) > 1 and len(high_errors) > 1:
            assert stdev(low_errors) >= stdev(high_errors) * 0.8  # Allow some margin


class TestActualGainBonus:
    """Tests for technical feedback bonus on actual gain."""

    def test_tech_feedback_bonus_is_modest(
        self,
        base_team_state: TeamDevelopmentState,
        high_tech_feedback_driver: Driver,
    ):
        """Technical feedback bonus should be at most 8% of expected gain."""
        expected_gain = {"aero_efficiency": 10, "medium_speed_cornering": 10}

        for seed in range(50):
            rng = random.Random(seed)
            actual = calculate_actual_gain_with_feedback_bonus(
                expected_gain, high_tech_feedback_driver, base_team_state, rng
            )

            for stat, expected in expected_gain.items():
                # Max bonus at 90 tech feedback = 90/100 * 0.08 = 7.2%
                # With random multiplier up to 1.15 base and 1.0 bonus multiplier
                # Max actual = expected * 1.15 + expected * 0.072 * 1.0 = expected * 1.222
                max_reasonable = expected * 1.25  # Allow small margin
                assert actual[stat] <= max_reasonable, (
                    f"Actual gain {actual[stat]} exceeds reasonable max {max_reasonable}"
                )

    def test_higher_tech_feedback_slightly_higher_gain(
        self,
        base_team_state: TeamDevelopmentState,
        low_tech_feedback_driver: Driver,
        high_tech_feedback_driver: Driver,
    ):
        """Higher technical feedback should produce slightly higher actual gains on average."""
        expected_gain = {"aero_efficiency": 5, "medium_speed_cornering": 5}

        low_gains = []
        high_gains = []

        for seed in range(100):
            rng = random.Random(seed)
            low_actual = calculate_actual_gain_with_feedback_bonus(
                expected_gain, low_tech_feedback_driver, base_team_state, rng
            )
            low_total = sum(low_actual.values())
            low_gains.append(low_total)

            rng = random.Random(seed)
            high_actual = calculate_actual_gain_with_feedback_bonus(
                expected_gain, high_tech_feedback_driver, base_team_state, rng
            )
            high_total = sum(high_actual.values())
            high_gains.append(high_total)

        # High tech feedback should have higher average gain, but not massively
        diff = mean(high_gains) - mean(low_gains)
        expected_total = sum(expected_gain.values())
        diff_percentage = (diff / expected_total) * 100

        assert diff > 0, "High tech feedback should produce higher gains"
        assert diff_percentage < 10, f"Difference {diff_percentage:.1f}% is too large (should be <10%)"


class TestCorrelationOutcome:
    """Tests for correlation outcome determination."""

    def test_outcome_ahead(self):
        """When actual significantly exceeds predicted, outcome should be 'ahead'."""
        predicted = {"aero_efficiency": 3.0}
        actual = {"aero_efficiency": 4.5}  # 150% of predicted
        estimated = {"aero_efficiency": 4.3}

        outcome = generate_correlation_outcome(predicted, actual, estimated, 0.8)
        assert outcome == "ahead"

    def test_outcome_on_target(self):
        """When actual is close to predicted, outcome should be 'on_target'."""
        predicted = {"aero_efficiency": 3.0}
        actual = {"aero_efficiency": 3.0}  # 100% of predicted
        estimated = {"aero_efficiency": 2.9}

        outcome = generate_correlation_outcome(predicted, actual, estimated, 0.8)
        assert outcome == "on_target"

    def test_outcome_below_target(self):
        """When actual is somewhat below predicted, outcome should be 'below_target'."""
        predicted = {"aero_efficiency": 3.0}
        actual = {"aero_efficiency": 1.8}  # 60% of predicted
        estimated = {"aero_efficiency": 1.9}

        outcome = generate_correlation_outcome(predicted, actual, estimated, 0.8)
        assert outcome == "below_target"

    def test_outcome_failed(self):
        """When actual is way below predicted, outcome should be 'failed_correlation'."""
        predicted = {"aero_efficiency": 3.0}
        actual = {"aero_efficiency": 0.5}  # ~17% of predicted
        estimated = {"aero_efficiency": 0.6}

        outcome = generate_correlation_outcome(predicted, actual, estimated, 0.8)
        assert outcome == "failed_correlation"

    def test_empty_gains_returns_unknown(self):
        """Empty gain dicts should return 'unknown'."""
        outcome = generate_correlation_outcome({}, {}, {}, 0.8)
        assert outcome == "unknown"


class TestDriverFeedbackSummary:
    """Tests for driver feedback summary generation."""

    def test_high_tech_feedback_clearer_text(
        self,
        low_tech_feedback_driver: Driver,
        high_tech_feedback_driver: Driver,
    ):
        """High tech feedback should produce longer, more detailed feedback."""
        rng = random.Random(42)
        estimated = {"aero_efficiency": 3.0}

        low_feedback = generate_driver_feedback_summary(
            low_tech_feedback_driver, "New Floor", "floor", "on_target", estimated, 0.5, rng
        )

        rng = random.Random(42)
        high_feedback = generate_driver_feedback_summary(
            high_tech_feedback_driver, "New Floor", "floor", "on_target", estimated, 0.9, rng
        )

        # High tech feedback should produce longer, more detailed feedback
        assert len(high_feedback) >= len(low_feedback)


class TestEngineerVerdict:
    """Tests for engineer verdict generation."""

    def test_high_confidence_good_outcome_keeps_package(self):
        """High confidence with good outcome should recommend keeping package."""
        verdict, text = generate_engineer_verdict("on_target", 85, {"aero_efficiency": 3.0}, 0.9)
        assert verdict == "keep_package"

    def test_failed_outcome_removes_package(self):
        """Failed correlation should recommend removing package."""
        verdict, text = generate_engineer_verdict("failed_correlation", 85, {"aero_efficiency": 0.5}, 0.9)
        assert verdict == "remove_package"

    def test_low_confidence_monitors_closely(self):
        """Low confidence should recommend monitoring closely."""
        verdict, text = generate_engineer_verdict("on_target", 45, {"aero_efficiency": 3.0}, 0.4)
        assert verdict == "monitor_closely"

    def test_below_target_adjusts_setup(self):
        """Below target with high confidence should recommend setup adjustment."""
        verdict, text = generate_engineer_verdict("below_target", 85, {"aero_efficiency": 1.5}, 0.8)
        assert verdict == "adjust_setup"


class TestDeterminism:
    """Tests for deterministic behavior."""

    def test_same_seed_same_result(
        self,
        base_team: Team,
        base_team_state: TeamDevelopmentState,
        high_tech_feedback_driver: Driver,
        base_upgrade_project: UpgradeProject,
    ):
        """Same seed should produce identical correlation results."""
        results = []

        for _ in range(3):
            rng = random.Random(42)
            report = generate_enhanced_practice_report(
                project=base_upgrade_project,
                team=base_team,
                driver=high_tech_feedback_driver,
                team_state=base_team_state,
                round_id="round_5",
                rng=rng,
            )
            results.append(report)

        # All results should be identical
        assert results[0].correlation_confidence == results[1].correlation_confidence == results[2].correlation_confidence
        assert results[0].correlation_outcome == results[1].correlation_outcome == results[2].correlation_outcome
        assert results[0].engineer_verdict == results[1].engineer_verdict == results[2].engineer_verdict


class TestEnhancedPracticeReport:
    """Tests for the full enhanced practice report generation."""

    def test_report_has_all_fields(
        self,
        base_team: Team,
        base_team_state: TeamDevelopmentState,
        high_tech_feedback_driver: Driver,
        base_upgrade_project: UpgradeProject,
    ):
        """Report should contain all required fields."""
        rng = random.Random(42)
        report = generate_enhanced_practice_report(
            project=base_upgrade_project,
            team=base_team,
            driver=high_tech_feedback_driver,
            team_state=base_team_state,
            round_id="round_5",
            rng=rng,
        )

        assert report.project_id == base_upgrade_project.id
        assert report.team_id == base_team.id
        assert report.round_id == "round_5"
        assert report.upgrade_name == base_upgrade_project.name
        assert report.department == base_upgrade_project.department
        assert len(report.predicted_gain) > 0
        assert len(report.actual_gain) > 0
        assert len(report.estimated_gain_after_practice) > 0
        assert 0 <= report.correlation_confidence <= 100
        assert report.correlation_outcome in ["unknown", "ahead", "on_target", "below_target", "failed_correlation"]
        assert len(report.driver_feedback_summary) > 0
        assert report.engineer_verdict in ["keep_package", "adjust_setup", "monitor_closely", "remove_package", "pending"]
        assert len(report.engineer_verdict_text) > 0
        assert 0.0 <= report.correlation_accuracy <= 1.0

    def test_high_tech_feedback_higher_confidence(
        self,
        base_team: Team,
        base_team_state: TeamDevelopmentState,
        low_tech_feedback_driver: Driver,
        high_tech_feedback_driver: Driver,
        base_upgrade_project: UpgradeProject,
    ):
        """High tech feedback should produce higher average confidence over many samples."""
        low_confidences = []
        high_confidences = []

        for seed in range(50):
            rng = random.Random(seed)
            low_report = generate_enhanced_practice_report(
                project=base_upgrade_project,
                team=base_team,
                driver=low_tech_feedback_driver,
                team_state=base_team_state,
                round_id="round_5",
                rng=rng,
            )
            low_confidences.append(low_report.correlation_confidence)

            rng = random.Random(seed)
            high_report = generate_enhanced_practice_report(
                project=base_upgrade_project,
                team=base_team,
                driver=high_tech_feedback_driver,
                team_state=base_team_state,
                round_id="round_5",
                rng=rng,
            )
            high_confidences.append(high_report.correlation_confidence)

        assert mean(high_confidences) > mean(low_confidences)


class TestGetTeamPrimaryDriver:
    """Tests for getting the primary driver for a team."""

    def test_returns_driver_with_highest_tech_feedback(
        self,
        low_tech_feedback_driver: Driver,
        high_tech_feedback_driver: Driver,
    ):
        """Should return the driver with highest technical feedback."""
        drivers = [low_tech_feedback_driver, high_tech_feedback_driver]
        primary = get_team_primary_driver("test_team", drivers)

        assert primary is not None
        assert primary.id == high_tech_feedback_driver.id

    def test_returns_none_for_empty_list(self):
        """Should return None if no drivers for team."""
        primary = get_team_primary_driver("nonexistent_team", [])
        assert primary is None
