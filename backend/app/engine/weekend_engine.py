import random
from dataclasses import dataclass

from app.models.calendar import CalendarRound
from app.models.driver import Driver
from app.models.race import (
    LapSnapshot,
    PracticeClassification,
    PracticeResult,
    QualifyingClassification,
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
    driver: Driver
    team: Team
    cumulative_time: float = 0
    fastest_lap: float = 999
    tire_compound: str = "medium"
    tire_age: int = 0
    tire_wear: float = 0
    pit_stops: int = 0
    status: str = "running"


def simulate_weekend(save: SaveGame, round_id: str) -> WeekendResult:
    calendar_round = _find_round(save, round_id)
    track = _find_track(save, calendar_round.track_id)
    drivers = [driver for driver in save.drivers if driver.series == "F2"]
    teams = {team.id: team for team in save.teams}
    rng = random.Random(f"{save.random_seed}:{round_id}")
    weather = _weather(track, rng)

    practice = _simulate_practice(drivers, teams, track, weather, rng)
    qualifying = _simulate_qualifying(drivers, teams, track, weather, rng)
    qualifying_order = [entry.driver_id for entry in qualifying.classification]
    sprint_grid = list(reversed(qualifying_order[:10])) + qualifying_order[10:]
    sprint = _simulate_race("sprint", sprint_grid, drivers, teams, track, weather, rng)
    feature = _simulate_race("feature", qualifying_order, drivers, teams, track, weather, rng)

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


def _simulate_practice(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
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
    )


def _simulate_qualifying(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> QualifyingResult:
    rows: list[tuple[float, Driver, str]] = []
    for driver in drivers:
        team = teams[driver.team_id]
        traffic = rng.random() < 0.08
        mistake = rng.random() > (driver.attributes.consistency + driver.attributes.discipline) / 210
        lap_time = _single_lap_time(driver, team, track, weather, rng)
        if traffic:
            lap_time += rng.uniform(0.25, 0.85)
        if mistake:
            lap_time += rng.uniform(0.35, 1.2)
        rows.append((lap_time, driver, _qualifying_note(traffic, mistake)))

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
    )


def _simulate_race(
    session_type: str,
    starting_grid: list[str],
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    weather: WeatherState,
    rng: random.Random,
) -> RaceResult:
    driver_map = {driver.id: driver for driver in drivers}
    runners = [Runner(driver=driver_map[driver_id], team=teams[driver_map[driver_id].team_id]) for driver_id in starting_grid]
    total_laps = 12 if session_type == "sprint" else 24
    points_table = SPRINT_POINTS if session_type == "sprint" else FEATURE_POINTS
    lap_log: list[LapSnapshot] = []
    safety_car_laps: list[int] = []
    dnfs: list[str] = []
    safety_car_remaining = 0

    for lap in range(1, total_laps + 1):
        commentary: list[str] = []
        if safety_car_remaining == 0 and rng.randint(1, 100) <= max(2, track.safety_car_chance // 18):
            safety_car_remaining = rng.randint(1, 2)
            commentary.append("Safety Car deployed after debris is reported near the racing line.")

        safety_car = safety_car_remaining > 0
        if safety_car:
            safety_car_laps.append(lap)

        for runner in runners:
            if runner.status == "dnf":
                continue

            reliability_roll = runner.team.reliability + runner.driver.attributes.awareness * 0.15 - track.safety_car_chance * 0.08
            if rng.random() < max(0.002, (72 - reliability_roll) / 4000):
                runner.status = "dnf"
                dnfs.append(runner.driver.id)
                commentary.append(f"{runner.driver.name} is out with a mechanical issue.")
                continue

            lap_time = _race_lap_time(runner, track, weather, rng, safety_car)
            runner.cumulative_time += lap_time
            runner.fastest_lap = min(runner.fastest_lap, lap_time)
            runner.tire_age += 1
            runner.tire_wear = min(100, runner.tire_wear + track.tire_deg / (22 if session_type == "sprint" else 34))

            if session_type == "feature" and runner.pit_stops == 0 and lap > total_laps // 2 and runner.tire_wear > 46:
                runner.cumulative_time += 22 + rng.uniform(-0.8, 1.8)
                runner.pit_stops += 1
                runner.tire_age = 0
                runner.tire_wear = 0
                runner.tire_compound = "hard"
                if runner.driver.id == "player_driver":
                    commentary.append("You pit for hard tyres and rejoin in traffic.")

        runners.sort(key=lambda runner: (runner.status == "dnf", runner.cumulative_time))
        if not safety_car and lap in {1, total_laps // 2, total_laps}:
            player_position = _position_of(runners, "player_driver")
            if player_position is not None:
                commentary.append(f"You cross lap {lap} in P{player_position}.")

        lap_log.append(_lap_snapshot(lap, runners, commentary, safety_car, weather))
        safety_car_remaining = max(0, safety_car_remaining - 1)

    classified = [runner for runner in runners if runner.status == "running"] + [
        runner for runner in runners if runner.status == "dnf"
    ]
    winner_time = next((runner.cumulative_time for runner in classified if runner.status == "running"), classified[0].cumulative_time)
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
                points=points_table.get(index, 0) if runner.status == "running" else 0,
                pit_stops=runner.pit_stops,
                fastest_lap=round(runner.fastest_lap, 3),
            )
            for index, runner in enumerate(classified, start=1)
        ],
        lap_log=lap_log,
        safety_car_laps=safety_car_laps,
        dnfs=dnfs,
    )


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
    team_score = team.car_performance * 0.7 + team.strategy * 0.15 + setup_bonus * 0.15
    weather_penalty = weather.rain_intensity * (105 - driver.attributes.wet_weather) / 900
    return track.base_lap_time + (90 - driver_score) * 0.045 + (90 - team_score) * 0.035 + weather_penalty + rng.uniform(-0.28, 0.28)


def _race_lap_time(
    runner: Runner,
    track: Track,
    weather: WeatherState,
    rng: random.Random,
    safety_car: bool,
) -> float:
    if safety_car:
        return track.base_lap_time * 1.32 + rng.uniform(-0.4, 0.4)

    driver = runner.driver
    team = runner.team
    wet_skill = driver.attributes.wet_weather if weather.condition != "dry" else driver.attributes.pace
    race_score = driver.attributes.pace * 0.28 + driver.attributes.racecraft * 0.24 + driver.attributes.consistency * 0.18 + driver.attributes.tire_management * 0.12 + wet_skill * 0.1
    team_score = team.car_performance * 0.62 + team.strategy * 0.2 + team.reliability * 0.18
    tire_penalty = runner.tire_wear * (104 - driver.attributes.tire_management) / 2200
    weather_penalty = weather.rain_intensity * (105 - driver.attributes.wet_weather) / 1000
    return track.base_lap_time + (90 - race_score) * 0.04 + (90 - team_score) * 0.035 + tire_penalty + weather_penalty + rng.uniform(-0.35, 0.4)


def _lap_snapshot(
    lap: int,
    runners: list[Runner],
    commentary: list[str],
    safety_car: bool,
    weather: WeatherState,
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
                tire_compound=runner.tire_compound,  # type: ignore[arg-type]
                tire_age=runner.tire_age,
                tire_wear=round(runner.tire_wear, 2),
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
    )


def _weather(track: Track, rng: random.Random) -> WeatherState:
    rain_roll = rng.randint(1, 100)
    if rain_roll <= track.rain_chance // 3:
        return WeatherState(condition="wet", air_temp=20, track_temp=24, rain_intensity=rng.randint(45, 80))
    if rain_roll <= track.rain_chance:
        return WeatherState(condition="damp", air_temp=22, track_temp=27, rain_intensity=rng.randint(15, 40))
    return WeatherState(condition="dry", air_temp=rng.randint(23, 32), track_temp=rng.randint(31, 44))


def _headline(save: SaveGame, feature: RaceResult) -> str:
    winner = next(driver for driver in save.drivers if driver.id == feature.classification[0].driver_id)
    player = next((row for row in feature.classification if row.driver_id == save.player_driver_id), None)
    if player and player.position <= 3:
        return f"{winner.name} wins as your F2 debut lands on the podium"
    if player and player.points > 0:
        return f"{winner.name} wins while you bank points in the F2 opener"
    if player:
        return f"{winner.name} controls the feature as your debut ends P{player.position}"
    return f"{winner.name} wins the F2 feature race"


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
