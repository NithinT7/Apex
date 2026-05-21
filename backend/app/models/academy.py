from typing import Literal

from app.models.base import AppModel


AcademyStyle = Literal[
    "brutal_ladder",
    "prestige",
    "technical_development",
    "flexible_pathway",
    "balanced_modern",
    "early_f1_chance",
    "sponsor_prestige",
    "long_term_project",
    "independent",
]


class Academy(AppModel):
    id: str
    name: str
    style: AcademyStyle
    f1_team_id: str | None
    support_level: int
    pressure: int
    patience: int
    political_stability: int
    testing_opportunities: int
    contract_strictness: int
    media_expectations: int
