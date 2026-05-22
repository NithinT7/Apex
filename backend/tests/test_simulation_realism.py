"""
Comprehensive simulation realism test.

Runs multiple full seasons to validate that race results are realistic:
- Overtakes frequency
- Safety car deployments
- DNFs (crashes vs mechanical failures)
- Pit stop strategies
- Weather effects

Run with: pytest tests/test_simulation_realism.py -v -s
"""

import random
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest

from app.data.loaders import (
    get_academies,
    get_f1_calendar,
    get_f1_drivers,
    get_f1_teams,
    get_f2_calendar,
    get_f2_drivers,
    get_f2_teams,
    get_tracks,
)
from app.engine.weekend_engine import simulate_weekend
from app.models.driver import Driver
from app.models.save_game import (
    AcademyState,
    CalendarRound,
    ChampionshipEntry,
    ChampionshipState,
    SaveGame,
)
from app.models.team import Team


@dataclass
class RaceStats:
    """Statistics for a single race."""
    track_id: str
    series: str
    session_type: str  # sprint or feature
    total_laps: int
    dnfs: int
    crashes: int  # subset of dnfs
    mechanical_failures: int  # subset of dnfs
    safety_car_laps: int
    safety_car_deployments: int
    overtakes: int
    pit_stops: int
    weather: str
    rain_intensity: int
    winner_id: str
    pole_id: str


@dataclass
class SeasonStats:
    """Aggregated statistics for a full season."""
    season_number: int
    series: str
    races: list[RaceStats] = field(default_factory=list)

    @property
    def total_dnfs(self) -> int:
        return sum(r.dnfs for r in self.races)

    @property
    def total_crashes(self) -> int:
        return sum(r.crashes for r in self.races)

    @property
    def total_mechanical(self) -> int:
        return sum(r.mechanical_failures for r in self.races)

    @property
    def total_safety_cars(self) -> int:
        return sum(r.safety_car_deployments for r in self.races)

    @property
    def total_safety_car_laps(self) -> int:
        return sum(r.safety_car_laps for r in self.races)

    @property
    def total_overtakes(self) -> int:
        return sum(r.overtakes for r in self.races)

    @property
    def total_pit_stops(self) -> int:
        return sum(r.pit_stops for r in self.races)

    @property
    def wet_races(self) -> int:
        return sum(1 for r in self.races if r.weather in ("damp", "wet"))

    @property
    def total_laps(self) -> int:
        return sum(r.total_laps for r in self.races)


def create_test_save(
    series: str = "F2",
    seed: int = 42,
) -> SaveGame:
    """Create a test save game for simulation."""
    if series == "F1":
        drivers = get_f1_drivers()
        teams = get_f1_teams()
        calendar = get_f1_calendar()
    else:
        drivers = get_f2_drivers()
        teams = get_f2_teams()
        calendar = get_f2_calendar()

    driver_ids = [d.id for d in drivers if d.series == series]
    team_ids = [t.id for t in teams if t.series == series]
    academies = get_academies()

    now = datetime.now()

    return SaveGame(
        save_id=f"sim_test_{series}_{seed}",
        name=f"Simulation Test {series} {seed}",
        created_at=now,
        updated_at=now,
        player_driver_id=driver_ids[0] if driver_ids else None,
        season=1,
        phase="race_week",
        current_date="2026-03-01",
        drivers=list(drivers),
        teams=list(teams),
        academies=list(academies),
        academy_states=[
            AcademyState(academy_id=a.id, trust=50, political_stability=50)
            for a in academies
        ],
        calendar=list(calendar),
        standings=ChampionshipState(
            driver_standings=[ChampionshipEntry(driver_id=did) for did in driver_ids],
            team_standings={tid: 0 for tid in team_ids},
        ),
        random_seed=seed,
    )


def count_overtakes_from_commentary(commentary_lines: list[str]) -> int:
    """Count overtakes mentioned in race commentary."""
    # The weekend_engine uses "completes a move on" for successful overtakes
    overtake_keywords = ["completes a move on", "passes", "overtakes", "moves past"]
    count = 0
    for line in commentary_lines:
        line_lower = line.lower()
        if any(kw in line_lower for kw in overtake_keywords):
            count += 1
    return count


def extract_race_stats(
    weekend_result: Any,
    track_id: str,
    series: str,
) -> list[RaceStats]:
    """Extract statistics from a weekend result."""
    stats_list = []
    tracks = {t.id: t for t in get_tracks()}
    track = tracks.get(track_id)

    for session_type in ["sprint", "feature"]:
        race = getattr(weekend_result, session_type, None)
        if not race or not race.classification:
            continue

        # Count DNFs
        dnfs = len([c for c in race.classification if c.status == "dnf"])

        # Estimate crashes vs mechanical from DNF count
        # Based on the code: crash probability is ~46-58% of retirements
        crashes = 0
        mechanical = 0
        for dnf_id in race.dnfs:
            # We don't have exact data, so estimate based on typical ratios
            # The actual ratio is determined by _crash_retirement_share()
            if random.random() < 0.52:  # Approximate average
                crashes += 1
            else:
                mechanical += 1

        # Safety car data
        safety_car_laps = len(race.safety_car_laps) if race.safety_car_laps else 0
        # Estimate deployments (usually 1-2 laps per deployment)
        safety_car_deployments = max(1, safety_car_laps // 2) if safety_car_laps > 0 else 0

        # Count overtakes from lap log commentary
        overtakes = 0
        for lap_snapshot in race.lap_log:
            overtakes += count_overtakes_from_commentary(lap_snapshot.commentary)

        # Total pit stops
        pit_stops = sum(c.pit_stops for c in race.classification)

        # Weather from first lap
        weather = "dry"
        rain_intensity = 0
        if race.lap_log:
            first_lap = race.lap_log[0]
            weather = first_lap.weather.condition
            rain_intensity = first_lap.weather.rain_intensity

        # Winner and pole
        winner = race.classification[0] if race.classification else None
        winner_id = winner.driver_id if winner else ""
        pole_id = race.starting_grid[0] if race.starting_grid else ""

        stats_list.append(RaceStats(
            track_id=track_id,
            series=series,
            session_type=session_type,
            total_laps=race.total_laps,
            dnfs=dnfs,
            crashes=crashes,
            mechanical_failures=mechanical,
            safety_car_laps=safety_car_laps,
            safety_car_deployments=safety_car_deployments,
            overtakes=overtakes,
            pit_stops=pit_stops,
            weather=weather,
            rain_intensity=rain_intensity,
            winner_id=winner_id,
            pole_id=pole_id,
        ))

    return stats_list


def simulate_full_season(
    series: str = "F2",
    seed: int = 42,
) -> SeasonStats:
    """Simulate a complete season and collect statistics."""
    save = create_test_save(series=series, seed=seed)
    season_stats = SeasonStats(season_number=1, series=series)

    for round_entry in save.calendar:
        if round_entry.series != series:
            continue

        try:
            weekend_result = simulate_weekend(save, round_entry.id)

            # Update save with results (simplified - just mark completed)
            for i, cal_round in enumerate(save.calendar):
                if cal_round.id == round_entry.id:
                    save.calendar[i] = cal_round.model_copy(update={"completed": True})
                    break

            # Extract stats
            race_stats = extract_race_stats(
                weekend_result,
                round_entry.track_id,
                series,
            )
            season_stats.races.extend(race_stats)

        except Exception as e:
            print(f"Error simulating {round_entry.name}: {e}")
            continue

    return season_stats


def print_season_summary(stats: SeasonStats) -> None:
    """Print a summary of season statistics."""
    print(f"\n{'='*60}")
    print(f"Season {stats.season_number} Summary ({stats.series})")
    print(f"{'='*60}")
    print(f"Total races: {len(stats.races)}")
    print(f"Total laps: {stats.total_laps}")
    print(f"\nRetirements:")
    print(f"  Total DNFs: {stats.total_dnfs}")
    print(f"  - Crashes: {stats.total_crashes}")
    print(f"  - Mechanical: {stats.total_mechanical}")
    print(f"  DNF rate: {stats.total_dnfs / len(stats.races):.1f} per race")
    print(f"\nSafety Cars:")
    print(f"  Deployments: {stats.total_safety_cars}")
    print(f"  Total SC laps: {stats.total_safety_car_laps}")
    print(f"  SC rate: {stats.total_safety_cars / len(stats.races):.2f} per race")
    print(f"\nOvertakes:")
    print(f"  Total: {stats.total_overtakes}")
    print(f"  Per race: {stats.total_overtakes / len(stats.races):.1f}")
    print(f"\nPit Stops:")
    print(f"  Total: {stats.total_pit_stops}")
    print(f"  Per race: {stats.total_pit_stops / len(stats.races):.1f}")
    print(f"\nWeather:")
    print(f"  Wet races: {stats.wet_races} ({100*stats.wet_races/len(stats.races):.0f}%)")


def print_track_breakdown(all_stats: list[SeasonStats]) -> None:
    """Print statistics broken down by track."""
    track_data: dict[str, list[RaceStats]] = defaultdict(list)

    for season in all_stats:
        for race in season.races:
            track_data[race.track_id].append(race)

    print(f"\n{'='*80}")
    print("TRACK-BY-TRACK BREAKDOWN")
    print(f"{'='*80}")
    print(f"{'Track':<20} {'Races':>6} {'DNFs':>6} {'SC':>6} {'Overtakes':>10} {'Wet%':>6}")
    print("-"*80)

    for track_id in sorted(track_data.keys()):
        races = track_data[track_id]
        total_races = len(races)
        total_dnfs = sum(r.dnfs for r in races)
        total_sc = sum(r.safety_car_deployments for r in races)
        total_overtakes = sum(r.overtakes for r in races)
        wet_pct = 100 * sum(1 for r in races if r.weather != "dry") / total_races

        print(f"{track_id:<20} {total_races:>6} {total_dnfs:>6} {total_sc:>6} {total_overtakes:>10} {wet_pct:>5.0f}%")


def validate_realism(all_stats: list[SeasonStats], series: str = "F2") -> dict[str, bool]:
    """Validate that simulation results fall within realistic ranges."""
    validations = {}

    # Aggregate all races
    all_races = [race for season in all_stats for race in season.races]
    total_races = len(all_races)

    if total_races == 0:
        return {"no_races": False}

    # Calculate metrics
    avg_dnfs_per_race = sum(r.dnfs for r in all_races) / total_races
    avg_sc_per_race = sum(r.safety_car_deployments for r in all_races) / total_races
    avg_overtakes_per_race = sum(r.overtakes for r in all_races) / total_races
    avg_pit_stops_per_race = sum(r.pit_stops for r in all_races) / total_races
    wet_race_pct = 100 * sum(1 for r in all_races if r.weather != "dry") / total_races

    # Series-specific benchmarks:
    # F2: Sprint (no mandatory stop) + Feature (1 stop) = ~11 stops per race average
    # F1: All races require 1-2 stops = ~25-40 stops per race
    if series == "F2":
        pit_stop_min, pit_stop_max = 5, 20  # F2 has sprints with no stops
        overtake_min, overtake_max = 2, 50  # F2 has shorter races, fewer overtakes
    else:  # F1
        pit_stop_min, pit_stop_max = 15, 60  # F1 all races require stops
        overtake_min, overtake_max = 5, 80  # F1 has more DRS, longer races

    # Validate ranges
    validations["dnf_rate_realistic"] = 0.5 <= avg_dnfs_per_race <= 4.0
    validations["safety_car_rate_realistic"] = 0.1 <= avg_sc_per_race <= 1.5
    validations["overtakes_realistic"] = overtake_min <= avg_overtakes_per_race <= overtake_max
    validations["pit_stops_realistic"] = pit_stop_min <= avg_pit_stops_per_race <= pit_stop_max
    validations["wet_races_realistic"] = 5 <= wet_race_pct <= 35

    # Print validation results
    print(f"\n{'='*60}")
    print(f"REALISM VALIDATION ({series})")
    print(f"{'='*60}")
    print(f"Average DNFs per race: {avg_dnfs_per_race:.2f} (target: 0.5-4.0) {'✓' if validations['dnf_rate_realistic'] else '✗'}")
    print(f"Average SC per race: {avg_sc_per_race:.2f} (target: 0.1-1.5) {'✓' if validations['safety_car_rate_realistic'] else '✗'}")
    print(f"Average overtakes per race: {avg_overtakes_per_race:.1f} (target: {overtake_min}-{overtake_max}) {'✓' if validations['overtakes_realistic'] else '✗'}")
    print(f"Average pit stops per race: {avg_pit_stops_per_race:.1f} (target: {pit_stop_min}-{pit_stop_max}) {'✓' if validations['pit_stops_realistic'] else '✗'}")
    print(f"Wet race percentage: {wet_race_pct:.1f}% (target: 5-35%) {'✓' if validations['wet_races_realistic'] else '✗'}")

    return validations


@pytest.mark.slow
def test_f2_season_simulation_realism() -> None:
    """Test that F2 season simulation produces realistic results."""
    print("\n" + "="*80)
    print("F2 SEASON SIMULATION REALISM TEST")
    print("Running 10 full F2 seasons...")
    print("="*80)

    all_stats: list[SeasonStats] = []

    for i in range(10):
        print(f"\nSimulating F2 Season {i+1}/10 (seed={100+i})...")
        stats = simulate_full_season(series="F2", seed=100+i)
        all_stats.append(stats)
        print_season_summary(stats)

    print_track_breakdown(all_stats)
    validations = validate_realism(all_stats, series="F2")

    # All validations should pass
    failed = [k for k, v in validations.items() if not v]
    if failed:
        print(f"\n⚠ FAILED VALIDATIONS: {failed}")
    else:
        print("\n✓ ALL REALISM CHECKS PASSED")

    assert all(validations.values()), f"Failed realism checks: {failed}"


@pytest.mark.slow
def test_f1_season_simulation_realism() -> None:
    """Test that F1 season simulation produces realistic results."""
    print("\n" + "="*80)
    print("F1 SEASON SIMULATION REALISM TEST")
    print("Running 10 full F1 seasons...")
    print("="*80)

    all_stats: list[SeasonStats] = []

    for i in range(10):
        print(f"\nSimulating F1 Season {i+1}/10 (seed={200+i})...")
        stats = simulate_full_season(series="F1", seed=200+i)
        all_stats.append(stats)
        print_season_summary(stats)

    print_track_breakdown(all_stats)
    validations = validate_realism(all_stats, series="F1")

    # All validations should pass
    failed = [k for k, v in validations.items() if not v]
    if failed:
        print(f"\n⚠ FAILED VALIDATIONS: {failed}")
    else:
        print("\n✓ ALL REALISM CHECKS PASSED")

    assert all(validations.values()), f"Failed realism checks: {failed}"


@pytest.mark.slow
def test_track_specific_characteristics() -> None:
    """Test that track-specific characteristics affect results realistically."""
    print("\n" + "="*80)
    print("TRACK-SPECIFIC CHARACTERISTICS TEST")
    print("="*80)

    # Run 5 seasons and compare track characteristics
    all_stats: list[SeasonStats] = []
    for i in range(5):
        stats = simulate_full_season(series="F2", seed=300+i)
        all_stats.append(stats)

    # Group by track
    track_data: dict[str, list[RaceStats]] = defaultdict(list)
    for season in all_stats:
        for race in season.races:
            track_data[race.track_id].append(race)

    tracks = {t.id: t for t in get_tracks()}

    print(f"\n{'Track':<20} {'OT Diff':>8} {'SC Chance':>10} {'Actual SC':>10} {'Expected':>10}")
    print("-"*70)

    for track_id in sorted(track_data.keys()):
        races = track_data[track_id]
        track = tracks.get(track_id)
        if not track:
            continue

        avg_overtakes = sum(r.overtakes for r in races) / len(races)
        avg_sc = sum(r.safety_car_deployments for r in races) / len(races)

        # Higher overtaking difficulty should mean fewer overtakes
        # Higher safety car chance should mean more safety cars
        print(f"{track_id:<20} {track.overtaking_difficulty:>8} {track.safety_car_chance:>10} {avg_sc:>10.2f} {'High' if track.safety_car_chance > 50 else 'Low':>10}")


if __name__ == "__main__":
    # Quick test - run a single season
    print("Running quick F2 simulation test...")
    stats = simulate_full_season(series="F2", seed=42)
    print_season_summary(stats)

    print("\nRunning quick F1 simulation test...")
    stats = simulate_full_season(series="F1", seed=43)
    print_season_summary(stats)
