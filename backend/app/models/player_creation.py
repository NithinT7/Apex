from typing import Literal

from pydantic import Field

from app.models.academy import Academy
from app.models.base import AppModel
from app.models.team import Team


# Legacy difficulty (kept for backwards compatibility)
Difficulty = Literal["casual", "realistic", "brutal"]

# New difficulty presets with proper balancing
DifficultyPreset = Literal["prodigy", "realistic_prospect", "underdog", "brutal_realism"]


class DriverBackground(AppModel):
    id: str
    name: str
    description: str
    attribute_effects: dict[str, int] = Field(default_factory=dict)
    hidden_effects: dict[str, int] = Field(default_factory=dict)


class DriverArchetype(AppModel):
    id: str
    name: str
    description: str
    attribute_effects: dict[str, int] = Field(default_factory=dict)
    hidden_effects: dict[str, int] = Field(default_factory=dict)


class CareerCreationOptions(AppModel):
    backgrounds: list[DriverBackground]
    archetypes: list[DriverArchetype]
    f2_teams: list[Team]
    academies: list[Academy]


class CreateCareerRequest(AppModel):
    name: str = Field(min_length=2, max_length=48)
    nationality: str = Field(min_length=2, max_length=40)
    age: int = Field(ge=16, le=30)
    driver_number: int = Field(ge=2, le=99)
    background_id: str
    archetype_id: str
    team_id: str
    academy_id: str = "academy_independent"
    difficulty: DifficultyPreset = "realistic_prospect"
