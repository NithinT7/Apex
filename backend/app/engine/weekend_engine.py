from __future__ import annotations

import random
from dataclasses import dataclass

from app.engine.car_performance_engine import (
    performance_composite,
    qualifying_car_score,
    race_car_score,
    setup_confidence_score,
    team_track_score,
)
from app.models.calendar import CalendarRound
from app.models.car_development import PracticeCorrelationReport
from app.models.driver import Driver
from app.models.race import (
    DecisionChoice,
    DecisionPrompt,
    LapSnapshot,
    PracticeClassification,
    PracticeResult,
    QualifyingClassification,
    QualifyingResult,
    QualifyingSegment,
    RaceClassification,
    RaceResult,
    RunningOrderEntry,
    WeatherState,
    WeekendResult,
)
from app.models.strategy import (
    PitStopEvent,
    RaceStrategyPlan,
    SafetyCarDecisionContext,
    StintSummary,
    StrategyCall,
)
from app.models.save_game import SaveGame
from app.models.team import Team
from app.models.track import Track


SPRINT_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
FEATURE_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
F1_SPRINT_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
F1_GRAND_PRIX_POINTS = FEATURE_POINTS


@dataclass
class Runner:
    driver: Driver
    team: Team
    cumulative_time: float = 0
    fastest_lap: float = 999
    tire_compound: str = "medium"
    tire_age: int = 0
    tire_wear: float = 0
    pit_stops: int = 0
    last_lap_time: float | None = None
    previous_lap_time: float | None = None
    planned_stops: int = 0
    planned_pit_laps: list[int] | None = None
    strategy_style: str = "balanced"
    pit_block_until_lap: int = 0
    component_wear: float = 0
    status: str = "running"


def simulate_weekend(
    save: SaveGame,
    round_id: str,
    practice_correlation_reports: list[PracticeCorrelationReport] | None = None,
) -> WeekendResult:
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)
    drivers = [driver for driver in save.drivers if driver.series == calendar_round.series]
    teams = {team.id: team for team in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}")
    weather = _weather(track, rng)

    practice = _simulate_practice(drivers, teams, track, weather, rng, practice_correlation_reports or [])
    qualifying = _simulate_qualifying(drivers, teams, track, weather, rng, series=calendar_round.series)
    qualifying_order = [entry.driver_id for entry in qualifying.classification]
    sprint_grid = sprint_grid_for_round(calendar_round, qualifying_order)
    sprint = (
        _simulate_race("sprint", calendar_round, sprint_grid, drivers, teams, track, weather, rng, save)
        if sprint_grid
        else empty_race_result("sprint", track)
    )
    feature = _simulate_race("feature", calendar_round, qualifying_order, drivers, teams, track, weather, rng, save)

    return WeekendResult(
        save_id=save.save_id,
        round_id=round_id,
        track_id=track.id,
        completed=True,
        practice=practice,
        qualifying=qualifying,
        sprint=sprint,
        feature=feature,
        headline=_headline(save, feature),
    )


def sprint_grid_for_round(calendar_round: CalendarRound, qualifying_order: list[str]) -> list[str]:
    if not calendar_round.has_sprint:
        return []
    if calendar_round.series == "F2":
        return list(reversed(qualifying_order[:10])) + qualifying_order[10:]
    return qualifying_order


def empty_race_result(session_type: str, track: Track) -> RaceResult:
    return RaceResult(
        race_id=f"{track.id}_{session_type}",
        session_type=session_type,  # type: ignore[arg-type]
        track_id=track.id,
        total_laps=0,
        starting_grid=[],
        classification=[],
        lap_log=[],
        decision_prompts=[],
        safety_car_laps=[],
        dnfs=[],
    )


def _simulate_practice(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    correlation_reports: list[PracticeCorrelationReport] | None = None,
) -> PracticeResult:
    rows: list[tuple[float, Driver, int]] = []
    for driver in drivers:
        team = teams[driver.team_id]
        setup_score = _clamp(
            int(
                driver.attributes.technical_feedback * 0.45
                + driver.attributes.adaptability * 0.25
                + team.strategy * 0.2
                + rng.randint(-8, 8)
            )
        )
        lap_time = _single_lap_time(driver, team, track, weather, rng, setup_bonus=setup_score)
        rows.append((lap_time, driver, setup_score))

    rows.sort(key=lambda row: row[0])
    return PracticeResult(
        track_id=track.id,
        weather=weather,
        classification=[
            PracticeClassification(
                position=index,
                driver_id=driver.id,
                lap_time=round(lap_time, 3),
                setup_score=setup_score,
                note=_practice_note(setup_score),
            )
            for index, (lap_time, driver, setup_score) in enumerate(rows, start=1)
        ],
        correlation_reports=correlation_reports or [],
    )


def _simulate_qualifying(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    series: str = "F2",
) -> QualifyingResult:
    """Simulate qualifying session. F1 uses Q1/Q2/Q3 knockout format."""
    if series == "F1":
        return _simulate_f1_qualifying(drivers, teams, track, weather, rng)
    return _simulate_f2_qualifying(drivers, teams, track, weather, rng)


def _simulate_f2_qualifying(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> QualifyingResult:
    """F2 uses a single group qualifying session."""
    rows: list[tuple[float, Driver, str]] = []
    for driver in drivers:
        team = teams[driver.team_id]
        lap_time, note = _qualifying_lap(driver, team, track, weather, rng)
        rows.append((lap_time, driver, note))

    rows.sort(key=lambda row: row[0])
    pole_time = rows[0][0]
    return QualifyingResult(
        track_id=track.id,
        weather=weather,
        classification=[
            QualifyingClassification(
                position=index,
                driver_id=driver.id,
                lap_time=round(lap_time, 3),
                gap_to_pole=round(lap_time - pole_time, 3),
                note=note,
            )
            for index, (lap_time, driver, note) in enumerate(rows, start=1)
        ],
        segments=None,
    )


def _simulate_f1_qualifying(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> QualifyingResult:
    """F1 uses knockout qualifying: Q1 (all), Q2 (top 15), Q3 (top 10)."""
    driver_map = {d.id: d for d in drivers}
    best_times: dict[str, float] = {}
    best_notes: dict[str, str] = {}
    segments: list[QualifyingSegment] = []

    # Q1: All drivers, eliminate bottom 5
    q1_drivers = list(drivers)
    q1_results = _run_qualifying_segment(q1_drivers, teams, track, weather, rng, best_times, best_notes)
    q1_eliminated = [d.driver_id for d in q1_results[15:]]  # P16-P20 eliminated
    q1_stories = _generate_qualifying_stories("Q1", q1_results, driver_map, q1_eliminated, rng)
    segments.append(QualifyingSegment(
        segment="Q1",
        classification=q1_results,
        eliminated=q1_eliminated,
        stories=q1_stories,
    ))

    # Q2: Top 15 from Q1, eliminate bottom 5
    q2_driver_ids = [d.driver_id for d in q1_results[:15]]
    q2_drivers = [driver_map[did] for did in q2_driver_ids]
    q2_results = _run_qualifying_segment(q2_drivers, teams, track, weather, rng, best_times, best_notes)
    q2_eliminated = [d.driver_id for d in q2_results[10:]]  # P11-P15 eliminated
    q2_stories = _generate_qualifying_stories("Q2", q2_results, driver_map, q2_eliminated, rng)
    segments.append(QualifyingSegment(
        segment="Q2",
        classification=q2_results,
        eliminated=q2_eliminated,
        stories=q2_stories,
    ))

    # Q3: Top 10 from Q2, fight for pole
    q3_driver_ids = [d.driver_id for d in q2_results[:10]]
    q3_drivers = [driver_map[did] for did in q3_driver_ids]
    q3_results = _run_qualifying_segment(q3_drivers, teams, track, weather, rng, best_times, best_notes)
    q3_stories = _generate_qualifying_stories("Q3", q3_results, driver_map, [], rng)
    segments.append(QualifyingSegment(
        segment="Q3",
        classification=q3_results,
        eliminated=[],
        stories=q3_stories,
    ))

    # Build final classification
    final_order: list[QualifyingClassification] = []
    pole_time = best_times[q3_results[0].driver_id]

    # Q3 results (P1-P10)
    for entry in q3_results:
        final_order.append(QualifyingClassification(
            position=len(final_order) + 1,
            driver_id=entry.driver_id,
            lap_time=best_times[entry.driver_id],
            gap_to_pole=round(best_times[entry.driver_id] - pole_time, 3),
            note=best_notes.get(entry.driver_id, ""),
        ))

    # Q2 eliminated (P11-P15)
    for driver_id in q2_eliminated:
        final_order.append(QualifyingClassification(
            position=len(final_order) + 1,
            driver_id=driver_id,
            lap_time=best_times[driver_id],
            gap_to_pole=round(best_times[driver_id] - pole_time, 3),
            note=best_notes.get(driver_id, "Out in Q2"),
        ))

    # Q1 eliminated (P16-P20)
    for driver_id in q1_eliminated:
        final_order.append(QualifyingClassification(
            position=len(final_order) + 1,
            driver_id=driver_id,
            lap_time=best_times[driver_id],
            gap_to_pole=round(best_times[driver_id] - pole_time, 3),
            note=best_notes.get(driver_id, "Out in Q1"),
        ))

    return QualifyingResult(
        track_id=track.id,
        weather=weather,
        classification=final_order,
        segments=segments,
    )


def _run_qualifying_segment(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    best_times: dict[str, float],
    best_notes: dict[str, str],
) -> list[QualifyingClassification]:
    """Run a single qualifying segment and update best times."""
    rows: list[tuple[float, Driver, str]] = []
    for driver in drivers:
        team = teams[driver.team_id]
        lap_time, note = _qualifying_lap(driver, team, track, weather, rng)
        # Driver may improve on previous best
        if driver.id not in best_times or lap_time < best_times[driver.id]:
            best_times[driver.id] = lap_time
            best_notes[driver.id] = note
        rows.append((best_times[driver.id], driver, best_notes[driver.id]))

    rows.sort(key=lambda row: row[0])
    pole_time = rows[0][0]
    return [
        QualifyingClassification(
            position=index,
            driver_id=driver.id,
            lap_time=round(lap_time, 3),
            gap_to_pole=round(lap_time - pole_time, 3),
            note=note,
        )
        for index, (lap_time, driver, note) in enumerate(rows, start=1)
    ]


def _qualifying_lap(
    driver: Driver,
    team: Team,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> tuple[float, str]:
    """Simulate a single qualifying lap attempt.

    Consistency strongly affects:
    - Mistake probability (low consistency = more mistakes)
    - Mistake severity (low consistency = bigger time loss)
    - Traffic recovery (high consistency = better at handling disruption)
    """
    # Traffic chance: 8% base
    traffic = rng.random() < 0.08

    # Mistake probability is influenced by consistency, discipline, and composure
    # We want meaningful differentiation:
    # - Low consistency (50): ~12-15% mistake chance
    # - Medium consistency (70): ~6-8% mistake chance
    # - High consistency (90): ~2-4% mistake chance
    consistency = driver.attributes.consistency
    discipline = driver.attributes.discipline

    # Pressure affects mistake chance - low pressure handling = more mistakes
    pressure_factor = 1.0 + (70 - driver.attributes.pressure) * 0.003  # ±10% at extremes

    # Base mistake chance: higher threshold = less likely to make mistake
    # Scale: 0.85 at low stats, 0.98 at high stats
    base_threshold = 0.82 + (consistency * 0.50 + discipline * 0.30 + driver.attributes.composure * 0.20) / 650

    # Elite qualifiers get a bonus
    if driver.attributes.qualifying >= 82 and driver.attributes.pace >= 82:
        base_threshold += 0.04

    # Wet conditions increase mistake chance for everyone
    wet_penalty = 0.06 if weather.condition != "dry" else 0.0

    # Final mistake threshold (higher = less likely to make mistake)
    mistake_threshold = min(0.98, base_threshold * pressure_factor - wet_penalty)
    mistake = rng.random() > mistake_threshold

    lap_time = _single_lap_time(driver, team, track, weather, rng)

    # Traffic penalty: consistent drivers recover better
    if traffic:
        traffic_base = rng.uniform(0.25, 0.85)
        # High consistency reduces traffic impact by up to 30%
        traffic_recovery = max(0.7, 1.0 - (consistency - 60) * 0.0075)
        lap_time += traffic_base * traffic_recovery

    # Mistake penalty: varies more based on consistency
    if mistake:
        # Low consistency: bigger mistakes (up to 1.5s)
        # High consistency: smaller mistakes (0.2-0.7s)
        mistake_severity_factor = 1.0 + (70 - consistency) * 0.015  # 1.3 at 50, 0.7 at 90
        mistake_severity_factor = max(0.6, min(1.5, mistake_severity_factor))
        mistake_base = rng.uniform(0.30, 0.90)
        lap_time += mistake_base * mistake_severity_factor

    return lap_time, _qualifying_note(traffic, mistake)


def _generate_qualifying_stories(
    segment: str,
    results: list[QualifyingClassification],
    driver_map: dict[str, Driver],
    eliminated: list[str],
    rng: random.Random,
) -> list[str]:
    """Generate narrative moments from a qualifying segment."""
    stories: list[str] = []

    if not results:
        return stories

    # Pole/top position story
    top_driver = driver_map.get(results[0].driver_id)
    if top_driver:
        if segment == "Q3":
            stories.append(f"{top_driver.name} takes POLE POSITION with a stunning {results[0].lap_time:.3f}!")
        elif segment == "Q1":
            stories.append(f"{top_driver.name} tops Q1 and looks comfortable heading into Q2.")
        else:
            stories.append(f"{top_driver.name} leads the way in Q2 with a {results[0].lap_time:.3f}.")

    # Close battle story
    if len(results) >= 2:
        gap = results[1].gap_to_pole
        if gap < 0.050:
            second_driver = driver_map.get(results[1].driver_id)
            if second_driver and top_driver:
                stories.append(f"Just {gap:.3f}s separates {top_driver.name} and {second_driver.name}!")

    # Surprise performance
    for entry in results[:5]:
        driver = driver_map.get(entry.driver_id)
        if driver and driver.team_id:
            # Check if driver is punching above their weight
            if entry.position <= 3 and driver.attributes.qualifying < 75:
                stories.append(f"Impressive lap from {driver.name} to put the car in P{entry.position}!")
                break

    # Elimination drama
    for driver_id in eliminated[:2]:
        driver = driver_map.get(driver_id)
        if driver:
            if driver.attributes.qualifying >= 80:
                stories.append(f"Shock exit! {driver.name} knocked out in {segment} after a difficult session.")
            elif rng.random() < 0.3:
                stories.append(f"{driver.name} will start from the back after being eliminated in {segment}.")

    # Random drama
    if rng.random() < 0.15:
        for entry in results:
            if "traffic" in entry.note.lower():
                driver = driver_map.get(entry.driver_id)
                if driver:
                    stories.append(f"{driver.name} furious after being blocked on their flying lap!")
                    break

    return stories[:4]  # Limit to 4 stories per segment


def _simulate_race(
    session_type: str,
    calendar_round: CalendarRound,
    starting_grid: list[str],
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    save: SaveGame,
) -> RaceResult:
    driver_map = {driver.id: driver for driver in drivers}
    total_laps = _total_laps(calendar_round, session_type, track, save)
    runners = []
    for index, driver_id in enumerate(starting_grid):
        driver = driver_map[driver_id]
        team = teams[driver.team_id]
        planned_stops = _planned_stop_count(calendar_round, session_type, team, track, weather, rng)
        runners.append(
            Runner(
                driver=driver,
                team=team,
                cumulative_time=index * rng.uniform(0.14, 0.28),
                tire_compound=_starting_compound(calendar_round, session_type, index + 1, team, track, weather, rng),
                planned_stops=planned_stops,
                planned_pit_laps=_planned_pit_laps(
                    calendar_round,
                    team,
                    total_laps,
                    planned_stops,
                    index + 1,
                    rng,
                ),
                strategy_style=_strategy_style(team),
            )
        )
    points_table = _points_table(calendar_round, session_type)
    lap_log: list[LapSnapshot] = []
    safety_car_laps: list[int] = []
    dnfs: list[str] = []
    decision_prompts: list[DecisionPrompt] = []
    last_prompt_lap = -10
    safety_car_remaining = 0
    safety_car_mode = "none"

    # Strategy event tracking
    strategy_plans: list[RaceStrategyPlan] = []
    pit_stop_events: list[PitStopEvent] = []
    strategy_calls: list[StrategyCall] = []
    safety_car_decisions: list[SafetyCarDecisionContext] = []

    # Track stint data for each driver: {driver_id: [(start_lap, compound, lap_times, tire_wear_start)]}
    stint_tracker: dict[str, list[dict]] = {}

    # Record initial strategy plans and stint starts
    for runner in runners:
        strategy_plans.append(
            RaceStrategyPlan(
                driver_id=runner.driver.id,
                planned_stops=runner.planned_stops,
                planned_pit_laps=runner.planned_pit_laps or [],
                starting_compound=runner.tire_compound,  # type: ignore[arg-type]
                target_compounds=_target_compounds(calendar_round, runner),
                strategy_style=runner.strategy_style,  # type: ignore[arg-type]
            )
        )
        stint_tracker[runner.driver.id] = [{
            "stint_number": 1,
            "start_lap": 1,
            "compound": runner.tire_compound,
            "lap_times": [],
            "tire_wear_start": 0.0,
        }]

    for lap in range(1, total_laps + 1):
        commentary: list[str] = []
        decision_prompt: DecisionPrompt | None = None
        weather = _evolve_weather(weather, track, lap, total_laps, rng, commentary)
        safety_car_trigger: str | None = None
        if safety_car_remaining == 0 and rng.randint(1, 1000) <= max(1, track.safety_car_chance // 24):
            incident = _random_neutralization_incident(runners, track, rng)
            if incident is not None:
                safety_car_mode, retired_driver_id, incident_lines = incident
                safety_car_remaining = rng.randint(1, 2)
                safety_car_trigger = f"incident_{retired_driver_id}"
                if retired_driver_id not in dnfs:
                    dnfs.append(retired_driver_id)
                commentary.extend(incident_lines)

        safety_car = safety_car_remaining > 0
        is_new_safety_car = safety_car and lap not in safety_car_laps
        if safety_car and safety_car_mode == "safety_car":
            safety_car_laps.append(lap)
            _compress_field_for_safety_car(runners, rng)
        elif safety_car:
            safety_car_laps.append(lap)

        # Record safety car decision context when safety car first deploys
        if is_new_safety_car and safety_car_trigger:
            pit_window_open = max(2, int(total_laps * 0.18)) <= lap <= total_laps - 4
            safety_car_decisions.append(
                SafetyCarDecisionContext(
                    id=f"sc_{lap}_{safety_car_mode}",
                    lap=lap,
                    mode=safety_car_mode,  # type: ignore[arg-type]
                    trigger=safety_car_trigger,
                    pit_window_open=pit_window_open,
                    decision="no_call",
                )
            )

        player_runner = _runner_for(runners, "player_driver")
        if player_runner is not None:
            decision_prompt = _maybe_decision_prompt(
                session_type=session_type,
                lap=lap,
                total_laps=total_laps,
                runners=runners,
                player_runner=player_runner,
                safety_car=safety_car,
                weather=weather,
                series=calendar_round.series,
            )
            max_prompts = 4 if session_type == "sprint" else 6
            if decision_prompt is not None and (
                len(decision_prompts) >= max_prompts or lap - last_prompt_lap < 3
            ):
                decision_prompt = None
            if decision_prompt is not None:
                decision_prompts.append(decision_prompt)
                last_prompt_lap = lap
                commentary.append(_default_decision_commentary(decision_prompt))
                _apply_default_decision(player_runner, decision_prompt)

        for runner in runners:
            if runner.status == "dnf":
                continue

            if rng.random() < _retirement_chance(calendar_round, runner, track, lap, total_laps):
                runner.status = "dnf"
                dnfs.append(runner.driver.id)
                if rng.random() < _crash_retirement_share(calendar_round, runner, track, lap, total_laps):
                    crash_neutralization = _crash_neutralization_mode(track, rng)
                    if crash_neutralization is None:
                        commentary.append(f"{runner.driver.name} crashes out but ends up in the gravel trap safely.")
                    elif crash_neutralization == "vsc":
                        commentary.append(f"{runner.driver.name} crashes out at a slow corner.")
                        if not safety_car:
                            safety_car = True
                            safety_car_remaining = max(safety_car_remaining, 1)
                            safety_car_mode = "vsc"
                            if lap not in safety_car_laps:
                                safety_car_laps.append(lap)
                            # Record safety car decision
                            pit_window_open = max(2, int(total_laps * 0.18)) <= lap <= total_laps - 4
                            safety_car_decisions.append(
                                SafetyCarDecisionContext(
                                    id=f"sc_{lap}_vsc_crash",
                                    lap=lap,
                                    mode="vsc",
                                    trigger=f"crash_{runner.driver.id}",
                                    pit_window_open=pit_window_open,
                                    decision="no_call",
                                )
                            )
                        commentary.append("Virtual Safety Car deployed for debris cleanup.")
                    else:
                        commentary.append(f"{runner.driver.name} crashes out and is stopped near the racing line.")
                        if not safety_car:
                            safety_car = True
                            safety_car_remaining = max(safety_car_remaining, rng.randint(1, 2))
                            safety_car_mode = "safety_car"
                            if lap not in safety_car_laps:
                                safety_car_laps.append(lap)
                            # Record safety car decision
                            pit_window_open = max(2, int(total_laps * 0.18)) <= lap <= total_laps - 4
                            safety_car_decisions.append(
                                SafetyCarDecisionContext(
                                    id=f"sc_{lap}_sc_crash",
                                    lap=lap,
                                    mode="safety_car",
                                    trigger=f"crash_{runner.driver.id}",
                                    pit_window_open=pit_window_open,
                                    decision="no_call",
                                )
                            )
                        commentary.append("Safety Car deployed while marshals recover the car.")
                else:
                    commentary.append(f"{runner.driver.name} is out with a mechanical issue.")
                    recovery_mode = _stranded_recovery_mode(runner, track, rng)
                    if recovery_mode is not None and not safety_car:
                        safety_car = True
                        safety_car_remaining = max(safety_car_remaining, rng.randint(1, 2))
                        safety_car_mode = recovery_mode
                        if lap not in safety_car_laps:
                            safety_car_laps.append(lap)
                        # Record safety car decision
                        pit_window_open = max(2, int(total_laps * 0.18)) <= lap <= total_laps - 4
                        safety_car_decisions.append(
                            SafetyCarDecisionContext(
                                id=f"sc_{lap}_{recovery_mode}_mechanical",
                                lap=lap,
                                mode=recovery_mode,  # type: ignore[arg-type]
                                trigger=f"mechanical_{runner.driver.id}",
                                pit_window_open=pit_window_open,
                                decision="no_call",
                            )
                        )
                        if recovery_mode == "safety_car":
                            commentary.append("Safety Car deployed because the car is stranded near the racing line.")
                        else:
                            commentary.append("Virtual Safety Car deployed while marshals recover the stopped car.")
                continue

            runner.previous_lap_time = runner.last_lap_time
            lap_time = _race_lap_time(runner, track, weather, rng, safety_car)
            if _driver_mistake(runner, track, weather, rng, lap, total_laps):
                mistake_loss = rng.uniform(0.7, 2.4)
                lap_time += mistake_loss
                if runner.driver.id == "player_driver":
                    commentary.append(f"You lose {mistake_loss:.1f}s with a small moment in low grip.")
            runner.cumulative_time += lap_time
            runner.fastest_lap = min(runner.fastest_lap, lap_time)
            runner.last_lap_time = lap_time
            runner.tire_age += 1
            runner.tire_wear = min(
                100,
                runner.tire_wear + _tire_wear_increment(runner, track, weather, session_type),
            )
            runner.component_wear = min(100, runner.component_wear + _component_wear_increment(runner, track, weather, session_type))
            if runner.driver.id == "player_driver" and runner.component_wear > 76 and lap % 4 == 0:
                commentary.append(f"Engineer: power unit temperatures are high, component wear at {runner.component_wear:.0f}%.")

            # Record lap time for stint tracking
            if runner.driver.id in stint_tracker and stint_tracker[runner.driver.id]:
                stint_tracker[runner.driver.id][-1]["lap_times"].append(lap_time)

            if _should_pit(calendar_round, session_type, runner, lap, total_laps, track, safety_car, runners):
                old_compound = runner.tire_compound
                old_tire_wear = runner.tire_wear
                position_before = _position_of(runners, runner.driver.id) or 0
                pit_loss = _pit_loss(calendar_round, rng, safety_car)
                runner.cumulative_time += pit_loss
                runner.last_lap_time = (runner.last_lap_time or lap_time) + pit_loss
                runner.pit_stops += 1
                runner.tire_age = 0
                runner.tire_wear = 0
                new_compound = _next_compound(calendar_round, runner)
                runner.tire_compound = new_compound

                # Finalize current stint and start new one
                if runner.driver.id in stint_tracker and stint_tracker[runner.driver.id]:
                    current_stint = stint_tracker[runner.driver.id][-1]
                    current_stint["end_lap"] = lap
                    current_stint["tire_wear_end"] = old_tire_wear

                    # Start new stint
                    stint_tracker[runner.driver.id].append({
                        "stint_number": len(stint_tracker[runner.driver.id]) + 1,
                        "start_lap": lap + 1,
                        "compound": new_compound,
                        "lap_times": [],
                        "tire_wear_start": 0.0,
                    })

                # Determine pit stop reason
                pit_reason = _determine_pit_reason(runner, lap, total_laps, safety_car, old_tire_wear)

                # Record pit stop event
                pit_stop_events.append(
                    PitStopEvent(
                        id=f"{runner.driver.id}_pit_{runner.pit_stops}",
                        driver_id=runner.driver.id,
                        lap=lap,
                        compound_in=old_compound,  # type: ignore[arg-type]
                        compound_out=new_compound,  # type: ignore[arg-type]
                        pit_loss=round(pit_loss, 3),
                        under_safety_car=safety_car,
                        reason=pit_reason,
                    )
                )

                if runner.driver.id == "player_driver":
                    commentary.append(f"You pit for {runner.tire_compound} tyres and rejoin in traffic.")

        runners.sort(key=lambda runner: (runner.status == "dnf", runner.cumulative_time))
        if not safety_car:
            _apply_ai_racecraft(runners, track, rng, commentary)
            _apply_green_flag_dirty_air(runners)
            runners.sort(key=lambda runner: (runner.status == "dnf", runner.cumulative_time))
        if not safety_car and lap in {1, total_laps // 2, total_laps}:
            player_position = _position_of(runners, "player_driver")
            if player_position is not None:
                commentary.append(f"You cross lap {lap} in P{player_position}.")

        lap_log.append(_lap_snapshot(lap, runners, commentary, safety_car, weather, decision_prompt))
        safety_car_remaining = max(0, safety_car_remaining - 1)
        if safety_car_remaining == 0:
            safety_car_mode = "none"

    classified = [runner for runner in runners if runner.status == "running"] + [
        runner for runner in runners if runner.status == "dnf"
    ]
    winner_time = next((runner.cumulative_time for runner in classified if runner.status == "running"), classified[0].cumulative_time)
    fastest_lap_bonus_driver = _fastest_lap_bonus_driver(calendar_round, classified)

    # Finalize last stint for each runner and generate stint summaries
    stint_summaries: list[StintSummary] = []
    for runner in runners:
        if runner.driver.id in stint_tracker:
            stints = stint_tracker[runner.driver.id]
            # Finalize the last stint
            if stints and "end_lap" not in stints[-1]:
                stints[-1]["end_lap"] = total_laps
                stints[-1]["tire_wear_end"] = runner.tire_wear

            # Generate stint summaries
            for stint_data in stints:
                lap_times = stint_data.get("lap_times", [])
                avg_lap = round(sum(lap_times) / len(lap_times), 3) if lap_times else None
                stint_summaries.append(
                    StintSummary(
                        driver_id=runner.driver.id,
                        stint_number=stint_data["stint_number"],
                        start_lap=stint_data["start_lap"],
                        end_lap=stint_data.get("end_lap", total_laps),
                        compound=stint_data["compound"],  # type: ignore[arg-type]
                        average_lap_time=avg_lap,
                        tire_wear_start=stint_data.get("tire_wear_start", 0.0),
                        tire_wear_end=stint_data.get("tire_wear_end"),
                    )
                )

    return RaceResult(
        race_id=f"{track.id}_{session_type}",
        session_type=session_type,  # type: ignore[arg-type]
        track_id=track.id,
        total_laps=total_laps,
        starting_grid=starting_grid,
        classification=[
            RaceClassification(
                position=index,
                driver_id=runner.driver.id,
                status=runner.status,  # type: ignore[arg-type]
                total_time=round(runner.cumulative_time, 3),
                gap_to_winner=round(max(0, runner.cumulative_time - winner_time), 3),
                points=(
                    points_table.get(index, 0) + (1 if runner.driver.id == fastest_lap_bonus_driver else 0)
                    if runner.status == "running"
                    else 0
                ),
                pit_stops=runner.pit_stops,
                fastest_lap=round(runner.fastest_lap, 3),
            )
            for index, runner in enumerate(classified, start=1)
        ],
        lap_log=lap_log,
        decision_prompts=decision_prompts,
        safety_car_laps=safety_car_laps,
        dnfs=dnfs,
        strategy_plans=strategy_plans,
        pit_stop_events=pit_stop_events,
        stint_summaries=stint_summaries,
        strategy_calls=strategy_calls,
        safety_car_decisions=safety_car_decisions,
    )


def _fastest_lap_bonus_driver(calendar_round: CalendarRound, classified: list[Runner]) -> str | None:
    if calendar_round.series != "F2":
        return None

    eligible = [
        runner
        for index, runner in enumerate(classified, start=1)
        if index <= 10 and runner.status == "running"
    ]
    if not eligible:
        return None

    return min(eligible, key=lambda runner: runner.fastest_lap).driver.id


def _should_pit(
    calendar_round: CalendarRound,
    session_type: str,
    runner: Runner,
    lap: int,
    total_laps: int,
    track: Track,
    safety_car: bool,
    runners: list[Runner] | None = None,
) -> bool:
    if session_type != "feature" or runner.status == "dnf":
        return False
    if lap <= runner.pit_block_until_lap:
        return False

    if calendar_round.series == "F2":
        if runner.pit_stops >= 1:
            return False
        pit_window_open = lap >= max(2, int(total_laps * 0.35))
        pit_deadline = lap >= _planned_deadline_lap(runner, total_laps, total_laps - 5)
        strategy_triggered = lap > total_laps // 2 and runner.tire_wear > _pit_wear_threshold(runner, 28)
        return pit_window_open and (
            _plan_says_pit(runner, lap, total_laps)
            or strategy_triggered
            or pit_deadline
            or _safety_car_pit_window(safety_car, lap, total_laps)
        )

    target_stops = max(1, runner.planned_stops or _target_f1_stops(track))
    if runner.pit_stops >= target_stops:
        return False

    progress = lap / total_laps
    safety_car_discount = _safety_car_pit_window(safety_car, lap, total_laps)
    plan_triggered = _plan_says_pit(runner, lap, total_laps)
    traffic_triggered = _traffic_pit_trigger(runner, runners)
    if target_stops >= 2:
        if runner.pit_stops == 0:
            window_open = progress >= 0.22
            deadline = lap >= _planned_deadline_lap(runner, total_laps, int(total_laps * 0.42))
            return window_open and (
                plan_triggered
                or runner.tire_wear > _pit_wear_threshold(runner, 34)
                or traffic_triggered
                or deadline
                or safety_car_discount
            )
        window_open = progress >= 0.56
        deadline = lap >= _planned_deadline_lap(runner, total_laps, int(total_laps * 0.78))
        return window_open and (
            plan_triggered
            or runner.tire_wear > _pit_wear_threshold(runner, 36)
            or traffic_triggered
            or deadline
            or safety_car_discount
        )

    window_open = progress >= 0.32
    deadline = lap >= _planned_deadline_lap(runner, total_laps, int(total_laps * 0.72))
    return window_open and (
        plan_triggered
        or runner.tire_wear > _pit_wear_threshold(runner, 38)
        or traffic_triggered
        or deadline
        or safety_car_discount
    )


def _target_f1_stops(track: Track) -> int:
    return 2 if track.tire_deg >= 64 else 1


def _pit_loss(calendar_round: CalendarRound, rng: random.Random, safety_car: bool) -> float:
    base_loss = 20.5 if calendar_round.series == "F1" else 22
    if safety_car:
        base_loss *= 0.62
    return base_loss + rng.uniform(-0.8, 1.8)


def _determine_pit_reason(
    runner: Runner, lap: int, total_laps: int, safety_car: bool, tire_wear: float
) -> str:
    """Determine the reason for a pit stop."""
    if safety_car:
        return "safety_car_opportunity"
    if tire_wear >= 75:
        return "tire_degradation"
    if runner.planned_pit_laps and lap in runner.planned_pit_laps:
        return "planned_stop"
    if lap >= total_laps - 3:
        return "late_race_gamble"
    if tire_wear >= 55:
        return "tire_wear_concern"
    return "strategic"


def _next_compound(calendar_round: CalendarRound, runner: Runner) -> str:
    if calendar_round.series == "F2":
        return "hard"
    if runner.planned_stops >= 2:
        return "hard" if runner.pit_stops == 1 else "medium"
    if runner.tire_compound == "hard":
        return "medium"
    return "hard"


def _starting_compound(
    calendar_round: CalendarRound,
    session_type: str,
    grid_position: int,
    team: Team,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> str:
    if weather.condition == "wet":
        return "wet"
    if weather.condition == "damp":
        return "inter"
    if session_type == "sprint":
        return "soft" if rng.random() < 0.78 else "medium"
    if calendar_round.series == "F2":
        return "medium" if rng.random() < 0.86 else "soft"

    style = _strategy_style(team)
    if style == "long_run" or grid_position > 14:
        return "hard" if rng.random() < 0.58 else "medium"
    if style == "aggressive" or grid_position > 10:
        return "soft" if rng.random() < 0.42 else "medium"
    if track.tire_deg >= 68:
        return "medium" if rng.random() < 0.74 else "hard"
    return "medium" if rng.random() < 0.62 else "soft"


def _target_compounds(calendar_round: CalendarRound, runner: Runner) -> list[str]:
    """Determine target compounds for race strategy based on planned stops."""
    starting = runner.tire_compound
    stops = runner.planned_stops

    if stops == 0:
        return [starting]

    # Common strategies based on starting compound
    if starting == "soft":
        if stops == 1:
            return ["soft", "medium"]
        return ["soft", "hard", "medium"]
    elif starting == "medium":
        if stops == 1:
            return ["medium", "hard"]
        return ["medium", "hard", "soft"]
    elif starting == "hard":
        if stops == 1:
            return ["hard", "medium"]
        return ["hard", "medium", "soft"]
    else:
        # Wet compounds
        return [starting] * (stops + 1)


def _planned_stop_count(
    calendar_round: CalendarRound,
    session_type: str,
    team: Team,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> int:
    if session_type == "sprint" or weather.condition != "dry":
        return 0
    if calendar_round.series == "F2":
        return 1

    base = _target_f1_stops(track)
    if _strategy_style(team) == "aggressive" and track.tire_deg >= 58 and rng.random() < 0.35:
        return min(2, base + 1)
    if _strategy_style(team) == "long_run" and base == 2 and rng.random() < 0.22:
        return 1
    return base


def _planned_pit_laps(
    calendar_round: CalendarRound,
    team: Team,
    total_laps: int,
    stops: int,
    grid_position: int,
    rng: random.Random,
) -> list[int]:
    if stops == 0:
        return []

    style = _strategy_style(team)
    offset = {"aggressive": -2, "balanced": 0, "long_run": 2}.get(style, 0)
    traffic_offset = -1 if grid_position in {9, 10, 11, 12, 13, 14} else 0
    backmarker_offset = 1 if grid_position > 16 else 0
    jitter = lambda: rng.randint(-3, 3)
    if stops >= 2:
        return [
            max(2, int(total_laps * 0.31) + offset + traffic_offset + backmarker_offset + jitter()),
            max(3, int(total_laps * 0.64) + offset + backmarker_offset + jitter()),
        ]
    return [
        max(
            2,
            int(total_laps * (0.43 if calendar_round.series == "F2" else 0.52))
            + offset
            + traffic_offset
            + backmarker_offset
            + jitter(),
        )
    ]


def _strategy_style(team: Team) -> str:
    profile = team.effective_car_profile()
    strategy = profile.strategy_team
    if strategy >= 84:
        return "balanced"
    if strategy <= 66:
        return "aggressive"
    if profile.tire_wear >= 82 and profile.overall_performance < 82:
        return "long_run"
    if profile.overall_performance >= 84:
        return "aggressive"
    return "balanced"


def _plan_says_pit(runner: Runner, lap: int, total_laps: int) -> bool:
    pit_laps = runner.planned_pit_laps or []
    if runner.pit_stops >= len(pit_laps):
        return False
    target_lap = pit_laps[runner.pit_stops]
    tolerance = 1 if runner.team.strategy >= 76 else 2
    return target_lap - tolerance <= lap <= min(total_laps - 2, target_lap + tolerance)


def _planned_deadline_lap(runner: Runner, total_laps: int, fallback: int) -> int:
    pit_laps = runner.planned_pit_laps or []
    if runner.pit_stops >= len(pit_laps):
        return fallback
    return min(total_laps - 2, max(fallback, pit_laps[runner.pit_stops] + 4))


def _traffic_pit_trigger(runner: Runner, runners: list[Runner] | None) -> bool:
    if not runners or runner.strategy_style == "long_run":
        return False
    ordered = sorted([entry for entry in runners if entry.status == "running"], key=lambda entry: entry.cumulative_time)
    position = next((idx for idx, entry in enumerate(ordered) if entry.driver.id == runner.driver.id), None)
    if position is None or position == 0:
        return False
    gap_ahead = runner.cumulative_time - ordered[position - 1].cumulative_time
    gap_behind = (
        ordered[position + 1].cumulative_time - runner.cumulative_time
        if position + 1 < len(ordered)
        else 99
    )
    pace_edge = _race_pace_score(runner) - _race_pace_score(ordered[position - 1])
    stuck_in_dirty_air = gap_ahead < 1.15 and pace_edge >= -0.5 and runner.tire_wear > 22
    vulnerable_to_undercut = gap_behind < 1.4 and runner.tire_wear > 30
    return runner.team.strategy >= 70 and (stuck_in_dirty_air or vulnerable_to_undercut)


def _safety_car_pit_window(safety_car: bool, lap: int, total_laps: int) -> bool:
    return safety_car and max(2, int(total_laps * 0.18)) <= lap <= total_laps - 4


def _pit_wear_threshold(runner: Runner, base_threshold: float) -> float:
    profile = runner.team.effective_car_profile()
    return base_threshold + (profile.strategy_team - 75) * 0.08 + (profile.tire_wear - 75) * 0.05


def _retirement_chance(
    calendar_round: CalendarRound,
    runner: Runner,
    track: Track,
    lap: int,
    total_laps: int,
) -> float:
    profile = runner.team.effective_car_profile()
    reliability_score = (
        profile.reliability * 0.62
        + profile.cooling * 0.10
        + runner.driver.attributes.awareness * 0.16
        + runner.driver.attributes.discipline * 0.12
    )
    reliability_pressure = max(0, 82 - reliability_score) / 26000
    series_floor = 0.00075 if calendar_round.series == "F1" else 0.00135
    track_pressure = track.safety_car_chance / (90000 if calendar_round.series == "F1" else 65000)
    lap_pressure = 0.00035 if lap == 1 else 0
    late_wear_pressure = max(0, runner.tire_wear - 72) / 90000
    component_pressure = max(0, runner.component_wear - 68) / 26000
    sprint_multiplier = 0.72 if total_laps <= 15 else 1
    return (series_floor + reliability_pressure + track_pressure + lap_pressure + late_wear_pressure + component_pressure) * sprint_multiplier


def _crash_retirement_share(
    calendar_round: CalendarRound,
    runner: Runner,
    track: Track,
    lap: int,
    total_laps: int,
) -> float:
    base = 0.46 if calendar_round.series == "F1" else 0.58
    aggression_factor = (runner.driver.attributes.aggression - runner.driver.attributes.discipline) / 180
    circuit_factor = (0.08 if track.street_circuit else 0) + track.safety_car_chance / 1000
    lap_factor = 0.12 if lap == 1 else (-0.08 if lap > total_laps * 0.65 else 0)
    return max(0.22, min(0.78, base + aggression_factor + circuit_factor + lap_factor))


def _random_neutralization_incident(
    runners: list[Runner],
    track: Track,
    rng: random.Random,
) -> tuple[str, str, list[str]] | None:
    running = [runner for runner in runners if runner.status == "running"]
    if len(running) <= 3:
        return None

    weights = [
        max(1, 92 - runner.team.reliability)
        + max(0, runner.driver.attributes.aggression - runner.driver.attributes.discipline) * 0.35
        + runner.driver.hidden.crash_proneness / 8
        for runner in running
    ]
    runner = rng.choices(running, weights=weights, k=1)[0]
    runner.status = "dnf"

    crash = rng.random() < min(0.72, 0.32 + track.safety_car_chance / 180 + (0.1 if track.street_circuit else 0))
    full_safety_car = crash or track.street_circuit or rng.random() < 0.42
    mode = "safety_car" if full_safety_car else "vsc"

    if crash:
        return (
            mode,
            runner.driver.id,
            [
                f"{runner.driver.name} crashes and stops in a dangerous position.",
                "Safety Car deployed while marshals recover the car." if mode == "safety_car" else "Virtual Safety Car deployed for recovery work.",
            ],
        )

    return (
        mode,
        runner.driver.id,
        [
            f"{runner.driver.name} slows with a mechanical failure and parks near an escape road.",
            "Safety Car deployed because the stopped car is exposed." if mode == "safety_car" else "Virtual Safety Car deployed while the car is cleared.",
        ],
    )


def _stranded_recovery_mode(runner: Runner, track: Track, rng: random.Random) -> str | None:
    exposure = 0.04 + track.safety_car_chance / 720
    if track.street_circuit:
        exposure += 0.06
    if runner.component_wear > 82:
        exposure += 0.05
    if rng.random() > min(0.24, exposure):
        return None
    return "safety_car" if rng.random() < (0.5 if track.street_circuit else 0.28) else "vsc"


def _crash_neutralization_mode(track: Track, rng: random.Random) -> str | None:
    """Determine if a crash needs neutralization and what type.

    In real F1, not every crash needs a safety car:
    - Some end in gravel traps or safe runoff (no neutralization)
    - Some need VSC for quick debris cleanup
    - Only serious crashes near the racing line need full SC

    Street circuits have fewer runoff areas so more neutralizations.
    """
    # Base chance of needing any neutralization
    if track.street_circuit:
        # Street circuits: ~65% need neutralization (less runoff)
        needs_neutralization = rng.random() < 0.65
    else:
        # Permanent circuits: ~40% need neutralization (more gravel/runoff)
        needs_neutralization = rng.random() < 0.40

    if not needs_neutralization:
        return None

    # Of crashes needing neutralization, what type?
    if track.street_circuit:
        # Street circuits: 55% full SC, 45% VSC
        return "safety_car" if rng.random() < 0.55 else "vsc"
    else:
        # Permanent circuits: 35% full SC, 65% VSC
        return "safety_car" if rng.random() < 0.35 else "vsc"


def _single_lap_time(
    driver: Driver,
    team: Team,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    setup_bonus: int = 70,
) -> float:
    wet_skill = driver.attributes.wet_weather if weather.condition != "dry" else driver.attributes.pace
    driver_score = driver.attributes.qualifying * 0.38 + driver.attributes.pace * 0.34 + wet_skill * 0.12 + driver.attributes.adaptability * 0.1
    car_score = qualifying_car_score(team, track, weather)
    setup_score = setup_confidence_score(team, driver.attributes.confidence, setup_bonus)
    context_score = max(45, min(100, 100 - weather.rain_intensity * 0.42 + max(0, weather.track_grip - 70) * 0.18))
    composite = performance_composite(
        series=team.series,
        car_score=car_score,
        driver_score=round(driver_score),
        setup_score=setup_score,
        context_score=round(context_score),
    )
    weather_penalty = weather.rain_intensity * (105 - driver.attributes.wet_weather) / 900
    lap_factor = 0.085 if team.series == "F1" else 0.065

    # Randomness is scaled by consistency attribute
    # High consistency (90+) = tighter window, more predictable
    # Low consistency (50) = wider window, more variance
    # Base range: F1 ±0.22s, F2 ±0.30s at consistency 70
    # At consistency 90: range shrinks by ~35% (more reliable)
    # At consistency 50: range grows by ~50% (more volatile)
    consistency = driver.attributes.consistency
    consistency_factor = 1.0 + (70 - consistency) * 0.025  # 1.5 at 50, 0.5 at 90, 1.0 at 70
    consistency_factor = max(0.5, min(1.6, consistency_factor))  # Clamp to reasonable range

    base_randomness = 0.22 if team.series == "F1" else 0.30
    randomness_range = base_randomness * consistency_factor

    # Asymmetric randomness: inconsistent drivers more likely to lose time than gain
    # Consistent drivers have symmetric variance around their true pace
    if consistency < 65:
        # Low consistency: biased toward slower laps (negative surprise rare)
        randomness = rng.uniform(-randomness_range * 0.6, randomness_range)
    elif consistency >= 85:
        # High consistency: symmetric, small variance
        randomness = rng.uniform(-randomness_range, randomness_range)
    else:
        # Medium consistency: slight bias toward slower
        randomness = rng.uniform(-randomness_range * 0.85, randomness_range)

    return _series_lap_time_base(track, team.series) + (90 - composite) * lap_factor + weather_penalty + randomness


def _race_lap_time(
    runner: Runner,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    safety_car: bool,
) -> float:
    if safety_car:
        return _series_lap_time_base(track, runner.team.series) * 1.32 + rng.uniform(-0.4, 0.4)

    driver = runner.driver
    team = runner.team
    wet_skill = driver.attributes.wet_weather if weather.condition != "dry" else driver.attributes.pace
    race_score = driver.attributes.pace * 0.28 + driver.attributes.racecraft * 0.24 + driver.attributes.consistency * 0.18 + driver.attributes.tire_management * 0.12 + wet_skill * 0.1
    car_score = race_car_score(team, track, weather)
    setup_score = setup_confidence_score(team, driver.attributes.confidence)
    context_score = max(45, min(100, weather.track_grip + (6 if weather.condition == "dry" else -weather.rain_intensity * 0.18)))
    composite = performance_composite(
        series=team.series,
        car_score=car_score,
        driver_score=round(race_score),
        setup_score=setup_score,
        context_score=round(context_score),
    )
    tire_penalty = runner.tire_wear * (104 - driver.attributes.tire_management) / 2200
    weather_penalty = weather.rain_intensity * (105 - driver.attributes.wet_weather) / 1000
    grip_penalty = max(0, 74 - weather.track_grip) / 70
    component_penalty = max(0, runner.component_wear - 72) / 115
    compound_delta = _compound_pace_delta(runner.tire_compound, weather)
    age_penalty = _tire_age_penalty(runner)
    return (
        _series_lap_time_base(track, team.series)
        + (90 - composite) * (0.088 if team.series == "F1" else 0.066)
        + _race_trim_penalty(track, team.series)
        + tire_penalty
        + age_penalty
        + weather_penalty
        + grip_penalty
        + component_penalty
        + compound_delta
        + rng.uniform(-0.12, 0.14)
    )


def _series_lap_time_base(track: Track, series: str) -> float:
    if series == "F2":
        return track.base_lap_time + max(9.0, track.base_lap_time * 0.14)
    return track.base_lap_time


def _race_trim_penalty(track: Track, series: str) -> float:
    if series == "F2":
        return max(2.4, track.base_lap_time * 0.035)
    return max(2.2, track.base_lap_time * 0.032)


def _compound_pace_delta(compound: str, weather: WeatherState) -> float:
    if weather.condition == "wet":
        return {"wet": -0.9, "inter": 0.65, "soft": 4.8, "medium": 5.2, "hard": 5.6}.get(compound, 5.2)
    if weather.condition == "damp":
        return {"inter": -0.55, "wet": 1.1, "soft": 0.45, "medium": 0.65, "hard": 0.85}.get(compound, 0.65)
    return {"soft": -0.38, "medium": 0.0, "hard": 0.34, "inter": 3.2, "wet": 5.5}.get(compound, 0.0)


def _tire_wear_increment(runner: Runner, track: Track, weather: WeatherState, session_type: str) -> float:
    session_divisor = 22 if session_type == "sprint" else 34
    compound_multiplier = {
        "soft": 1.28,
        "medium": 1.0,
        "hard": 0.78,
        "inter": 1.08 if weather.condition != "dry" else 1.7,
        "wet": 1.0 if weather.condition == "wet" else 1.9,
    }.get(runner.tire_compound, 1.0)
    management_factor = 1 - max(-0.16, min(0.18, (runner.driver.attributes.tire_management - 75) / 220))
    car_factor = 1 - max(-0.12, min(0.15, (runner.team.effective_car_profile().tire_wear - 75) / 240))
    grip_factor = 1 + max(0, 68 - weather.track_grip) / 180
    return track.tire_deg / session_divisor * compound_multiplier * management_factor * car_factor * grip_factor


def _component_wear_increment(runner: Runner, track: Track, weather: WeatherState, session_type: str) -> float:
    session_factor = 0.52 if session_type == "sprint" else 0.42
    profile = runner.team.effective_car_profile()
    reliability_factor = 1 + max(0, 84 - profile.reliability) / 65
    cooling_factor = 1 + max(0, track.tire_deg - profile.cooling) / 220
    heat_factor = 1 + max(0, weather.track_temp - 36) / 80
    wet_factor = 0.92 if weather.condition != "dry" else 1
    push_factor = 1 + max(0, runner.driver.attributes.aggression - runner.driver.attributes.discipline) / 180
    return session_factor * reliability_factor * cooling_factor * heat_factor * wet_factor * push_factor


def _driver_mistake(runner: Runner, track: Track, weather: WeatherState, rng: random.Random, lap: int, total_laps: int) -> bool:
    if weather.track_grip >= 74 and runner.tire_wear < 62:
        return False
    control = runner.driver.attributes.consistency * 0.45 + runner.driver.attributes.discipline * 0.25 + runner.driver.attributes.wet_weather * 0.3
    grip_pressure = max(0, 76 - weather.track_grip) / 240
    tire_pressure = max(0, runner.tire_wear - 58) / 520
    late_pressure = 0.0015 if lap > total_laps * 0.8 else 0
    crash_prone = runner.driver.hidden.crash_proneness / 35000
    return rng.random() < max(0.0008, grip_pressure + tire_pressure + late_pressure + crash_prone - control / 26000)


def _tire_age_penalty(runner: Runner) -> float:
    age_start = {"soft": 8, "medium": 11, "hard": 15, "inter": 9, "wet": 8}.get(runner.tire_compound, 11)
    if runner.tire_age <= age_start:
        return 0
    compound_ramp = {"soft": 0.045, "medium": 0.035, "hard": 0.026, "inter": 0.04, "wet": 0.045}.get(runner.tire_compound, 0.035)
    return min(1.8, (runner.tire_age - age_start) * compound_ramp)


def _compress_field_for_safety_car(runners: list[Runner], rng: random.Random) -> None:
    running = [runner for runner in runners if runner.status == "running"]
    if not running:
        return

    leader_time = min(runner.cumulative_time for runner in running)
    ordered = sorted(running, key=lambda runner: runner.cumulative_time)
    for index, runner in enumerate(ordered):
        max_gap = index * rng.uniform(0.22, 0.38)
        runner.cumulative_time = min(runner.cumulative_time, leader_time + max_gap)


def _apply_green_flag_dirty_air(runners: list[Runner]) -> None:
    running = sorted(
        [runner for runner in runners if runner.status == "running"],
        key=lambda runner: runner.cumulative_time,
    )

    for index, runner in enumerate(running[1:], start=1):
        car_ahead = running[index - 1]
        gap = runner.cumulative_time - car_ahead.cumulative_time
        if gap >= 1.2:
            continue

        runner_score = _race_pace_score(runner)
        ahead_score = _race_pace_score(car_ahead)
        if runner_score <= ahead_score + 1.5:
            runner.cumulative_time += min(0.18, (1.2 - gap) * 0.12)


def _apply_ai_racecraft(runners: list[Runner], track: Track, rng: random.Random, commentary: list[str]) -> None:
    running = sorted(
        [runner for runner in runners if runner.status == "running"],
        key=lambda runner: runner.cumulative_time,
    )
    used_driver_ids: set[str] = set()
    moves_reported = 0

    for index in range(1, len(running)):
        attacker = running[index]
        defender = running[index - 1]
        if attacker.driver.id in used_driver_ids or defender.driver.id in used_driver_ids:
            continue

        gap = attacker.cumulative_time - defender.cumulative_time
        gap_limit = _overtake_gap_limit(track)
        if gap <= 0 or gap > gap_limit:
            continue

        # Get car performance scores
        attacker_car_score = team_track_score(attacker.team, track)
        defender_car_score = team_track_score(defender.team, track)

        # Car performance delta bonus: faster car attacking slower car gets a significant advantage
        # This simulates real F1 where a Red Bull starting P15 easily passes midfield cars
        # Range: -8 (much slower car attacking) to +15 (much faster car attacking)
        car_delta = attacker_car_score - defender_car_score
        car_delta_bonus = max(-8, min(15, car_delta * 0.45))

        tire_delta = defender.tire_wear - attacker.tire_wear
        tire_attack_bonus = max(-8, min(12, tire_delta * 0.28))

        # Attack score now weights car performance more heavily
        attack_score = (
            attacker.driver.attributes.racecraft * 0.28
            + attacker.driver.attributes.aggression * 0.20
            + attacker.driver.attributes.pace * 0.14
            + attacker_car_score * 0.24  # Increased car weight from 0.18
            + car_delta_bonus           # NEW: bonus for faster car
            + tire_attack_bonus
            + rng.uniform(-7, 7)
        )

        # Defense score - car matters for defending too
        defense_score = (
            defender.driver.attributes.racecraft * 0.26
            + defender.driver.attributes.awareness * 0.20
            + defender.driver.attributes.discipline * 0.16
            + defender_car_score * 0.22  # Increased car weight from 0.18
            + max(-6, min(8, -tire_delta * 0.18))
            + rng.uniform(-6, 7)
        )

        pass_threshold = _overtake_score_threshold(track, tire_delta)
        pass_gap = min(0.70, gap_limit * 0.85)  # Slightly easier to complete pass

        if attack_score > defense_score + pass_threshold and gap < pass_gap:
            # Pass completed - faster cars gain more time
            time_gained = rng.uniform(0.015, 0.07)
            if car_delta > 8:  # Much faster car gets clean pass
                time_gained = rng.uniform(0.04, 0.12)
            attacker.cumulative_time = defender.cumulative_time - time_gained
            used_driver_ids.update({attacker.driver.id, defender.driver.id})
            if moves_reported < 2:
                commentary.append(f"{attacker.driver.name} completes a move on {defender.driver.name}.")
                moves_reported += 1
        elif defense_score > attack_score + 4 and gap < 0.8:
            attacker.cumulative_time += rng.uniform(0.04, 0.16)
            used_driver_ids.update({attacker.driver.id, defender.driver.id})
            if moves_reported < 2:
                commentary.append(f"{defender.driver.name} defends from {attacker.driver.name}.")
                moves_reported += 1


def _overtake_gap_limit(track: Track) -> float:
    # Gap limit determines how close you need to be to attempt an overtake
    return max(0.30, min(1.05, 1.0 - track.overtaking_difficulty / 138 + track.drs_strength / 235))


def _overtake_score_threshold(track: Track, tire_delta: float) -> float:
    # Base threshold tuned for 30-35 overtakes per race average
    circuit_barrier = 4.2 + track.overtaking_difficulty * 0.21 - track.drs_strength * 0.056
    if tire_delta > 18:
        circuit_barrier -= min(4.5, (tire_delta - 18) * 0.22)
    return max(4.5, circuit_barrier)


def _race_pace_score(runner: Runner) -> float:
    driver = runner.driver
    return (
        driver.attributes.pace * 0.32
        + driver.attributes.racecraft * 0.22
        + driver.attributes.consistency * 0.16
        + driver.attributes.tire_management * 0.1
        + runner.team.effective_car_profile().overall_performance * 0.2
    )


def _lap_snapshot(
    lap: int,
    runners: list[Runner],
    commentary: list[str],
    safety_car: bool,
    weather: WeatherState,
    decision_prompt: DecisionPrompt | None,
) -> LapSnapshot:
    leader_time = next((runner.cumulative_time for runner in runners if runner.status == "running"), runners[0].cumulative_time)
    previous_time = leader_time
    running_order: list[RunningOrderEntry] = []
    for index, runner in enumerate(runners, start=1):
        gap_to_leader = max(0, runner.cumulative_time - leader_time)
        gap_to_car_ahead = 0 if index == 1 else max(0, runner.cumulative_time - previous_time)
        running_order.append(
            RunningOrderEntry(
                position=index,
                driver_id=runner.driver.id,
                gap_to_leader=round(gap_to_leader, 3),
                gap_to_car_ahead=round(gap_to_car_ahead, 3),
                current_lap_time=round(runner.last_lap_time, 3) if runner.last_lap_time is not None else None,
                previous_lap_time=round(runner.previous_lap_time, 3) if runner.previous_lap_time is not None else None,
                best_lap_time=round(runner.fastest_lap, 3) if runner.fastest_lap < 999 else None,
                tire_compound=runner.tire_compound,  # type: ignore[arg-type]
                tire_age=runner.tire_age,
                tire_wear=round(runner.tire_wear, 2),
                component_wear=round(runner.component_wear, 2),
                status=runner.status,  # type: ignore[arg-type]
            )
        )
        previous_time = runner.cumulative_time

    return LapSnapshot(
        lap=lap,
        running_order=running_order,
        commentary=commentary,
        safety_car=safety_car,
        weather=weather,
        decision_prompt=decision_prompt,
    )


def _maybe_decision_prompt(
    session_type: str,
    lap: int,
    total_laps: int,
    runners: list[Runner],
    player_runner: Runner,
    safety_car: bool,
    weather: WeatherState,
    series: str,
) -> DecisionPrompt | None:
    player_position = _position_of(runners, player_runner.driver.id)
    if player_position is None or player_runner.status == "dnf":
        return None

    car_ahead_gap = _gap_to_car_ahead(runners, player_position)
    car_behind_gap = _gap_to_car_behind(runners, player_position)

    if lap == 1:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_start",
            lap=lap,
            type="start",
            title="Launch Mode",
            description="The lights are out and there is space into Turn 1.",
            default_choice_id="balanced_launch",
            choices=[
                DecisionChoice(id="safe_launch", label="Protect position", risk=20, effects={"paceDelta": 0.1, "incidentRisk": -8}),
                DecisionChoice(id="balanced_launch", label="Race the cars around you", risk=45, effects={"paceDelta": -0.05}),
                DecisionChoice(id="aggressive_launch", label="Attack immediately", risk=70, effects={"paceDelta": -0.18, "tireWear": 3, "incidentRisk": 8}),
            ],
        )

    if safety_car and session_type == "feature" and lap > total_laps // 3:
        return _safety_car_prompt(session_type, lap, total_laps, runners, player_runner, series)

    if session_type == "feature" and lap in {max(3, total_laps // 3), max(4, (total_laps * 2) // 3)}:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_strategy_window",
            lap=lap,
            type="strategy",
            title="Strategy Window",
            description=(
                f"You are on {player_runner.tire_compound}s with {player_runner.tire_wear:.0f}% wear. "
                "The pit wall is weighing track position against tyre life."
            ),
            default_choice_id="follow_plan",
            choices=[
                DecisionChoice(id="pit_early", label="Bias toward the undercut", risk=48, effects={"paceDelta": -0.04, "tireWear": 4, "pitWindowDelta": -2}),
                DecisionChoice(id="follow_plan", label="Stay on the planned window", risk=24, effects={"strategyConfidence": 3}),
                DecisionChoice(id="extend_stint", label="Extend for clean air later", risk=42, effects={"paceDelta": 0.06, "tireWear": -2, "pitWindowDelta": 4}),
            ],
        )

    if weather.condition != "dry" and lap in {3, total_laps // 2}:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_weather",
            lap=lap,
            type="weather",
            title="Changing Grip",
            description="Grip is inconsistent and the racing line is evolving.",
            default_choice_id="build_temperature",
            choices=[
                DecisionChoice(id="push_for_heat", label="Push to build tyre temperature", risk=62, effects={"paceDelta": -0.12, "incidentRisk": 6}),
                DecisionChoice(id="build_temperature", label="Build temperature progressively", risk=32, effects={"paceDelta": 0.02}),
                DecisionChoice(id="stay_wide", label="Avoid painted kerbs", risk=18, effects={"paceDelta": 0.14, "incidentRisk": -7}),
            ],
        )

    if player_runner.tire_wear > 62 and lap < total_laps - 2:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_tires",
            lap=lap,
            type="tires",
            title="Tyres Overheating",
            description="Your engineer warns the rears are starting to slide under traction.",
            default_choice_id="manage_tires",
            choices=[
                DecisionChoice(id="keep_pushing", label="Keep pushing", risk=65, effects={"paceDelta": -0.08, "tireWear": 8}),
                DecisionChoice(id="manage_tires", label="Manage traction zones", risk=25, effects={"paceDelta": 0.12, "tireWear": -6}),
                DecisionChoice(id="cool_tires", label="Drop back and cool tyres", risk=15, effects={"paceDelta": 0.25, "tireWear": -12}),
            ],
        )

    if car_ahead_gap is not None and car_ahead_gap <= 1.0 and lap not in {total_laps}:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_attack",
            lap=lap,
            type="attack",
            title="Attack Range",
            description="You are inside DRS range and the car ahead is vulnerable.",
            default_choice_id="wait_for_drs",
            choices=[
                DecisionChoice(id="send_inside", label="Send it down the inside", risk=78, effects={"paceDelta": -0.2, "tireWear": 5, "incidentRisk": 12}),
                DecisionChoice(id="wait_for_drs", label="Wait for the DRS straight", risk=38, effects={"paceDelta": -0.05}),
                DecisionChoice(id="save_tires", label="Save tyres and attack later", risk=18, effects={"paceDelta": 0.12, "tireWear": -5}),
            ],
        )

    if car_behind_gap is not None and car_behind_gap <= 0.9:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_defend",
            lap=lap,
            type="defend",
            title="Pressure From Behind",
            description="The car behind is closing quickly with DRS.",
            default_choice_id="cover_inside",
            choices=[
                DecisionChoice(id="cover_inside", label="Cover the inside line", risk=42, effects={"paceDelta": 0.08}),
                DecisionChoice(id="break_drs", label="Push to break DRS", risk=66, effects={"paceDelta": -0.12, "tireWear": 5}),
                DecisionChoice(id="save_race", label="Do not over-defend", risk=20, effects={"paceDelta": 0.05, "reputation": 1}),
            ],
        )

    if lap == total_laps - 1 and player_position <= 10:
        return DecisionPrompt(
            id=f"{session_type}_lap_{lap}_late_pressure",
            lap=lap,
            type="late_pressure",
            title="Points On The Line",
            description="The final laps can decide whether this becomes a points finish.",
            default_choice_id="bring_it_home",
            choices=[
                DecisionChoice(id="all_in", label="Use everything left", risk=72, effects={"paceDelta": -0.18, "tireWear": 6}),
                DecisionChoice(id="bring_it_home", label="Bring it home cleanly", risk=24, effects={"paceDelta": 0.04, "incidentRisk": -5}),
                DecisionChoice(id="defensive_margin", label="Prioritise exits and traction", risk=34, effects={"paceDelta": 0.08, "tireWear": -4}),
            ],
        )

    return None


def _safety_car_prompt(
    session_type: str,
    lap: int,
    total_laps: int,
    runners: list[Runner],
    player_runner: Runner,
    series: str,
) -> DecisionPrompt:
    pit_loss = 12.7 if series == "F1" else 13.6
    current_position = _position_of(runners, player_runner.driver.id) or 1
    rejoin_position = _estimated_rejoin_position(runners, player_runner, pit_loss)
    positions_lost = max(0, rejoin_position - current_position)
    next_compound = "hard" if series == "F2" else _next_compound_for_label(series, player_runner)
    should_pit = player_runner.tire_wear > 30 or _plan_says_pit(player_runner, lap, total_laps)
    default_choice = "pit_now" if should_pit else "stay_out"
    return DecisionPrompt(
        id=f"{session_type}_lap_{lap}_safety_car",
        lap=lap,
        type="safety_car",
        title="Safety Car Window",
        description=(
            f"Pit loss about {pit_loss:.1f}s. You are P{current_position}; "
            f"a stop projects P{rejoin_position} ({positions_lost} places lost) on {next_compound}s."
        ),
        default_choice_id=default_choice,
        choices=[
            DecisionChoice(
                id="pit_now",
                label=f"Pit now: +{pit_loss:.1f}s, rejoin ~P{rejoin_position}",
                risk=34,
                effects={"pitNow": 1, "pitLoss": round(pit_loss, 1), "projectedPosition": rejoin_position},
            ),
            DecisionChoice(
                id="stay_out",
                label="Stay out and keep track position",
                risk=56,
                effects={"trackPosition": 1, "tireWear": 6},
            ),
            DecisionChoice(
                id="engineer_recommendation",
                label="Take engineer recommendation",
                risk=28,
                effects={"pitNow": 1 if should_pit else 0, "strategyConfidence": 4},
            ),
        ],
    )


def _estimated_rejoin_position(runners: list[Runner], player_runner: Runner, pit_loss: float) -> int:
    projected_time = player_runner.cumulative_time + pit_loss
    running = sorted([runner for runner in runners if runner.status == "running"], key=lambda runner: runner.cumulative_time)
    return 1 + sum(1 for runner in running if runner.driver.id != player_runner.driver.id and runner.cumulative_time < projected_time)


def _next_compound_for_label(series: str, runner: Runner) -> str:
    if series == "F2":
        return "hard"
    if runner.planned_stops >= 2:
        return "hard" if runner.pit_stops == 0 else "medium"
    if runner.tire_compound == "hard":
        return "medium"
    return "hard"


def _apply_default_decision(player_runner: Runner, prompt: DecisionPrompt) -> None:
    choice = next(choice for choice in prompt.choices if choice.id == prompt.default_choice_id)
    pace_delta = float(choice.effects.get("paceDelta", 0))
    tire_wear_delta = float(choice.effects.get("tireWear", 0))
    player_runner.cumulative_time += max(-0.35, min(0.35, pace_delta))
    player_runner.tire_wear = max(0, min(100, player_runner.tire_wear + tire_wear_delta))


def _default_decision_commentary(prompt: DecisionPrompt) -> str:
    choice = next(choice for choice in prompt.choices if choice.id == prompt.default_choice_id)
    return f"Decision: {prompt.title}. Default call: {choice.label}."


def _runner_for(runners: list[Runner], driver_id: str) -> Runner | None:
    return next((runner for runner in runners if runner.driver.id == driver_id), None)


def _gap_to_car_ahead(runners: list[Runner], position: int) -> float | None:
    if position <= 1:
        return None
    return max(0, runners[position - 1].cumulative_time - runners[position - 2].cumulative_time)


def _gap_to_car_behind(runners: list[Runner], position: int) -> float | None:
    if position >= len(runners):
        return None
    return max(0, runners[position].cumulative_time - runners[position - 1].cumulative_time)


def _weather(track: Track, rng: random.Random) -> WeatherState:
    rain_roll = rng.randint(1, 100)
    if rain_roll <= track.rain_chance // 3:
        rain = rng.randint(45, 80)
        return WeatherState(condition="wet", air_temp=20, track_temp=24, rain_intensity=rain, track_grip=max(28, 64 - rain // 2))
    if rain_roll <= track.rain_chance:
        rain = rng.randint(15, 40)
        return WeatherState(condition="damp", air_temp=22, track_temp=27, rain_intensity=rain, track_grip=max(48, 74 - rain // 3))
    return WeatherState(condition="dry", air_temp=rng.randint(23, 32), track_temp=rng.randint(31, 44), track_grip=rng.randint(68, 78))


def _evolve_weather(weather: WeatherState, track: Track, lap: int, total_laps: int, rng: random.Random, commentary: list[str]) -> WeatherState:
    rain = weather.rain_intensity
    if track.rain_chance > 0 and rng.randint(1, 1000) <= max(3, track.rain_chance // 4):
        rain += rng.choice([-10, -6, 8, 12, 16])
    elif weather.condition != "dry":
        rain += rng.choice([-3, -2, -1, 0, 1])
    else:
        rain += rng.choice([0, 0, 1])
    rain = max(0, min(85, rain))

    if rain >= 42:
        condition = "wet"
    elif rain >= 10:
        condition = "damp"
    else:
        condition = "dry"

    drying = 2 if condition == "dry" else -rain // 18
    grip = max(25, min(86, weather.track_grip + drying + rng.choice([-1, 0, 0, 1])))
    if condition == "wet":
        grip = min(grip, max(30, 62 - rain // 2))
    elif condition == "damp":
        grip = min(grip, max(48, 75 - rain // 3))

    if condition != weather.condition:
        commentary.append(f"Weather update: track is now {condition}, grip {grip}%.")
    elif lap in {1, total_laps // 2}:
        commentary.append(f"Track evolution: {condition} surface, grip {grip}%.")

    return weather.model_copy(update={"condition": condition, "rain_intensity": rain, "track_grip": grip})


def _headline(save: SaveGame, feature: RaceResult) -> str:
    winner = next(driver for driver in save.drivers if driver.id == feature.classification[0].driver_id)
    player = next((row for row in feature.classification if row.driver_id == save.player_driver_id), None)
    series = next((driver.series for driver in save.drivers if driver.id == feature.classification[0].driver_id), "F2")
    if player and player.position <= 3:
        return f"{winner.name} wins as your {series} race lands on the podium"
    if player and player.points > 0:
        return f"{winner.name} wins while you bank {series} points"
    if player:
        return f"{winner.name} controls the feature as your debut ends P{player.position}"
    return f"{winner.name} wins the {series} feature race"


def _total_laps(calendar_round: CalendarRound, session_type: str, track: Track | None = None, save: SaveGame | None = None) -> int:
    mode = (save.event_flags.get("race_length_mode") if save else None) or "authentic_scaled"
    if mode == "compact":
        if calendar_round.series == "F1":
            return 15 if session_type == "sprint" else 30
        return 12 if session_type == "sprint" else 24

    base_lap_time = _series_lap_time_base(track, calendar_round.series) if track else 90
    if calendar_round.series == "F1":
        target_seconds = 1800 if session_type == "sprint" else 5400
        return max(18 if session_type == "sprint" else 45, min(28 if session_type == "sprint" else 78, round(target_seconds / base_lap_time)))

    target_seconds = 2700 if session_type == "sprint" else 3600
    return max(20 if session_type == "sprint" else 30, min(32 if session_type == "sprint" else 44, round(target_seconds / base_lap_time)))


def _points_table(calendar_round: CalendarRound, session_type: str) -> dict[int, int]:
    if calendar_round.series == "F1":
        return F1_SPRINT_POINTS if session_type == "sprint" else F1_GRAND_PRIX_POINTS
    return SPRINT_POINTS if session_type == "sprint" else FEATURE_POINTS


def _find_round(save: SaveGame, round_id: str) -> CalendarRound:
    return next(calendar_round for calendar_round in save.calendar if calendar_round.id == round_id)


def _find_track(save: SaveGame, track_id: str) -> Track:
    from app.data.loaders import get_tracks

    return next(track for track in get_tracks() if track.id == track_id)


def _position_of(runners: list[Runner], driver_id: str) -> int | None:
    for index, runner in enumerate(runners, start=1):
        if runner.driver.id == driver_id:
            return index
    return None


def _practice_note(setup_score: int) -> str:
    if setup_score >= 78:
        return "Strong setup direction"
    if setup_score <= 58:
        return "Setup work still needed"
    return "Baseline programme completed"


def _qualifying_note(traffic: bool, mistake: bool) -> str:
    if traffic and mistake:
        return "Traffic and a correction cost time"
    if traffic:
        return "Lost time in traffic"
    if mistake:
        return "Small mistake on push lap"
    return "Clean push lap"


def _clamp(value: int) -> int:
    return max(1, min(100, value))
