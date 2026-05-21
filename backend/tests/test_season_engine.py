"""Tests for season engine."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import activity_routes, career_routes, weekend_routes, season_routes
from app.engine.season_engine import (
    get_championship_position,
    get_player_season_summary,
    get_season_summary,
    is_season_complete,
    prepare_next_season,
    transition_to_offseason,
)
from app.main import app
from app.save.save_manager import SaveManager


def _create_career(tmp_path) -> tuple[TestClient, SaveManager, str]:
    """Create a career for testing."""
    manager = SaveManager(tmp_path)
    career_routes.manager = manager
    activity_routes.manager = manager
    weekend_routes.manager = manager
    season_routes.manager = manager
    client = TestClient(app)

    response = client.post(
        "/career/new",
        json={
            "name": "Test Driver",
            "nationality": "British",
            "age": 18,
            "driverNumber": 27,
            "backgroundId": "karting_prodigy",
            "archetypeId": "one_lap_monster",
            "teamId": "f2_prema",
            "academyId": "academy_ferrari",
            "difficulty": "realistic",
        },
    )
    save_id = response.json()["saveId"]
    return client, manager, save_id


class TestIsSeasonComplete:
    def test_incomplete_season(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        assert not is_season_complete(save)

    def test_complete_season(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Mark all rounds as complete
        updated_calendar = [r.model_copy(update={"completed": True}) for r in save.calendar]
        save = save.model_copy(update={"calendar": updated_calendar})

        assert is_season_complete(save)


class TestGetChampionshipPosition:
    def test_returns_position(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        # Complete a race to have standings
        client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

        save = manager.get(save_id)
        player_id = save.player_driver_id

        position = get_championship_position(save, player_id)
        assert position is not None
        assert 1 <= position <= 22

    def test_returns_none_for_unknown_driver(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        position = get_championship_position(save, "nonexistent_driver")
        assert position is None


class TestGetPlayerSeasonSummary:
    def test_returns_summary_after_races(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        # Complete a few races
        for i in range(1, 4):
            client.post(f"/career/{save_id}/weekend/f2_2026_round_{i:02d}/simulate")

        save = manager.get(save_id)
        summary = get_player_season_summary(save)

        assert summary is not None
        assert "driver_id" in summary
        assert "championship_position" in summary
        assert "points" in summary
        assert "wins" in summary
        assert "rating" in summary


class TestGetSeasonSummary:
    def test_returns_full_summary(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        # Complete a race
        client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

        save = manager.get(save_id)
        summary = get_season_summary(save)

        assert "season" in summary
        assert "champion" in summary
        assert "team_champion" in summary
        assert "final_standings" in summary
        assert len(summary["final_standings"]) > 0


class TestTransitionToOffseason:
    def test_transitions_when_complete(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Mark all rounds as complete
        updated_calendar = [r.model_copy(update={"completed": True}) for r in save.calendar]
        save = save.model_copy(update={"calendar": updated_calendar})

        updated_save, news = transition_to_offseason(save)

        assert updated_save.phase == "offseason"
        assert updated_save.event_flags.get("season_complete") is True
        assert len(news) > 0

    def test_does_not_transition_when_incomplete(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        updated_save, news = transition_to_offseason(save)

        assert updated_save.phase == save.phase
        assert len(news) == 0


class TestPrepareNextSeason:
    def test_increments_season(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Set to offseason
        save = save.model_copy(update={"phase": "offseason"})

        updated_save = prepare_next_season(save)

        assert updated_save.season == save.season + 1

    def test_resets_calendar(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Mark rounds as complete and set offseason
        updated_calendar = [r.model_copy(update={"completed": True}) for r in save.calendar]
        save = save.model_copy(update={"calendar": updated_calendar, "phase": "offseason"})

        updated_save = prepare_next_season(save)

        assert all(not r.completed for r in updated_save.calendar)

    def test_resets_standings(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        # Complete a race to have standings
        client.post(f"/career/{save_id}/weekend/f2_2026_round_01/simulate")

        save = manager.get(save_id)
        save = save.model_copy(update={"phase": "offseason"})

        updated_save = prepare_next_season(save)

        for entry in updated_save.standings.driver_standings:
            assert entry.points == 0
            assert entry.wins == 0

    def test_ages_drivers(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)
        save = save.model_copy(update={"phase": "offseason"})

        original_ages = {d.id: d.age for d in save.drivers}

        updated_save = prepare_next_season(save)

        for driver in updated_save.drivers:
            assert driver.age == original_ages[driver.id] + 1


class TestSeasonStatusEndpoint:
    def test_returns_status(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.get(f"/career/{save_id}/season/status")
        assert response.status_code == 200

        body = response.json()
        assert "season" in body
        assert "phase" in body
        assert "totalRounds" in body
        assert "completedRounds" in body
        assert "isSeasonComplete" in body


class TestSeasonSummaryEndpoint:
    def test_requires_complete_season(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.get(f"/career/{save_id}/season/summary")
        assert response.status_code == 400

    def test_returns_summary_when_complete(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Mark all rounds as complete
        updated_calendar = [r.model_copy(update={"completed": True}) for r in save.calendar]
        save = save.model_copy(update={"calendar": updated_calendar})
        manager.save(save)

        response = client.get(f"/career/{save_id}/season/summary")
        assert response.status_code == 200


class TestAdvanceSeasonEndpoint:
    def test_requires_offseason_phase(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)

        response = client.post(f"/career/{save_id}/season/advance")
        assert response.status_code == 400

    def test_advances_when_in_offseason(self, tmp_path):
        client, manager, save_id = _create_career(tmp_path)
        save = manager.get(save_id)

        # Set to offseason
        save = save.model_copy(update={"phase": "offseason"})
        manager.save(save)

        response = client.post(f"/career/{save_id}/season/advance")
        assert response.status_code == 200

        body = response.json()
        assert body["season"] == save.season + 1
        assert body["phase"] == "preseason"
