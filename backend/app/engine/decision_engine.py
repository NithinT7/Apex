"""Engine for interactive race decisions."""

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


SPRINT_POINTS = {1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
FEATURE_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}


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
    track: Track
    weather: WeatherState
    runners: list[Runner]
    rng: random.Random
    current_lap: int = 0
    total_laps: int = 24
    lap_snapshots: list[LapSnapshot] = field(default_factory=list)
    decision_history: list[DecisionOutcome] = field(default_factory=list)
    safety_car_remaining: int = 0
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
    drivers = [driver for driver in save.drivers if driver.series == "F2"]
    teams = {team.id: team for team in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}:{race_type}")

    # Determine starting grid
    qualifying_order = [entry.driver_id for entry in qualifying.classification]
    if race_type == "sprint":
        # Reverse top 10 for sprint
        starting_grid = list(reversed(qualifying_order[:10])) + qualifying_order[10:]
    else:
        starting_grid = qualifying_order

    # Create runners
    driver_map = {driver.id: driver for driver in drivers}
    runners = [
        Runner(driver=driver_map[driver_id], team=teams[driver_map[driver_id].team_id])
        for driver_id in starting_grid
    ]

    total_laps = 12 if race_type == "sprint" else 24
    weather = _get_weather(track, rng)

    # Store internal state in save game's event_flags for persistence
    internal_state = InteractiveRaceState(
        save_id=save.save_id,
        round_id=round_id,
        race_type=race_type,
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

    while internal_state.current_lap < internal_state.total_laps:
        internal_state.current_lap += 1
        lap = internal_state.current_lap

        commentary: list[str] = []
        decision_prompt: DecisionPrompt | None = None

        # Check for safety car
        if internal_state.safety_car_remaining == 0:
            sc_chance = max(2, internal_state.track.safety_car_chance // 18)
            if internal_state.rng.randint(1, 100) <= sc_chance:
                internal_state.safety_car_remaining = internal_state.rng.randint(1, 2)
                commentary.append("Safety Car deployed after debris is reported.")

        safety_car = internal_state.safety_car_remaining > 0
        if safety_car:
            internal_state.safety_car_laps.append(lap)

        # Simulate all runners
        for runner in internal_state.runners:
            if runner.status == "dnf":
                continue

            # Check for DNF
            reliability_roll = (
                runner.team.reliability
                + runner.driver.attributes.awareness * 0.15
                - internal_state.track.safety_car_chance * 0.08
            )
            if internal_state.rng.random() < max(0.002, (72 - reliability_roll) / 4000):
                runner.status = "dnf"
                internal_state.dnfs.append(runner.driver.id)
                commentary.append(f"{runner.driver.name} is out with a mechanical issue.")
                continue

            # Calculate lap time with modifiers
            lap_time = _race_lap_time(runner, internal_state.track, internal_state.weather, internal_state.rng, safety_car)

            # Apply decision modifiers for player
            if runner.driver.id == player_driver_id and runner.modifier_laps_remaining > 0:
                lap_time += runner.pace_modifier
                runner.modifier_laps_remaining -= 1

            runner.cumulative_time += lap_time
            runner.fastest_lap = min(runner.fastest_lap, lap_time)
            runner.tire_age += 1

            # Tire wear with modifier
            base_wear = internal_state.track.tire_deg / (22 if race_type == "sprint" else 34)
            extra_wear = runner.tire_wear_modifier if runner.driver.id == player_driver_id else 0
            runner.tire_wear = min(100, runner.tire_wear + base_wear + extra_wear)

            # Auto-pit in feature race
            if (
                race_type == "feature"
                and runner.pit_stops == 0
                and lap > internal_state.total_laps // 2
                and runner.tire_wear > 46
            ):
                runner.cumulative_time += 22 + internal_state.rng.uniform(-0.8, 1.8)
                runner.pit_stops += 1
                runner.tire_age = 0
                runner.tire_wear = 0
                runner.tire_compound = "hard"
                if runner.driver.id == player_driver_id:
                    commentary.append("You pit for hard tyres and rejoin in traffic.")

        # Sort by cumulative time
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

        player_runner.pace_modifier = pace_delta
        player_runner.tire_wear_modifier = tire_wear_delta / 3  # Spread over 3 laps
        player_runner.modifier_laps_remaining = 3

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

    # Continue simulation
    return simulate_to_next_decision(save, round_id, race_type)


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

        # Safety car check
        if internal_state.safety_car_remaining == 0:
            sc_chance = max(2, internal_state.track.safety_car_chance // 18)
            if internal_state.rng.randint(1, 100) <= sc_chance:
                internal_state.safety_car_remaining = internal_state.rng.randint(1, 2)
                commentary.append("Safety Car deployed.")

        safety_car = internal_state.safety_car_remaining > 0
        if safety_car:
            internal_state.safety_car_laps.append(lap)

        # Simulate runners
        for runner in internal_state.runners:
            if runner.status == "dnf":
                continue

            reliability_roll = runner.team.reliability + runner.driver.attributes.awareness * 0.15
            if internal_state.rng.random() < max(0.002, (72 - reliability_roll) / 4000):
                runner.status = "dnf"
                internal_state.dnfs.append(runner.driver.id)
                commentary.append(f"{runner.driver.name} retires.")
                continue

            lap_time = _race_lap_time(runner, internal_state.track, internal_state.weather, internal_state.rng, safety_car)
            runner.cumulative_time += lap_time
            runner.fastest_lap = min(runner.fastest_lap, lap_time)
            runner.tire_age += 1
            runner.tire_wear = min(100, runner.tire_wear + internal_state.track.tire_deg / 30)

            # Auto-pit
            if (
                race_type == "feature"
                and runner.pit_stops == 0
                and lap > internal_state.total_laps // 2
                and runner.tire_wear > 46
            ):
                runner.cumulative_time += 22 + internal_state.rng.uniform(-0.8, 1.8)
                runner.pit_stops += 1
                runner.tire_age = 0
                runner.tire_wear = 0
                runner.tire_compound = "hard"

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
            )
            if decision_prompt and lap - internal_state.last_prompt_lap >= 3:
                _apply_default_decision(player_runner, decision_prompt)
                internal_state.last_prompt_lap = lap
                commentary.append(f"Auto-decision: {decision_prompt.title}")

        lap_snapshot = _lap_snapshot(lap, internal_state.runners, commentary, safety_car, internal_state.weather, None)
        internal_state.lap_snapshots.append(lap_snapshot)
        internal_state.safety_car_remaining = max(0, internal_state.safety_car_remaining - 1)

    internal_state.is_complete = True

    # Build final result
    return _build_race_result(internal_state)


def _build_race_result(state: InteractiveRaceState) -> RaceResult:
    """Build the final RaceResult from internal state."""
    points_table = SPRINT_POINTS if state.race_type == "sprint" else FEATURE_POINTS

    classified = [r for r in state.runners if r.status == "running"] + [
        r for r in state.runners if r.status == "dnf"
    ]

    winner_time = next(
        (r.cumulative_time for r in classified if r.status == "running"),
        classified[0].cumulative_time if classified else 0,
    )

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
                points=points_table.get(index, 0) if runner.status == "running" else 0,
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
        return track.base_lap_time * 1.32 + rng.uniform(-0.4, 0.4)

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
    team_score = team.car_performance * 0.62 + team.strategy * 0.2 + team.reliability * 0.18
    tire_penalty = runner.tire_wear * (104 - driver.attributes.tire_management) / 2200
    weather_penalty = weather.rain_intensity * (105 - driver.attributes.wet_weather) / 1000

    return (
        track.base_lap_time
        + (90 - race_score) * 0.04
        + (90 - team_score) * 0.035
        + tire_penalty
        + weather_penalty
        + rng.uniform(-0.35, 0.4)
    )


def _maybe_decision_prompt(
    race_type: str,
    lap: int,
    total_laps: int,
    runners: list[Runner],
    player_runner: Runner,
    safety_car: bool,
    weather: WeatherState,
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
                    effects={"paceDelta": 0.1, "incidentRisk": -8},
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
                    effects={"paceDelta": -0.18, "tireWear": 3, "incidentRisk": 8},
                ),
            ],
        )

    # Safety car pit decision
    if safety_car and race_type == "feature" and lap > total_laps // 3:
        return DecisionPrompt(
            id=f"{race_type}_lap_{lap}_safety_car",
            lap=lap,
            type="safety_car",
            title="Safety Car Window",
            description="The safety car is out. Pit lane is open.",
            default_choice_id="engineer_recommendation",
            choices=[
                DecisionChoice(
                    id="pit_now",
                    label="Pit now for fresh tyres",
                    risk=45,
                    effects={"pitPreference": "early"},
                ),
                DecisionChoice(
                    id="stay_out",
                    label="Stay out and keep position",
                    risk=55,
                    effects={"trackPosition": 1, "tireWear": 6},
                ),
                DecisionChoice(
                    id="engineer_recommendation",
                    label="Follow engineer advice",
                    risk=30,
                    effects={"strategyConfidence": 4},
                ),
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
                    effects={"paceDelta": -0.12, "incidentRisk": 6},
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
                    effects={"paceDelta": 0.14, "incidentRisk": -7},
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
                    effects={"paceDelta": -0.08, "tireWear": 8},
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
                    effects={"paceDelta": 0.25, "tireWear": -12},
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
                    effects={"paceDelta": -0.2, "tireWear": 5, "incidentRisk": 12},
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
                    effects={"paceDelta": 0.12, "tireWear": -5},
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
                    effects={"paceDelta": -0.12, "tireWear": 5},
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
                    effects={"paceDelta": -0.18, "tireWear": 6},
                ),
                DecisionChoice(
                    id="bring_it_home",
                    label="Bring it home cleanly",
                    risk=24,
                    effects={"paceDelta": 0.04, "incidentRisk": -5},
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


def _apply_default_decision(player_runner: Runner, prompt: DecisionPrompt) -> None:
    """Apply the default decision choice to a runner."""
    choice = next(c for c in prompt.choices if c.id == prompt.default_choice_id)
    pace_delta = float(choice.effects.get("paceDelta", 0))
    tire_wear_delta = float(choice.effects.get("tireWear", 0))
    player_runner.cumulative_time += max(-0.35, min(0.35, pace_delta))
    player_runner.tire_wear = max(0, min(100, player_runner.tire_wear + tire_wear_delta))


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
        return WeatherState(condition="wet", air_temp=20, track_temp=24, rain_intensity=rng.randint(45, 80))
    if rain_roll <= track.rain_chance:
        return WeatherState(condition="damp", air_temp=22, track_temp=27, rain_intensity=rng.randint(15, 40))
    return WeatherState(condition="dry", air_temp=rng.randint(23, 32), track_temp=rng.randint(31, 44))


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
                tire_compound=runner.tire_compound,  # type: ignore
                tire_age=runner.tire_age,
                tire_wear=round(runner.tire_wear, 2),
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
