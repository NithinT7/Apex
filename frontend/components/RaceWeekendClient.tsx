"use client";

import { Flag, Loader2, Play } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getSave, getSaves, simulateNextWeekend, simulateWeekend } from "@/lib/api";
import type { Driver, RaceResult, SaveGame, SaveSummary, WeekendResult } from "@/lib/types";

export function RaceWeekendClient() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [save, setSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [selectedRoundId, setSelectedRoundId] = useState("");
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
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
      .then((loaded) => {
        setSave(loaded);
        setSelectedRoundId(nextRoundId(loaded) ?? loaded.calendar[0]?.id ?? "");
      })
      .catch(() => setError("Could not load selected save."));
  }, [selectedSaveId]);

  const weekend = save?.weekendResults.find((result) => result.roundId === selectedRoundId);
  const nextPlayableRound = save ? nextRoundId(save) : null;
  const driverMap = useMemo(() => {
    const map = new Map<string, Driver>();
    for (const driver of save?.drivers ?? []) {
      map.set(driver.id, driver);
    }
    return map;
  }, [save]);

  async function runWeekend() {
    if (!selectedSaveId) return;
    setSimulating(true);
    setError(null);
    try {
      setSave(await simulateWeekend(selectedSaveId, selectedRoundId));
    } catch {
      setError("Weekend simulation failed. It may already be complete or the backend may be offline.");
    } finally {
      setSimulating(false);
    }
  }

  async function runNextWeekend() {
    if (!selectedSaveId) return;
    setSimulating(true);
    setError(null);
    try {
      const updated = await simulateNextWeekend(selectedSaveId);
      setSave(updated);
      setSelectedRoundId(updated.weekendResults.at(-1)?.roundId ?? selectedRoundId);
    } catch {
      setError("Next weekend simulation failed. The season may already be complete.");
    } finally {
      setSimulating(false);
    }
  }

  if (loading) {
    return <p className="lede">Loading saves...</p>;
  }

  if (!saves.length) {
    return (
      <section className="panel">
        <h2>No Saves Yet</h2>
        <p>Create a driver first, then return here to simulate the opening F2 weekend.</p>
      </section>
    );
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
        <label>
          Round
          <select value={selectedRoundId} onChange={(event) => setSelectedRoundId(event.target.value)}>
            {(save?.calendar ?? []).map((round) => (
              <option key={round.id} value={round.id}>
                R{round.roundNumber} {round.name}
              </option>
            ))}
          </select>
        </label>
        <button className="primary-button" type="button" onClick={runWeekend} disabled={simulating || !!weekend}>
          {simulating ? <Loader2 size={18} className="spin" /> : <Play size={18} />}
          {weekend ? "Weekend Complete" : "Simulate Weekend"}
        </button>
      </div>
      <div className="panel compact-action-row">
        <p>
          Next playable race:{" "}
          <strong>
            {nextPlayableRound
              ? save?.calendar.find((round) => round.id === nextPlayableRound)?.name
              : "Season complete"}
          </strong>
        </p>
        <button
          className="secondary-button"
          type="button"
          onClick={runNextWeekend}
          disabled={simulating || !nextPlayableRound}
        >
          <Flag size={18} />
          Simulate Next Race
        </button>
      </div>

      {error ? <p className="error-text">{error}</p> : null}

      {weekend ? (
        <WeekendView weekend={weekend} driverMap={driverMap} />
      ) : (
        <section className="panel">
          <h2>Ready</h2>
          <p>Run the selected weekend to generate practice, qualifying, sprint, feature, prompts, and news.</p>
        </section>
      )}
    </section>
  );
}

function nextRoundId(save: SaveGame) {
  return save.calendar.find((round) => !round.completed)?.id ?? null;
}

function WeekendView({
  weekend,
  driverMap,
}: {
  weekend: WeekendResult;
  driverMap: Map<string, Driver>;
}) {
  return (
    <>
      <section className="panel hero-panel">
        <p className="eyebrow-text">Headline</p>
        <h2>{weekend.headline}</h2>
        <dl className="stat-grid">
          <div>
            <dt>Feature Laps</dt>
            <dd>{weekend.feature.totalLaps}</dd>
          </div>
          <div>
            <dt>Safety Car</dt>
            <dd>{weekend.feature.safetyCarLaps.length}</dd>
          </div>
          <div>
            <dt>DNFs</dt>
            <dd>{weekend.feature.dnfs.length}</dd>
          </div>
          <div>
            <dt>Prompts</dt>
            <dd>{weekend.feature.decisionPrompts.length}</dd>
          </div>
        </dl>
      </section>

      <section className="panel-grid">
        <Classification title="Qualifying" rows={weekend.qualifying.classification.slice(0, 10)} driverMap={driverMap} />
        <RaceClassification title="Feature Result" race={weekend.feature} driverMap={driverMap} />
      </section>

      <section className="panel">
        <h2>Decision Prompts</h2>
        <div className="prompt-list">
          {weekend.feature.decisionPrompts.map((prompt) => (
            <article className="prompt-card" key={prompt.id}>
              <p>Lap {prompt.lap}</p>
              <h3>{prompt.title}</h3>
              <span>{prompt.description}</span>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <h2>Lap Feed</h2>
        <div className="lap-feed">
          {weekend.feature.lapLog
            .filter((lap) => lap.commentary.length || lap.decisionPrompt)
            .slice(0, 12)
            .map((lap) => (
              <article key={lap.lap}>
                <strong>Lap {lap.lap}</strong>
                {lap.commentary.map((line) => (
                  <span key={line}>{line}</span>
                ))}
              </article>
            ))}
        </div>
      </section>
    </>
  );
}

function Classification({
  title,
  rows,
  driverMap,
}: {
  title: string;
  rows: Array<{ position: number; driverId: string; lapTime: number; note: string }>;
  driverMap: Map<string, Driver>;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <table className="timing-table">
        <tbody>
          {rows.map((row) => (
            <tr key={row.driverId}>
              <td>P{row.position}</td>
              <td>{driverMap.get(row.driverId)?.name ?? row.driverId}</td>
              <td>{row.lapTime.toFixed(3)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function RaceClassification({
  title,
  race,
  driverMap,
}: {
  title: string;
  race: RaceResult;
  driverMap: Map<string, Driver>;
}) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      <table className="timing-table">
        <tbody>
          {race.classification.slice(0, 10).map((row) => (
            <tr key={row.driverId}>
              <td>P{row.position}</td>
              <td>{driverMap.get(row.driverId)?.name ?? row.driverId}</td>
              <td>
                {row.status === "dnf"
                  ? "DNF"
                  : row.position === 1
                    ? "Winner"
                    : `+${row.gapToWinner.toFixed(3)}`}
              </td>
              <td>{row.points} pts</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
