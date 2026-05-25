"""Detailed car performance and track fit calculations."""

from __future__ import annotations

from typing import Literal

from app.models.car import CarPerformanceProfile, TrackCarDemandProfile
from app.models.race import WeatherState
from app.models.team import Team
from app.models.track import Track


CarTier = Literal["Dominant", "Front Runner", "Upper Midfield", "Midfield", "Lower Midfield", "Backmarker"]


def clamp_rating(value: float | int) -> int:
    return max(1, min(100, round(value)))


def car_tier(profile: CarPerformanceProfile) -> CarTier:
    score = profile.overall_performance
    if score >= 94:
        return "Dominant"
    if score >= 88:
        return "Front Runner"
    if score >= 82:
        return "Upper Midfield"
    if score >= 75:
        return "Midfield"
    if score >= 68:
        return "Lower Midfield"
    return "Backmarker"


def team_profile(team: Team) -> CarPerformanceProfile:
    return team.effective_car_profile()


def track_demand_profile(track: Track) -> TrackCarDemandProfile:
    street_bonus = 12 if track.street_circuit else 0
    low_speed = 34 + street_bonus + track.qualifying_importance * 0.20 + track.setup_complexity * 0.09 + max(0, 75 - track.drs_strength) * 0.10
    straight_line = 30 + track.drs_strength * 0.58 + max(0, 58 - track.overtaking_difficulty) * 0.18
    high_speed = 34 + (track.base_lap_time - 80) * 0.20 + track.drs_strength * 0.22
    medium_speed = 44 + track.setup_complexity * 0.16 + (track.base_lap_time - 85) * 0.08
    traction = 36 + track.tire_deg * 0.24 + street_bonus * 0.45
    tire_deg = 30 + track.tire_deg * 0.58
    cooling = 30 + track.tire_deg * 0.18 + (10 if track.street_circuit else 0) + track.safety_car_chance * 0.10

    setup_complexity = track.setup_complexity - max(0, track.drs_strength - 70) * 0.45

    return TrackCarDemandProfile(
        track_id=track.id,
        low_speed_importance=clamp_rating(low_speed),
        medium_speed_importance=clamp_rating(medium_speed),
        high_speed_importance=clamp_rating(high_speed),
        straight_line_importance=clamp_rating(straight_line),
        traction_importance=clamp_rating(traction),
        tire_deg_importance=clamp_rating(tire_deg),
        cooling_stress=clamp_rating(cooling),
        setup_complexity=clamp_rating(setup_complexity),
    )


def track_car_fit(profile: CarPerformanceProfile, track: Track) -> int:
    demand = track_demand_profile(track)
    weighted = [
        (profile.low_speed_cornering, demand.low_speed_importance),
        (profile.medium_speed_cornering, demand.medium_speed_importance),
        (profile.high_speed_cornering, demand.high_speed_importance),
        (profile.aero_efficiency, round((demand.straight_line_importance + demand.high_speed_importance) * 0.32)),
        (profile.straight_line_speed, demand.straight_line_importance),
        (profile.traction, demand.traction_importance),
        (profile.tire_wear, demand.tire_deg_importance),
        (profile.cooling, demand.cooling_stress),
        (profile.setup_window, demand.setup_complexity),
    ]
    total_weight = sum(weight for _, weight in weighted) or 1
    return clamp_rating(sum(value * weight for value, weight in weighted) / total_weight)


def team_track_score(team: Team, track: Track) -> int:
    profile = team_profile(team)
    fit = track_car_fit(profile, track)
    return clamp_rating(profile.overall_performance * 0.54 + fit * 0.46)


def qualifying_car_score(team: Team, track: Track, weather: WeatherState) -> int:
    profile = team_profile(team)
    score = team_track_score(team, track) * 0.72
    score += profile.tire_warmup * 0.12
    score += profile.setup_window * 0.10
    score += profile.cooling * 0.06
    if weather.condition != "dry":
        score = score * 0.92 + (profile.traction * 0.05 + profile.tire_warmup * 0.03)
    return clamp_rating(score)


def race_car_score(team: Team, track: Track, weather: WeatherState) -> int:
    profile = team_profile(team)
    score = team_track_score(team, track) * 0.67
    score += profile.tire_wear * 0.12
    score += profile.reliability * 0.08
    score += profile.strategy_team * 0.08
    score += profile.cooling * 0.05
    if weather.condition != "dry":
        score = score * 0.92 + profile.traction * 0.08
    return clamp_rating(score)


def setup_confidence_score(team: Team, driver_confidence: int, setup_score: int | None = None) -> int:
    profile = team_profile(team)
    setup_component = setup_score if setup_score is not None else profile.setup_window
    return clamp_rating(driver_confidence * 0.42 + profile.setup_window * 0.36 + team.strategy * 0.22 + (setup_component - 75) * 0.12)


def performance_composite(
    *,
    series: str,
    car_score: int,
    driver_score: int,
    setup_score: int,
    context_score: int,
) -> int:
    if series == "F1":
        return clamp_rating(car_score * 0.60 + driver_score * 0.25 + setup_score * 0.10 + context_score * 0.05)
    return clamp_rating(car_score * 0.35 + driver_score * 0.45 + setup_score * 0.10 + context_score * 0.10)


def car_strengths_weaknesses(profile: CarPerformanceProfile) -> tuple[list[str], list[str]]:
    labels = {
        "aero_efficiency": "Aero efficiency",
        "low_speed_cornering": "Low speed",
        "medium_speed_cornering": "Medium speed",
        "high_speed_cornering": "High speed",
        "straight_line_speed": "Straight line",
        "traction": "Traction",
        "tire_wear": "Tire life",
        "tire_warmup": "Warmup",
        "reliability": "Reliability",
        "cooling": "Cooling",
        "setup_window": "Setup window",
        "strategy_team": "Strategy",
        "pit_crew": "Pit crew",
    }
    values = [(label, getattr(profile, key)) for key, label in labels.items()]
    strengths = [label for label, _ in sorted(values, key=lambda item: item[1], reverse=True)[:3]]
    weaknesses = [label for label, _ in sorted(values, key=lambda item: item[1])[:3]]
    return strengths, weaknesses


def apply_profile_delta(profile: CarPerformanceProfile, gains: dict[str, int]) -> CarPerformanceProfile:
    updates: dict[str, int] = {}
    for key, delta in gains.items():
        if hasattr(profile, key):
            updates[key] = clamp_rating(getattr(profile, key) + delta)
    if updates and "overall_performance" not in updates:
        performance_keys = [
            "aero_efficiency",
            "low_speed_cornering",
            "medium_speed_cornering",
            "high_speed_cornering",
            "straight_line_speed",
            "traction",
            "tire_wear",
        ]
        average = sum(updates.get(key, getattr(profile, key)) for key in performance_keys) / len(performance_keys)
        updates["overall_performance"] = clamp_rating(profile.overall_performance * 0.72 + average * 0.28)
    return profile.model_copy(update=updates)
