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

## First Milestone

Create a driver, choose an F2 team and academy, simulate one F2 race weekend with a lap-by-lap timing feed, make a few decisions, and see standings plus a news headline.

## Current Phase

Phase 1 data foundation is implemented:

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
