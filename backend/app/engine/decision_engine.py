"""Engine for interactive race decisions."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.race import (
    ActiveRaceState,
    DecisionChoice,
    DecisionOutcome,
    DecisionPrompt,
    DecisionResponse,
    LapSnapshot,
    PendingDecision,
    PracticeResult,
    QualifyingResult,
    RaceClassification,
    RaceResult,
    RunningOrderEntry,
    WeatherState,
    WeekendResult,
)
from app.models.save_game import SaveGame
from app.models.team import Team
from app.models.track import Track
from app.engine.weekend_engine import sprint_grid_for_round


SPRINT_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
FEATURE_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}
F1_SPRINT_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
F1_GRAND_PRIX_POINTS = FEATURE_POINTS


@dataclass
class Runner:
    """Internal race runner state."""

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
    pace_modifier: float = 0  # From decisions
    tire_wear_modifier: float = 0  # From decisions
    modifier_laps_remaining: int = 0  # How long modifiers last


@dataclass
class InteractiveRaceState:
    """Internal state for an interactive race."""

    save_id: str
    round_id: str
    race_type: str
    series: str
    track: Track
    weather: WeatherState
    runners: list[Runner]
    rng: random.Random
    current_lap: int = 0
    total_laps: int = 24
    lap_snapshots: list[LapSnapshot] = field(default_factory=list)
    decision_history: list[DecisionOutcome] = field(default_factory=list)
    safety_car_remaining: int = 0
    safety_car_mode: str = "none"
    last_prompt_lap: int = -10
    prompt_count: int = 0
    is_complete: bool = False
    dnfs: list[str] = field(default_factory=list)
    safety_car_laps: list[int] = field(default_factory=list)


def start_interactive_race(
    save: SaveGame,
    round_id: str,
    race_type: str,
    practice: PracticeResult,
    qualifying: QualifyingResult,
) -> ActiveRaceState:
    """
    Initialize an interactive race.

    Returns the initial ActiveRaceState ready for simulation.
    """
    calendar_round = _find_round(save, round_id)
    track = _find_track(calendar_round.track_id)
    drivers = [driver for driver in save.drivers if driver.series == calendar_round.series]
    teams = {team.id: team for team in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}:{race_type}")

    qualifying_order = [entry.driver_id for entry in qualifying.classification]
    if race_type == "sprint":
        starting_grid = sprint_grid_for_round(calendar_round, qualifying_order)
        if not starting_grid:
            raise ValueError("This round does not have a sprint race.")
    else:
        starting_grid = qualifying_order

    # Create runners
    driver_map = {driver.id: driver for driver in drivers}
    total_laps = _total_laps(calendar_round, race_type, track, save)
    weather = _get_weather(track, rng)
    runners = []
    for index, driver_id in enumerate(starting_grid):
        driver = driver_map[driver_id]
        team = teams[driver.team_id]
        planned_stops = _planned_stop_count(calendar_round, race_type, team, track, weather, rng)
        runners.append(
            Runner(
                driver=driver,
                team=team,
                cumulative_time=index * rng.uniform(0.14, 0.28),
                tire_compound=_starting_compound(calendar_round, race_type, index + 1, team, track, weather, rng),
                planned_stops=planned_stops,
                planned_pit_laps=_planned_pit_laps(calendar_round, team, total_laps, planned_stops, index + 1, rng),
                strategy_style=_strategy_style(team),
            )
        )

    # Store internal state in save game's event_flags for persistence
    internal_state = InteractiveRaceState(
        save_id=save.save_id,
        round_id=round_id,
        race_type=race_type,
        series=calendar_round.series,
        track=track,
        weather=weather,
        runners=runners,
        rng=rng,
        total_laps=total_laps,
    )

    # Store serialized state
    _store_internal_state(save, internal_state)

    return _to_active_race_state(internal_state, save.player_driver_id)


def simulate_to_next_decision(
    save: SaveGame,
    round_id: str,
    race_type: str,
) -> ActiveRaceState:
    """
    Simulate laps until the next decision prompt or race end.

    Returns the updated ActiveRaceState with any pending decision.
    """
    internal_state = _load_internal_state(save, round_id, race_type)

    if internal_state.is_complete:
        return _to_active_race_state(internal_state, save.player_driver_id)

    player_driver_id = save.player_driver_id
    max_prompts = 4 if race_type == "sprint" else 6

    if internal_state.current_lap < internal_state.total_laps:
        internal_state.current_lap += 1
        lap = internal_state.current_lap

        commentary: list[str] = []
        decision_prompt: DecisionPrompt | None = None
        internal_state.weather = _evolve_weather(
            internal_state.weather,
            internal_state.track,
            lap,
            internal_state.total_laps,
            internal_state.rng,
            commentary,
        )

        # Check for safety car
        if internal_state.safety_car_remaining == 0:
            sc_chance = max(1, internal_state.track.safety_car_chance // 24)
            if internal_state.rng.randint(1, 1000) <= sc_chance:
                incident = _random_neutralization_incident(
                    internal_state.runners,
                    internal_state.track,
                    internal_state.rng,
                )
                if incident is not None:
                    safety_car_mode, retired_driver_id, incident_lines = incident
                    internal_state.safety_car_remaining = internal_state.rng.randint(1, 2)
                    internal_state.safety_car_mode = safety_car_mode
                    if retired_driver_id not in internal_state.dnfs:
                        internal_state.dnfs.append(retired_driver_id)
                    commentary.extend(incident_lines)

        safety_car = internal_state.safety_car_remaining > 0
        if safety_car and internal_state.safety_car_mode == "safety_car":
            internal_state.safety_car_laps.append(lap)
            _compress_field_for_safety_car(internal_state.runners, internal_state.rng)
        elif safety_car:
            internal_state.safety_car_laps.append(lap)

        # Simulate all runners
        for runner in internal_state.runners:
            if runner.status == "dnf":
                continue

            # Check for DNF
            if internal_state.rng.random() < _retirement_chance(
                internal_state.series,
                runner,
                internal_state.track,
                lap,
                internal_state.total_laps,
            ):
                runner.status = "dnf"
                internal_state.dnfs.append(runner.driver.id)
                if internal_state.rng.random() < _crash_retirement_share(
                    internal_state.series,
                    runner,
                    internal_state.track,
                    lap,
                    internal_state.total_laps,
                ):
                    commentary.append(f"{runner.driver.name} crashes out and is stopped near the racing line.")
                    if not safety_car:
                        safety_car = True
                        internal_state.safety_car_remaining = max(
                            internal_state.safety_car_remaining,
                            internal_state.rng.randint(1, 2),
                        )
                        internal_state.safety_car_mode = "safety_car"
                        if lap not in internal_state.safety_car_laps:
                            internal_state.safety_car_laps.append(lap)
                    commentary.append("Safety Car deployed while marshals recover the car.")
                else:
                    commentary.append(f"{runner.driver.name} is out with a mechanical issue.")
                    recovery_mode = _stranded_recovery_mode(runner, internal_state.track, internal_state.rng)
                    if recovery_mode is not None and not safety_car:
                        safety_car = True
                        internal_state.safety_car_remaining = max(
                            internal_state.safety_car_remaining,
                            internal_state.rng.randint(1, 2),
                        )
                        internal_state.safety_car_mode = recovery_mode
                        if lap not in internal_state.safety_car_laps:
                            internal_state.safety_car_laps.append(lap)
                        if recovery_mode == "safety_car":
                            commentary.append("Safety Car deployed because the car is stranded near the racing line.")
                        else:
                            commentary.append("Virtual Safety Car deployed while marshals recover the stopped car.")
                continue

            runner.previous_lap_time = runner.last_lap_time
            lap_time = _race_lap_time(runner, internal_state.track, internal_state.weather, internal_state.rng, safety_car)
            if _driver_mistake(
                runner,
                internal_state.track,
                internal_state.weather,
                internal_state.rng,
                lap,
                internal_state.total_laps,
            ):
                mistake_loss = internal_state.rng.uniform(0.7, 2.4)
                lap_time += mistake_loss
                if runner.driver.id == player_driver_id:
                    commentary.append(f"You lose {mistake_loss:.1f}s with a small moment in low grip.")

            # Apply decision modifiers for player
            if runner.driver.id == player_driver_id and runner.modifier_laps_remaining > 0:
                lap_time += runner.pace_modifier
                runner.modifier_laps_remaining -= 1
                if runner.modifier_laps_remaining == 0:
                    runner.pace_modifier = 0
                    runner.tire_wear_modifier = 0

            runner.cumulative_time += lap_time
            runner.fastest_lap = min(runner.fastest_lap, lap_time)
            runner.last_lap_time = lap_time
            runner.tire_age += 1

            # Tire wear with modifier
            base_wear = _tire_wear_increment(runner, internal_state.track, internal_state.weather, race_type)
            extra_wear = runner.tire_wear_modifier if runner.driver.id == player_driver_id else 0
            runner.tire_wear = min(100, runner.tire_wear + base_wear + extra_wear)
            runner.component_wear = min(
                100,
                runner.component_wear
                + _component_wear_increment(runner, internal_state.track, internal_state.weather, race_type),
            )
            if runner.driver.id == player_driver_id and runner.component_wear > 76 and lap % 4 == 0:
                commentary.append(f"Engineer: power unit temperatures are high, component wear at {runner.component_wear:.0f}%.")

            if _should_pit(
                internal_state.series,
                race_type,
                runner,
                lap,
                internal_state.total_laps,
                internal_state.track,
                safety_car,
                internal_state.runners,
            ):
                pit_loss = _pit_loss(internal_state.series, internal_state.rng, safety_car)
                runner.cumulative_time += pit_loss
                runner.last_lap_time = (runner.last_lap_time or lap_time) + pit_loss
                runner.pit_stops += 1
                runner.tire_age = 0
                runner.tire_wear = 0
                runner.tire_compound = _next_compound(internal_state.series, runner)
                if runner.driver.id == player_driver_id:
                    commentary.append(f"You pit for {runner.tire_compound} tyres and rejoin in traffic.")

        # Sort by cumulative time
        internal_state.runners.sort(key=lambda r: (r.status == "dnf", r.cumulative_time))
        if not safety_car:
            _apply_ai_racecraft(internal_state.runners, internal_state.track, internal_state.rng, commentary)
            _apply_green_flag_dirty_air(internal_state.runners)
            internal_state.runners.sort(key=lambda r: (r.status == "dnf", r.cumulative_time))

        # Check for decision prompt for player
        player_runner = _runner_for(internal_state.runners, player_driver_id)
        if player_runner is not None and player_runner.status == "running":
            decision_prompt = _maybe_decision_prompt(
                race_type=race_type,
                lap=lap,
                total_laps=internal_state.total_laps,
                runners=internal_state.runners,
                player_runner=player_runner,
                safety_car=safety_car,
                weather=internal_state.weather,
                series=internal_state.series,
            )

            # Check cooldown and max prompts
            if decision_prompt is not None:
                if internal_state.prompt_count >= max_prompts or lap - internal_state.last_prompt_lap < 3:
                    decision_prompt = None

        # Add position update commentary
        if not safety_car and lap in {1, internal_state.total_laps // 2, internal_state.total_laps}:
            player_position = _position_of(internal_state.runners, player_driver_id)
            if player_position is not None:
                commentary.append(f"You cross lap {lap} in P{player_position}.")

        # Create lap snapshot
        lap_snapshot = _lap_snapshot(
            lap, internal_state.runners, commentary, safety_car, internal_state.weather, decision_prompt
        )
        internal_state.lap_snapshots.append(lap_snapshot)

        # Decrement safety car
        internal_state.safety_car_remaining = max(0, internal_state.safety_car_remaining - 1)
        if internal_state.safety_car_remaining == 0:
            internal_state.safety_car_mode = "none"

        # If we have a decision prompt, pause and return
        if decision_prompt is not None:
            internal_state.last_prompt_lap = lap
            internal_state.prompt_count += 1
            _store_internal_state(save, internal_state)

            active_state = _to_active_race_state(internal_state, player_driver_id)
            active_state.pending_decision = PendingDecision(
                prompt=decision_prompt,
                race_type=race_type,  # type: ignore
                expires_at_lap=min(lap + 3, internal_state.total_laps),
            )
            return active_state

        if internal_state.current_lap < internal_state.total_laps:
            _store_internal_state(save, internal_state)
            return _to_active_race_state(internal_state, player_driver_id)

    # Race complete
    internal_state.is_complete = True
    _store_internal_state(save, internal_state)
    return _to_active_race_state(internal_state, player_driver_id)


def submit_decision(
    save: SaveGame,
    round_id: str,
    race_type: str,
    response: DecisionResponse,
) -> ActiveRaceState:
    """
    Apply the player's decision and continue simulation.

    Returns the updated ActiveRaceState.
    """
    internal_state = _load_internal_state(save, round_id, race_type)
    player_driver_id = save.player_driver_id

    # Find the decision prompt from the last lap snapshot
    last_snapshot = internal_state.lap_snapshots[-1] if internal_state.lap_snapshots else None
    if last_snapshot is None or last_snapshot.decision_prompt is None:
        # No pending decision, just continue
        return simulate_to_next_decision(save, round_id, race_type)

    prompt = last_snapshot.decision_prompt
    choice = prompt.choices[response.choice_index]

    # Apply effects to player runner
    player_runner = _runner_for(internal_state.runners, player_driver_id)
    if player_runner is not None:
        pace_delta = float(choice.effects.get("paceDelta", 0))
        tire_wear_delta = float(choice.effects.get("tireWear", 0))
        component_wear_delta = float(choice.effects.get("componentWear", 0))

        player_runner.pace_modifier = pace_delta
        player_runner.tire_wear_modifier = tire_wear_delta
        player_runner.modifier_laps_remaining = 1
        if component_wear_delta:
            player_runner.component_wear = max(0, min(100, player_runner.component_wear + component_wear_delta))
        pit_delta = int(choice.effects.get("pitWindowDelta", 0))
        if pit_delta and race_type == "feature":
            _shift_next_pit_window(player_runner, prompt.lap, internal_state.total_laps, pit_delta)
            if pit_delta > 0:
                player_runner.pit_block_until_lap = max(player_runner.pit_block_until_lap, prompt.lap + min(4, pit_delta))
        if bool(choice.effects.get("pitNow", 0)) and race_type == "feature":
            max_stops = max(1, player_runner.planned_stops or _target_f1_stops(internal_state.track))
            if player_runner.pit_stops < max_stops:
                pit_loss = _pit_loss(internal_state.series, internal_state.rng, True)
                player_runner.cumulative_time += pit_loss
                player_runner.last_lap_time = (player_runner.last_lap_time or 0) + pit_loss
                player_runner.pit_stops += 1
                player_runner.tire_age = 0
                player_runner.tire_wear = 0
                player_runner.tire_compound = _next_compound(internal_state.series, player_runner)

    # Record outcome
    outcome = DecisionOutcome(
        decision_id=prompt.id,
        choice_id=choice.id,
        choice_label=choice.label,
        pace_modifier=float(choice.effects.get("paceDelta", 0)),
        tire_wear_modifier=float(choice.effects.get("tireWear", 0)),
        incident_risk_modifier=float(choice.effects.get("incidentRisk", 0)),
        narrative=_generate_decision_narrative(prompt, choice),
    )
    internal_state.decision_history.append(outcome)

    # Update lap snapshot commentary with decision
    if internal_state.lap_snapshots:
        last_snapshot = internal_state.lap_snapshots[-1]
        new_commentary = list(last_snapshot.commentary)
        new_commentary.append(f"Decision: {choice.label}")
        internal_state.lap_snapshots[-1] = LapSnapshot(
            lap=last_snapshot.lap,
            running_order=last_snapshot.running_order,
            commentary=new_commentary,
            safety_car=last_snapshot.safety_car,
            weather=last_snapshot.weather,
            decision_prompt=last_snapshot.decision_prompt,
        )

    _store_internal_state(save, internal_state)

    return _to_active_race_state(internal_state, player_driver_id)


def auto_complete_race(
    save: SaveGame,
    round_id: str,
    race_type: str,
) -> RaceResult:
    """
    Skip all remaining decisions and complete the race.

    Returns the final RaceResult.
    """
    internal_state = _load_internal_state(save, round_id, race_type)
    player_driver_id = save.player_driver_id

    # Simulate remaining laps without pausing for decisions
    while internal_state.current_lap < internal_state.total_laps:
        internal_state.current_lap += 1
        lap = internal_state.current_lap

        commentary: list[str] = []
        internal_state.weather = _evolve_weather(
            internal_state.weather,
            internal_state.track,
            lap,
            internal_state.total_laps,
            internal_state.rng,
            commentary,
        )

        # Safety car check
        if internal_state.safety_car_remaining == 0:
            sc_chance = max(1, internal_state.track.safety_car_chance // 24)
            if internal_state.rng.randint(1, 1000) <= sc_chance:
                incident = _random_neutralization_incident(
                    internal_state.runners,
                    internal_state.track,
                    internal_state.rng,
                )
                if incident is not None:
                    safety_car_mode, retired_driver_id, incident_lines = incident
                    internal_state.safety_car_remaining = internal_state.rng.randint(1, 2)
                    internal_state.safety_car_mode = safety_car_mode
                    if retired_driver_id not in internal_state.dnfs:
                        internal_state.dnfs.append(retired_driver_id)
                    commentary.extend(incident_lines)

        safety_car = internal_state.safety_car_remaining > 0
        if safety_car and internal_state.safety_car_mode == "safety_car":
            internal_state.safety_car_laps.append(lap)
            _compress_field_for_safety_car(internal_state.runners, internal_state.rng)
        elif safety_car:
            internal_state.safety_car_laps.append(lap)

        # Simulate runners
        for runner in internal_state.runners:
            if runner.status == "dnf":
                continue

            if internal_state.rng.random() < _retirement_chance(
                internal_state.series,
                runner,
                internal_state.track,
                lap,
                internal_state.total_laps,
            ):
                runner.status = "dnf"
                internal_state.dnfs.append(runner.driver.id)
                if internal_state.rng.random() < _crash_retirement_share(
                    internal_state.series,
                    runner,
                    internal_state.track,
                    lap,
                    internal_state.total_laps,
                ):
                    commentary.append(f"{runner.driver.name} crashes out and retires from the race.")
                    if not safety_car:
                        safety_car = True
                        internal_state.safety_car_remaining = max(
                            internal_state.safety_car_remaining,
                            internal_state.rng.randint(1, 2),
                        )
                        internal_state.safety_car_mode = "safety_car"
                        if lap not in internal_state.safety_car_laps:
                            internal_state.safety_car_laps.append(lap)
                    commentary.append("Safety Car deployed while marshals recover the car.")
                else:
                    commentary.append(f"{runner.driver.name} retires with a mechanical issue.")
                    recovery_mode = _stranded_recovery_mode(runner, internal_state.track, internal_state.rng)
                    if recovery_mode is not None and not safety_car:
                        safety_car = True
                        internal_state.safety_car_remaining = max(
                            internal_state.safety_car_remaining,
                            internal_state.rng.randint(1, 2),
                        )
                        internal_state.safety_car_mode = recovery_mode
                        if lap not in internal_state.safety_car_laps:
                            internal_state.safety_car_laps.append(lap)
                        if recovery_mode == "safety_car":
                            commentary.append("Safety Car deployed because the car is stranded near the racing line.")
                        else:
                            commentary.append("Virtual Safety Car deployed while marshals recover the stopped car.")
                continue

            runner.previous_lap_time = runner.last_lap_time
            lap_time = _race_lap_time(runner, internal_state.track, internal_state.weather, internal_state.rng, safety_car)
            if _driver_mistake(
                runner,
                internal_state.track,
                internal_state.weather,
                internal_state.rng,
                lap,
                internal_state.total_laps,
            ):
                mistake_loss = internal_state.rng.uniform(0.7, 2.4)
                lap_time += mistake_loss
                if runner.driver.id == player_driver_id:
                    commentary.append(f"You lose {mistake_loss:.1f}s with a small moment in low grip.")
            runner.cumulative_time += lap_time
            runner.fastest_lap = min(runner.fastest_lap, lap_time)
            runner.last_lap_time = lap_time
            runner.tire_age += 1
            runner.tire_wear = min(
                100,
                runner.tire_wear + _tire_wear_increment(runner, internal_state.track, internal_state.weather, race_type),
            )
            runner.component_wear = min(
                100,
                runner.component_wear
                + _component_wear_increment(runner, internal_state.track, internal_state.weather, race_type),
            )
            if runner.driver.id == player_driver_id and runner.component_wear > 76 and lap % 4 == 0:
                commentary.append(f"Engineer: power unit temperatures are high, component wear at {runner.component_wear:.0f}%.")

            if _should_pit(
                internal_state.series,
                race_type,
                runner,
                lap,
                internal_state.total_laps,
                internal_state.track,
                safety_car,
                internal_state.runners,
            ):
                pit_loss = _pit_loss(internal_state.series, internal_state.rng, safety_car)
                runner.cumulative_time += pit_loss
                runner.last_lap_time = (runner.last_lap_time or lap_time) + pit_loss
                runner.pit_stops += 1
                runner.tire_age = 0
                runner.tire_wear = 0
                runner.tire_compound = _next_compound(internal_state.series, runner)

        internal_state.runners.sort(key=lambda r: (r.status == "dnf", r.cumulative_time))
        if not safety_car:
            _apply_ai_racecraft(internal_state.runners, internal_state.track, internal_state.rng, commentary)
            _apply_green_flag_dirty_air(internal_state.runners)
            internal_state.runners.sort(key=lambda r: (r.status == "dnf", r.cumulative_time))

        # Check for auto-decision (apply defaults)
        player_runner = _runner_for(internal_state.runners, player_driver_id)
        if player_runner:
            decision_prompt = _maybe_decision_prompt(
                race_type=race_type,
                lap=lap,
                total_laps=internal_state.total_laps,
                runners=internal_state.runners,
                player_runner=player_runner,
                safety_car=safety_car,
                weather=internal_state.weather,
                series=internal_state.series,
            )
            if decision_prompt and lap - internal_state.last_prompt_lap >= 3:
                _apply_default_decision(player_runner, decision_prompt)
                internal_state.last_prompt_lap = lap
                commentary.append(f"Auto-decision: {decision_prompt.title}")

        lap_snapshot = _lap_snapshot(lap, internal_state.runners, commentary, safety_car, internal_state.weather, None)
        internal_state.lap_snapshots.append(lap_snapshot)
        internal_state.safety_car_remaining = max(0, internal_state.safety_car_remaining - 1)
        if internal_state.safety_car_remaining == 0:
            internal_state.safety_car_mode = "none"

    internal_state.is_complete = True

    # Build final result
    return _build_race_result(internal_state)


def _build_race_result(state: InteractiveRaceState) -> RaceResult:
    """Build the final RaceResult from internal state."""
    points_table = _points_table(state.series, state.race_type)

    classified = [r for r in state.runners if r.status == "running"] + [
        r for r in state.runners if r.status == "dnf"
    ]

    winner_time = next(
        (r.cumulative_time for r in classified if r.status == "running"),
        classified[0].cumulative_time if classified else 0,
    )
    fastest_lap_bonus_driver = _fastest_lap_bonus_driver(state.series, classified)

    starting_grid = [r.driver.id for r in state.runners]

    # Collect all decision prompts from lap snapshots
    decision_prompts = [
        snap.decision_prompt
        for snap in state.lap_snapshots
        if snap.decision_prompt is not None
    ]

    return RaceResult(
        race_id=f"{state.track.id}_{state.race_type}",
        session_type=state.race_type,  # type: ignore
        track_id=state.track.id,
        total_laps=state.total_laps,
        starting_grid=starting_grid,
        classification=[
            RaceClassification(
                position=index,
                driver_id=runner.driver.id,
                status=runner.status,  # type: ignore
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
        lap_log=state.lap_snapshots,
        decision_prompts=decision_prompts,
        safety_car_laps=state.safety_car_laps,
        dnfs=state.dnfs,
    )


def _fastest_lap_bonus_driver(series: str, classified: list[Runner]) -> str | None:
    if series != "F2":
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
    series: str,
    race_type: str,
    runner: Runner,
    lap: int,
    total_laps: int,
    track: Track,
    safety_car: bool,
    runners: list[Runner] | None = None,
) -> bool:
    if race_type != "feature" or runner.status == "dnf":
        return False
    if lap <= runner.pit_block_until_lap:
        return False

    if series == "F2":
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


def _pit_loss(series: str, rng: random.Random, safety_car: bool) -> float:
    base_loss = 20.5 if series == "F1" else 22
    if safety_car:
        base_loss *= 0.62
    return base_loss + rng.uniform(-0.8, 1.8)


def _next_compound(series: str, runner: Runner) -> str:
    if series == "F2":
        return "hard"
    if runner.planned_stops >= 2:
        return "hard" if runner.pit_stops == 1 else "medium"
    if runner.tire_compound == "hard":
        return "medium"
    return "hard"


def _starting_compound(
    calendar_round: CalendarRound,
    race_type: str,
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
    if race_type == "sprint":
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


def _planned_stop_count(
    calendar_round: CalendarRound,
    race_type: str,
    team: Team,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> int:
    if race_type == "sprint" or weather.condition != "dry":
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
    if team.strategy >= 84:
        return "balanced"
    if team.strategy <= 66:
        return "aggressive"
    if team.reliability >= 82 and team.car_performance < 82:
        return "long_run"
    if team.car_performance >= 84:
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


def _shift_next_pit_window(runner: Runner, current_lap: int, total_laps: int, delta: int) -> None:
    pit_laps = list(runner.planned_pit_laps or [])
    if runner.pit_stops >= len(pit_laps):
        return
    next_index = runner.pit_stops
    minimum_lap = min(total_laps - 2, current_lap + 1)
    pit_laps[next_index] = max(2, min(total_laps - 2, max(minimum_lap, pit_laps[next_index] + delta)))
    for index in range(next_index + 1, len(pit_laps)):
        pit_laps[index] = max(pit_laps[index], min(total_laps - 2, pit_laps[index - 1] + 5))
    runner.planned_pit_laps = pit_laps


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
    return base_threshold + (runner.team.strategy - 75) * 0.08


def _retirement_chance(
    series: str,
    runner: Runner,
    track: Track,
    lap: int,
    total_laps: int,
) -> float:
    reliability_score = (
        runner.team.reliability * 0.72
        + runner.driver.attributes.awareness * 0.16
        + runner.driver.attributes.discipline * 0.12
    )
    reliability_pressure = max(0, 82 - reliability_score) / 26000
    series_floor = 0.00075 if series == "F1" else 0.00135
    track_pressure = track.safety_car_chance / (90000 if series == "F1" else 65000)
    lap_pressure = 0.00035 if lap == 1 else 0
    late_wear_pressure = max(0, runner.tire_wear - 72) / 90000
    component_pressure = max(0, runner.component_wear - 68) / 26000
    sprint_multiplier = 0.72 if total_laps <= 15 else 1
    return (
        series_floor
        + reliability_pressure
        + track_pressure
        + lap_pressure
        + late_wear_pressure
        + component_pressure
    ) * sprint_multiplier


def _crash_retirement_share(
    series: str,
    runner: Runner,
    track: Track,
    lap: int,
    total_laps: int,
) -> float:
    base = 0.46 if series == "F1" else 0.58
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
                "Safety Car deployed while marshals recover the car.",
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


def _to_active_race_state(state: InteractiveRaceState, player_driver_id: str | None) -> ActiveRaceState:
    """Convert internal state to API-facing ActiveRaceState."""
    player_runner = _runner_for(state.runners, player_driver_id)
    player_position = _position_of(state.runners, player_driver_id) if player_driver_id else None

    return ActiveRaceState(
        save_id=state.save_id,
        round_id=state.round_id,
        race_type=state.race_type,  # type: ignore
        current_lap=state.current_lap,
        total_laps=state.total_laps,
        lap_snapshots=state.lap_snapshots,
        pending_decision=None,
        decision_history=state.decision_history,
        is_complete=state.is_complete,
        player_position=player_position,
        player_tire_wear=player_runner.tire_wear if player_runner else 0,
        safety_car_active=state.safety_car_remaining > 0,
    )


# Internal state persistence (stored in memory for now, could be moved to save file)
_INTERNAL_STATES: dict[str, InteractiveRaceState] = {}


def _store_internal_state(save: SaveGame, state: InteractiveRaceState) -> None:
    """Store internal state for later retrieval."""
    key = f"{save.save_id}:{state.round_id}:{state.race_type}"
    _INTERNAL_STATES[key] = state


def _load_internal_state(save: SaveGame, round_id: str, race_type: str) -> InteractiveRaceState:
    """Load internal state from storage."""
    key = f"{save.save_id}:{round_id}:{race_type}"
    if key not in _INTERNAL_STATES:
        raise ValueError(f"No active race found for {key}. Call start_interactive_race first.")
    return _INTERNAL_STATES[key]


def _total_laps(calendar_round: CalendarRound, race_type: str, track: Track | None = None, save: SaveGame | None = None) -> int:
    mode = (save.event_flags.get("race_length_mode") if save else None) or "authentic_scaled"
    if mode == "compact":
        if calendar_round.series == "F1":
            return 15 if race_type == "sprint" else 30
        return 12 if race_type == "sprint" else 24

    base_lap_time = _series_lap_time_base(track, calendar_round.series) if track else 90
    if calendar_round.series == "F1":
        target_seconds = 1800 if race_type == "sprint" else 5400
        return max(18 if race_type == "sprint" else 45, min(28 if race_type == "sprint" else 78, round(target_seconds / base_lap_time)))

    target_seconds = 2700 if race_type == "sprint" else 3600
    return max(20 if race_type == "sprint" else 30, min(32 if race_type == "sprint" else 44, round(target_seconds / base_lap_time)))


def _points_table(series: str, race_type: str) -> dict[int, int]:
    if series == "F1":
        return F1_SPRINT_POINTS if race_type == "sprint" else F1_GRAND_PRIX_POINTS
    return SPRINT_POINTS if race_type == "sprint" else FEATURE_POINTS


def clear_internal_state(save_id: str, round_id: str, race_type: str) -> None:
    """Clear internal state after race completion."""
    key = f"{save_id}:{round_id}:{race_type}"
    _INTERNAL_STATES.pop(key, None)


# Helper functions (adapted from weekend_engine.py)


def _race_lap_time(
    runner: Runner,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    safety_car: bool,
) -> float:
    """Calculate a single race lap time."""
    if safety_car:
        return _series_lap_time_base(track, runner.team.series) * 1.32 + rng.uniform(-0.4, 0.4)

    driver = runner.driver
    team = runner.team
    wet_skill = driver.attributes.wet_weather if weather.condition != "dry" else driver.attributes.pace
    race_score = (
        driver.attributes.pace * 0.28
        + driver.attributes.racecraft * 0.24
        + driver.attributes.consistency * 0.18
        + driver.attributes.tire_management * 0.12
        + wet_skill * 0.1
    )
    team_score = team.car_performance * 0.78 + team.strategy * 0.12 + team.reliability * 0.1
    tire_penalty = runner.tire_wear * (104 - driver.attributes.tire_management) / 2200
    weather_penalty = weather.rain_intensity * (105 - driver.attributes.wet_weather) / 1000
    grip_penalty = max(0, 74 - weather.track_grip) / 70
    component_penalty = max(0, runner.component_wear - 72) / 115
    compound_delta = _compound_pace_delta(runner.tire_compound, weather)
    age_penalty = _tire_age_penalty(runner)

    return (
        _series_lap_time_base(track, team.series)
        + (90 - race_score) * 0.028
        + (90 - team_score) * (0.072 if team.series == "F1" else 0.05)
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


def _tire_wear_increment(runner: Runner, track: Track, weather: WeatherState, race_type: str) -> float:
    session_divisor = 22 if race_type == "sprint" else 34
    compound_multiplier = {
        "soft": 1.28,
        "medium": 1.0,
        "hard": 0.78,
        "inter": 1.08 if weather.condition != "dry" else 1.7,
        "wet": 1.0 if weather.condition == "wet" else 1.9,
    }.get(runner.tire_compound, 1.0)
    management_factor = 1 - max(-0.16, min(0.18, (runner.driver.attributes.tire_management - 75) / 220))
    grip_factor = 1 + max(0, 68 - weather.track_grip) / 180
    return track.tire_deg / session_divisor * compound_multiplier * management_factor * grip_factor


def _component_wear_increment(runner: Runner, track: Track, weather: WeatherState, race_type: str) -> float:
    session_factor = 0.52 if race_type == "sprint" else 0.42
    reliability_factor = 1 + max(0, 84 - runner.team.reliability) / 65
    heat_factor = 1 + max(0, weather.track_temp - 36) / 80
    wet_factor = 0.92 if weather.condition != "dry" else 1
    push_factor = 1 + max(0, runner.driver.attributes.aggression - runner.driver.attributes.discipline) / 180
    return session_factor * reliability_factor * heat_factor * wet_factor * push_factor


def _driver_mistake(runner: Runner, track: Track, weather: WeatherState, rng: random.Random, lap: int, total_laps: int) -> bool:
    if weather.track_grip >= 74 and runner.tire_wear < 62:
        return False
    control = (
        runner.driver.attributes.consistency * 0.45
        + runner.driver.attributes.discipline * 0.25
        + runner.driver.attributes.wet_weather * 0.3
    )
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
    """Bunch running cars without changing the order when the safety car is out."""
    running = [runner for runner in runners if runner.status == "running"]
    if not running:
        return

    leader_time = min(runner.cumulative_time for runner in running)
    ordered = sorted(running, key=lambda runner: runner.cumulative_time)
    for index, runner in enumerate(ordered):
        max_gap = index * rng.uniform(0.22, 0.38)
        runner.cumulative_time = min(runner.cumulative_time, leader_time + max_gap)


def _apply_green_flag_dirty_air(runners: list[Runner]) -> None:
    """Let green-flag gaps open unless the following car has a pace edge."""
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

        tire_delta = defender.tire_wear - attacker.tire_wear
        tire_attack_bonus = max(-8, min(10, tire_delta * 0.26))
        attack_score = (
            attacker.driver.attributes.racecraft * 0.34
            + attacker.driver.attributes.aggression * 0.24
            + attacker.driver.attributes.pace * 0.18
            + attacker.team.car_performance * 0.18
            + tire_attack_bonus
            + rng.uniform(-8, 8)
        )
        defense_score = (
            defender.driver.attributes.racecraft * 0.3
            + defender.driver.attributes.awareness * 0.22
            + defender.driver.attributes.discipline * 0.18
            + defender.team.car_performance * 0.18
            + max(-6, min(8, -tire_delta * 0.18))
            + rng.uniform(-6, 7)
        )

        pass_threshold = _overtake_score_threshold(track, tire_delta)
        pass_gap = min(0.65, gap_limit * 0.82)
        if attack_score > defense_score + pass_threshold and gap < pass_gap:
            attacker.cumulative_time = defender.cumulative_time - rng.uniform(0.015, 0.07)
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
    return max(0.32, min(1.08, 1.04 - track.overtaking_difficulty / 135 + track.drs_strength / 230))


def _overtake_score_threshold(track: Track, tire_delta: float) -> float:
    circuit_barrier = 4.0 + track.overtaking_difficulty * 0.22 - track.drs_strength * 0.06
    if tire_delta > 18:
        circuit_barrier -= min(5.0, (tire_delta - 18) * 0.25)
    return max(4.5, circuit_barrier)


def _race_pace_score(runner: Runner) -> float:
    driver = runner.driver
    return (
        driver.attributes.pace * 0.32
        + driver.attributes.racecraft * 0.22
        + driver.attributes.consistency * 0.16
        + driver.attributes.tire_management * 0.1
        + runner.team.car_performance * 0.2
    )


def _maybe_decision_prompt(
    race_type: str,
    lap: int,
    total_laps: int,
    runners: list[Runner],
    player_runner: Runner,
    safety_car: bool,
    weather: WeatherState,
    series: str,
) -> DecisionPrompt | None:
    """Check if a decision prompt should appear."""
    player_position = _position_of(runners, player_runner.driver.id)
    if player_position is None or player_runner.status == "dnf":
        return None

    car_ahead_gap = _gap_to_car_ahead(runners, player_position)
    car_behind_gap = _gap_to_car_behind(runners, player_position)

    # Lap 1: Start decision
    if lap == 1:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_start",
            lap=lap,
            type="start",
            title="Launch Mode",
            description="The lights are out. How do you approach Turn 1?",
            default_choice_id="balanced_launch",
            choices=[
                DecisionChoice(
                    id="safe_launch",
                    label="Protect position",
                    risk=20,
                    effects={"paceDelta": 0.1, "incidentRisk": -8, "componentWear": -1},
                ),
                DecisionChoice(
                    id="balanced_launch",
                    label="Race the cars around you",
                    risk=45,
                    effects={"paceDelta": -0.05},
                ),
                DecisionChoice(
                    id="aggressive_launch",
                    label="Attack immediately",
                    risk=70,
                    effects={"paceDelta": -0.18, "tireWear": 3, "incidentRisk": 8, "componentWear": 2},
                ),
            ],
        )

    if safety_car and race_type == "feature" and lap > total_laps // 3:
        return _safety_car_prompt(race_type, lap, total_laps, runners, player_runner, series)

    if race_type == "feature" and lap in {max(3, total_laps // 3), max(4, (total_laps * 2) // 3)}:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_strategy_window",
            lap=lap,
            type="strategy",
            title="Strategy Window",
            description=(
                f"You are on {player_runner.tire_compound}s with {player_runner.tire_wear:.0f}% wear. "
                "The pit wall is weighing track position against tyre life."
            ),
            default_choice_id="follow_plan",
            choices=[
                DecisionChoice(id="pit_early", label="Bias toward the undercut", risk=48, effects={"paceDelta": -0.04, "tireWear": 4, "pitWindowDelta": -2, "componentWear": 1}),
                DecisionChoice(id="follow_plan", label="Stay on the planned window", risk=24, effects={"strategyConfidence": 3}),
                DecisionChoice(id="extend_stint", label="Extend for clean air later", risk=42, effects={"paceDelta": 0.06, "tireWear": -2, "pitWindowDelta": 4, "componentWear": -1}),
            ],
        )

    # Weather decision
    if weather.condition != "dry" and lap in {3, total_laps // 2}:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_weather",
            lap=lap,
            type="weather",
            title="Changing Grip",
            description="Grip is inconsistent in these conditions.",
            default_choice_id="build_temperature",
            choices=[
                DecisionChoice(
                    id="push_for_heat",
                    label="Push to build tyre temperature",
                    risk=62,
                    effects={"paceDelta": -0.12, "incidentRisk": 6, "componentWear": 2},
                ),
                DecisionChoice(
                    id="build_temperature",
                    label="Build temperature progressively",
                    risk=32,
                    effects={"paceDelta": 0.02},
                ),
                DecisionChoice(
                    id="stay_wide",
                    label="Avoid painted kerbs",
                    risk=18,
                    effects={"paceDelta": 0.14, "incidentRisk": -7, "componentWear": -1},
                ),
            ],
        )

    # Component management decision
    if player_runner.component_wear > 68 and lap < total_laps - 2:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_power_unit",
            lap=lap,
            type="strategy",
            title="Power Unit Warning",
            description=(
                f"Component wear is at {player_runner.component_wear:.0f}%. "
                "The pit wall wants a call on whether to keep pushing or protect the engine."
            ),
            default_choice_id="lift_and_coast",
            choices=[
                DecisionChoice(
                    id="keep_engine_pushing",
                    label="Keep pushing on full deployment",
                    risk=72,
                    effects={"paceDelta": -0.1, "componentWear": 8, "incidentRisk": 5},
                ),
                DecisionChoice(
                    id="lift_and_coast",
                    label="Lift and coast on entry",
                    risk=28,
                    effects={"paceDelta": 0.12, "componentWear": -4},
                ),
                DecisionChoice(
                    id="cool_power_unit",
                    label="Cool the power unit",
                    risk=18,
                    effects={"paceDelta": 0.25, "componentWear": -8, "tireWear": -2},
                ),
            ],
        )

    # Tire degradation decision
    if player_runner.tire_wear > 62 and lap < total_laps - 2:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_tires",
            lap=lap,
            type="tires",
            title="Tyres Overheating",
            description="Your engineer warns the rears are starting to slide.",
            default_choice_id="manage_tires",
            choices=[
                DecisionChoice(
                    id="keep_pushing",
                    label="Keep pushing",
                    risk=65,
                    effects={"paceDelta": -0.08, "tireWear": 8, "componentWear": 4},
                ),
                DecisionChoice(
                    id="manage_tires",
                    label="Manage traction zones",
                    risk=25,
                    effects={"paceDelta": 0.12, "tireWear": -6},
                ),
                DecisionChoice(
                    id="cool_tires",
                    label="Drop back and cool tyres",
                    risk=15,
                    effects={"paceDelta": 0.25, "tireWear": -12, "componentWear": -2},
                ),
            ],
        )

    # Attack decision
    if car_ahead_gap is not None and car_ahead_gap <= 1.0 and lap != total_laps:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_attack",
            lap=lap,
            type="attack",
            title="Attack Range",
            description="You are inside DRS range. The car ahead is vulnerable.",
            default_choice_id="wait_for_drs",
            choices=[
                DecisionChoice(
                    id="send_inside",
                    label="Send it down the inside",
                    risk=78,
                    effects={"paceDelta": -0.2, "tireWear": 5, "incidentRisk": 12, "componentWear": 3},
                ),
                DecisionChoice(
                    id="wait_for_drs",
                    label="Wait for the DRS straight",
                    risk=38,
                    effects={"paceDelta": -0.05},
                ),
                DecisionChoice(
                    id="save_tires",
                    label="Save tyres and attack later",
                    risk=18,
                    effects={"paceDelta": 0.12, "tireWear": -5, "componentWear": -2},
                ),
            ],
        )

    # Defend decision
    if car_behind_gap is not None and car_behind_gap <= 0.9:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_defend",
            lap=lap,
            type="defend",
            title="Pressure From Behind",
            description="The car behind is closing with DRS.",
            default_choice_id="cover_inside",
            choices=[
                DecisionChoice(
                    id="cover_inside",
                    label="Cover the inside line",
                    risk=42,
                    effects={"paceDelta": 0.08},
                ),
                DecisionChoice(
                    id="break_drs",
                    label="Push to break DRS",
                    risk=66,
                    effects={"paceDelta": -0.12, "tireWear": 5, "componentWear": 3},
                ),
                DecisionChoice(
                    id="save_race",
                    label="Do not over-defend",
                    risk=20,
                    effects={"paceDelta": 0.05, "reputation": 1},
                ),
            ],
        )

    # Late pressure decision
    if lap == total_laps - 1 and player_position <= 10:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_late_pressure",
            lap=lap,
            type="late_pressure",
            title="Points On The Line",
            description="Final laps. Points are at stake.",
            default_choice_id="bring_it_home",
            choices=[
                DecisionChoice(
                    id="all_in",
                    label="Use everything left",
                    risk=72,
                    effects={"paceDelta": -0.18, "tireWear": 6, "componentWear": 4},
                ),
                DecisionChoice(
                    id="bring_it_home",
                    label="Bring it home cleanly",
                    risk=24,
                    effects={"paceDelta": 0.04, "incidentRisk": -5, "componentWear": -2},
                ),
                DecisionChoice(
                    id="defensive_margin",
                    label="Prioritise exits and traction",
                    risk=34,
                    effects={"paceDelta": 0.08, "tireWear": -4},
                ),
            ],
        )

    return None


def _safety_car_prompt(
    race_type: str,
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
    next_compound = _next_compound_for_label(series, player_runner)
    should_pit = player_runner.tire_wear > 30 or _plan_says_pit(player_runner, lap, total_laps)
    default_choice = "pit_now" if should_pit else "stay_out"
    return DecisionPrompt(
        id=f"{race_type}_lap_{lap}_safety_car",
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
    """Apply the default decision choice to a runner."""
    choice = next(c for c in prompt.choices if c.id == prompt.default_choice_id)
    pace_delta = float(choice.effects.get("paceDelta", 0))
    tire_wear_delta = float(choice.effects.get("tireWear", 0))
    component_wear_delta = float(choice.effects.get("componentWear", 0))
    player_runner.cumulative_time += max(-0.35, min(0.35, pace_delta))
    player_runner.tire_wear = max(0, min(100, player_runner.tire_wear + tire_wear_delta))
    player_runner.component_wear = max(0, min(100, player_runner.component_wear + component_wear_delta))


def _generate_decision_narrative(prompt: DecisionPrompt, choice: DecisionChoice) -> str:
    """Generate a narrative description of the decision outcome."""
    narratives = {
        "safe_launch": "You protect your position off the line, playing it safe into Turn 1.",
        "balanced_launch": "You race hard but fair into Turn 1, holding your own.",
        "aggressive_launch": "You attack immediately and gain ground, but use up your tyres.",
        "pit_now": "You dive into the pits for fresh rubber.",
        "stay_out": "You stay out to maintain track position.",
        "engineer_recommendation": "You follow your engineer's strategy call.",
        "push_for_heat": "You push hard to get temperature into the tyres.",
        "build_temperature": "You take a measured approach to building tyre temperature.",
        "stay_wide": "You stay wide to avoid the slippery painted kerbs.",
        "keep_pushing": "You keep the pressure on despite the tyre warnings.",
        "manage_tires": "You manage your inputs through the traction zones.",
        "cool_tires": "You back off to let the tyres recover.",
        "send_inside": "You commit to the inside line and make the move!",
        "wait_for_drs": "You wait for the DRS straight to make your move.",
        "save_tires": "You decide to save the tyres for a later attack.",
        "keep_engine_pushing": "You keep pushing on full deployment, accepting the component risk.",
        "lift_and_coast": "You lift and coast to protect the power unit without giving up too much pace.",
        "cool_power_unit": "You back off to bring power unit temperatures under control.",
        "cover_inside": "You cover the inside line to defend your position.",
        "break_drs": "You push hard to break DRS range.",
        "save_race": "You don't over-defend, keeping the race clean.",
        "all_in": "You use everything the car has left for these final laps.",
        "bring_it_home": "You bring the car home cleanly, securing the result.",
        "defensive_margin": "You focus on clean exits to maintain your gap.",
    }
    return narratives.get(choice.id, f"You chose: {choice.label}")


def _runner_for(runners: list[Runner], driver_id: str | None) -> Runner | None:
    """Find a runner by driver ID."""
    if driver_id is None:
        return None
    return next((r for r in runners if r.driver.id == driver_id), None)


def _position_of(runners: list[Runner], driver_id: str | None) -> int | None:
    """Get the position of a driver."""
    if driver_id is None:
        return None
    for index, runner in enumerate(runners, start=1):
        if runner.driver.id == driver_id:
            return index
    return None


def _gap_to_car_ahead(runners: list[Runner], position: int) -> float | None:
    """Get the gap to the car ahead."""
    if position <= 1:
        return None
    return max(0, runners[position - 1].cumulative_time - runners[position - 2].cumulative_time)


def _gap_to_car_behind(runners: list[Runner], position: int) -> float | None:
    """Get the gap to the car behind."""
    if position >= len(runners):
        return None
    return max(0, runners[position].cumulative_time - runners[position - 1].cumulative_time)


def _get_weather(track: Track, rng: random.Random) -> WeatherState:
    """Generate weather for the race."""
    rain_roll = rng.randint(1, 100)
    if rain_roll <= track.rain_chance // 3:
        rain = rng.randint(45, 80)
        return WeatherState(condition="wet", air_temp=20, track_temp=24, rain_intensity=rain, track_grip=max(28, 64 - rain // 2))
    if rain_roll <= track.rain_chance:
        rain = rng.randint(15, 40)
        return WeatherState(condition="damp", air_temp=22, track_temp=27, rain_intensity=rain, track_grip=max(48, 74 - rain // 3))
    return WeatherState(condition="dry", air_temp=rng.randint(23, 32), track_temp=rng.randint(31, 44), track_grip=rng.randint(68, 78))


def _evolve_weather(
    weather: WeatherState,
    track: Track,
    lap: int,
    total_laps: int,
    rng: random.Random,
    commentary: list[str],
) -> WeatherState:
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


def _find_round(save: SaveGame, round_id: str) -> CalendarRound:
    """Find a calendar round by ID."""
    return next(r for r in save.calendar if r.id == round_id)


def _find_track(track_id: str) -> Track:
    """Find a track by ID."""
    from app.data.loaders import get_tracks

    return next(t for t in get_tracks() if t.id == track_id)


def _lap_snapshot(
    lap: int,
    runners: list[Runner],
    commentary: list[str],
    safety_car: bool,
    weather: WeatherState,
    decision_prompt: DecisionPrompt | None,
) -> LapSnapshot:
    """Create a lap snapshot."""
    leader_time = next((r.cumulative_time for r in runners if r.status == "running"), runners[0].cumulative_time)
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
                tire_compound=runner.tire_compound,  # type: ignore
                tire_age=runner.tire_age,
                tire_wear=round(runner.tire_wear, 2),
                component_wear=round(runner.component_wear, 2),
                status=runner.status,  # type: ignore
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
