from __future__ import annotations

import json
import random
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.data.loaders import get_academies, get_f1_drivers, get_f1_teams, get_f2_calendar, get_f2_drivers, get_f2_teams
from app.models.save_game import (
    AcademyState,
    ChampionshipEntry,
    ChampionshipState,
    CreateSaveRequest,
    NewsItem,
    SaveGame,
    SaveSummary,
)


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
        academies = get_academies()
        save = SaveGame(
            save_id=save_id,
            name=name,
            created_at=now,
            updated_at=now,
            current_date="2026-03-01",
            season=2026,
            phase="preseason",
            drivers=drivers,
            teams=[*get_f1_teams(), *get_f2_teams()],
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
                team_standings={team.id: 0 for team in get_f2_teams()},
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
            random_seed=random_seed,
        )

        return self.save(save)

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

        return SaveGame.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def delete(self, save_id: str) -> bool:
        path = self._path(save_id)
        if not path.exists():
            return False

        path.unlink()
        return True

    def _path(self, save_id: str) -> Path:
        return self.save_dir / f"{save_id}.json"
