from __future__ import annotations

import argparse
import random
import sys
from dataclasses import dataclass
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.data.loaders import get_f1_drivers, get_f1_teams, get_tracks  # noqa: E402
from app.models.driver import Driver  # noqa: E402
from app.models.team import Team  # noqa: E402
from app.models.track import Track  # noqa: E402


F1_2026_TRACK_IDS = [
    "melbourne",
    "shanghai",
    "suzuka",
    "miami",
    "montreal",
    "monaco",
    "barcelona",
    "spielberg",
    "silverstone",
    "spa",
    "budapest",
    "zandvoort",
    "monza",
    "madrid",
    "baku",
    "singapore",
    "cota",
    "mexico_city",
    "interlagos",
    "las_vegas",
    "lusail",
    "yas_marina",
]

F1_POINTS = {1: 25, 2: 18, 3: 15, 4: 12, 5: 10, 6: 8, 7: 6, 8: 4, 9: 2, 10: 1}


@dataclass
class DriverStanding:
    driver: Driver
    points: int = 0
    wins: int = 0
    podiums: int = 0
    dnfs: int = 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate a standalone 2026 F1 season.")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--rounds", type=int, default=len(F1_2026_TRACK_IDS))
    args = parser.parse_args()

    rng = random.Random(args.seed)
    teams = {team.id: team for team in get_f1_teams()}
    tracks = {track.id: track for track in get_tracks()}
    drivers = get_f1_drivers()
    standings = {driver.id: DriverStanding(driver=driver) for driver in drivers}

    print(f"Standalone F1 season simulation, seed {args.seed}")
    print("=" * 72)

    for round_number, track_id in enumerate(F1_2026_TRACK_IDS[: args.rounds], start=1):
        track = tracks[track_id]
        result = simulate_grand_prix(drivers, teams, track, rng)
        winner = result[0]
        print(
            f"R{round_number:02d} {track.name}: "
            f"{winner.name} wins from {teams[winner.team_id].name}"
        )

        for position, driver in enumerate(result, start=1):
            standing = standings[driver.id]
            standing.points += F1_POINTS.get(position, 0)
            standing.wins += 1 if position == 1 else 0
            standing.podiums += 1 if position <= 3 else 0

    print()
    print("Drivers")
    print("-" * 72)
    for position, standing in enumerate(
        sorted(standings.values(), key=lambda row: (row.points, row.wins, row.podiums), reverse=True),
        start=1,
    ):
        print(
            f"{position:>2}. {standing.driver.name:<24} "
            f"{standing.points:>3} pts  W {standing.wins:<2} P {standing.podiums:<2}"
        )

    print()
    print("Constructors")
    print("-" * 72)
    constructor_points = {team.id: 0 for team in teams.values()}
    for standing in standings.values():
        constructor_points[standing.driver.team_id] += standing.points
    for position, (team_id, points) in enumerate(
        sorted(constructor_points.items(), key=lambda item: item[1], reverse=True),
        start=1,
    ):
        print(f"{position:>2}. {teams[team_id].name:<24} {points:>3} pts")


def simulate_grand_prix(
    drivers: list[Driver],
    teams: dict[str, Team],
    track: Track,
    rng: random.Random,
) -> list[Driver]:
    qualifying = sorted(
        drivers,
        key=lambda driver: qualifying_score(driver, teams[driver.team_id], track, rng),
        reverse=True,
    )

    race_rows = []
    for grid_position, driver in enumerate(qualifying, start=1):
        team = teams[driver.team_id]
        score = race_score(driver, team, track, rng) - grid_position * track.qualifying_importance / 420
        dnf_chance = max(0.005, (78 - team.reliability) / 500 + driver.hidden.crash_proneness / 2500)
        if rng.random() < dnf_chance:
            score -= 100
        race_rows.append((score, driver))

    race_rows.sort(key=lambda row: row[0], reverse=True)
    return [driver for _, driver in race_rows]


def qualifying_score(driver: Driver, team: Team, track: Track, rng: random.Random) -> float:
    return (
        driver.attributes.qualifying * 0.42
        + driver.attributes.pace * 0.26
        + driver.attributes.adaptability * 0.12
        + team.car_performance * 0.18
        + track.qualifying_importance * 0.03
        + rng.uniform(-4.0, 4.0)
    )


def race_score(driver: Driver, team: Team, track: Track, rng: random.Random) -> float:
    tire_factor = driver.attributes.tire_management * track.tire_deg / 100
    wet_factor = driver.attributes.wet_weather * track.rain_chance / 100
    return (
        driver.attributes.pace * 0.24
        + driver.attributes.racecraft * 0.22
        + driver.attributes.consistency * 0.18
        + tire_factor * 0.1
        + wet_factor * 0.08
        + team.car_performance * 0.18
        + team.strategy * 0.07
        + team.reliability * 0.04
        + rng.uniform(-5.0, 5.0)
    )


if __name__ == "__main__":
    main()
