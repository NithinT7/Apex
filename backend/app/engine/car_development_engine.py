"""Deterministic car upgrade and regulation development engine."""

from __future__ import annotations

import random
import uuid

from app.engine.car_performance_engine import apply_profile_delta, clamp_rating
from app.models.car import CarComponentReliability, TeamCarState
from app.models.car_development import (
    CorrelationOutcome,
    EngineerVerdict,
    PracticeCorrelationReport,
    TeamDevelopmentState,
    UpgradeHistoryEntry,
    UpgradeProject,
)
from app.models.driver import Driver
from app.models.save_game import NewsItem, SaveGame
from app.models.team import Team


TARGETS_BY_DEPARTMENT: dict[str, list[str]] = {
    "front_wing": ["aero_efficiency", "low_speed_cornering", "medium_speed_cornering"],
    "rear_wing": ["aero_efficiency", "high_speed_cornering", "straight_line_speed"],
    "floor": ["aero_efficiency", "medium_speed_cornering", "high_speed_cornering"],
    "sidepods_cooling": ["cooling", "aero_efficiency", "reliability"],
    "suspension": ["traction", "low_speed_cornering", "tire_wear"],
    "power_unit": ["straight_line_speed", "reliability", "cooling"],
    "brakes": ["low_speed_cornering", "reliability"],
    "weight_reduction": ["overall_performance", "traction", "tire_warmup"],
    "pit_crew": ["pit_crew"],
    "strategy_tools": ["strategy_team", "setup_window", "tire_wear"],
}

DEPARTMENTS = tuple(TARGETS_BY_DEPARTMENT)
UPGRADE_TYPES = ("minor", "major", "concept", "reliability", "track_specific", "regulation_research")

# ============================================================================
# Technical Feedback → Upgrade Correlation System
# ============================================================================
#
# This system makes driver Technical Feedback matter for understanding upgrades:
# - Higher technical_feedback improves correlation accuracy (smaller error margin)
# - Higher technical_feedback produces clearer driver feedback text
# - Higher technical_feedback leads to better engineer verdicts
# - Only a modest bonus to actual gain (max 8% of expected gain)


def calculate_correlation_accuracy(
    team: Team,
    driver: Driver,
    team_state: TeamDevelopmentState,
    rng: random.Random,
) -> float:
    """
    Calculate how accurately the team understands upgrade performance.

    Formula (weights sum to 1.0):
    - team_engineering_quality: 45%
    - simulator_quality: 20%
    - driver_technical_feedback: 25%
    - team_relationship (driver morale): 5%
    - randomness: 5%

    Returns a value between 0.0 and 1.0 where:
    - 0.0 = no correlation (estimated gain can be wildly off)
    - 1.0 = perfect correlation (estimated gain equals actual gain)
    """
    # Normalize all inputs to 0-1 scale (assuming 0-100 scale inputs)
    engineering = team_state.engineering_quality / 100.0
    simulator = team_state.simulator_quality / 100.0
    technical_feedback = driver.attributes.technical_feedback / 100.0
    team_relationship = driver.morale / 100.0
    random_factor = rng.uniform(0.0, 1.0)

    # Apply the formula weights
    accuracy = (
        engineering * 0.45
        + simulator * 0.20
        + technical_feedback * 0.25
        + team_relationship * 0.05
        + random_factor * 0.05
    )

    # Clamp to 0.0-1.0 range
    return max(0.0, min(1.0, accuracy))


def calculate_actual_gain_with_feedback_bonus(
    expected_gain: dict[str, int],
    driver: Driver,
    team_state: TeamDevelopmentState,
    rng: random.Random,
) -> dict[str, float]:
    """
    Calculate actual gain with a modest bonus from Technical Feedback.

    Technical Feedback can slightly improve actual gain (0-8% of expected gain).
    This represents the driver helping engineers optimize the package.
    The bonus is intentionally modest - factory/engineering quality matters more.
    """
    # Technical feedback bonus: 0% to 8% of expected gain
    # At technical_feedback = 50, bonus = 4%
    # At technical_feedback = 100, bonus = 8%
    # At technical_feedback = 0, bonus = 0%
    feedback_bonus_multiplier = (driver.attributes.technical_feedback / 100.0) * 0.08

    actual_gain: dict[str, float] = {}
    for stat, expected in expected_gain.items():
        # Base gain with small random variation
        base = expected * rng.uniform(0.85, 1.15)
        # Add technical feedback bonus
        bonus = expected * feedback_bonus_multiplier * rng.uniform(0.5, 1.0)
        actual_gain[stat] = round(base + bonus, 2)

    return actual_gain


def calculate_estimated_gain_after_practice(
    actual_gain: dict[str, float],
    correlation_accuracy: float,
    rng: random.Random,
) -> dict[str, float]:
    """
    Calculate what the team thinks the upgrade provides after practice.

    Higher correlation_accuracy = smaller error margin between estimate and actual.
    Lower correlation_accuracy = wider error margin (can be significantly off).

    Error margin formula:
    - At accuracy = 1.0: error_margin = ±5% (nearly perfect)
    - At accuracy = 0.5: error_margin = ±25%
    - At accuracy = 0.0: error_margin = ±50% (could be way off)
    """
    # Calculate error margin based on correlation accuracy
    # Higher accuracy = smaller error margin
    max_error_at_low_accuracy = 0.50  # 50% error at 0 accuracy
    min_error_at_high_accuracy = 0.05  # 5% error at perfect accuracy
    error_margin = max_error_at_low_accuracy - (correlation_accuracy * (max_error_at_low_accuracy - min_error_at_high_accuracy))

    estimated_gain: dict[str, float] = {}
    for stat, actual in actual_gain.items():
        # Add random error within the margin
        error = rng.uniform(-error_margin, error_margin)
        estimated = actual * (1 + error)
        estimated_gain[stat] = round(estimated, 2)

    return estimated_gain


def generate_correlation_outcome(
    predicted_gain: dict[str, float],
    actual_gain: dict[str, float],
    estimated_gain: dict[str, float],
    correlation_accuracy: float,
) -> CorrelationOutcome:
    """
    Generate correlation outcome based on how well estimates match reality.

    Outcomes:
    - "ahead": Actual significantly exceeds predicted (lucky/great development)
    - "on_target": Actual close to predicted
    - "below_target": Actual below predicted but still positive
    - "failed_correlation": Actual is negative or way below predicted
    - "unknown": Not enough data
    """
    if not predicted_gain or not actual_gain:
        return "unknown"

    # Calculate average ratio of actual to predicted
    ratios = []
    for stat in predicted_gain:
        if stat in actual_gain and predicted_gain[stat] > 0:
            ratio = actual_gain[stat] / predicted_gain[stat]
            ratios.append(ratio)

    if not ratios:
        return "unknown"

    avg_ratio = sum(ratios) / len(ratios)

    # Determine outcome based on ratio
    if avg_ratio >= 1.25:
        return "ahead"
    elif avg_ratio >= 0.85:
        return "on_target"
    elif avg_ratio >= 0.40:
        return "below_target"
    else:
        return "failed_correlation"


def generate_driver_feedback_summary(
    driver: Driver,
    upgrade_name: str,
    department: str,
    correlation_outcome: CorrelationOutcome,
    estimated_gain: dict[str, float],
    correlation_accuracy: float,
    rng: random.Random,
) -> str:
    """
    Generate narrative driver feedback based on Technical Feedback attribute.

    Higher technical_feedback = clearer, more specific feedback
    Lower technical_feedback = vague, less useful feedback
    """
    technical_feedback = driver.attributes.technical_feedback

    # Feedback templates by outcome and technical feedback level
    if technical_feedback >= 85:
        # High technical feedback: precise, detailed
        feedback_by_outcome = {
            "ahead": [
                f"The {department} is outperforming tunnel predictions. Balance improvement is immediate and consistent through all corner types.",
                f"Exceptional correlation on the {department}. Rear stability improved, and tire temperatures are staying in the window longer than expected.",
                f"This {department} upgrade is delivering more than the data suggested. Setup direction is clear.",
            ],
            "on_target": [
                f"The {department} is behaving as the engineers predicted. Balance shift is measurable and the setup window feels wider.",
                f"Good correlation on the {department}. The car is responding to setup changes as expected, confidence is building.",
                f"Telemetry matches feel. The {department} is working as intended.",
            ],
            "below_target": [
                f"The {department} isn't delivering the expected step. There's improvement in high-speed but the low-speed balance is tighter than predicted.",
                f"Some inconsistency with the {department}. The gains are there but narrower than the sim suggested. Need to investigate thermal behavior.",
                f"The {department} is positive but not to prediction. Possible interaction with rear suspension geometry.",
            ],
            "failed_correlation": [
                f"The {department} is not correlating. The car feels worse in medium-speed corners and rear tire temps are spiking. Engineers should review the package.",
                f"Something is wrong with the {department}. Balance has shifted in the wrong direction. Recommend removing for further analysis.",
                f"Failed correlation on the {department}. The data doesn't match the wind tunnel at all.",
            ],
            "unknown": [
                f"Need more running to understand the {department}. Initial impressions are unclear.",
            ],
        }
    elif technical_feedback >= 70:
        # Medium-high technical feedback: good but less specific
        feedback_by_outcome = {
            "ahead": [
                f"The {department} feels better than expected. Good step forward in balance.",
                f"Positive surprise with the {department}. Car is more stable.",
            ],
            "on_target": [
                f"The {department} seems to be working as planned. Car feels better.",
                f"Happy with the {department}. Balance improved.",
            ],
            "below_target": [
                f"The {department} isn't quite what we hoped. Some improvement but not as much.",
                f"Mixed feelings on the {department}. Gains are smaller than expected.",
            ],
            "failed_correlation": [
                f"Not happy with the {department}. Car doesn't feel right.",
                f"The {department} might be making things worse. Need to check.",
            ],
            "unknown": [
                f"Hard to say on the {department} yet. Need more laps.",
            ],
        }
    elif technical_feedback >= 50:
        # Medium technical feedback: generic
        feedback_by_outcome = {
            "ahead": [
                f"Car feels good. The {department} seems to be working.",
            ],
            "on_target": [
                f"The {department} feels okay. Car is responding.",
            ],
            "below_target": [
                f"Not sure about the {department}. Something feels off but hard to pinpoint.",
            ],
            "failed_correlation": [
                f"The {department} doesn't feel right. Car is harder to drive.",
            ],
            "unknown": [
                f"Can't really tell yet. Need more time.",
            ],
        }
    else:
        # Low technical feedback: vague
        feedback_by_outcome = {
            "ahead": ["Car feels faster."],
            "on_target": ["It's okay."],
            "below_target": ["Not sure. Maybe slower?"],
            "failed_correlation": ["Something is wrong with the car."],
            "unknown": ["I don't know."],
        }

    options = feedback_by_outcome.get(correlation_outcome, feedback_by_outcome["unknown"])
    return rng.choice(options)


def generate_engineer_verdict(
    correlation_outcome: CorrelationOutcome,
    correlation_confidence: int,
    estimated_gain: dict[str, float],
    correlation_accuracy: float,
) -> tuple[EngineerVerdict, str]:
    """
    Generate engineer recommendation based on correlation data.

    Returns (verdict, explanation_text)
    """
    # With high confidence and good outcome, clear recommendation
    if correlation_confidence >= 80:
        if correlation_outcome == "ahead":
            return "keep_package", "Strong performance. Keep the package and optimize setup around it."
        elif correlation_outcome == "on_target":
            return "keep_package", "Package is delivering as expected. Proceed with planned setup direction."
        elif correlation_outcome == "below_target":
            return "adjust_setup", "Below expectations but positive. Adjust rear suspension to maximize the gains."
        else:
            return "remove_package", "Failed correlation. Recommend reverting to previous spec for race."

    # With medium confidence, more cautious
    elif correlation_confidence >= 60:
        if correlation_outcome in ("ahead", "on_target"):
            return "keep_package", "Preliminary data is positive. Keep package, monitor tire temps."
        elif correlation_outcome == "below_target":
            return "monitor_closely", "Uncertain data. Monitor closely through FP2 and FP3."
        else:
            return "remove_package", "Data suggests correlation issue. Consider removing."

    # With low confidence, hedge
    else:
        if correlation_outcome in ("ahead", "on_target"):
            return "monitor_closely", "Not enough data. Continue evaluation before committing."
        elif correlation_outcome == "below_target":
            return "monitor_closely", "Unclear picture. Need more running to decide."
        else:
            return "remove_package", "Low confidence but concerning signs. Safer to revert."


def generate_enhanced_practice_report(
    project: UpgradeProject,
    team: Team,
    driver: Driver,
    team_state: TeamDevelopmentState,
    round_id: str,
    rng: random.Random,
) -> PracticeCorrelationReport:
    """
    Generate a comprehensive practice correlation report using Technical Feedback.

    This is the main function that brings together all correlation calculations.
    """
    # Calculate correlation accuracy
    correlation_accuracy = calculate_correlation_accuracy(team, driver, team_state, rng)

    # Get predicted gain (what team expected before practice)
    predicted_gain = {k: float(v) for k, v in project.expected_gain.items()}

    # Calculate actual gain with technical feedback bonus
    actual_gain = calculate_actual_gain_with_feedback_bonus(
        project.expected_gain, driver, team_state, rng
    )

    # Calculate estimated gain (what team thinks after practice)
    estimated_gain = calculate_estimated_gain_after_practice(actual_gain, correlation_accuracy, rng)

    # Generate correlation outcome
    correlation_outcome = generate_correlation_outcome(
        predicted_gain, actual_gain, estimated_gain, correlation_accuracy
    )

    # Calculate confidence (affected by correlation accuracy and technical feedback)
    base_confidence = int(correlation_accuracy * 80 + 20)  # Range 20-100
    confidence_jitter = rng.randint(-8, 8)
    correlation_confidence = max(10, min(100, base_confidence + confidence_jitter))

    # Generate driver feedback summary
    driver_feedback_summary = generate_driver_feedback_summary(
        driver, project.name, project.department, correlation_outcome,
        estimated_gain, correlation_accuracy, rng
    )

    # Generate engineer verdict
    engineer_verdict, engineer_verdict_text = generate_engineer_verdict(
        correlation_outcome, correlation_confidence, estimated_gain, correlation_accuracy
    )

    return PracticeCorrelationReport(
        project_id=project.id,
        team_id=team.id,
        round_id=round_id,
        upgrade_name=project.name,
        department=project.department,
        predicted_gain=predicted_gain,
        actual_gain=actual_gain,
        estimated_gain_after_practice=estimated_gain,
        # Legacy fields for backward compatibility
        expected_gain={k: int(v) for k, v in project.expected_gain.items()},
        actual_estimated_gain=estimated_gain,
        correlation_confidence=correlation_confidence,
        confidence_percentage=correlation_confidence,
        correlation_outcome=correlation_outcome,
        correlation_quality=correlation_outcome,
        driver_feedback_summary=driver_feedback_summary,
        driver_feedback=driver_feedback_summary,
        engineer_verdict=engineer_verdict,
        engineer_verdict_text=engineer_verdict_text,
        affected_stats=list(project.expected_gain.keys()),
        correlation_accuracy=correlation_accuracy,
    )


def get_team_primary_driver(team_id: str, drivers: list[Driver]) -> Driver | None:
    """Get the primary driver for a team (first driver found, or highest technical_feedback)."""
    team_drivers = [d for d in drivers if d.team_id == team_id]
    if not team_drivers:
        return None
    # Return driver with highest technical feedback
    return max(team_drivers, key=lambda d: d.attributes.technical_feedback)


# ============================================================================
# End Technical Feedback → Upgrade Correlation System
# ============================================================================


def ensure_car_development_state(save: SaveGame) -> SaveGame:
    teams = [_with_car_state(team, save.season) for team in save.teams]
    development = {
        **{team.id: TeamDevelopmentState(team_id=team.id) for team in teams},
        **save.team_development,
    }
    save = save.model_copy(update={"teams": teams, "team_development": development})
    return schedule_season_upgrades(save)


def schedule_season_upgrades(save: SaveGame) -> SaveGame:
    scheduled: dict[str, TeamDevelopmentState] = {}
    max_round = max((round_.round_number for round_ in save.calendar), default=14)
    for team in save.teams:
        state = save.team_development.get(team.id, TeamDevelopmentState(team_id=team.id))
        if state.active_projects or any(entry.season == save.season for entry in state.upgrade_history):
            scheduled[team.id] = state
            continue

        rng = random.Random(f"{save.random_seed}:{save.season}:{team.id}:upgrade_schedule")
        project_count = 3 if team.series == "F1" and rng.random() < 0.62 else 2
        delivery_slots = sorted(rng.sample(range(3, max(4, max_round)), k=min(project_count, max(1, max_round - 3))))
        active_projects = [
            _generate_project(team, save.season, delivery_round, rng, index)
            for index, delivery_round in enumerate(delivery_slots)
        ]
        scheduled[team.id] = state.model_copy(update={"active_projects": active_projects})

    return save.model_copy(update={"team_development": scheduled})


def apply_due_upgrades(save: SaveGame, round_number: int, round_id: str) -> tuple[SaveGame, list[PracticeCorrelationReport], list[NewsItem]]:
    save = ensure_car_development_state(save)
    updated_teams = {team.id: _with_car_state(team, save.season) for team in save.teams}
    updated_development: dict[str, TeamDevelopmentState] = {}
    reports: list[PracticeCorrelationReport] = []
    news: list[NewsItem] = []

    # Build a lookup for drivers by team
    drivers_by_team: dict[str, list[Driver]] = {}
    for driver in save.drivers:
        if driver.team_id not in drivers_by_team:
            drivers_by_team[driver.team_id] = []
        drivers_by_team[driver.team_id].append(driver)

    for team in updated_teams.values():
        state = save.team_development.get(team.id, TeamDevelopmentState(team_id=team.id))
        remaining: list[UpgradeProject] = []
        history = list(state.upgrade_history)
        applied_this_round: list[str] = []

        # Get the primary driver for correlation calculations
        # Use player if they're on this team, otherwise highest technical_feedback driver
        primary_driver = get_team_primary_driver(team.id, save.drivers)

        for project in state.active_projects:
            if project.delivery_round is None or project.delivery_round > round_number or project.status in {"delivered", "failed", "cancelled"}:
                remaining.append(project)
                continue

            rng = random.Random(f"{save.random_seed}:{save.season}:{team.id}:{project.id}:apply")

            # If we have a driver, use the enhanced correlation system
            if primary_driver is not None:
                # Generate enhanced practice report with Technical Feedback
                report = generate_enhanced_practice_report(
                    project=project,
                    team=team,
                    driver=primary_driver,
                    team_state=state,
                    round_id=round_id,
                    rng=rng,
                )

                # Use the calculated actual gain and determine outcome
                actual_gain = {k: int(round(v)) for k, v in report.actual_gain.items()}
                outcome = report.correlation_outcome

                # Side effects still use the risk system
                side_effects: dict[str, int] = {}
                roll = rng.randint(1, 100)
                if project.upgrade_type in {"concept", "major"} and roll <= project.risk:
                    side_effects[rng.choice(["reliability", "cooling", "setup_window"])] = -1

                # Update project with enhanced correlation data
                updated_project = project.model_copy(
                    update={
                        "actual_gain": actual_gain,
                        "side_effects": side_effects,
                        "correlation_outcome": outcome,
                        "status": "delivered",
                        "predicted_gain": {k: float(v) for k, v in project.expected_gain.items()},
                        "estimated_gain_after_practice": report.estimated_gain_after_practice,
                        "correlation_confidence": report.correlation_confidence,
                        "driver_feedback_summary": report.driver_feedback_summary,
                        "engineer_verdict": report.engineer_verdict,
                    }
                )
                reports.append(report)
            else:
                # Fallback to legacy behavior if no driver available
                actual_gain, side_effects, outcome = _resolve_project(project, rng)
                updated_project = project.model_copy(
                    update={
                        "actual_gain": actual_gain,
                        "side_effects": side_effects,
                        "correlation_outcome": outcome,
                        "status": "delivered",
                    }
                )
                reports.append(_practice_report(updated_project, team.id, round_id, rng))

            combined_gain = {**actual_gain}
            for key, value in side_effects.items():
                combined_gain[key] = combined_gain.get(key, 0) + value

            profile = apply_profile_delta(team.effective_car_profile(), combined_gain)
            car_state = (team.car_state or TeamCarState(team_id=team.id, season=save.season)).model_copy(update={"profile": profile})
            team = _sync_legacy_team_ratings(team.model_copy(update={"car_state": car_state}))
            updated_teams[team.id] = team

            # Create history entry with enhanced correlation data
            history_entry = UpgradeHistoryEntry(
                id=f"hist_{updated_project.id}",
                project_id=updated_project.id,
                round_id=round_id,
                season=save.season,
                summary=f"{updated_project.name} delivered with {outcome.replace('_', ' ')} correlation.",
                applied_gain=actual_gain,
                side_effects=side_effects,
                correlation_outcome=outcome,
                predicted_gain=updated_project.predicted_gain,
                estimated_gain_after_practice=updated_project.estimated_gain_after_practice,
                correlation_confidence=updated_project.correlation_confidence,
                driver_feedback_summary=updated_project.driver_feedback_summary,
                engineer_verdict=updated_project.engineer_verdict,
            )
            history.append(history_entry)
            applied_this_round.append(project.name)

        updated_development[team.id] = state.model_copy(update={"active_projects": remaining, "upgrade_history": history})
        if applied_this_round and team.series == "F1":
            news.append(
                NewsItem(
                    id=f"upgrade_{round_id}_{team.id}",
                    date=save.current_date,
                    category="system",
                    headline=f"{team.name} brings upgrade package",
                    body=", ".join(applied_this_round[:2]) + " will be evaluated through practice correlation.",
                    importance=3,
                )
            )

    return save.model_copy(update={"teams": list(updated_teams.values()), "team_development": updated_development}), reports, news


def offseason_car_evolution(save: SaveGame) -> tuple[SaveGame, list[NewsItem]]:
    """
    Realistic F1 car development with multi-year competitive cycles.

    Key realism features:
    1. Dynasty mechanics - Dominant teams maintain edge for 3-5 years (like Mercedes 2014-2020)
    2. Asymmetric regression - Harder to fall from top, easier to rise from bottom
    3. Momentum tracking - Teams on upward/downward trends continue that trajectory
    4. Design philosophy persistence - Teams keep their characteristic strengths
    5. Financial impact scales with position - Budget matters more at the top
    6. Natural competitive cycles - ~5 year periods of dominance before decline
    7. Rare financial events - Bankruptcy, takeovers, cash injections
    """
    # ═══════════════════════════════════════════════════════════════════════
    # PROCESS RARE FINANCIAL EVENTS FIRST
    # ═══════════════════════════════════════════════════════════════════════
    # These can affect team budgets, development rates, or even replace teams
    from app.engine.financial_events_engine import process_financial_events

    save, financial_news, financial_events = process_financial_events(save)

    regulation_reset = (save.season + 1) % 4 == 0
    updated_teams: list[Team] = []
    updated_development: dict[str, TeamDevelopmentState] = {}
    news_items: list[NewsItem] = list(financial_news)  # Start with financial news

    # Get championship positions for context
    f1_standings = save.f1_standings.driver_standings if save.f1_standings else []
    team_positions = _calculate_team_championship_positions(save)

    for team in save.teams:
        team = _with_car_state(team, save.season)
        state = save.team_development.get(team.id, TeamDevelopmentState(team_id=team.id))
        rng = random.Random(f"{save.random_seed}:{save.season}:{team.id}:offseason_car")
        profile = team.effective_car_profile()
        current_perf = profile.overall_performance

        # Track last season's performance for momentum calculation
        last_perf = state.last_season_performance or current_perf

        # ═══════════════════════════════════════════════════════════════════
        # DYNASTY MECHANICS - Top teams maintain their edge longer
        # ═══════════════════════════════════════════════════════════════════
        dynasty_years = state.dynasty_years
        if current_perf >= 88:  # Top tier performance
            dynasty_years = min(7, dynasty_years + 1)  # Cap at 7 years
        elif current_perf >= 85:  # Upper midfield
            dynasty_years = max(0, dynasty_years - 1)
        else:
            dynasty_years = 0  # Reset if fallen too far

        # Dynasty bonus: Dominant teams have institutional knowledge that persists
        # Reduces over time as key personnel leave, regs change, etc.
        dynasty_bonus = 0
        if dynasty_years >= 2 and not regulation_reset:
            # Years 2-4: Modest bonus (peak dominance)
            # Years 5-7: Declining bonus (natural end of cycle)
            if dynasty_years <= 4:
                dynasty_bonus = rng.randint(0, 2)  # +0 to +2 points (was 1-3)
            else:
                dynasty_bonus = rng.randint(-1, 1) - (dynasty_years - 4)  # Declining faster

        # ═══════════════════════════════════════════════════════════════════
        # MOMENTUM TRACKING - Teams on trends continue them
        # ═══════════════════════════════════════════════════════════════════
        year_change = current_perf - last_perf
        momentum = state.momentum

        # Update momentum based on recent performance
        if year_change >= 3:
            momentum = min(10, momentum + 2)  # Significant improvement
        elif year_change >= 1:
            momentum = min(10, momentum + 1)  # Modest improvement
        elif year_change <= -3:
            momentum = max(-10, momentum - 2)  # Significant decline
        elif year_change <= -1:
            momentum = max(-10, momentum - 1)  # Modest decline
        else:
            # Regression to 0 (no strong trend)
            momentum = round(momentum * 0.7)

        # Struggling teams shouldn't have persistently negative momentum
        # At some point, things can only get better (or stay same)
        min_floor = 58 if team.series == "F1" else 55
        if current_perf <= min_floor + 8 and momentum < -3:
            momentum = max(momentum, -3)  # Cap negative momentum for backmarkers

        # Momentum contributes to next season (inertia)
        momentum_effect = round(momentum * 0.4)  # 40% of momentum translates to performance

        # ═══════════════════════════════════════════════════════════════════
        # ENGINEERING SCORE - How well the team can develop
        # ═══════════════════════════════════════════════════════════════════
        # Financial health matters MORE for top teams (diminishing returns at top)
        financial_weight = 0.28 if current_perf >= 85 else 0.22
        engineering = (
            team.development_rate * 0.42
            + team.financial_health * financial_weight
            + profile.upgrade_potential * 0.16
            + profile.development_rate * 0.10
            + (state.engineering_quality or 75) * 0.04
        )

        # Design roll - some randomness in car concepts
        design_roll = rng.randint(-4, 5)

        # Stability bonus for non-regulation years
        stability = 0 if regulation_reset else round((profile.setup_window - 75) / 12)

        # Research investment pays off in regulation years
        research_bonus = 0
        if regulation_reset and team.series == "F1":
            research_bonus = min(10, state.research_points // 2)
        elif team.series == "F1":
            research_bonus = min(2, state.research_points // 6)

        # ═══════════════════════════════════════════════════════════════════
        # ASYMMETRIC REGRESSION - Harder to fall from top, easier to rise
        # ═══════════════════════════════════════════════════════════════════
        # Real F1: Mercedes dominated for 7 years, but backmarkers can surge
        # with good investment (McLaren 2023, Aston Martin 2023)

        target_center = 80 if team.series == "F1" else 74
        distance_from_center = current_perf - target_center

        if regulation_reset and team.series == "F1":
            # Regulation resets are great equalizers but still favor prepared teams
            continuity = 0.45  # 45% carryover (was 35%)
            # Top teams have better infrastructure to adapt
            if current_perf >= 88:
                continuity += 0.08  # 53% for top teams
            elif current_perf <= 72:
                continuity -= 0.05  # 40% for backmarkers (bigger opportunity)
        else:
            # Normal seasons: High continuity, especially for top teams
            if current_perf >= 90:
                continuity = 0.92  # Top teams: very hard to fall (was 0.78)
            elif current_perf >= 85:
                continuity = 0.88  # Upper midfield: still protected
            elif current_perf >= 80:
                continuity = 0.82  # Midfield: normal
            elif current_perf >= 75:
                continuity = 0.75  # Lower midfield: easier to change
            else:
                continuity = 0.68  # Backmarkers: most volatile (can rise quickly)

        # Asymmetric pull: Gentle for top teams, minimal for backmarkers
        # Key insight: F1 has persistent gaps - Williams hasn't won since 1997
        if distance_from_center > 0:
            # Above average - very gentle pull down (dominance can last)
            baseline_pull = round(distance_from_center * (1 - continuity) * 0.4)
            baseline_pull = -baseline_pull  # Pull DOWN toward center
        else:
            # Below average - minimal pull up (catching up is HARD)
            # In real F1, backmarkers rarely surge to front without massive investment
            # Williams, Sauber, etc. have been stuck at back for decades
            baseline_pull = round(abs(distance_from_center) * (1 - continuity) * 0.35)
            # Pull UP toward center, but heavily capped
            baseline_pull = min(baseline_pull, 2)  # Max 2 points free improvement per season

        # ═══════════════════════════════════════════════════════════════════
        # CALCULATE TOTAL DELTA
        # ═══════════════════════════════════════════════════════════════════
        engineering_delta = round((engineering - 78) / 10)
        delta = (
            engineering_delta
            + design_roll
            + stability
            + research_bonus
            + baseline_pull
            + dynasty_bonus
            + momentum_effect
        )

        # ═══════════════════════════════════════════════════════════════════
        # SOFT CEILING - Elite performance is hard to reach AND maintain
        # ═══════════════════════════════════════════════════════════════════
        # Real F1: Very few teams operate at "maximum possible performance"
        # Even dominant teams have weak points; true 100s are rare
        if team.series == "F1" and current_perf >= 95:
            elite_resistance = 0
            if current_perf >= 98:
                # At 98-100: Strong resistance, very hard to stay at absolute top
                elite_resistance = rng.randint(2, 4)  # Lose 2-4 points naturally
            elif current_perf >= 96:
                # At 96-97: Moderate resistance
                elite_resistance = rng.randint(1, 3)  # Lose 1-3 points
            else:
                # At 95: Mild resistance
                elite_resistance = rng.randint(0, 2)  # Lose 0-2 points

            # Exceptional teams can resist the pull (requires great engineering + luck)
            if engineering >= 85 and rng.random() < 0.35:
                elite_resistance = max(0, elite_resistance - 2)  # Reduce but not eliminate

            delta -= elite_resistance

        # F2 has smaller changes
        if team.series == "F2":
            delta = round(delta * 0.55)

        # Cap extreme changes (no team gains/loses more than 8 in normal year, 12 in reg reset)
        max_change = 12 if regulation_reset else 8
        delta = max(-max_change, min(max_change, delta))

        # ═══════════════════════════════════════════════════════════════════
        # SURVIVAL FLOOR - Backmarkers can't decline indefinitely
        # ═══════════════════════════════════════════════════════════════════
        # Real F1: Even the worst teams maintain some competence
        # Williams, Sauber, etc. don't fall below a certain baseline
        min_floor = 58 if team.series == "F1" else 55
        if current_perf <= min_floor + 5 and delta < 0:
            # Team is struggling - reduce decline or force slight recovery
            if current_perf <= min_floor:
                # At floor: Stop declining, maybe small recovery
                delta = max(0, rng.randint(-1, 2))
            else:
                # Near floor: Reduce decline
                delta = max(delta // 2, -2)

        # ═══════════════════════════════════════════════════════════════════
        # DESIGN PHILOSOPHY PERSISTENCE - Teams keep characteristic strengths
        # ═══════════════════════════════════════════════════════════════════
        philosophy = dict(state.design_philosophy) if state.design_philosophy else {}

        # Initialize or update design philosophy
        if not philosophy:
            # New philosophy based on current car strengths
            stats_to_track = ["aero_efficiency", "high_speed_cornering", "low_speed_cornering", "straight_line_speed", "traction"]
            for stat in stats_to_track:
                stat_value = getattr(profile, stat, 75)
                if stat_value >= 80:
                    philosophy[stat] = rng.randint(2, 4)  # Team strength
                elif stat_value <= 70:
                    philosophy[stat] = rng.randint(-3, -1)  # Team weakness

        # Apply philosophy to stat distribution (strengths improve more, weaknesses less)
        broad_gain = {
            "overall_performance": delta,
            "aero_efficiency": round(delta * 0.75) + rng.choice([-1, 0, 1]) + philosophy.get("aero_efficiency", 0),
            "low_speed_cornering": round(delta * 0.55) + rng.choice([-1, 0, 1]) + philosophy.get("low_speed_cornering", 0),
            "medium_speed_cornering": round(delta * 0.65) + philosophy.get("medium_speed_cornering", 0),
            "high_speed_cornering": round(delta * 0.70) + philosophy.get("high_speed_cornering", 0),
            "straight_line_speed": round(delta * 0.60) + rng.choice([-1, 0, 1]) + philosophy.get("straight_line_speed", 0),
            "traction": round(delta * 0.50) + philosophy.get("traction", 0),
            "reliability": rng.randint(-2, 2) + round((team.development_rate - 78) / 20),
            "strategy_team": rng.choice([-1, 0, 0, 1]),
        }

        # Regulation reset can reshuffle philosophy
        if regulation_reset and team.series == "F1":
            broad_gain["setup_window"] = rng.randint(-3, 4)
            # Philosophy partially resets (some DNA carries over)
            for stat in list(philosophy.keys()):
                philosophy[stat] = round(philosophy[stat] * 0.5) + rng.randint(-1, 1)
                if abs(philosophy[stat]) <= 1:
                    del philosophy[stat]

        # Apply the gains
        new_profile = apply_profile_delta(profile, broad_gain)
        new_perf = new_profile.overall_performance

        # Update peak performance tracking
        peak_performance = max(state.peak_performance or current_perf, new_perf)

        # Create updated car state
        car_state = (team.car_state or TeamCarState(team_id=team.id, season=save.season)).model_copy(
            update={"season": save.season + 1, "profile": new_profile}
        )
        updated_teams.append(_sync_legacy_team_ratings(team.model_copy(update={"car_state": car_state})))

        # Update development state with new tracking fields
        updated_development[team.id] = state.model_copy(update={
            "active_projects": [],
            "research_points": max(0, state.research_points // 2),
            "momentum": momentum,
            "dynasty_years": dynasty_years,
            "design_philosophy": philosophy,
            "last_season_performance": current_perf,
            "peak_performance": peak_performance,
        })

        # Generate news for significant changes
        if team.series == "F1" and abs(delta) >= 4:
            if delta >= 4:
                news_items.append(NewsItem(
                    id=f"team_surge_{team.id}_{uuid.uuid4().hex[:8]}",
                    date=save.current_date,
                    category="system",
                    headline=f"{team.name} makes major step forward",
                    body=f"Winter testing reveals {team.name} has made significant gains, with analysts predicting a much stronger season.",
                    importance=4,
                    linked_team_ids=[team.id],
                ))
            else:
                news_items.append(NewsItem(
                    id=f"team_drop_{team.id}_{uuid.uuid4().hex[:8]}",
                    date=save.current_date,
                    category="system",
                    headline=f"{team.name} struggles with new package",
                    body=f"Sources indicate {team.name} has taken a step backwards, raising concerns about their development direction.",
                    importance=4,
                    linked_team_ids=[team.id],
                ))

    # Main headline
    headline = "Major regulation reset shakes up the F1 grid" if regulation_reset else "Teams reveal offseason development gains"
    body = (
        "New rules reduce carryover from old cars, rewarding regulation research and producing a less predictable order."
        if regulation_reset
        else "Winter development updates car profiles before the next campaign."
    )
    news_items.insert(0, NewsItem(
        id=f"offseason_car_{uuid.uuid4().hex[:8]}",
        date=save.current_date,
        category="system",
        headline=headline,
        body=body,
        importance=5 if regulation_reset else 3,
    ))

    return save.model_copy(update={"teams": updated_teams, "team_development": updated_development}), news_items


def _calculate_team_championship_positions(save: SaveGame) -> dict[str, int]:
    """Calculate team championship positions from driver standings."""
    if not save.f1_standings:
        return {}

    # Build driver_id -> team_id mapping
    driver_teams = {d.id: d.team_id for d in save.drivers}

    team_points: dict[str, int] = {}
    for entry in save.f1_standings.driver_standings:
        team_id = driver_teams.get(entry.driver_id)
        if team_id:
            team_points[team_id] = team_points.get(team_id, 0) + entry.points

    sorted_teams = sorted(team_points.items(), key=lambda x: x[1], reverse=True)
    return {team_id: pos + 1 for pos, (team_id, _) in enumerate(sorted_teams)}


def _with_car_state(team: Team, season: int) -> Team:
    if team.car_state is not None:
        return team
    return team.model_copy(
        update={
            "car_state": TeamCarState(
                team_id=team.id,
                season=season,
                profile=team.effective_car_profile(),
                component_reliability=CarComponentReliability.from_legacy(team.reliability),
            )
        }
    )


def _generate_project(team: Team, season: int, delivery_round: int, rng: random.Random, index: int) -> UpgradeProject:
    department = rng.choice(DEPARTMENTS)
    upgrade_type = rng.choice(UPGRADE_TYPES if team.series == "F1" else ("minor", "reliability", "track_specific"))
    targets = TARGETS_BY_DEPARTMENT[department]
    if upgrade_type == "regulation_research":
        targets = ["upgrade_potential", "development_rate"]
    selected = rng.sample(targets, k=min(len(targets), 2 if upgrade_type in {"major", "concept"} else 1))
    gain_base = {"minor": 1, "major": 3, "concept": 4, "reliability": 2, "track_specific": 2, "regulation_research": 0}[upgrade_type]
    expected_gain = {stat: gain_base + (1 if upgrade_type == "concept" and rng.random() < 0.35 else 0) for stat in selected}
    if upgrade_type == "reliability":
        expected_gain = {"reliability": 2, "cooling": 1}
    risk = {"minor": 14, "major": 28, "concept": 46, "reliability": 12, "track_specific": 24, "regulation_research": 8}[upgrade_type]
    name = f"{_label(department)} {upgrade_type.replace('_', ' ')} package"
    return UpgradeProject(
        id=f"{team.id}_{season}_upgrade_{index + 1}",
        name=name,
        department=department,
        upgrade_type=upgrade_type,
        target_stats={stat: 1 for stat in selected},
        expected_gain=expected_gain,
        risk=risk,
        status="in_progress",
        delivery_round=delivery_round,
    )


def _resolve_project(project: UpgradeProject, rng: random.Random) -> tuple[dict[str, int], dict[str, int], CorrelationOutcome]:
    roll = rng.randint(1, 100)
    if roll <= project.risk // 4:
        multiplier, outcome = 0.0, "failed_correlation"
    elif roll <= project.risk:
        multiplier, outcome = 0.55, "below_target"
    elif roll >= 94:
        multiplier, outcome = 1.35, "ahead"
    else:
        multiplier, outcome = 1.0, "on_target"

    actual_gain = {key: max(0, round(value * multiplier)) for key, value in project.expected_gain.items()}
    side_effects: dict[str, int] = {}
    if project.upgrade_type in {"concept", "major"} and roll <= project.risk:
        side_effects[rng.choice(["reliability", "cooling", "setup_window"])] = -1
    return actual_gain, side_effects, outcome


def _practice_report(project: UpgradeProject, team_id: str, round_id: str, rng: random.Random) -> PracticeCorrelationReport:
    confidence_by_outcome = {
        "ahead": 86,
        "on_target": 74,
        "below_target": 52,
        "failed_correlation": 34,
        "unknown": 50,
    }
    confidence = confidence_by_outcome[project.correlation_outcome] + rng.randint(-5, 5)
    feedback = {
        "ahead": "Driver feedback suggests the package is delivering cleaner balance than the tunnel prediction.",
        "on_target": "Driver feedback matches the expected balance shift and the data looks representative.",
        "below_target": "The car is responding, but drivers report a narrower window than expected.",
        "failed_correlation": "Driver feedback does not match the expected behavior; engineers will review the package.",
        "unknown": "The team still needs more running before confirming the upgrade.",
    }[project.correlation_outcome]
    return PracticeCorrelationReport(
        project_id=project.id,
        team_id=team_id,
        round_id=round_id,
        expected_gain=project.expected_gain,
        actual_estimated_gain={key: value + rng.uniform(-0.35, 0.35) for key, value in project.actual_gain.items()},
        driver_feedback=feedback,
        correlation_quality=project.correlation_outcome,
        confidence_percentage=clamp_rating(confidence),
    )


def _sync_legacy_team_ratings(team: Team) -> Team:
    profile = team.effective_car_profile()
    return team.model_copy(
        update={
            "car_performance": clamp_rating(profile.overall_performance),
            "reliability": clamp_rating(profile.reliability),
            "strategy": clamp_rating(profile.strategy_team),
            "development_rate": clamp_rating(profile.development_rate),
        }
    )


def _label(value: str) -> str:
    return value.replace("_", " ").title()
