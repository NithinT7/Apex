import json
from datetime import datetime, timezone

from app.data.loaders import get_academies, get_f2_calendar, get_f2_drivers, get_f2_teams
from app.models.car import CarComponentReliability, TeamCarState
from app.models.save_game import AcademyState, ChampionshipEntry, ChampionshipState, CreateSaveRequest, SaveGame
from app.save.save_manager import SaveManager
from app.engine.weekend_engine import simulate_weekend


def test_existing_save_shape_loads_with_phase1_defaults(tmp_path) -> None:
    manager = SaveManager(tmp_path)
    save = manager.create(CreateSaveRequest(name="Legacy Shape"))
    payload = json.loads((tmp_path / f"{save.save_id}.json").read_text(encoding="utf-8"))

    payload.pop("teamDevelopment", None)
    payload.pop("worldState", None)
    for team in payload["teams"]:
        team.pop("carState", None)
    for driver in payload["drivers"]:
        driver.pop("paddockPerception", None)

    (tmp_path / f"{save.save_id}.json").write_text(json.dumps(payload), encoding="utf-8")

    loaded = manager.get(save.save_id)

    assert loaded is not None
    assert loaded.team_development
    assert loaded.world_state.team_politics
    assert all(team.car_state is not None for team in loaded.teams)
    assert all(driver.paddock_perception is not None for driver in loaded.drivers)


def test_new_save_includes_phase1_optional_state(tmp_path) -> None:
    save = SaveManager(tmp_path).create(CreateSaveRequest(name="Phase 1"))

    assert save.team_development
    assert set(save.team_development) == {team.id for team in save.teams}
    assert save.world_state.team_politics
    assert all(team.car_state is not None for team in save.teams)


def test_legacy_team_fields_derive_car_performance_profile() -> None:
    team = get_f2_teams()[0]

    profile = team.effective_car_profile()

    assert profile.overall_performance == team.car_performance
    assert profile.reliability == team.reliability
    assert profile.strategy_team == team.strategy
    assert profile.development_rate == team.development_rate
    assert 1 <= profile.low_speed_cornering <= 100
    assert 1 <= profile.pit_crew <= 100


def test_save_serialization_round_trips_phase1_models(tmp_path) -> None:
    save = SaveManager(tmp_path).create(CreateSaveRequest(name="Round Trip"))

    payload = save.model_dump(by_alias=True)
    reloaded = SaveGame.model_validate(payload)

    assert reloaded.team_development.keys() == save.team_development.keys()
    assert reloaded.world_state.team_politics.keys() == save.world_state.team_politics.keys()
    assert reloaded.teams[0].car_state is not None
    assert reloaded.drivers[0].paddock_perception is not None


def test_car_state_presence_does_not_change_weekend_simulation() -> None:
    raw_save = _test_save(with_car_state=False)
    enriched_save = _test_save(with_car_state=True)

    raw_weekend = simulate_weekend(raw_save, raw_save.calendar[0].id)
    enriched_weekend = simulate_weekend(enriched_save, enriched_save.calendar[0].id)

    raw_payload = raw_weekend.model_dump(by_alias=True, exclude={"save_id"})
    enriched_payload = enriched_weekend.model_dump(by_alias=True, exclude={"save_id"})
    assert enriched_payload == raw_payload


def _test_save(with_car_state: bool) -> SaveGame:
    drivers = get_f2_drivers()
    teams = list(get_f2_teams())
    if with_car_state:
        teams = [
            team.model_copy(
                update={
                    "car_state": TeamCarState(
                        team_id=team.id,
                        season=2026,
                        profile=team.effective_car_profile(),
                        component_reliability=CarComponentReliability.from_legacy(team.reliability),
                    )
                }
            )
            for team in teams
        ]
    academies = get_academies()
    return SaveGame(
        save_id="phase1-sim",
        name="Phase 1 Simulation",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        current_date="2026-03-01",
        season=2026,
        phase="race_week",
        player_driver_id=drivers[0].id,
        drivers=drivers,
        teams=teams,
        academies=academies,
        academy_states=[
            AcademyState(academy_id=academy.id, trust=50, political_stability=academy.political_stability)
            for academy in academies
        ],
        calendar=get_f2_calendar(),
        standings=ChampionshipState(
            driver_standings=[ChampionshipEntry(driver_id=driver.id) for driver in drivers],
            team_standings={team.id: 0 for team in teams},
        ),
        random_seed=4242,
        event_flags={"race_length_mode": "authentic_scaled"},
    )
