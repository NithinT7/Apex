"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { getSave, getSaves } from "@/lib/api";
import type { Driver, SaveGame, SaveSummary } from "@/lib/types";

export function CareerDashboardClient() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [save, setSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSaves()
      .then((loaded) => {
        setSaves(loaded);
        setSelectedSaveId(loaded[0]?.saveId ?? "");
      })
      .catch(() => setError("Could not load saves."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedSaveId) {
      setSave(null);
      return;
    }
    getSave(selectedSaveId)
      .then(setSave)
      .catch(() => setError("Could not load selected save."));
  }, [selectedSaveId]);

  const player = useMemo(
    () => save?.drivers.find((driver) => driver.id === save.playerDriverId) ?? null,
    [save],
  );
  const driverMap = useMemo(() => {
    const map = new Map<string, Driver>();
    for (const driver of save?.drivers ?? []) {
      map.set(driver.id, driver);
    }
    return map;
  }, [save]);
  const playerStanding = save?.standings.driverStandings.find(
    (standing) => standing.driverId === save.playerDriverId,
  );
  const nextRound = save?.calendar.find((round) => !round.completed);
  const latestNews = save?.news.slice(-3).reverse() ?? [];

  if (loading) {
    return <p className="lede">Loading career dashboard...</p>;
  }

  if (!saves.length) {
    return (
      <section className="panel dashboard-panel">
        <h2>No Career Save</h2>
        <p>Create a driver to unlock the dashboard, standings, race weekends, and news feed.</p>
      </section>
    );
  }

  return (
    <section className="dashboard-panel">
      <div className="control-panel panel">
        <label>
          Career Save
          <select value={selectedSaveId} onChange={(event) => setSelectedSaveId(event.target.value)}>
            {saves.map((item) => (
              <option key={item.saveId} value={item.saveId}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <Link className="secondary-button" href="/standings">
          Standings
        </Link>
        <Link className="secondary-button" href="/news">
          News
        </Link>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {save ? (
        <div className="panel-grid">
          <article className="panel hero-panel">
            <p className="eyebrow-text">Driver</p>
            <h2>{player?.name ?? "Unassigned Driver"}</h2>
            <dl className="stat-grid">
              <div>
                <dt>Team</dt>
                <dd>{teamName(save, player?.teamId)}</dd>
              </div>
              <div>
                <dt>Points</dt>
                <dd>{playerStanding?.points ?? 0}</dd>
              </div>
              <div>
                <dt>Phase</dt>
                <dd>{save.phase}</dd>
              </div>
            </dl>
          </article>

          <article className="panel">
            <h2>Next Race</h2>
            <p>
              {nextRound
                ? `Round ${nextRound.roundNumber}: ${nextRound.name}, ${nextRound.country}`
                : "F2 season complete."}
            </p>
            <Link className="inline-action" href="/race-weekend">
              Open race weekend
            </Link>
          </article>

          <article className="panel">
            <h2>Latest News</h2>
            <div className="news-stack">
              {latestNews.map((item) => (
                <div key={item.id}>
                  <strong>{item.headline}</strong>
                  <span>{item.date}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="panel">
            <h2>Top Three</h2>
            <table className="timing-table">
              <tbody>
                {save.standings.driverStandings.slice(0, 3).map((standing, index) => (
                  <tr key={standing.driverId}>
                    <td>P{index + 1}</td>
                    <td>{driverMap.get(standing.driverId)?.name ?? standing.driverId}</td>
                    <td>{standing.points} pts</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </article>
        </div>
      ) : null}
    </section>
  );
}

function teamName(save: SaveGame, teamId?: string) {
  return save.teams.find((team) => team.id === teamId)?.name ?? "No team";
}
