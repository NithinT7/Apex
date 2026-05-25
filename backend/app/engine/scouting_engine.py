"""Engine for calculating F1 team scouting interest in the player."""

from __future__ import annotations

from typing import Literal

from app.engine.silly_season_engine import (
    HIRING_PREFERENCES,
    F1_INTEREST_THRESHOLDS,
    get_driver_rating,
    get_team_rookie_tier,
    _driver_profile_fit,
    _academy_affinity,
    _marketability_package,
    _is_top_team,
    _championship_position_map,
    _seat_risk_score,
    _series_position_map,
)
from app.models.driver import Driver
from app.models.save_game import Contract, SaveGame
from app.models.team import Team


class SeatStatus:
    """Status of a driver's seat at a team."""

    def __init__(
        self,
        driver_id: str,
        driver_name: str,
        contract_years_remaining: int | None,
        seat_risk: int,
        is_at_risk: bool,
        status_note: str,
    ):
        self.driver_id = driver_id
        self.driver_name = driver_name
        self.contract_years_remaining = contract_years_remaining
        self.seat_risk = seat_risk
        self.is_at_risk = is_at_risk
        self.status_note = status_note

    def to_dict(self) -> dict:
        return {
            "driverId": self.driver_id,
            "driverName": self.driver_name,
            "contractYearsRemaining": self.contract_years_remaining,
            "seatRisk": self.seat_risk,
            "isAtRisk": self.is_at_risk,
            "statusNote": self.status_note,
        }


class ScoutingInterest:
    """Represents a team's scouting interest in the player."""

    def __init__(
        self,
        team_id: str,
        team_name: str,
        interest_level: int,  # 0-100
        interest_tier: Literal["none", "watching", "interested", "very_interested", "pursuing"],
        reasons: list[str],
        concerns: list[str],
        requirements: list[str],
        car_performance: int,
        team_tier: str,
        is_academy_team: bool,
        hiring_profile: str,
        seat_available: bool,
        seat_availability_note: str,
        current_drivers: list[SeatStatus],
    ):
        self.team_id = team_id
        self.team_name = team_name
        self.interest_level = interest_level
        self.interest_tier = interest_tier
        self.reasons = reasons
        self.concerns = concerns
        self.requirements = requirements
        self.car_performance = car_performance
        self.team_tier = team_tier
        self.is_academy_team = is_academy_team
        self.hiring_profile = hiring_profile
        self.seat_available = seat_available
        self.seat_availability_note = seat_availability_note
        self.current_drivers = current_drivers

    def to_dict(self) -> dict:
        return {
            "teamId": self.team_id,
            "teamName": self.team_name,
            "interestLevel": self.interest_level,
            "interestTier": self.interest_tier,
            "reasons": self.reasons,
            "concerns": self.concerns,
            "requirements": self.requirements,
            "carPerformance": self.car_performance,
            "teamTier": self.team_tier,
            "isAcademyTeam": self.is_academy_team,
            "hiringProfile": self.hiring_profile,
            "seatAvailable": self.seat_available,
            "seatAvailabilityNote": self.seat_availability_note,
            "currentDrivers": [d.to_dict() for d in self.current_drivers],
        }


def _interest_tier_from_level(level: int) -> Literal["none", "watching", "interested", "very_interested", "pursuing"]:
    """Convert interest level to tier."""
    if level < 15:
        return "none"
    if level < 35:
        return "watching"
    if level < 55:
        return "interested"
    if level < 75:
        return "very_interested"
    return "pursuing"


def _evaluate_team_seat_availability(
    save: SaveGame,
    team: Team,
) -> tuple[bool, str, list[SeatStatus]]:
    """
    Evaluate seat availability at an F1 team.

    Returns:
        - seat_available: Whether a seat might open
        - availability_note: Human-readable explanation
        - current_drivers: Status of each current driver
    """
    if save is None:
        # For testing without a save
        return False, "No save data", []

    # Get F1 standings for performance evaluation
    f1_position_map = _series_position_map(save, "F1")

    # Get team's current drivers
    team_drivers = [d for d in save.drivers if d.team_id == team.id and d.series == "F1"]

    if len(team_drivers) < 2:
        return True, "Team has an open seat", []

    driver_statuses: list[SeatStatus] = []
    seat_opening_reasons: list[str] = []

    for driver in team_drivers:
        # Get contract info
        contract = next(
            (c for c in save.contracts if c.driver_id == driver.id and c.active),
            None,
        )

        # Calculate years remaining
        if contract is None:
            years_remaining = 0
        else:
            years_remaining = max(0, (contract.start_season + contract.length_years) - (save.season + 1))

        # Calculate seat risk
        driver_position = f1_position_map.get(driver.id)
        seat_risk = _seat_risk_score(team, driver, driver_position)

        # Determine status
        is_at_risk = False
        status_note = ""

        if contract is None:
            is_at_risk = True
            status_note = "No active contract"
            seat_opening_reasons.append(f"{driver.name} has no contract")
        elif years_remaining == 0:
            # Contract expiring this season
            if seat_risk >= 50:
                is_at_risk = True
                status_note = "Contract expiring, likely to be replaced"
                seat_opening_reasons.append(f"{driver.name}'s contract expiring, underperforming")
            elif seat_risk >= 36:
                is_at_risk = True
                status_note = "Contract expiring, seat at risk"
                seat_opening_reasons.append(f"{driver.name}'s contract expiring, seat uncertain")
            elif driver.age >= 37:
                is_at_risk = True
                status_note = "Contract expiring, may retire"
                seat_opening_reasons.append(f"{driver.name} may retire")
            else:
                status_note = f"Contract expiring, likely to re-sign"
        elif years_remaining == 1:
            if seat_risk >= 60:
                is_at_risk = True
                status_note = "Under pressure, could be dropped"
                seat_opening_reasons.append(f"{driver.name} under serious pressure")
            else:
                status_note = f"1 year remaining"
        else:
            if seat_risk >= 70:
                is_at_risk = True
                status_note = f"{years_remaining}y remaining but severely underperforming"
                seat_opening_reasons.append(f"{driver.name} may be dropped mid-contract")
            else:
                status_note = f"{years_remaining} years remaining"

        driver_statuses.append(SeatStatus(
            driver_id=driver.id,
            driver_name=driver.name,
            contract_years_remaining=years_remaining,
            seat_risk=seat_risk,
            is_at_risk=is_at_risk,
            status_note=status_note,
        ))

    # Determine overall availability
    at_risk_count = sum(1 for d in driver_statuses if d.is_at_risk)

    if at_risk_count >= 1:
        seat_available = True
        if len(seat_opening_reasons) == 1:
            availability_note = seat_opening_reasons[0]
        else:
            availability_note = f"{at_risk_count} potential opening(s)"
    else:
        seat_available = False
        # Find the soonest contract expiration
        min_years = min((d.contract_years_remaining or 99 for d in driver_statuses), default=99)
        if min_years == 0:
            availability_note = "Both drivers likely to re-sign"
        elif min_years <= 2:
            availability_note = f"Both seats secure for now, earliest opening in {min_years}y"
        else:
            availability_note = "Both drivers locked in long-term"

    return seat_available, availability_note, driver_statuses


def _get_player_championship_position(save: SaveGame, player: Driver) -> int | None:
    """Get player's current championship position."""
    position_map = _championship_position_map(save)
    return position_map.get(player.id)


def calculate_team_interest(
    save: SaveGame,
    player: Driver,
    team: Team,
    player_position: int | None,
    academy_trust: int | None,
) -> ScoutingInterest:
    """
    Calculate a single F1 team's scouting interest in the player.

    This provides detailed breakdown of why a team is (or isn't) interested.
    Makes it appropriately hard to get interest from top teams.
    """
    reasons: list[str] = []
    concerns: list[str] = []
    requirements: list[str] = []

    # Get team preferences
    prefs = HIRING_PREFERENCES.get(
        team.hiring_profile or "established_midfield",
        HIRING_PREFERENCES["established_midfield"]
    )
    min_rating = int(prefs["min_rating"])

    # Calculate basic scores
    driver_rating = get_driver_rating(player)
    profile_fit = _driver_profile_fit(team, player, player_position)
    marketability = _marketability_package(player)
    team_tier = get_team_rookie_tier(team)
    academy_affinity = _academy_affinity(team, player.academy_id)
    is_academy_team = academy_affinity >= 28

    # Start with base interest based on team tier
    # Backmarker teams are more accessible, top teams are very hard
    tier_base = {
        "contender": 5,       # Nearly impossible without exceptional performance
        "upper_midfield": 15,  # Very difficult
        "lower_midfield": 30,  # Challenging but achievable
        "backmarker": 45,      # Most accessible entry point
    }
    interest = tier_base.get(team_tier, 30)

    # Championship position is critical
    if player_position is not None:
        if player_position == 1:
            interest += 35
            reasons.append("F2 championship leader - elite prospect")
        elif player_position <= 3:
            interest += 25
            reasons.append(f"P{player_position} in championship - strong contender")
        elif player_position <= 6:
            interest += 15
            reasons.append(f"Top 6 in championship")
        elif player_position <= 10:
            interest += 5
            reasons.append(f"Top 10 in championship")
        else:
            interest -= 15
            concerns.append(f"P{player_position} in championship - needs improvement")
    else:
        interest -= 20
        concerns.append("No championship position data")

    # Driver rating vs team minimum
    rating_gap = driver_rating - min_rating
    if rating_gap >= 10:
        interest += 15
        reasons.append(f"Rating ({driver_rating}) exceeds team minimum")
    elif rating_gap >= 0:
        interest += 8
        reasons.append(f"Meets team's rating threshold")
    elif rating_gap >= -5:
        interest -= 5
        concerns.append(f"Rating slightly below team standard")
    else:
        interest -= 15
        concerns.append(f"Rating ({driver_rating}) below team minimum ({min_rating})")
        requirements.append(f"Improve overall rating to {min_rating}+")

    # Academy connection - significant advantage
    if is_academy_team:
        interest += 25
        reasons.append("Academy driver - internal pipeline priority")
        if academy_trust is not None:
            if academy_trust >= 85:
                interest += 15
                reasons.append("High academy trust")
            elif academy_trust >= 70:
                interest += 8
                reasons.append("Good academy standing")
            elif academy_trust < 50:
                interest -= 10
                concerns.append("Low academy trust")
    elif academy_affinity > 0:
        interest += academy_affinity // 2
        reasons.append("Affiliate team connection")
    else:
        # Non-academy drivers face extra scrutiny at top teams
        if _is_top_team(team):
            interest -= 15
            concerns.append("Not in team's academy pipeline")
            requirements.append("Exceptional results needed without academy backing")

    # Marketability for big teams
    if team.hiring_profile in {"big_brand", "title_contender"}:
        if marketability >= 85:
            interest += 12
            reasons.append("Strong marketability profile")
        elif marketability >= 75:
            interest += 5
        elif marketability < 65:
            interest -= 10
            concerns.append("Marketability below team standards")
            requirements.append("Build media presence and sponsor value")

    # Current form matters
    if player.current_form >= 85:
        interest += 10
        reasons.append("Exceptional current form")
    elif player.current_form >= 75:
        interest += 5
        reasons.append("Good recent performances")
    elif player.current_form < 60:
        interest -= 10
        concerns.append("Recent form concerns")

    # Age considerations
    if player.age <= 21:
        if team.hiring_profile in {"junior_pipeline", "long_term_project", "rebuilding"}:
            interest += 8
            reasons.append("Young talent fits team philosophy")
        elif team.hiring_profile == "veteran_stability":
            interest -= 10
            concerns.append("Team prefers experienced drivers")
    elif player.age >= 26:
        if team.hiring_profile == "junior_pipeline":
            interest -= 8
            concerns.append("Age above team's target demographic")

    # Specific attributes teams care about
    attrs = player.attributes

    if team.hiring_profile == "title_contender":
        # Title contenders need mental giants
        mental_score = (attrs.pressure + attrs.composure + attrs.consistency) / 3
        if mental_score >= 82:
            reasons.append("Mental fortitude suits championship pressure")
        else:
            concerns.append("Needs to prove championship mentality")
            requirements.append("Demonstrate composure in high-pressure situations")

    if team.hiring_profile == "financially_pressured":
        if attrs.sponsor_value >= 75:
            interest += 10
            reasons.append("Brings valuable sponsor connections")

    if team.hiring_profile in {"rebuilding", "junior_pipeline", "long_term_project"}:
        if player.hidden.potential >= 88:
            interest += 8
            reasons.append("High development ceiling")
        if player.hidden.development_rate >= 70:
            interest += 5
            reasons.append("Quick learner")

    # Apply tier-specific caps - makes top teams truly hard to crack
    tier_caps = {
        "contender": 35,        # Max 35% interest for contenders unless exceptional
        "upper_midfield": 55,   # Max 55% for upper midfield
        "lower_midfield": 80,   # Max 80% for lower midfield
        "backmarker": 95,       # Nearly full range for backmarkers
    }

    # === THE ANTONELLI EXCEPTION ===
    # Academy drivers of a top team with high trust can break through caps
    # This represents teams promoting their own junior program graduates
    # (e.g., Mercedes promoting Antonelli, Red Bull promoting Verstappen)
    if is_academy_team and academy_trust is not None:
        if academy_trust >= 85 and player_position is not None and player_position <= 3:
            # High trust + top 3 championship = serious internal candidate
            # Can reach 75% even at contender teams (realistic shot)
            tier_caps = {k: min(95, v + 40) for k, v in tier_caps.items()}
            if player_position == 1:
                reasons.append("Prime academy candidate for promotion")
            else:
                reasons.append("Strong academy pipeline candidate")
        elif academy_trust >= 75 and player_position is not None and player_position <= 5:
            # Good trust + top 5 = on the radar
            tier_caps = {k: min(85, v + 25) for k, v in tier_caps.items()}
        elif academy_trust >= 90:
            # Exceptional trust alone raises caps (long-term investment)
            tier_caps = {k: min(75, v + 20) for k, v in tier_caps.items()}
            reasons.append("Team has invested heavily in your development")

    # Champions and exceptional performers can exceed caps (non-academy path)
    # This is the harder path - requires truly exceptional results
    if player_position == 1 and driver_rating >= 86 and marketability >= 82:
        # Exceptional performance lifts all caps
        tier_caps = {k: min(95, v + 30) for k, v in tier_caps.items()}
    elif player_position is not None and player_position <= 2 and driver_rating >= 84:
        tier_caps = {k: min(90, v + 15) for k, v in tier_caps.items()}

    cap = tier_caps.get(team_tier, 80)
    interest = max(0, min(cap, interest))

    # Generate requirement hints for low interest
    if interest < 30:
        if player_position is None or player_position > 3:
            requirements.append("Finish in top 3 of F2 championship")
        if driver_rating < min_rating:
            requirements.append(f"Develop skills to reach {min_rating}+ rating")
        if not is_academy_team and _is_top_team(team):
            requirements.append("Without academy backing, need dominant F2 championship")

    # Academy-specific guidance for top teams
    if is_academy_team and _is_top_team(team) and interest < 50:
        if academy_trust is not None and academy_trust < 85:
            requirements.append(f"Build academy trust to 85+ (currently {academy_trust})")
        if player_position is not None and player_position > 3:
            requirements.append("Top 3 championship finish needed for promotion consideration")
        if player_position is None:
            requirements.append("Prove yourself in the championship standings")

    # === SEAT AVAILABILITY CHECK ===
    # Even high interest doesn't matter if no seat is available
    seat_available, availability_note, current_drivers = _evaluate_team_seat_availability(save, team)

    if not seat_available:
        # Reduce effective interest if no seat is available
        # But keep tracking the "potential interest" for when a seat opens
        concerns.append(f"No seat available: {availability_note}")
        if interest >= 50:
            requirements.append("Wait for contract expiration or driver underperformance")

    return ScoutingInterest(
        team_id=team.id,
        team_name=team.name,
        interest_level=interest,
        interest_tier=_interest_tier_from_level(interest),
        reasons=reasons[:4],  # Limit to top 4
        concerns=concerns[:4],  # Limit to top 4 (increased for seat info)
        requirements=requirements[:3],  # Limit to top 3
        car_performance=team.car_performance,
        team_tier=team_tier,
        is_academy_team=is_academy_team,
        hiring_profile=team.hiring_profile or "established_midfield",
        seat_available=seat_available,
        seat_availability_note=availability_note,
        current_drivers=current_drivers,
    )


def get_all_f1_team_interest(save: SaveGame) -> list[ScoutingInterest]:
    """
    Get scouting interest from all F1 teams for the player.

    Returns a list sorted by interest level (highest first).
    """
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    if not player:
        return []

    # Only relevant for F2 drivers looking to move up
    if player.series != "F2":
        return []

    # Get player's championship position
    player_position = _get_player_championship_position(save, player)

    # Get academy trust if applicable
    academy_trust = None
    if player.academy_id:
        academy_state = next(
            (s for s in save.academy_states if s.academy_id == player.academy_id),
            None
        )
        if academy_state:
            academy_trust = academy_state.trust

    # Calculate interest from all F1 teams
    interests: list[ScoutingInterest] = []

    for team in save.teams:
        if team.series != "F1":
            continue

        interest = calculate_team_interest(
            save=save,
            player=player,
            team=team,
            player_position=player_position,
            academy_trust=academy_trust,
        )
        interests.append(interest)

    # Sort by interest level (highest first)
    interests.sort(key=lambda x: x.interest_level, reverse=True)

    return interests


def get_scouting_summary(save: SaveGame) -> dict:
    """
    Get a summary of the player's scouting situation.

    Returns overview statistics and top interested teams.
    """
    interests = get_all_f1_team_interest(save)

    if not interests:
        return {
            "available": False,
            "message": "Scouting data only available for F2 drivers",
        }

    # Count teams at each interest tier
    tier_counts = {
        "pursuing": 0,
        "very_interested": 0,
        "interested": 0,
        "watching": 0,
        "none": 0,
    }
    for interest in interests:
        tier_counts[interest.interest_tier] += 1

    # Get top 3 most interested teams
    top_teams = [i.to_dict() for i in interests[:3] if i.interest_level >= 15]

    # Calculate overall "heat" score
    heat_score = sum(i.interest_level for i in interests) // len(interests) if interests else 0

    # Get player position for context
    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    player_position = _get_player_championship_position(save, player) if player else None

    # Count seats with openings
    seats_available = sum(1 for i in interests if i.seat_available)
    realistic_opportunities = sum(
        1 for i in interests
        if i.seat_available and i.interest_level >= 35
    )

    return {
        "available": True,
        "heatScore": heat_score,
        "tierCounts": tier_counts,
        "topTeams": top_teams,
        "allTeams": [i.to_dict() for i in interests],
        "playerPosition": player_position,
        "teamsWithInterest": sum(1 for i in interests if i.interest_level >= 35),
        "teamsWatching": sum(1 for i in interests if 15 <= i.interest_level < 35),
        "seatsAvailable": seats_available,
        "realisticOpportunities": realistic_opportunities,
    }
