"use client";

import { Flag, Loader2, Play, Pause, FastForward } from "lucide-react";
import { useEffect, useMemo, useState, useCallback } from "react";
import {
  autoCompleteRace,
  completeRace,
  finalizeWeekend,
  getSave,
  getSaves,
  prepareWeekend,
  simulateNextWeekend,
  simulateToDecision,
  simulateWeekend,
  startRace,
  submitDecision,
} from "@/lib/api";
import type {
  ActiveRaceState,
  Driver,
  RaceResult,
  SaveGame,
  SaveSummary,
  WeekendPrep,
  WeekendResult,
} from "@/lib/types";
import { DecisionPromptModal } from "./DecisionPromptModal";

type RaceMode = "auto" | "interactive";
type InteractivePhase =
  | "idle"
  | "preparing"
  | "prep_complete"
  | "sprint_running"
  | "sprint_decision"
  | "sprint_complete"
  | "feature_running"
  | "feature_decision"
  | "feature_complete"
  | "finalizing";

export function RaceWeekendClient() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [save, setSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [selectedRoundId, setSelectedRoundId] = useState("");
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Interactive race state
  const [raceMode, setRaceMode] = useState<RaceMode>("interactive");
  const [interactivePhase, setInteractivePhase] = useState<InteractivePhase>("idle");
  const [weekendPrep, setWeekendPrep] = useState<WeekendPrep | null>(null);
  const [activeRace, setActiveRace] = useState<ActiveRaceState | null>(null);
  const [sprintResult, setSprintResult] = useState<RaceResult | null>(null);
  const [featureResult, setFeatureResult] = useState<RaceResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
        resetInteractiveState();
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

  const resetInteractiveState = useCallback(() => {
    setInteractivePhase("idle");
    setWeekendPrep(null);
    setActiveRace(null);
    setSprintResult(null);
    setFeatureResult(null);
    setError(null);
  }, []);

  // Auto-simulate full weekend
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

  // Interactive race functions
  async function handlePrepareWeekend() {
    if (!selectedSaveId || !selectedRoundId) return;
    setInteractivePhase("preparing");
    setError(null);
    try {
      const prep = await prepareWeekend(selectedSaveId, selectedRoundId);
      setWeekendPrep(prep);
      setInteractivePhase("prep_complete");
    } catch {
      setError("Failed to prepare weekend. It may already be complete.");
      setInteractivePhase("idle");
    }
  }

  async function handleStartRace(raceType: "sprint" | "feature") {
    if (!selectedSaveId || !selectedRoundId) return;
    const phase = raceType === "sprint" ? "sprint_running" : "feature_running";
    setInteractivePhase(phase);
    setError(null);
    try {
      const state = await startRace(selectedSaveId, selectedRoundId, raceType);
      setActiveRace(state);
      // Immediately simulate to first decision or end
      await handleSimulateToDecision(raceType, state);
    } catch (err) {
      setError(`Failed to start ${raceType} race.`);
      setInteractivePhase("prep_complete");
    }
  }

  async function handleSimulateToDecision(raceType: "sprint" | "feature", currentState?: ActiveRaceState) {
    if (!selectedSaveId || !selectedRoundId) return;
    setError(null);
    try {
      const state = await simulateToDecision(selectedSaveId, selectedRoundId, raceType);
      setActiveRace(state);

      if (state.isComplete) {
        // Race finished, get final result
        await handleCompleteRace(raceType);
      } else if (state.pendingDecision) {
        // Decision needed
        setInteractivePhase(raceType === "sprint" ? "sprint_decision" : "feature_decision");
      }
    } catch {
      setError("Failed to simulate race.");
    }
  }

  async function handleSubmitDecision(choiceIndex: number) {
    if (!selectedSaveId || !selectedRoundId || !activeRace?.pendingDecision) return;
    const raceType = activeRace.raceType;
    setIsSubmitting(true);
    setError(null);
    try {
      const decision = {
        decisionId: activeRace.pendingDecision.prompt.id,
        choiceIndex,
      };
      const state = await submitDecision(selectedSaveId, selectedRoundId, raceType, decision);
      setActiveRace(state);
      setInteractivePhase(raceType === "sprint" ? "sprint_running" : "feature_running");

      // Continue simulation
      await handleSimulateToDecision(raceType, state);
    } catch {
      setError("Failed to submit decision.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleAutoComplete() {
    if (!selectedSaveId || !selectedRoundId || !activeRace) return;
    const raceType = activeRace.raceType;
    setIsSubmitting(true);
    setError(null);
    try {
      const result = await autoCompleteRace(selectedSaveId, selectedRoundId, raceType);
      if (raceType === "sprint") {
        setSprintResult(result);
        setInteractivePhase("sprint_complete");
      } else {
        setFeatureResult(result);
        setInteractivePhase("feature_complete");
      }
      setActiveRace(null);
    } catch {
      setError("Failed to auto-complete race.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCompleteRace(raceType: "sprint" | "feature") {
    if (!selectedSaveId || !selectedRoundId) return;
    setError(null);
    try {
      const result = await completeRace(selectedSaveId, selectedRoundId, raceType);
      if (raceType === "sprint") {
        setSprintResult(result);
        setInteractivePhase("sprint_complete");
      } else {
        setFeatureResult(result);
        setInteractivePhase("feature_complete");
      }
      setActiveRace(null);
    } catch {
      setError("Failed to complete race.");
    }
  }

  async function handleFinalizeWeekend() {
    if (!selectedSaveId || !selectedRoundId || !sprintResult || !featureResult) return;
    setInteractivePhase("finalizing");
    setError(null);
    try {
      const updated = await finalizeWeekend(selectedSaveId, selectedRoundId, sprintResult, featureResult);
      setSave(updated);
      resetInteractiveState();
    } catch {
      setError("Failed to finalize weekend.");
      setInteractivePhase("feature_complete");
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

  const isInteractiveInProgress = interactivePhase !== "idle";

  return (
    <section className="viewer-stack">
      <div className="panel control-panel">
        <label>
          Save
          <select
            value={selectedSaveId}
            onChange={(event) => setSelectedSaveId(event.target.value)}
            disabled={isInteractiveInProgress}
          >
            {saves.map((item) => (
              <option key={item.saveId} value={item.saveId}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Round
          <select
            value={selectedRoundId}
            onChange={(event) => {
              setSelectedRoundId(event.target.value);
              resetInteractiveState();
            }}
            disabled={isInteractiveInProgress}
          >
            {(save?.calendar ?? []).map((round) => (
              <option key={round.id} value={round.id}>
                R{round.roundNumber} {round.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Mode
          <select
            value={raceMode}
            onChange={(e) => setRaceMode(e.target.value as RaceMode)}
            disabled={isInteractiveInProgress || !!weekend}
          >
            <option value="interactive">Interactive</option>
            <option value="auto">Auto-Simulate</option>
          </select>
        </label>
      </div>

      {raceMode === "auto" && (
        <div className="panel compact-action-row">
          <p>
            Next playable race:{" "}
            <strong>
              {nextPlayableRound
                ? save?.calendar.find((round) => round.id === nextPlayableRound)?.name
                : "Season complete"}
            </strong>
          </p>
          <div style={{ display: "flex", gap: "12px" }}>
            <button
              className="primary-button"
              style={{ marginTop: 0, width: "auto" }}
              type="button"
              onClick={runWeekend}
              disabled={simulating || !!weekend}
            >
              {simulating ? <Loader2 size={18} className="spin" /> : <Play size={18} />}
              {weekend ? "Complete" : "Simulate"}
            </button>
            <button
              className="secondary-button"
              type="button"
              onClick={runNextWeekend}
              disabled={simulating || !nextPlayableRound}
            >
              <Flag size={18} />
              Next Race
            </button>
          </div>
        </div>
      )}

      {raceMode === "interactive" && !weekend && (
        <InteractiveControls
          phase={interactivePhase}
          weekendPrep={weekendPrep}
          activeRace={activeRace}
          sprintResult={sprintResult}
          featureResult={featureResult}
          driverMap={driverMap}
          onPrepare={handlePrepareWeekend}
          onStartSprint={() => handleStartRace("sprint")}
          onStartFeature={() => handleStartRace("feature")}
          onFinalize={handleFinalizeWeekend}
        />
      )}

      {error ? <p className="error-text">{error}</p> : null}

      {/* Decision Modal */}
      {activeRace?.pendingDecision &&
        (interactivePhase === "sprint_decision" || interactivePhase === "feature_decision") && (
          <DecisionPromptModal
            decision={activeRace.pendingDecision}
            onSubmit={handleSubmitDecision}
            onAutoComplete={handleAutoComplete}
            isSubmitting={isSubmitting}
          />
        )}

      {/* Live Race View */}
      {activeRace && !activeRace.pendingDecision && (
        <LiveRaceView activeRace={activeRace} driverMap={driverMap} playerDriverId={save?.playerDriverId} />
      )}

      {/* Completed Weekend View */}
      {weekend ? (
        <WeekendView weekend={weekend} driverMap={driverMap} />
      ) : !isInteractiveInProgress ? (
        <section className="panel">
          <h2>Ready</h2>
          <p>
            {raceMode === "interactive"
              ? "Click 'Prepare Weekend' to simulate practice and qualifying, then race interactively with decision prompts."
              : "Run the selected weekend to generate practice, qualifying, sprint, feature, prompts, and news."}
          </p>
        </section>
      ) : null}
    </section>
  );
}

function InteractiveControls({
  phase,
  weekendPrep,
  activeRace,
  sprintResult,
  featureResult,
  driverMap,
  onPrepare,
  onStartSprint,
  onStartFeature,
  onFinalize,
}: {
  phase: InteractivePhase;
  weekendPrep: WeekendPrep | null;
  activeRace: ActiveRaceState | null;
  sprintResult: RaceResult | null;
  featureResult: RaceResult | null;
  driverMap: Map<string, Driver>;
  onPrepare: () => void;
  onStartSprint: () => void;
  onStartFeature: () => void;
  onFinalize: () => void;
}) {
  if (phase === "idle") {
    return (
      <div className="panel compact-action-row">
        <p>Ready to start the race weekend</p>
        <button className="primary-button" style={{ marginTop: 0, width: "auto" }} onClick={onPrepare}>
          <Play size={18} />
          Prepare Weekend
        </button>
      </div>
    );
  }

  if (phase === "preparing") {
    return (
      <div className="panel compact-action-row">
        <p>Simulating practice and qualifying...</p>
        <Loader2 size={24} className="spin" />
      </div>
    );
  }

  if (phase === "prep_complete" && weekendPrep) {
    return (
      <>
        <div className="panel">
          <h2>Weekend Prepared</h2>
          <p>Practice and qualifying complete. Ready to start the sprint race.</p>
        </div>
        <section className="panel-grid">
          <QualifyingPreview qualifying={weekendPrep.qualifying} driverMap={driverMap} />
          <section className="panel">
            <h2>Sprint Grid</h2>
            <p className="lede" style={{ marginBottom: 12 }}>
              Top 10 reversed from qualifying
            </p>
            <ol className="compact-list">
              {weekendPrep.sprintGrid.slice(0, 10).map((driverId, idx) => (
                <li key={driverId}>
                  {driverMap.get(driverId)?.name ?? driverId}
                </li>
              ))}
            </ol>
          </section>
        </section>
        <div className="panel compact-action-row">
          <p>Start the sprint race</p>
          <button className="primary-button" style={{ marginTop: 0, width: "auto" }} onClick={onStartSprint}>
            <Flag size={18} />
            Start Sprint Race
          </button>
        </div>
      </>
    );
  }

  if ((phase === "sprint_running" || phase === "sprint_decision") && activeRace) {
    return (
      <div className="panel compact-action-row">
        <p>
          <strong>Sprint Race</strong> - Lap {activeRace.currentLap} / {activeRace.totalLaps}
        </p>
        {phase === "sprint_running" && <Loader2 size={24} className="spin" />}
      </div>
    );
  }

  if (phase === "sprint_complete" && sprintResult) {
    return (
      <>
        <div className="panel">
          <h2>Sprint Complete</h2>
          <RaceResultPreview race={sprintResult} driverMap={driverMap} />
        </div>
        <div className="panel compact-action-row">
          <p>Ready for the feature race</p>
          <button className="primary-button" style={{ marginTop: 0, width: "auto" }} onClick={onStartFeature}>
            <Flag size={18} />
            Start Feature Race
          </button>
        </div>
      </>
    );
  }

  if ((phase === "feature_running" || phase === "feature_decision") && activeRace) {
    return (
      <div className="panel compact-action-row">
        <p>
          <strong>Feature Race</strong> - Lap {activeRace.currentLap} / {activeRace.totalLaps}
        </p>
        {phase === "feature_running" && <Loader2 size={24} className="spin" />}
      </div>
    );
  }

  if (phase === "feature_complete" && featureResult) {
    return (
      <>
        <div className="panel">
          <h2>Feature Complete</h2>
          <RaceResultPreview race={featureResult} driverMap={driverMap} />
        </div>
        <div className="panel compact-action-row">
          <p>Finalize weekend to update standings</p>
          <button className="primary-button" style={{ marginTop: 0, width: "auto" }} onClick={onFinalize}>
            <FastForward size={18} />
            Finalize Weekend
          </button>
        </div>
      </>
    );
  }

  if (phase === "finalizing") {
    return (
      <div className="panel compact-action-row">
        <p>Finalizing weekend and updating standings...</p>
        <Loader2 size={24} className="spin" />
      </div>
    );
  }

  return null;
}

function LiveRaceView({
  activeRace,
  driverMap,
  playerDriverId,
}: {
  activeRace: ActiveRaceState;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null | undefined;
}) {
  const latestSnapshot = activeRace.lapSnapshots.at(-1);

  return (
    <div className="race-viewer">
      <section className="panel">
        <div className="race-status-bar">
          <div className="race-progress">
            <strong>
              Lap {activeRace.currentLap} / {activeRace.totalLaps}
            </strong>
            {activeRace.safetyCarActive && <span style={{ color: "#facc15" }}>Safety Car</span>}
          </div>
          {activeRace.playerPosition && (
            <span>
              Your Position: <strong>P{activeRace.playerPosition}</strong>
            </span>
          )}
        </div>
      </section>

      {latestSnapshot && (
        <>
          <section className="panel">
            <h2>Running Order</h2>
            <div className="running-order">
              {latestSnapshot.runningOrder.slice(0, 10).map((entry) => (
                <div
                  key={entry.driverId}
                  className={`running-order-row ${entry.driverId === playerDriverId ? "player" : ""}`}
                >
                  <span className="position">P{entry.position}</span>
                  <span>{driverMap.get(entry.driverId)?.name ?? entry.driverId}</span>
                  <span className="gap">
                    {entry.position === 1 ? "Leader" : `+${entry.gapToLeader.toFixed(1)}s`}
                  </span>
                  <span className={`tire tire-${entry.tireCompound}`}>
                    {entry.tireCompound.toUpperCase()} L{entry.tireAge}
                  </span>
                  <span className="gap">{(entry.tireWear * 100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </section>

          {latestSnapshot.commentary.length > 0 && (
            <section className="panel">
              <h2>Commentary</h2>
              <div className="commentary-feed">
                {latestSnapshot.commentary.map((line, idx) => (
                  <p key={idx} className="commentary-line">
                    {line}
                  </p>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function QualifyingPreview({
  qualifying,
  driverMap,
}: {
  qualifying: WeekendPrep["qualifying"];
  driverMap: Map<string, Driver>;
}) {
  return (
    <section className="panel">
      <h2>Qualifying Result</h2>
      <table className="timing-table">
        <tbody>
          {qualifying.classification.slice(0, 10).map((row) => (
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

function RaceResultPreview({
  race,
  driverMap,
}: {
  race: RaceResult;
  driverMap: Map<string, Driver>;
}) {
  return (
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
        <Classification
          title="Qualifying"
          rows={weekend.qualifying.classification.slice(0, 10)}
          driverMap={driverMap}
        />
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
