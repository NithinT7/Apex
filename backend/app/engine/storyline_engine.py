"""Pre-race storyline and drama generation for weekend preparation."""

from __future__ import annotations

import random
import uuid
from typing import Literal

from app.models.driver import Driver
from app.models.save_game import NewsItem, SaveGame
from app.models.team import Team
from app.models.track import Track


StorylineType = Literal[
    "championship_battle",
    "rivalry_clash",
    "redemption_arc",
    "form_streak",
    "team_drama",
    "underdog_story",
    "pressure_cooker",
    "home_race",
    "contract_pressure",
    "rookie_test",
    "veteran_farewell",
    "academy_showcase",
]


class PreRaceStoryline:
    """A storyline heading into a race weekend."""

    def __init__(
        self,
        story_type: StorylineType,
        headline: str,
        narrative: str,
        drama_level: int,  # 1-10
        driver_ids: list[str],
        team_ids: list[str] | None = None,
    ):
        self.id = f"story_{uuid.uuid4().hex[:8]}"
        self.story_type = story_type
        self.headline = headline
        self.narrative = narrative
        self.drama_level = drama_level
        self.driver_ids = driver_ids
        self.team_ids = team_ids or []


def generate_pre_race_storylines(
    save: SaveGame,
    round_id: str,
    track: Track,
) -> list[PreRaceStoryline]:
    """Generate compelling pre-race storylines for the upcoming weekend."""
    storylines: list[PreRaceStoryline] = []
    rng = random.Random(f"{save.random_seed}:{round_id}:storylines")

    player = next((d for d in save.drivers if d.id == save.player_driver_id), None)
    calendar_round = next((r for r in save.calendar if r.id == round_id), None)
    if not calendar_round:
        return []

    series = calendar_round.series
    drivers = [d for d in save.drivers if d.series == series]
    teams = [t for t in save.teams if t.series == series]
    completed_rounds = sum(1 for r in save.calendar if r.completed and r.series == series)

    # Championship battle storylines
    storylines.extend(_championship_storylines(save, drivers, completed_rounds, rng))

    # Rivalry storylines
    storylines.extend(_rivalry_storylines(save, player, drivers, rng))

    # Form and momentum storylines
    storylines.extend(_form_storylines(save, drivers, rng))

    # Team drama storylines
    storylines.extend(_team_drama_storylines(save, teams, drivers, rng))

    # Track-specific storylines
    storylines.extend(_track_storylines(save, track, drivers, rng))

    # Pressure and contract storylines
    storylines.extend(_pressure_storylines(save, player, drivers, completed_rounds, rng))

    # Academy showcase storylines
    storylines.extend(_academy_storylines(save, drivers, rng))

    # Sort by drama level and return top stories
    storylines.sort(key=lambda s: s.drama_level, reverse=True)
    return storylines[:6]


def _championship_storylines(
    save: SaveGame,
    drivers: list[Driver],
    completed_rounds: int,
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate championship battle storylines."""
    stories: list[PreRaceStoryline] = []
    if completed_rounds < 2:
        return stories

    standings = sorted(save.standings.driver_standings, key=lambda e: e.points, reverse=True)
    if len(standings) < 2:
        return stories

    leader_entry = standings[0]
    second_entry = standings[1]
    leader = next((d for d in drivers if d.id == leader_entry.driver_id), None)
    second = next((d for d in drivers if d.id == second_entry.driver_id), None)

    if not leader or not second:
        return stories

    gap = leader_entry.points - second_entry.points

    if gap <= 15:
        drama = 9 if gap <= 5 else 7
        stories.append(
            PreRaceStoryline(
                story_type="championship_battle",
                headline=f"Title fight reaches boiling point",
                narrative=(
                    f"Just {gap} points separate {leader.name} from {second.name} at the top. "
                    f"Every position counts this weekend as the title race enters a critical phase. "
                    f"The pressure is immense on both sides of this battle."
                ),
                drama_level=drama,
                driver_ids=[leader.id, second.id],
            )
        )
    elif gap <= 30 and completed_rounds >= 4:
        stories.append(
            PreRaceStoryline(
                story_type="championship_battle",
                headline=f"{second.name} needs a statement result",
                narrative=(
                    f"Trailing by {gap} points, {second.name} knows the championship is slipping away. "
                    f"Anything less than a podium this weekend could be fatal to title hopes."
                ),
                drama_level=6,
                driver_ids=[second.id, leader.id],
            )
        )

    # Check for third place threat
    if len(standings) >= 3:
        third_entry = standings[2]
        third = next((d for d in drivers if d.id == third_entry.driver_id), None)
        if third and second_entry.points - third_entry.points <= 10:
            stories.append(
                PreRaceStoryline(
                    story_type="championship_battle",
                    headline="Three-way fight for glory",
                    narrative=(
                        f"The top three are separated by just {leader_entry.points - third_entry.points} points. "
                        f"{leader.name}, {second.name}, and {third.name} are all in the hunt. "
                        f"This weekend could reshape the entire championship picture."
                    ),
                    drama_level=8,
                    driver_ids=[leader.id, second.id, third.id],
                )
            )

    return stories


def _rivalry_storylines(
    save: SaveGame,
    player: Driver | None,
    drivers: list[Driver],
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate rivalry-based storylines."""
    stories: list[PreRaceStoryline] = []

    for rivalry in save.rivalries:
        if rivalry.intensity < 40:
            continue

        rival = next((d for d in drivers if d.id == rivalry.opponent_id), None)
        if not rival:
            continue

        drama = min(10, 5 + rivalry.intensity // 15)

        if rivalry.rivalry_type == "teammate" and rivalry.intensity >= 60:
            player_team = next((t for t in save.teams if t.id == player.team_id), None) if player else None
            if player_team:
                stories.append(
                    PreRaceStoryline(
                        story_type="rivalry_clash",
                        headline=f"Teammate tension simmers at {player_team.name}",
                        narrative=(
                            f"The relationship between you and {rival.name} has become increasingly strained. "
                            f"On-track battles have carried into the paddock. The team is watching closely—"
                            f"whoever outperforms the other this weekend sends a powerful message."
                        ),
                        drama_level=drama,
                        driver_ids=[player.id if player else rivalry.opponent_id, rival.id],
                        team_ids=[player_team.id],
                    )
                )

        elif rivalry.rivalry_type == "championship" and rivalry.intensity >= 50:
            stories.append(
                PreRaceStoryline(
                    story_type="rivalry_clash",
                    headline=f"Championship rivals set for showdown",
                    narrative=(
                        f"You and {rival.name} have been circling each other all season. "
                        f"The respect is there, but so is the desperation to win. "
                        f"Expect fireworks when these two get close on track."
                    ),
                    drama_level=drama,
                    driver_ids=[player.id if player else rivalry.opponent_id, rival.id],
                )
            )

        elif rivalry.rivalry_type == "historical" and len(rivalry.recent_events) >= 2:
            stories.append(
                PreRaceStoryline(
                    story_type="rivalry_clash",
                    headline=f"Bad blood reaches new heights",
                    narrative=(
                        f"After {len(rivalry.recent_events)} incidents, the feud with {rival.name} "
                        f"has become personal. Neither driver is backing down. "
                        f"Stewards will be watching this one very closely."
                    ),
                    drama_level=min(10, drama + 1),
                    driver_ids=[player.id if player else rivalry.opponent_id, rival.id],
                )
            )

    return stories[:2]  # Limit rivalry stories


def _form_storylines(
    save: SaveGame,
    drivers: list[Driver],
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate form and momentum storylines."""
    stories: list[PreRaceStoryline] = []

    # Hot streak
    hot_drivers = [d for d in drivers if d.current_form >= 85]
    for driver in hot_drivers[:2]:
        stories.append(
            PreRaceStoryline(
                story_type="form_streak",
                headline=f"{driver.name} riding wave of confidence",
                narrative=(
                    f"Everything is clicking for {driver.name} right now. "
                    f"Confidence is sky-high, the car feels perfect, and results are coming. "
                    f"When a driver is in this kind of form, they're dangerous to everyone."
                ),
                drama_level=6,
                driver_ids=[driver.id],
            )
        )

    # Cold streak / redemption arc
    struggling = [d for d in drivers if d.current_form <= 55 and d.morale <= 60]
    for driver in struggling[:1]:
        stories.append(
            PreRaceStoryline(
                story_type="redemption_arc",
                headline=f"{driver.name} desperate for turnaround",
                narrative=(
                    f"Recent results have been brutal for {driver.name}. "
                    f"Confidence is low, critics are circling, and pressure is mounting. "
                    f"A strong weekend could be the spark that turns the season around."
                ),
                drama_level=7,
                driver_ids=[driver.id],
            )
        )

    return stories


def _team_drama_storylines(
    save: SaveGame,
    teams: list[Team],
    drivers: list[Driver],
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate team-related drama storylines."""
    stories: list[PreRaceStoryline] = []

    for team in teams:
        team_drivers = [d for d in drivers if d.team_id == team.id]
        if len(team_drivers) < 2:
            continue

        # Internal competition heating up
        form_gap = abs(team_drivers[0].current_form - team_drivers[1].current_form)
        if form_gap >= 15:
            leader = team_drivers[0] if team_drivers[0].current_form > team_drivers[1].current_form else team_drivers[1]
            follower = team_drivers[1] if leader == team_drivers[0] else team_drivers[0]
            stories.append(
                PreRaceStoryline(
                    story_type="team_drama",
                    headline=f"Power balance shifting at {team.name}",
                    narrative=(
                        f"{leader.name} has been dominating the internal battle at {team.name}. "
                        f"{follower.name} needs a response—and soon. Team politics rarely stay quiet "
                        f"when one driver has the upper hand for too long."
                    ),
                    drama_level=6,
                    driver_ids=[leader.id, follower.id],
                    team_ids=[team.id],
                )
            )

        # Reliability concerns
        if team.reliability <= 70:
            stories.append(
                PreRaceStoryline(
                    story_type="team_drama",
                    headline=f"{team.name} fighting reliability demons",
                    narrative=(
                        f"Mechanical failures have plagued {team.name} this season. "
                        f"The drivers know they need to push, but every extra mile risks another DNF. "
                        f"It's a high-wire act that could end in disaster at any moment."
                    ),
                    drama_level=5,
                    driver_ids=[d.id for d in team_drivers],
                    team_ids=[team.id],
                )
            )

    return stories[:2]


def _track_storylines(
    save: SaveGame,
    track: Track,
    drivers: list[Driver],
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate track-specific storylines."""
    stories: list[PreRaceStoryline] = []

    # High overtaking difficulty = qualifying importance
    if track.qualifying_importance >= 85 or track.overtaking_difficulty >= 80:
        stories.append(
            PreRaceStoryline(
                story_type="pressure_cooker",
                headline="Grid position is everything here",
                narrative=(
                    f"At {track.name}, track position is king. "
                    f"Overtaking is brutally difficult—qualifying could decide the race before it even starts. "
                    f"The pressure in Saturday's session will be immense."
                ),
                drama_level=6,
                driver_ids=[],
            )
        )

    # High tire degradation
    if track.tire_deg >= 75:
        stories.append(
            PreRaceStoryline(
                story_type="pressure_cooker",
                headline="Tire strategy will make or break results",
                narrative=(
                    f"{track.name}'s abrasive surface destroys tires. "
                    f"The strategists are working overtime, but in the end, it comes down to "
                    f"who can read the race and make the right calls under pressure."
                ),
                drama_level=5,
                driver_ids=[],
            )
        )

    # High safety car chance
    if track.safety_car_chance >= 45:
        stories.append(
            PreRaceStoryline(
                story_type="pressure_cooker",
                headline="Expect the unexpected at this circuit",
                narrative=(
                    f"Narrow margins and unforgiving walls make {track.name} a lottery. "
                    f"Safety cars are almost guaranteed, and they can flip the race on its head. "
                    f"Patience and opportunism will be key."
                ),
                drama_level=7,
                driver_ids=[],
            )
        )

    # Home race potential
    for driver in drivers:
        if driver.nationality.lower() == track.country.lower():
            stories.append(
                PreRaceStoryline(
                    story_type="home_race",
                    headline=f"Home glory on the line for {driver.name}",
                    narrative=(
                        f"{driver.name} races in front of home fans this weekend. "
                        f"The support will be incredible, but so will the pressure. "
                        f"A home win would be career-defining—a disappointment would sting for months."
                    ),
                    drama_level=7,
                    driver_ids=[driver.id],
                )
            )
            break  # Only one home race story

    return stories


def _pressure_storylines(
    save: SaveGame,
    player: Driver | None,
    drivers: list[Driver],
    completed_rounds: int,
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate pressure and contract storylines."""
    stories: list[PreRaceStoryline] = []

    # Contract pressure for drivers
    for contract in save.contracts:
        if not contract.active:
            continue
        years_left = (contract.start_season + contract.length_years) - save.season
        if years_left == 1:
            driver = next((d for d in drivers if d.id == contract.driverId), None)
            if driver and driver.current_form <= 70:
                stories.append(
                    PreRaceStoryline(
                        story_type="contract_pressure",
                        headline=f"Contract year pressure mounts for {driver.name}",
                        narrative=(
                            f"With their contract expiring, {driver.name} knows every race is an audition. "
                            f"Recent form hasn't helped. The whispers about replacements are getting louder, "
                            f"and a strong performance this weekend is crucial."
                        ),
                        drama_level=7,
                        driver_ids=[driver.id],
                    )
                )

    # Rookie test
    young_drivers = [d for d in drivers if d.age <= 21]
    for driver in young_drivers[:1]:
        if completed_rounds <= 6:
            stories.append(
                PreRaceStoryline(
                    story_type="rookie_test",
                    headline=f"{driver.name} faces another rookie examination",
                    narrative=(
                        f"The first season is always a learning curve, and {driver.name} is under the microscope. "
                        f"Every mistake is magnified, every success scrutinized. "
                        f"Can they handle the pressure of being the new kid on the block?"
                    ),
                    drama_level=5,
                    driver_ids=[driver.id],
                )
            )

    # Veteran farewell consideration
    veterans = [d for d in drivers if d.age >= 37]
    for driver in veterans[:1]:
        if driver.hidden.retirementChance >= 40:
            stories.append(
                PreRaceStoryline(
                    story_type="veteran_farewell",
                    headline=f"Could this be one of {driver.name}'s final seasons?",
                    narrative=(
                        f"The paddock whispers grow louder about {driver.name}'s future. "
                        f"At {driver.age}, the physical demands are immense. "
                        f"Every race could be part of a farewell tour."
                    ),
                    drama_level=5,
                    driver_ids=[driver.id],
                )
            )

    return stories[:2]


def _academy_storylines(
    save: SaveGame,
    drivers: list[Driver],
    rng: random.Random,
) -> list[PreRaceStoryline]:
    """Generate academy-related storylines."""
    stories: list[PreRaceStoryline] = []

    for state in save.academy_states:
        if state.trust >= 85:
            academy = next((a for a in save.academies if a.id == state.academy_id), None)
            academy_driver = next((d for d in drivers if d.academy_id == state.academy_id), None)
            if academy and academy_driver:
                stories.append(
                    PreRaceStoryline(
                        story_type="academy_showcase",
                        headline=f"{academy.name} eyes F1 promotion decision",
                        narrative=(
                            f"Academy trust is sky-high. {academy.name} is seriously evaluating "
                            f"their junior for a potential F1 seat. "
                            f"A strong weekend could seal the deal—this is audition season."
                        ),
                        drama_level=8,
                        driver_ids=[academy_driver.id],
                    )
                )

    return stories[:1]


def storylines_to_news(
    storylines: list[PreRaceStoryline],
    date: str,
) -> list[NewsItem]:
    """Convert storylines to news items for the pre-race feed."""
    news: list[NewsItem] = []
    for story in storylines:
        category = "media"
        if story.story_type in {"rivalry_clash", "team_drama"}:
            category = "rivalry"
        elif story.story_type in {"contract_pressure", "academy_showcase"}:
            category = "rumor"

        news.append(
            NewsItem(
                id=f"prerace_{story.id}",
                date=date,
                category=category,  # type: ignore[arg-type]
                headline=story.headline,
                body=story.narrative,
                linked_driver_ids=story.driver_ids,
                importance=min(5, 2 + story.drama_level // 3),
            )
        )
    return news


def storylines_to_dict(storylines: list[PreRaceStoryline]) -> list[dict]:
    """Convert storylines to JSON-serializable dict format."""
    return [
        {
            "id": s.id,
            "type": s.story_type,
            "headline": s.headline,
            "narrative": s.narrative,
            "dramaLevel": s.drama_level,
            "driverIds": s.driver_ids,
            "teamIds": s.team_ids,
        }
        for s in storylines
    ]
