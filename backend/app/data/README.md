# Data Files

Editable seed data for the career simulator. Real-world names are kept here so
the simulation engine can stay data-driven.

Initial 2026 roster/calendar references:

- F1 drivers and teams: `https://www.formula1.com/en/drivers`
- F2 teams and drivers: `https://www.fiaformula2.com/Teams-and-Drivers`
- F2 calendar: `https://www.fiaformula2.com/Calendar`

Attribute values are gameplay tuning estimates, not official ratings.

F1 team tuning notes:

- `carPerformance` is weighted toward current 2026 race form and constructor
  points.
- `developmentRate` is not the same as current pace. It reflects recent
  development trajectory, resources, and believable upgrade potential. For
  example, McLaren keeps the highest development rate because its 2024-2025
  rise was exceptional even though Mercedes is the strongest early-2026 team.
- New or reset projects such as Audi and Cadillac have lower current pace but
  stronger long-term development than their current points alone would imply.
- Large-resource underperformers such as Aston Martin keep strong development
  potential while their current performance is set near the back based on 2026
  results so far.

Track data includes every circuit on the 2026 F1 calendar plus a wider pool of
recent, historic, and plausible F1 venues for future dynamic calendars.
