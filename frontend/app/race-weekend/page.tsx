import Link from "next/link";

export default function RaceWeekendPage() {
  return (
    <main className="page-shell">
      <Link href="/" className="eyebrow-link">
        Back to dashboard
      </Link>
      <h1>Race Weekend</h1>
      <p className="lede">
        The backend can now simulate a complete F2 weekend with practice,
        qualifying, sprint, feature race, lap-by-lap logs, safety cars, DNFs,
        points, standings updates, and a headline.
      </p>
      <section className="panel-grid">
        <div className="panel">
          <h2>Current Flow</h2>
          <ul className="compact-list">
            <li>Create a career from the driver creation page.</li>
            <li>Use POST /career/:saveId/weekend/f2_2026_round_01/simulate.</li>
            <li>Read the completed result with GET /career/:saveId/weekend/f2_2026_round_01.</li>
          </ul>
        </div>
        <div className="panel">
          <h2>Simulation Output</h2>
          <p>
            Each weekend result includes weather, setup notes, qualifying gaps,
            sprint and feature classifications, every race lap snapshot, safety
            car laps, DNFs, points, and post-race news.
          </p>
        </div>
      </section>
    </main>
  );
}
