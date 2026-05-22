# F1 Career Simulator

Personal F1/F2 career simulator web app.

## Project Structure

- `frontend` - Next.js app for career creation, dashboards, race viewer, and UI.
- `backend` - FastAPI app for data loading, save games, and simulation logic.
- `backend/app/data` - editable JSON files for drivers, teams, academies, tracks, and calendars.
- `backend/app/engine` - race, weekend, standings, progression, and market simulation.
- `backend/app/models` - Pydantic domain models.
- `backend/app/api` - FastAPI route modules.
- `backend/app/save` - JSON save-game persistence.

## Current Capabilities

The app currently supports a complete early career loop from F2 into F1:

- Create a custom driver with background, archetype, F2 team, academy, and difficulty.
- Run F2 race weekends through either auto-simulation or interactive player decisions.
- Track practice, qualifying, sprint and feature race results, lap logs, weather, tyre wear, safety cars, DNFs, points, standings, and news.
- Manage between-race activities that affect fatigue, morale, form, academy trust, rivalries, and race preparation.
- Progress through a season into offseason summaries, contract evaluation, silly season driver moves, F1 offers, and next-season setup.
- Transition promoted players onto an F1 calendar with F1 teams, standings, and race points.

## Implemented Systems

### Data Foundation

- Editable 2026 JSON data for F1/F2 drivers, teams, academies, tracks, F2 calendar, points systems, and starter events.
- Pydantic models for drivers, teams, academies, tracks, calendar rounds, and bootstrap data.
- Data loader validation for cross-file references.
- FastAPI data endpoints:
  - `GET /data/bootstrap`
  - `GET /data/drivers/f1`
  - `GET /data/drivers/f2`
  - `GET /data/teams/f1`
  - `GET /data/teams/f2`
  - `GET /data/academies`
  - `GET /data/tracks`
  - `GET /data/calendar/f2`

### Save-Game Foundation

- JSON save snapshots under `backend/saves`.
- Save files include current date, phase, rosters, teams, academy state,
  calendar, standings shell, news, contracts, rivalries, random seed, and event
  flags.
- FastAPI save endpoints:
  - `POST /saves`
  - `GET /saves`
  - `GET /saves/{save_id}`
  - `DELETE /saves/{save_id}`

### Career Creation

- FastAPI career endpoints for creation options and new custom careers.
- Player driver generation from background and archetype modifiers.
- Initial F2 team assignment, academy linkage, contracts, and race-week setup.

### Race Weekend Simulation

- Full F2 and F1 weekend simulation for a save and calendar round.
- Practice, qualifying, sprint race, feature race, race classifications, lap
  logs, weather, tire wear, safety cars, DNFs, points, standings, and news.
- Interactive race mode with decision prompts for starts, attacks, defence,
  weather, tyre management, safety cars, and late-race pressure.
- FastAPI weekend endpoints:
  - `GET /career/{save_id}/weekend/next/round`
  - `POST /career/{save_id}/weekend/next/simulate`
  - `POST /career/{save_id}/weekend/{round_id}/simulate`
  - `GET /career/{save_id}/weekend/{round_id}`
- FastAPI interactive race endpoints:
  - `POST /career/{save_id}/race/{round_id}/prepare`
  - `POST /career/{save_id}/race/{round_id}/{race_type}/start`
  - `POST /career/{save_id}/race/{round_id}/{race_type}/simulate`
  - `POST /career/{save_id}/race/{round_id}/{race_type}/decide`
  - `POST /career/{save_id}/race/{round_id}/{race_type}/auto-complete`
  - `POST /career/{save_id}/race/{round_id}/{race_type}/complete`
  - `POST /career/{save_id}/race/{round_id}/finalize`

### Between-Race Activities

- Activities such as simulator work, fitness recovery, media interviews, and
  sponsor events.
- Player status tracking for fatigue, morale, form, reputation, and days until
  the next race.
- Skip-to-race-week flow that advances the save date and phase.

### Academy And Rivalries

- Academy trust, seat security, F1 pathway, warnings, opportunities, and season
  milestone evaluations.
- Rivalry generation and updates based on teammate battles, championship
  pressure, race results, and incidents.

### Season Progression And Silly Season

- Season summaries with champions, team champions, final standings, and player
  performance ratings.
- Offseason phase with F1 offer evaluation, player F1 decisions, AI market
  simulation, contract renewals, and next-season preparation.
- F1 promotion path that switches the active calendar, standings, teams, race
  field, and scoring to the F1 series.

## Dev Utilities

Run the backend test suite:

```bash
python3 -m pytest backend/tests
```

Run frontend type/build checks:

```bash
cd frontend
npm run typecheck
npm run build
```

Run a standalone F1 season simulation without touching career saves:

```bash
python3 backend/scripts/simulate_f1_season.py --seed 2026
```

Use `--rounds 3` for a shorter sample run.
