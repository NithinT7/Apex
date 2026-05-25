from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.data.loaders import (
    get_academies,
    get_driver_archetypes,
    get_driver_backgrounds,
    get_f2_teams,
)
from app.engine.player_balance import (
    generate_starting_attributes,
    get_all_difficulty_options,
    get_difficulty_config,
)
from app.models.development_profile import create_player_starting_profile
from app.models.driver import Driver, DriverAttributes, DriverIdentity, HiddenDriverAttributes
from app.models.player_creation import (
    CareerCreationOptions,
    CreateCareerRequest,
    DriverArchetype,
    DriverBackground,
)
from app.models.save_game import ChampionshipEntry, CreateSaveRequest, NewsItem, SaveGame
from app.save.save_manager import SaveManager


router = APIRouter(prefix="/career", tags=["career"])
manager = SaveManager()

ARCHETYPE_IDENTITY_SEEDS = {
    "smooth_operator": "tire_whisperer",
    "one_lap_monster": "qualifying_merchant",
    "wheel_to_wheel_fighter": "aggressive_menace",
    "rain_specialist": "rain_god",
    "technical_developer": "team_leader",
    "high_risk_prodigy": "aggressive_menace",
}


@router.get("/new/options")
def new_career_options() -> dict:
    """Get all options for creating a new career."""
    return {
        "backgrounds": [b.model_dump(by_alias=True) for b in get_driver_backgrounds()],
        "archetypes": [a.model_dump(by_alias=True) for a in get_driver_archetypes()],
        "f2Teams": [t.model_dump(by_alias=True) for t in get_f2_teams()],
        "academies": [a.model_dump(by_alias=True) for a in get_academies()],
        "difficultyPresets": get_all_difficulty_options(),
    }


@router.post("/new", response_model=SaveGame, status_code=status.HTTP_201_CREATED)
def create_career(payload: CreateCareerRequest) -> SaveGame:
    background = _find_by_id(get_driver_backgrounds(), payload.background_id, "background_id")
    archetype = _find_by_id(get_driver_archetypes(), payload.archetype_id, "archetype_id")

    team_ids = {team.id for team in get_f2_teams()}
    academy_ids = {academy.id for academy in get_academies()}
    if payload.team_id not in team_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown team_id")
    if payload.academy_id not in academy_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown academy_id")

    save = manager.create(CreateSaveRequest(name=f"{payload.name.strip()} Career"))
    replaced_driver = _find_replaced_driver(save, payload.team_id)

    # Build player with difficulty-based attributes
    player = _build_player(payload, background, archetype, save.random_seed)

    drivers = [player if driver.id == replaced_driver.id else driver for driver in save.drivers]
    standings = save.standings.model_copy(
        update={
            "driver_standings": [
                ChampionshipEntry(driver_id=player.id)
                if entry.driver_id == replaced_driver.id
                else entry
                for entry in save.standings.driver_standings
            ]
        }
    )
    academy_states = [
        state.model_copy(
            update={
                "trust": 55 if state.academy_id == payload.academy_id else state.trust,
                "junior_depth": _with_player_depth(state.junior_depth, player.id),
            }
        )
        if state.academy_id == payload.academy_id
        else state
        for state in save.academy_states
    ]

    # Create development profile based on player's hidden potential and difficulty
    difficulty_config = get_difficulty_config(payload.difficulty)
    development_profile = create_player_starting_profile(
        potential=player.hidden.potential,
        starting_points=difficulty_config.starting_dev_points,
        branch_xp_bonus=difficulty_config.starting_branch_xp_bonus,
    )

    updated = save.model_copy(
        update={
            "name": f"{payload.name.strip()} Career",
            "player_driver_id": player.id,
            "drivers": drivers,
            "academy_states": academy_states,
            "standings": standings,
            "development_profile": development_profile,
            "difficulty": payload.difficulty,
            "news": [
                *save.news,
                NewsItem(
                    id="player_announced",
                    date=save.current_date,
                    category="system",
                    headline=f"{payload.name.strip()} signs with {_team_name(save, payload.team_id)} for F2 debut",
                    body=(
                        f"{payload.name.strip()} enters Formula 2 as a {background.name.lower()} "
                        f"with a {archetype.name.lower()} profile."
                    ),
                    linked_driver_ids=[player.id],
                    importance=3,
                ),
            ],
        }
    )
    return manager.save(updated)


def _build_player(
    payload: CreateCareerRequest,
    background: DriverBackground,
    archetype: DriverArchetype,
    seed: int,
) -> Driver:
    """Build a player driver with difficulty-adjusted attributes."""
    # Generate attributes based on difficulty preset
    attributes, hidden = generate_starting_attributes(
        difficulty=payload.difficulty,
        background_effects=background.attribute_effects,
        archetype_effects=archetype.attribute_effects,
        seed=seed,
    )

    # Apply background and archetype hidden effects
    for effects in [background.hidden_effects, archetype.hidden_effects]:
        for key, value in effects.items():
            snake_key = _camel_to_snake(key)
            if snake_key in hidden:
                hidden[snake_key] = _clamp(hidden[snake_key] + value)

    seed_trait = ARCHETYPE_IDENTITY_SEEDS.get(archetype.id)
    identity = DriverIdentity(
        primary_trait=None,
        trait_scores={seed_trait: 8} if seed_trait else {},
        summary="Profile still forming",
    )

    return Driver(
        id="player_driver",
        name=payload.name.strip(),
        nationality=payload.nationality.strip(),
        age=payload.age,
        driver_number=payload.driver_number,
        series="F2",
        team_id=payload.team_id,
        academy_id=payload.academy_id,
        attributes=DriverAttributes(**attributes),
        hidden=HiddenDriverAttributes(**hidden),
        identity=identity,
        current_form=55,
        fatigue=0,
        morale=55,
    )


def _find_replaced_driver(save: SaveGame, team_id: str) -> Driver:
    team_drivers = [
        driver for driver in save.drivers if driver.series == "F2" and driver.team_id == team_id
    ]
    if not team_drivers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selected team has no replaceable F2 seat",
        )

    return min(
        team_drivers,
        key=lambda driver: (
            driver.attributes.pace
            + driver.attributes.qualifying
            + driver.attributes.racecraft
            + driver.attributes.consistency
        ),
    )


def _find_by_id(items: list[DriverBackground] | list[DriverArchetype], item_id: str, field: str):
    item = next((candidate for candidate in items if candidate.id == item_id), None)
    if item is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown {field}")

    return item


def _team_name(save: SaveGame, team_id: str) -> str:
    team = next(team for team in save.teams if team.id == team_id)
    return team.name


def _with_player_depth(driver_ids: list[str], player_id: str) -> list[str]:
    return driver_ids if player_id in driver_ids else [*driver_ids, player_id]


def _clamp(value: int) -> int:
    return max(1, min(100, value))


def _camel_to_snake(value: str) -> str:
    result = []
    for char in value:
        if char.isupper():
            result.append("_")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result).lstrip("_")
