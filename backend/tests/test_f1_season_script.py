import subprocess
import sys
from pathlib import Path


def test_f1_season_script_runs_three_rounds() -> None:
    backend_root = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [
            sys.executable,
            str(backend_root / "scripts" / "simulate_f1_season.py"),
            "--seed",
            "1",
            "--rounds",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Standalone F1 season simulation, seed 1" in result.stdout
    assert "R01" in result.stdout
    assert "R03" in result.stdout
    assert "Drivers" in result.stdout
    assert "Constructors" in result.stdout
