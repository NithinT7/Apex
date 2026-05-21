import Link from "next/link";

export default function SavesPage() {
  return (
    <main className="page-shell">
      <Link href="/" className="eyebrow-link">
        Back to dashboard
      </Link>
      <h1>Save / Load</h1>
      <p className="lede">
        Save-game persistence is available through the backend API. The next
        phase will connect driver creation to these save files.
      </p>
      <section className="panel-grid">
        <div className="panel">
          <h2>Available API</h2>
          <ul className="compact-list">
            <li>POST /saves</li>
            <li>GET /saves</li>
            <li>GET /saves/:saveId</li>
            <li>DELETE /saves/:saveId</li>
          </ul>
        </div>
        <div className="panel">
          <h2>Save Snapshot</h2>
          <p>
            Each save currently stores the season date, phase, real F1/F2
            rosters, teams, academies, F2 calendar, standings shell, news,
            contracts, rivalries, random seed, and event flags.
          </p>
        </div>
      </section>
    </main>
  );
}
