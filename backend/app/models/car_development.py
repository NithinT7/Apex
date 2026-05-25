from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models.base import AppModel


UpgradeDepartment = Literal[
    "front_wing",
    "rear_wing",
    "floor",
    "sidepods_cooling",
    "suspension",
    "power_unit",
    "brakes",
    "weight_reduction",
    "pit_crew",
    "strategy_tools",
    # Legacy aliases kept so older expanded saves remain valid.
    "aero",
    "chassis",
    "reliability",
    "operations",
    "strategy",
]
UpgradeType = Literal["minor", "major", "concept", "reliability", "track_specific", "regulation_research", "research"]
UpgradeStatus = Literal["planned", "in_progress", "delivered", "failed", "cancelled"]
CorrelationOutcome = Literal["unknown", "ahead", "on_target", "below_target", "failed_correlation"]
EngineerVerdict = Literal["keep_package", "adjust_setup", "monitor_closely", "remove_package", "pending"]


class UpgradePackage(AppModel):
    id: str
    name: str
    department: UpgradeDepartment
    upgrade_type: UpgradeType
    target_stats: dict[str, int] = Field(default_factory=dict)
    expected_gain: dict[str, int] = Field(default_factory=dict)
    risk: int = 0
    cost: int = 0
    required_rounds: int = 1


class UpgradeProject(AppModel):
    id: str
    name: str
    department: UpgradeDepartment
    upgrade_type: UpgradeType
    target_stats: dict[str, int] = Field(default_factory=dict)
    expected_gain: dict[str, int] = Field(default_factory=dict)
    actual_gain: dict[str, int] = Field(default_factory=dict)
    risk: int = 0
    status: UpgradeStatus = "planned"
    delivery_round: int | None = None
    correlation_outcome: CorrelationOutcome = "unknown"
    side_effects: dict[str, int] = Field(default_factory=dict)
    # New fields for Technical Feedback correlation system
    predicted_gain: dict[str, float] = Field(default_factory=dict)
    estimated_gain_after_practice: dict[str, float] = Field(default_factory=dict)
    correlation_confidence: int = 50
    driver_feedback_summary: str = ""
    engineer_verdict: EngineerVerdict = "pending"


class UpgradeHistoryEntry(AppModel):
    id: str
    project_id: str
    round_id: str | None = None
    season: int
    summary: str
    applied_gain: dict[str, int] = Field(default_factory=dict)
    side_effects: dict[str, int] = Field(default_factory=dict)
    correlation_outcome: CorrelationOutcome = "unknown"
    # New fields for Technical Feedback correlation system
    predicted_gain: dict[str, float] = Field(default_factory=dict)
    estimated_gain_after_practice: dict[str, float] = Field(default_factory=dict)
    correlation_confidence: int = 50
    driver_feedback_summary: str = ""
    engineer_verdict: EngineerVerdict = "pending"


class PracticeCorrelationReport(AppModel):
    project_id: str
    team_id: str
    round_id: str
    upgrade_name: str = ""
    department: UpgradeDepartment | None = None
    # Original team prediction before track running
    predicted_gain: dict[str, float] = Field(default_factory=dict)
    # What the package actually provides (hidden from player initially)
    actual_gain: dict[str, float] = Field(default_factory=dict)
    # What the team estimates after practice (affected by technical feedback)
    estimated_gain_after_practice: dict[str, float] = Field(default_factory=dict)
    # Legacy field for backward compatibility
    expected_gain: dict[str, int] = Field(default_factory=dict)
    actual_estimated_gain: dict[str, float] = Field(default_factory=dict)
    # How confident the team is in their estimate (0-100, affected by technical feedback)
    correlation_confidence: int = 50
    # Detailed assessment of how well estimate matches reality
    correlation_outcome: CorrelationOutcome = "unknown"
    # Legacy field for backward compatibility
    correlation_quality: CorrelationOutcome = "unknown"
    # Narrative feedback based on driver technical feedback attribute
    driver_feedback_summary: str = ""
    # Legacy field for backward compatibility
    driver_feedback: str = ""
    # What the engineers recommend based on the data
    engineer_verdict: EngineerVerdict = "pending"
    engineer_verdict_text: str = ""
    # Stats affected by this upgrade
    affected_stats: list[str] = Field(default_factory=list)
    # Confidence percentage legacy field
    confidence_percentage: int = 50
    # Correlation accuracy score (internal, used for calculations)
    correlation_accuracy: float = 0.5


class TeamDevelopmentState(AppModel):
    team_id: str
    budget: int = 0
    focus: UpgradeDepartment | None = None
    active_projects: list[UpgradeProject] = Field(default_factory=list)
    available_packages: list[UpgradePackage] = Field(default_factory=list)
    upgrade_history: list[UpgradeHistoryEntry] = Field(default_factory=list)
    research_points: int = 0
    facilities: dict[str, int] = Field(default_factory=dict)
    # New fields for Technical Feedback correlation system
    engineering_quality: int = 75  # Team's engineering capability (affects correlation accuracy)
    simulator_quality: int = 70    # Quality of team's simulator (affects pre-track predictions)
    manufacturing_speed: int = 70  # How fast upgrades can be produced
    upgrade_risk_tolerance: int = 50  # Team's willingness to take risks on aggressive upgrades
    # Momentum/Dynasty tracking for realistic multi-year competitive cycles
    momentum: int = 0  # -10 to +10, positive = team on upward trajectory
    dynasty_years: int = 0  # Years of sustained top performance (>=88 car)
    design_philosophy: dict[str, int] = Field(default_factory=dict)  # Team's strengths that persist
    last_season_performance: int = 75  # Track year-over-year changes
    peak_performance: int = 75  # Highest performance achieved (affects prestige/recruitment)
