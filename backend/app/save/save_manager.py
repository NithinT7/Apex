from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.data.loaders import get_academies, get_f1_drivers, get_f1_teams, get_f2_calendar, get_f2_drivers, get_f2_teams
from app.engine.car_development_engine import ensure_car_development_state
from app.models.car import CarComponentReliability, TeamCarState
from app.models.car_development import TeamDevelopmentState
from app.models.development_profile import create_player_starting_profile
from app.models.save_game import (
    AcademyState,
    ChampionshipEntry,
    ChampionshipState,
    Contract,
    CreateSaveRequest,
    NewsItem,
    SaveGame,
    SaveSummary,
)
from app.models.team import Team
from app.models.world import TeamPoliticsState, WorldState


SAVE_DIR = Path(__file__).resolve().parents[2] / "saves"


class SaveManager:
    def __init__(self, save_dir: Path = SAVE_DIR) -> None:
        self.save_dir = save_dir

    def create(self, payload: CreateSaveRequest | None = None) -> SaveGame:
        now = datetime.now(timezone.utc)
        save_id = str(uuid4())
        random_seed = random.SystemRandom().randint(1, 2_147_483_647)
        name = payload.name.strip() if payload and payload.name else "New F2 Career"

        drivers = [*get_f1_drivers(), *get_f2_drivers()]
        teams = _with_default_car_states([*get_f1_teams(), *get_f2_teams()], season=2026)
        academies = get_academies()
        contracts = _generate_initial_contracts(drivers, teams, season=2026)
        save = SaveGame(
            save_id=save_id,
            name=name,
            created_at=now,
            updated_at=now,
            current_date="2026-03-01",
            season=2026,
            phase="preseason",
            drivers=drivers,
            teams=teams,
            academies=academies,
            academy_states=[
                AcademyState(
                    academy_id=academy.id,
                    trust=50,
                    junior_depth=[driver.id for driver in drivers if driver.academy_id == academy.id],
                    political_stability=academy.political_stability,
                )
                for academy in academies
            ],
            calendar=get_f2_calendar(),
            standings=ChampionshipState(
                driver_standings=[
                    ChampionshipEntry(driver_id=driver.id)
                    for driver in drivers
                    if driver.series == "F2"
                ],
                team_standings={team.id: 0 for team in teams if team.series == "F2"},
            ),
            f1_standings=ChampionshipState(
                driver_standings=[
                    ChampionshipEntry(driver_id=driver.id)
                    for driver in drivers
                    if driver.series == "F1"
                ],
                team_standings={team.id: 0 for team in teams if team.series == "F1"},
            ),
            team_development={team.id: TeamDevelopmentState(team_id=team.id) for team in teams},
            world_state=WorldState(
                team_politics={
                    team.id: TeamPoliticsState(
                        team_id=team.id,
                        stability=team.seat_security or 70,
                        budget_pressure=max(0, 100 - team.financial_health),
                        technical_confidence=team.development_rate,
                    )
                    for team in teams
                    if team.series == "F1"
                }
            ),
            news=[
                NewsItem(
                    id="season_seeded",
                    date="2026-03-01",
                    category="system",
                    headline="F2 paddock prepares for a new road to Formula 1",
                    body="Teams, academies, and scouts are watching the new Formula 2 season closely.",
                    importance=2,
                )
            ],
            contracts=contracts,
            random_seed=random_seed,
            event_flags={"race_length_mode": "authentic_scaled"},
        )

        return self.save(ensure_car_development_state(save))

    def save(self, save_game: SaveGame) -> SaveGame:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        updated = save_game.model_copy(update={"updated_at": datetime.now(timezone.utc)})
        self._path(updated.save_id).write_text(
            updated.model_dump_json(by_alias=True, indent=2),
            encoding="utf-8",
        )
        return updated

    def list(self) -> list[SaveSummary]:
        self.save_dir.mkdir(parents=True, exist_ok=True)
        saves = [self.get(path.stem) for path in self.save_dir.glob("*.json")]
        summaries = [
            SaveSummary(
                save_id=save.save_id,
                name=save.name,
                updated_at=save.updated_at,
                season=save.season,
                phase=save.phase,
                player_driver_id=save.player_driver_id,
            )
            for save in saves
            if save is not None
        ]
        return sorted(summaries, key=lambda save: save.updated_at, reverse=True)

    def get(self, save_id: str) -> SaveGame | None:
        path = self._path(save_id)
        if not path.exists():
            return None

        return _migrate_save_game(SaveGame.model_validate(json.loads(path.read_text(encoding="utf-8"))))

    def delete(self, save_id: str) -> bool:
        path = self._path(save_id)
        if not path.exists():
            return False

        path.unlink()
        return True

    def _path(self, save_id: str) -> Path:
        return self.save_dir / f"{save_id}.json"


def _generate_initial_contracts(
    drivers: list, teams: list[Team], season: int
) -> list[Contract]:
    """Generate realistic initial contracts for all drivers.

    Contract lengths are based on:
    - Driver age and reputation
    - Team tier (top teams offer longer deals to stars)
    - Series (F1 vs F2)
    - Real-world patterns (younger drivers get shorter initial deals)
    """
    from app.models.driver import Driver

    rng = random.Random(season * 12345)  # Deterministic for same season
    contracts: list[Contract] = []
    team_by_id = {t.id: t for t in teams}

    for driver in drivers:
        if not isinstance(driver, Driver):
            continue

        team = team_by_id.get(driver.team_id)
        if team is None:
            continue

        # Determine contract role
        if driver.series == "F1":
            role = "f1_race_seat"
        elif driver.series == "F2":
            role = "f2_race_seat"
        else:
            role = "academy_deal"

        # Calculate contract length based on driver profile
        # Base contract length by age
        if driver.age <= 21:
            base_length = rng.choice([1, 1, 2])  # Young drivers get short initial deals
        elif driver.age <= 25:
            base_length = rng.choice([1, 2, 2, 3])  # Prime age, variable deals
        elif driver.age <= 32:
            base_length = rng.choice([2, 2, 3, 3])  # Established, longer deals
        elif driver.age <= 36:
            base_length = rng.choice([1, 1, 2])  # Older, shorter deals
        else:
            base_length = 1  # Veterans get 1-year deals

        # Adjust for team tier (F1)
        if team.series == "F1":
            if team.car_performance >= 88:  # Top team
                # Top teams give longer deals to star drivers
                rating = (driver.attributes.pace + driver.attributes.racecraft) // 2
                if rating >= 90:
                    base_length = min(5, base_length + 2)
                elif rating >= 85:
                    base_length = min(4, base_length + 1)

        # Create contract starting from a random past season
        # so contracts expire at different times
        start_offset = rng.randint(0, max(1, base_length - 1))
        start_season = season - start_offset

        contracts.append(Contract(
            id=f"contract_{driver.id}_{start_season}",
            driver_id=driver.id,
            team_id=driver.team_id,
            role=role,
            start_season=start_season,
            length_years=base_length,
            active=True,
        ))

    return contracts


def _with_default_car_states(teams: list[Team], season: int) -> list[Team]:
    updated: list[Team] = []
    for team in teams:
        if team.car_state is not None:
            updated.append(team)
            continue
        updated.append(
            team.model_copy(
                update={
                    "car_state": TeamCarState(
                        team_id=team.id,
                        season=season,
                        profile=team.effective_car_profile(),
                        component_reliability=CarComponentReliability.from_legacy(team.reliability),
                    )
                }
            )
        )
    return updated


def _migrate_save_game(save: SaveGame) -> SaveGame:
    teams = _with_default_car_states(save.teams, season=save.season)
    team_development = {
        **{team.id: TeamDevelopmentState(team_id=team.id) for team in teams},
        **save.team_development,
    }
    world_state = save.world_state
    if not world_state.team_politics:
        world_state = world_state.model_copy(
            update={
                "team_politics": {
                    team.id: TeamPoliticsState(
                        team_id=team.id,
                        stability=team.seat_security or 70,
                        budget_pressure=max(0, 100 - team.financial_health),
                        technical_confidence=team.development_rate,
                    )
                    for team in teams
                    if team.series == "F1"
                }
            }
        )

    # Migrate development profile for existing saves with a player
    development_profile = save.development_profile
    if development_profile is None and save.player_driver_id is not None:
        # Find player's potential for initial XP calculation
        player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
        potential = player.hidden.potential if player else 85
        development_profile = create_player_starting_profile(potential)

    migrated = save.model_copy(
        update={
            "teams": teams,
            "team_development": team_development,
            "world_state": world_state,
            "development_profile": development_profile,
        }
    )
    return ensure_car_development_state(migrated)
