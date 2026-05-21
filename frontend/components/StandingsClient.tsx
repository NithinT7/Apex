"use client";

import { useEffect, useMemo, useState } from "react";
import { getSave, getSaves } from "@/lib/api";
import type { Driver, SaveGame, SaveSummary } from "@/lib/types";

export function StandingsClient() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [save, setSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSaves()
      .then((loaded) => {
        setSaves(loaded);
        setSelectedSaveId(loaded[0]?.saveId ?? "");
      })
      .catch(() => setError("Could not load saves."));
  }, []);

  useEffect(() => {
    if (!selectedSaveId) return;
    getSave(selectedSaveId)
      .then(setSave)
      .catch(() => setError("Could not load standings."));
  }, [selectedSaveId]);

  const driverMap = useMemo(() => {
    const map = new Map<string, Driver>();
    for (const driver of save?.drivers ?? []) {
      map.set(driver.id, driver);
    }
    return map;
  }, [save]);

  if (!saves.length) {
    return <p className="lede">Create a career save to see standings.</p>;
  }

  return (
    <section className="viewer-stack">
      <div className="panel control-panel">
        <label>
          Save
          <select value={selectedSaveId} onChange={(event) => setSelectedSaveId(event.target.value)}>
            {saves.map((item) => (
              <option key={item.saveId} value={item.saveId}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      {save ? (
        <section className="panel">
          <h2>F2 Drivers</h2>
          <table className="timing-table standings-table">
            <thead>
              <tr>
                <th>Pos</th>
                <th>Driver</th>
                <th>Team</th>
                <th>Pts</th>
                <th>Wins</th>
                <th>Podiums</th>
              </tr>
            </thead>
            <tbody>
              {save.standings.driverStandings.map((standing, index) => {
                const driver = driverMap.get(standing.driverId);
                return (
                  <tr key={standing.driverId}>
                    <td>P{index + 1}</td>
                    <td>{driver?.name ?? standing.driverId}</td>
                    <td>{teamName(save, driver?.teamId)}</td>
                    <td>{standing.points}</td>
                    <td>{standing.wins}</td>
                    <td>{standing.podiums}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}
    </section>
  );
}

function teamName(save: SaveGame, teamId?: string) {
  return save.teams.find((team) => team.id === teamId)?.name ?? "No team";
}
