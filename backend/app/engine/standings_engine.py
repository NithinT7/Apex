from app.models.race import RaceResult
from app.models.save_game import ChampionshipEntry, ChampionshipState


def apply_race_points(standings: ChampionshipState, race: RaceResult) -> ChampionshipState:
    entries = {entry.driver_id: entry for entry in standings.driver_standings}
    for classified in race.classification:
        existing = entries.get(classified.driver_id, ChampionshipEntry(driver_id=classified.driver_id))
        entries[classified.driver_id] = existing.model_copy(
            update={
                "points": existing.points + classified.points,
                "wins": existing.wins + (1 if classified.position == 1 else 0),
                "podiums": existing.podiums + (1 if classified.position <= 3 else 0),
                "dnfs": existing.dnfs + (1 if classified.status == "dnf" else 0),
            }
        )

    return standings.model_copy(
        update={
            "driver_standings": sorted(
                entries.values(),
                key=lambda entry: (entry.points, entry.wins, entry.podiums),
                reverse=True,
            )
        }
    )
