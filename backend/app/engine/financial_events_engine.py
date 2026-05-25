"""
Financial Events Engine

Handles rare but impactful financial events that can affect F1 teams:
- Bankruptcy (team replaced by new entrant)
- Takeover (new ownership, budget/development changes)
- Cash injection (sudden investment boost)
- Manufacturer entry/exit
- Title sponsor changes

These events are RARE - typically 0-1 events per season, sometimes none for years.
"""
from __future__ import annotations

import random
from uuid import uuid4

from app.data.loaders import get_potential_entrants, get_takeover_investors
from app.models.car import CarComponentReliability, TeamCarState
from app.models.car_development import TeamDevelopmentState
from app.models.save_game import NewsItem, SaveGame
from app.models.team import Team
from app.models.world import FinancialEvent, PotentialEntrant


def process_financial_events(save: SaveGame) -> tuple[SaveGame, list[NewsItem], list[FinancialEvent]]:
    """
    Process rare financial events during offseason.

    Returns updated save, news items, and any financial events that occurred.
    Events are very rare - most seasons will have no events.
    """
    rng = random.Random(save.random_seed + save.season * 7919)
    news: list[NewsItem] = []
    events: list[FinancialEvent] = []

    f1_teams = [t for t in save.teams if t.series == "F1"]

    # Get available entrants (filter out any that have already entered)
    existing_team_ids = {t.id for t in save.teams}
    entrants = [e for e in get_potential_entrants() if e.interested and e.id not in existing_team_ids]
    investors = get_takeover_investors()

    # ═══════════════════════════════════════════════════════════════════════
    # BANKRUPTCY CHECK - Only for backmarkers and struggling midfield teams
    # ═══════════════════════════════════════════════════════════════════════
    # Real F1: Caterham, Manor, HRT, Force India - always backmarkers/struggling midfield
    # Top teams (Ferrari, Mercedes, Red Bull, McLaren) NEVER go bankrupt

    # Teams that are protected from bankruptcy (historic teams, major manufacturers)
    protected_teams = {
        "ferrari", "mercedes", "red_bull", "mclaren",  # Historic top teams - never bankrupt
    }

    for team in f1_teams:
        state = save.team_development.get(team.id)
        if not state:
            continue

        # Protected teams NEVER go bankrupt
        if team.id in protected_teams:
            continue

        # Well-funded teams very rarely go bankrupt
        if team.financial_health >= 80:
            continue

        # Top performers are safe
        if team.car_performance >= 88:
            continue

        # Bankruptcy risk factors
        bankruptcy_risk = 0

        # Financial distress is the primary driver
        if team.financial_health < 55:
            bankruptcy_risk += 8
        elif team.financial_health < 65:
            bankruptcy_risk += 4
        elif team.financial_health < 75:
            bankruptcy_risk += 1

        # Sustained poor performance compounds the risk
        if state.momentum <= -6:
            bankruptcy_risk += 5
        elif state.momentum <= -3:
            bankruptcy_risk += 2

        # Being at the back increases risk significantly
        if team.car_performance < 68:
            bankruptcy_risk += 6
        elif team.car_performance < 75:
            bankruptcy_risk += 3
        elif team.car_performance < 82:
            bankruptcy_risk += 1

        # Cap at 15% max - bankruptcy should be RARE but possible
        bankruptcy_risk = min(15, bankruptcy_risk)

        # Roll for bankruptcy
        if bankruptcy_risk > 0 and rng.randint(1, 100) <= bankruptcy_risk:
            # Team goes bankrupt - find a replacement
            event, team_news = _handle_bankruptcy(save, team, entrants, rng)
            if event:
                events.append(event)
                news.extend(team_news)
                # Remove this entrant from pool for future events this season
                entrants = [e for e in entrants if e.id != event.entrant_id]
            break  # Only one bankruptcy per season max

    # ═══════════════════════════════════════════════════════════════════════
    # TAKEOVER CHECK - New ownership for struggling or mid-tier teams
    # ═══════════════════════════════════════════════════════════════════════
    # Real F1: Stroll buying Force India, Dorilton buying Williams
    # Maybe once every 3-5 years
    # Top teams (Ferrari, Mercedes, Red Bull, McLaren) don't get taken over

    if not events:  # Don't do takeover if bankruptcy already happened
        # Exclude historic top teams from takeover
        takeover_protected = {"ferrari", "mercedes", "red_bull", "mclaren"}
        takeover_candidates = [
            t for t in f1_teams
            if t.id not in takeover_protected
            and t.financial_health < 85
            and t.car_performance < 90
        ]

        if takeover_candidates and investors:
            # 5% chance of any takeover happening this season
            if rng.randint(1, 100) <= 5:
                # Weight toward struggling teams
                weights = [max(1, 100 - t.financial_health + (85 - t.car_performance) // 2) for t in takeover_candidates]
                team = rng.choices(takeover_candidates, weights=weights, k=1)[0]
                investor = rng.choice(investors)
                event, team_news = _handle_takeover(save, team, investor, rng)
                events.append(event)
                news.extend(team_news)

    # ═══════════════════════════════════════════════════════════════════════
    # CASH INJECTION - Major sponsor or investment for a team
    # ═══════════════════════════════════════════════════════════════════════
    # Real F1: Aramco at Aston Martin, Mission Winnow at Ferrari
    # Maybe once every 2 years

    if not events:  # Don't stack multiple events
        # 6% chance of cash injection
        if rng.randint(1, 100) <= 6:
            # More likely for mid-tier teams (they need it more)
            candidates = [t for t in f1_teams if 60 <= t.financial_health <= 80]
            if candidates:
                team = rng.choice(candidates)
                event, team_news = _handle_cash_injection(save, team, rng)
                events.append(event)
                news.extend(team_news)

    # ═══════════════════════════════════════════════════════════════════════
    # MANUFACTURER EXIT - A manufacturer pulls out of F1
    # ═══════════════════════════════════════════════════════════════════════
    # Real F1: Honda leaving McLaren, BMW leaving, Toyota leaving
    # Very rare - maybe once every 5-7 years

    if not events:
        # Only manufacturer-backed teams can have this happen
        manufacturer_teams = [
            t for t in f1_teams
            if t.id in ["audi", "cadillac", "alpine"]  # Teams with manufacturer backing
        ]

        # 2% chance per season
        if manufacturer_teams and rng.randint(1, 100) <= 2:
            team = rng.choice(manufacturer_teams)
            event, team_news = _handle_manufacturer_exit(save, team, rng)
            events.append(event)
            news.extend(team_news)

    # ═══════════════════════════════════════════════════════════════════════
    # TITLE SPONSOR CHANGE - Major sponsor arrives or leaves
    # ═══════════════════════════════════════════════════════════════════════
    # More common than major structural changes - a few per decade

    if not events:
        # 18% chance of sponsor change
        if rng.randint(1, 100) <= 18:
            team = rng.choice(f1_teams)

            # 55% chance of gaining sponsor, 45% of losing
            if rng.random() < 0.55:
                event, team_news = _handle_sponsor_gain(save, team, rng)
            else:
                event, team_news = _handle_sponsor_loss(save, team, rng)

            events.append(event)
            news.extend(team_news)

    # Apply events to save
    if events:
        save = _apply_financial_events(save, events)

    return save, news, events


def _handle_bankruptcy(
    save: SaveGame,
    team: Team,
    entrants: list[PotentialEntrant],
    rng: random.Random
) -> tuple[FinancialEvent | None, list[NewsItem]]:
    """Handle a team going bankrupt and being replaced."""
    if not entrants:
        return None, []

    # Pick a replacement - prefer those with higher likelihood
    weights = [max(1, 50 + e.likelihood_modifier) for e in entrants]
    entrant = rng.choices(entrants, weights=weights, k=1)[0]

    event = FinancialEvent(
        id=str(uuid4()),
        season=save.season,
        event_type="bankruptcy",
        team_id=team.id,
        new_team_id=entrant.id,
        entrant_id=entrant.id,
        budget_change=entrant.base_budget - team.financial_health,
        development_change=entrant.base_development - team.development_rate,
        headline=f"{team.name} exits F1, {entrant.name} takes over entry",
        description=(
            f"After years of financial struggles, {team.name} has ceased operations in Formula 1. "
            f"{entrant.name} has acquired the entry and will compete from next season with "
            f"new facilities and investment."
        ),
    )

    news = [
        NewsItem(
            id=f"bankruptcy_{team.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"BREAKING: {team.name} exits Formula 1",
            body=(
                f"{team.name} has announced they will cease Formula 1 operations at the end of the season "
                f"due to financial difficulties. The team's entry has been acquired by {entrant.name}, "
                f"who will take over the grid slot from next year."
            ),
            importance=5,
        ),
        NewsItem(
            id=f"entrant_{entrant.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"{entrant.name} confirms F1 entry",
            body=(
                f"{entrant.name} has officially confirmed their entry into Formula 1, taking over the "
                f"grid slot vacated by {team.name}. The {entrant.country} outfit brings fresh investment "
                f"and ambition to the paddock."
            ),
            importance=4,
        ),
    ]

    return event, news


def _handle_takeover(
    save: SaveGame,
    team: Team,
    investor,  # TakeoverInvestor
    rng: random.Random
) -> tuple[FinancialEvent, list[NewsItem]]:
    """Handle a team being taken over by new owners."""
    budget_change = min(30, investor.budget_boost + rng.randint(-3, 3))
    dev_change = min(20, investor.development_boost + rng.randint(-2, 2))

    event = FinancialEvent(
        id=str(uuid4()),
        season=save.season,
        event_type="takeover",
        team_id=team.id,
        budget_change=budget_change,
        development_change=dev_change,
        headline=f"{investor.name} completes takeover of {team.name}",
        description=(
            f"{investor.name} has completed the acquisition of {team.name}, promising significant "
            f"investment in facilities and personnel. The team is expected to benefit from "
            f"increased resources in the coming seasons."
        ),
    )

    news = [
        NewsItem(
            id=f"takeover_{team.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"{team.name} sold to {investor.name}",
            body=(
                f"In a major paddock shake-up, {team.name} has been acquired by {investor.name}. "
                f"The new owners have pledged significant investment to improve the team's "
                f"competitiveness, with plans to upgrade facilities and recruit top talent."
            ),
            importance=4,
        ),
    ]

    return event, news


def _handle_cash_injection(
    save: SaveGame,
    team: Team,
    rng: random.Random
) -> tuple[FinancialEvent, list[NewsItem]]:
    """Handle a major cash injection from new sponsor or investor."""
    sponsor_names = [
        "Aramco", "Amazon", "Apple", "Google", "Microsoft", "Oracle",
        "Crypto.com", "Binance", "Saudi Investment Fund", "Qatar Airways",
        "Emirates", "Santander", "Rolex", "Tag Heuer", "Richard Mille"
    ]
    sponsor = rng.choice(sponsor_names)
    budget_boost = rng.randint(8, 18)

    event = FinancialEvent(
        id=str(uuid4()),
        season=save.season,
        event_type="cash_injection",
        team_id=team.id,
        budget_change=budget_boost,
        development_change=rng.randint(2, 6),
        headline=f"{team.name} secures major {sponsor} partnership",
        description=(
            f"{team.name} has announced a landmark partnership with {sponsor}, bringing "
            f"significant additional funding to their F1 program."
        ),
    )

    news = [
        NewsItem(
            id=f"cash_injection_{team.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"{team.name} lands major {sponsor} deal",
            body=(
                f"{team.name} has secured a multi-year partnership with {sponsor} worth a "
                f"reported significant sum. The deal will provide a substantial boost to the "
                f"team's development budget and is expected to accelerate their progress."
            ),
            importance=3,
        ),
    ]

    return event, news


def _handle_manufacturer_exit(
    save: SaveGame,
    team: Team,
    rng: random.Random
) -> tuple[FinancialEvent, list[NewsItem]]:
    """Handle a manufacturer pulling out of F1."""
    budget_loss = rng.randint(15, 25)
    dev_loss = rng.randint(8, 15)

    event = FinancialEvent(
        id=str(uuid4()),
        season=save.season,
        event_type="manufacturer_exit",
        team_id=team.id,
        budget_change=-budget_loss,
        development_change=-dev_loss,
        headline=f"Manufacturer backing withdrawn from {team.name}",
        description=(
            f"In a shock announcement, the manufacturer backing {team.name} has decided to "
            f"withdraw from Formula 1. The team will continue as a privateer operation but "
            f"faces significant challenges ahead."
        ),
    )

    news = [
        NewsItem(
            id=f"manufacturer_exit_{team.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"BREAKING: {team.name} loses manufacturer support",
            body=(
                f"In a major blow to their F1 ambitions, {team.name} has lost their manufacturer "
                f"backing. The team will have to find alternative funding and technical partnerships "
                f"to remain competitive. Sources suggest the withdrawal is due to a strategic "
                f"shift in the parent company's motorsport priorities."
            ),
            importance=5,
        ),
    ]

    return event, news


def _handle_sponsor_loss(
    save: SaveGame,
    team: Team,
    rng: random.Random
) -> tuple[FinancialEvent, list[NewsItem]]:
    """Handle a team losing their title sponsor."""
    budget_loss = rng.randint(5, 12)

    event = FinancialEvent(
        id=str(uuid4()),
        season=save.season,
        event_type="title_sponsor_loss",
        team_id=team.id,
        budget_change=-budget_loss,
        headline=f"{team.name} loses title sponsor",
        description=f"{team.name} will need to find alternative sponsorship after losing their title partner.",
    )

    news = [
        NewsItem(
            id=f"sponsor_loss_{team.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"{team.name} title sponsor ends partnership",
            body=(
                f"{team.name} has confirmed their title sponsor will not renew their contract. "
                f"The team is actively seeking replacement partners but may face a budget shortfall "
                f"in the short term."
            ),
            importance=2,
        ),
    ]

    return event, news


def _handle_sponsor_gain(
    save: SaveGame,
    team: Team,
    rng: random.Random
) -> tuple[FinancialEvent, list[NewsItem]]:
    """Handle a team gaining a new major sponsor."""
    sponsor_names = [
        "Tech Giant", "Energy Drink Brand", "Cryptocurrency Platform",
        "Luxury Watch Maker", "Airline Partner", "Financial Services Group"
    ]
    sponsor = rng.choice(sponsor_names)
    budget_boost = rng.randint(4, 10)

    event = FinancialEvent(
        id=str(uuid4()),
        season=save.season,
        event_type="title_sponsor_gain",
        team_id=team.id,
        budget_change=budget_boost,
        headline=f"{team.name} announces new partnership",
        description=f"{team.name} secures new {sponsor} sponsorship deal.",
    )

    news = [
        NewsItem(
            id=f"sponsor_gain_{team.id}_{save.season}",
            date=save.current_date,
            category="system",
            headline=f"{team.name} announces new sponsorship deal",
            body=(
                f"{team.name} has secured a new partnership with a major {sponsor}. "
                f"The deal will provide additional resources for the team's development program."
            ),
            importance=2,
        ),
    ]

    return event, news


def _apply_financial_events(save: SaveGame, events: list[FinancialEvent]) -> SaveGame:
    """Apply financial events to the save game."""
    updated_teams = list(save.teams)
    updated_development = dict(save.team_development)
    world_state = save.world_state

    for event in events:
        if event.event_type == "bankruptcy":
            # Replace the team with the new entrant
            updated_teams, updated_development = _replace_team(
                updated_teams, updated_development, event, save.season
            )
        else:
            # Modify existing team
            for i, team in enumerate(updated_teams):
                if team.id == event.team_id:
                    new_financial = max(40, min(100, team.financial_health + event.budget_change))
                    new_dev = max(50, min(95, team.development_rate + event.development_change))

                    updated_teams[i] = team.model_copy(
                        update={
                            "financial_health": new_financial,
                            "development_rate": new_dev,
                        }
                    )
                    break

    # Add events to world state
    updated_world = world_state.model_copy(
        update={"financial_events": world_state.financial_events + events}
    )

    return save.model_copy(
        update={
            "teams": updated_teams,
            "team_development": updated_development,
            "world_state": updated_world,
        }
    )


def _replace_team(
    teams: list[Team],
    development: dict[str, TeamDevelopmentState],
    event: FinancialEvent,
    season: int,
) -> tuple[list[Team], dict[str, TeamDevelopmentState]]:
    """Replace a bankrupt team with a new entrant."""
    from app.data.loaders import get_potential_entrants

    entrants = get_potential_entrants()
    entrant = next((e for e in entrants if e.id == event.entrant_id), None)

    if not entrant:
        return teams, development

    # Find and replace the old team
    updated_teams = []
    old_team = None

    for team in teams:
        if team.id == event.team_id:
            old_team = team
            # Create new team from entrant
            new_team = Team(
                id=entrant.id,
                name=entrant.name,
                series="F1",
                country=entrant.country,
                car_performance=65,  # New teams start at back
                reliability=70,
                strategy=70,
                development_rate=entrant.base_development,
                financial_health=entrant.base_budget,
                academy_id=None,
                seat_security=60,
                car_state=TeamCarState(
                    team_id=entrant.id,
                    season=season,
                    component_reliability=CarComponentReliability(),
                ),
            )
            updated_teams.append(new_team)
        else:
            updated_teams.append(team)

    # Update development state
    updated_dev = {k: v for k, v in development.items() if k != event.team_id}
    updated_dev[entrant.id] = TeamDevelopmentState(
        team_id=entrant.id,
        engineering_quality=entrant.base_development,
        simulator_quality=65,
        manufacturing_speed=65,
    )

    return updated_teams, updated_dev
