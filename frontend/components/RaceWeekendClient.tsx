"use client";

import { useEffect, useMemo, useState, useCallback } from "react";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section, StatRow, DriverCell, Tire } from "@/components/Shell";
import {
  autoCompleteRace,
  completeRace,
  finalizeWeekend,
  prepareWeekend,
  simulateWeekend,
  simulateToDecision,
  startRace,
  submitDecision,
} from "@/lib/api";
import type {
  ActiveRaceState,
  CalendarRound,
  Driver,
  LapSnapshot,
  RaceClassification,
  RaceResult,
  RunningOrderEntry,
  Team,
  WeekendPrep,
  WeekendResult,
} from "@/lib/types";
import { DecisionPromptModal } from "./DecisionPromptModal";

// Team color mapping
const TEAM_COLORS: Record<string, string> = {
  f2_prema: "#e23526",
  f2_virtuosi: "#ffd700",
  f2_carlin: "#004aad",
  f2_dams: "#002f87",
  f2_hitech: "#cecece",
  f2_mp: "#ff6600",
  f2_art: "#008c45",
  f2_campos: "#e6002d",
  f2_trident: "#0057b8",
  f2_invicta: "#2a2a2a",
  f2_rodin: "#8b4513",
  f2_van_amersfoort: "#1e90ff",
  // F1 teams
  f1_redbull: "#3671c6",
  f1_ferrari: "#e80020",
  f1_mercedes: "#27f4d2",
  f1_mclaren: "#ff8000",
  f1_astonmartin: "#229971",
  f1_alpine: "#ff87bc",
  f1_williams: "#64c4ff",
  f1_haas: "#b6babd",
  f1_sauber: "#52e252",
  f1_rb: "#6692ff",
};

function getTeamColor(teamId: string): string {
  return TEAM_COLORS[teamId] || "#555";
}

function getTeamAbbrev(teamName: string): string {
  const abbrevs: Record<string, string> = {
    prema: "PRE",
    virtuosi: "VIR",
    carlin: "CAR",
    dams: "DAM",
    hitech: "HIT",
    mp: "MP",
    art: "ART",
    campos: "CAM",
    trident: "TRI",
    invicta: "INV",
    rodin: "ROD",
    "van amersfoort": "VAR",
  };
  const lower = teamName.toLowerCase();
  for (const [key, val] of Object.entries(abbrevs)) {
    if (lower.includes(key)) return val;
  }
  return teamName.slice(0, 3).toUpperCase();
}

function getDriverCode(name: string): string {
  const parts = name.split(" ");
  if (parts.length >= 2) {
    return parts[parts.length - 1].slice(0, 3).toUpperCase();
  }
  return name.slice(0, 3).toUpperCase();
}

function getDriverInitials(name: string): string {
  return name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

type InteractivePhase =
  | "idle"
  | "preparing"
  | "practice_complete"
  | "quali_q1"
  | "quali_q2"
  | "quali_q3"
  | "quali_complete"
  | "sprint_running"
  | "sprint_decision"
  | "sprint_complete"
  | "feature_running"
  | "feature_decision"
  | "feature_complete"
  | "finalizing";

type SessionTimingRow = {
  position: number;
  driverId: string;
  lapTime: number;
  note?: string;
};

export function RaceWeekendClient() {
  const { currentSave: save, selectedSaveId, loading, refreshSave } = useSave();
  const [selectedRoundId, setSelectedRoundId] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Interactive race state
  const [interactivePhase, setInteractivePhase] = useState<InteractivePhase>("idle");
  const [weekendPrep, setWeekendPrep] = useState<WeekendPrep | null>(null);
  const [activeRace, setActiveRace] = useState<ActiveRaceState | null>(null);
  const [sprintResult, setSprintResult] = useState<RaceResult | null>(null);
  const [featureResult, setFeatureResult] = useState<RaceResult | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSimulatingWeekend, setIsSimulatingWeekend] = useState(false);

  useEffect(() => {
    if (save) {
      const nextRound = save.calendar.find((r) => !r.completed);
      setSelectedRoundId(nextRound?.id ?? save.calendar[0]?.id ?? "");
      resetInteractiveState();
    }
  }, [save?.saveId]);

  const weekend = save?.weekendResults.find((result) => result.roundId === selectedRoundId);
  const selectedRound = save?.calendar.find((r) => r.id === selectedRoundId);

  const driverMap = useMemo(() => {
    const map = new Map<string, Driver>();
    for (const driver of save?.drivers ?? []) {
      map.set(driver.id, driver);
    }
    return map;
  }, [save]);

  const teamMap = useMemo(() => {
    const map = new Map<string, Team>();
    for (const team of save?.teams ?? []) {
      map.set(team.id, team);
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

  // Interactive race functions
  async function handlePrepareWeekend() {
    if (!selectedSaveId || !selectedRoundId) return;
    setInteractivePhase("preparing");
    setError(null);
    try {
      const prep = await prepareWeekend(selectedSaveId, selectedRoundId);
      setWeekendPrep(prep);
      // Start with practice complete, then step through qualifying
      setInteractivePhase("practice_complete");
    } catch {
      setError("Failed to prepare weekend. It may already be complete.");
      setInteractivePhase("idle");
    }
  }

  function handleAdvanceQualifying() {
    if (!weekendPrep) return;
    const hasSegments = weekendPrep.qualifying.segments && weekendPrep.qualifying.segments.length > 0;

    if (interactivePhase === "practice_complete") {
      setInteractivePhase(hasSegments ? "quali_q1" : "quali_complete");
    } else if (interactivePhase === "quali_q1") {
      setInteractivePhase("quali_q2");
    } else if (interactivePhase === "quali_q2") {
      setInteractivePhase("quali_q3");
    } else if (interactivePhase === "quali_q3") {
      setInteractivePhase("quali_complete");
    }
  }

  async function handleSimulateWeekend() {
    if (!selectedSaveId || !selectedRoundId) return;
    setIsSimulatingWeekend(true);
    setError(null);
    try {
      await simulateWeekend(selectedSaveId, selectedRoundId);
      await refreshSave();
      resetInteractiveState();
    } catch {
      setError("Failed to simulate weekend. Only the next playable round can be simulated.");
    } finally {
      setIsSimulatingWeekend(false);
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
    } catch {
      setError(`Failed to start ${raceType} race.`);
      setInteractivePhase("quali_complete");
    }
  }

  async function handleAdvanceLap() {
    if (!selectedSaveId || !selectedRoundId || !activeRace) return;
    const activeRaceType = activeRace.raceType;
    setError(null);
    try {
      setInteractivePhase(activeRaceType === "sprint" ? "sprint_running" : "feature_running");
      const state = await simulateToDecision(selectedSaveId, selectedRoundId, activeRaceType);
      setActiveRace(state);

      if (state.isComplete) {
        await handleCompleteRace(activeRaceType);
      } else if (state.pendingDecision) {
        setInteractivePhase(activeRaceType === "sprint" ? "sprint_decision" : "feature_decision");
      }
    } catch {
      setError("Failed to advance lap.");
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
    if (!selectedSaveId || !selectedRoundId || !weekendPrep || !featureResult) return;
    const sprintForFinalize = sprintResult ?? emptySprintResult(weekendPrep);
    setInteractivePhase("finalizing");
    setError(null);
    try {
      await finalizeWeekend(selectedSaveId, selectedRoundId, sprintForFinalize, featureResult);
      await refreshSave();
      resetInteractiveState();
    } catch {
      setError("Failed to finalize weekend.");
      setInteractivePhase("feature_complete");
    }
  }

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading race weekend...</p>
      </div>
    );
  }

  if (!save) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>No Career Save</h2>
          <p>Create a driver first, then return here to race.</p>
        </div>
      </div>
    );
  }

  const completedRounds = save.calendar.filter((r) => r.completed).length;
  const isInteractiveInProgress = interactivePhase !== "idle";

  return (
    <div className="page">
      <PageHead
        meta={`Round ${selectedRound?.roundNumber ?? "?"} of ${save.calendar.length}`}
        title={selectedRound?.name ?? "Race Weekend"}
        sub={`${selectedRound?.country ?? ""} · ${selectedRound?.series ?? "F2"} · ${completedRounds} rounds completed`}
      />

      {/* Round selector */}
      <Section>
        <div className="flex" style={{ gap: 16, alignItems: "flex-end" }}>
          <div style={{ flex: 1, maxWidth: 280 }}>
            <div className="t3 tiny" style={{ marginBottom: 6 }}>Select Round</div>
            <select
              value={selectedRoundId}
              onChange={(e) => {
                setSelectedRoundId(e.target.value);
                resetInteractiveState();
              }}
              disabled={isInteractiveInProgress}
              style={{ width: "100%" }}
            >
              {save.calendar.map((round) => (
                <option key={round.id} value={round.id}>
                  R{round.roundNumber} {round.name} {round.completed ? "✓" : ""}
                </option>
              ))}
            </select>
          </div>
          {!weekend && interactivePhase === "idle" && (
            <div className="flex" style={{ gap: 8 }}>
              <button className="btn primary" onClick={handlePrepareWeekend} disabled={isSimulatingWeekend}>
                Prepare Weekend
              </button>
              <button className="btn" onClick={handleSimulateWeekend} disabled={isSimulatingWeekend}>
                {isSimulatingWeekend ? "Simulating..." : "Sim Weekend"}
              </button>
            </div>
          )}
        </div>
      </Section>

      {error && <p className="tag neg" style={{ marginBottom: 20 }}>{error}</p>}

      {/* Pre-race preview when idle */}
      {!weekend && interactivePhase === "idle" && selectedRound && (
        <PreRacePreview
          round={selectedRound}
          save={save}
          driverMap={driverMap}
          teamMap={teamMap}
        />
      )}

      {/* Interactive Controls */}
      {!weekend && interactivePhase !== "idle" && (
        <InteractiveControls
          phase={interactivePhase}
          weekendPrep={weekendPrep}
          activeRace={activeRace}
          sprintResult={sprintResult}
          featureResult={featureResult}
          driverMap={driverMap}
          teamMap={teamMap}
          round={selectedRound}
          playerDriverId={save.playerDriverId}
          onStartSprint={() => handleStartRace("sprint")}
          onStartFeature={() => handleStartRace("feature")}
          onAdvanceLap={handleAdvanceLap}
          onAdvanceQualifying={handleAdvanceQualifying}
          onFinalize={handleFinalizeWeekend}
          onSubmitDecision={handleSubmitDecision}
          onAutoComplete={handleAutoComplete}
          isSubmitting={isSubmitting}
        />
      )}

      {/* Completed Weekend View */}
      {weekend && <WeekendView weekend={weekend} driverMap={driverMap} playerDriverId={save.playerDriverId} />}
    </div>
  );
}

function InteractiveControls({
  phase,
  weekendPrep,
  activeRace,
  sprintResult,
  featureResult,
  driverMap,
  teamMap,
  round,
  playerDriverId,
  onStartSprint,
  onStartFeature,
  onAdvanceLap,
  onAdvanceQualifying,
  onFinalize,
  onSubmitDecision,
  onAutoComplete,
  isSubmitting,
}: {
  phase: InteractivePhase;
  weekendPrep: WeekendPrep | null;
  activeRace: ActiveRaceState | null;
  sprintResult: RaceResult | null;
  featureResult: RaceResult | null;
  driverMap: Map<string, Driver>;
  teamMap: Map<string, Team>;
  round: CalendarRound | undefined;
  playerDriverId: string | null;
  onStartSprint: () => void;
  onStartFeature: () => void;
  onAdvanceLap: () => void;
  onAdvanceQualifying: () => void;
  onFinalize: () => void;
  onSubmitDecision: (choiceIndex: number) => void;
  onAutoComplete: () => void;
  isSubmitting: boolean;
}) {
  if (phase === "preparing") {
    return (
      <Section>
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <div className="spin" style={{ fontSize: 24, marginBottom: 12 }}>⏳</div>
          <p className="t2">Simulating practice and qualifying...</p>
        </div>
      </Section>
    );
  }

  // Practice complete - show practice results, advance to qualifying
  if (phase === "practice_complete" && weekendPrep) {
    return (
      <>
        <BroadcastWeekendIntro
          round={round}
          weekendPrep={weekendPrep}
          driverMap={driverMap}
          playerDriverId={playerDriverId}
        />

        <Section title="Practice Complete">
          <SessionResult
            label="Practice"
            session={weekendPrep.practice}
            driverMap={driverMap}
            playerDriverId={playerDriverId}
          />
        </Section>

        <Section>
          <div className="card" style={{ textAlign: "center", padding: 24 }}>
            <p className="t2" style={{ marginBottom: 16 }}>
              Practice is complete. Time to see who's fastest in qualifying.
            </p>
            <button className="btn primary" onClick={onAdvanceQualifying}>
              Start Qualifying →
            </button>
          </div>
        </Section>
      </>
    );
  }

  // Qualifying segments (Q1, Q2, Q3)
  if ((phase === "quali_q1" || phase === "quali_q2" || phase === "quali_q3") && weekendPrep) {
    const segments = weekendPrep.qualifying.segments;
    const segmentIndex = phase === "quali_q1" ? 0 : phase === "quali_q2" ? 1 : 2;
    const segment = segments?.[segmentIndex];
    const segmentLabel = phase === "quali_q1" ? "Q1" : phase === "quali_q2" ? "Q2" : "Q3";
    const nextLabel = phase === "quali_q1" ? "Q2" : phase === "quali_q2" ? "Q3" : "See Final Grid";

    if (!segment) {
      // Fallback for F2 (no segments)
      return (
        <>
          <Section title="Qualifying">
            <SessionResult
              label="Qualifying"
              session={weekendPrep.qualifying}
              driverMap={driverMap}
              playerDriverId={playerDriverId}
            />
          </Section>
          <Section>
            <button className="btn primary" onClick={onAdvanceQualifying}>
              Continue →
            </button>
          </Section>
        </>
      );
    }

    return (
      <>
        <Section title={segmentLabel}>
          <QualifyingSegmentView
            segment={segment}
            driverMap={driverMap}
            playerDriverId={playerDriverId}
          />
        </Section>

        <Section>
          <div className="card" style={{ textAlign: "center", padding: 24 }}>
            {segment.eliminated.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div className="t3 small" style={{ marginBottom: 8 }}>ELIMINATED</div>
                <div className="flex center wrap" style={{ gap: 8 }}>
                  {segment.eliminated.map((driverId) => {
                    const driver = driverMap.get(driverId);
                    return (
                      <span key={driverId} className="tag neg">
                        {driver?.name ?? driverId}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}
            <button className="btn primary" onClick={onAdvanceQualifying}>
              {nextLabel} →
            </button>
          </div>
        </Section>
      </>
    );
  }

  // Qualifying complete - show final grid, ready for race
  if (phase === "quali_complete" && weekendPrep) {
    const readyTitle = weekendPrep.hasSprint ? "Ready for Sprint Race" : "Ready for Main Race";
    const readyCopy = weekendPrep.hasSprint
      ? "Sprint grid is set. Make decisions during the race to affect your result."
      : "The grid is set. Make decisions during the race to affect your result.";

    return (
      <>
        <Section title="Final Grid">
          <SessionResult
            label="Qualifying"
            session={weekendPrep.qualifying}
            driverMap={driverMap}
            playerDriverId={playerDriverId}
          />
        </Section>

        <Section>
          <div className="card">
            <div className="card-head">
              <div className="card-title">{readyTitle}</div>
            </div>
            <p className="t2" style={{ marginBottom: 16 }}>
              {readyCopy}
            </p>
            <button className="btn primary" onClick={weekendPrep.hasSprint ? onStartSprint : onStartFeature}>
              {weekendPrep.hasSprint ? "Start Sprint Race →" : "Start Main Race →"}
            </button>
          </div>
        </Section>
      </>
    );
  }

  if ((phase === "sprint_running" || phase === "sprint_decision") && activeRace) {
    return (
      <>
        <LiveRaceView
          activeRace={activeRace}
          driverMap={driverMap}
          teamMap={teamMap}
          playerDriverId={playerDriverId}
          raceType="Sprint"
          onAdvanceLap={onAdvanceLap}
          isDecisionPending={phase === "sprint_decision"}
          pendingDecision={activeRace.pendingDecision}
          onSubmitDecision={onSubmitDecision}
          onAutoComplete={onAutoComplete}
          isSubmitting={isSubmitting}
          startingGrid={weekendPrep?.sprintGrid ?? []}
        />
      </>
    );
  }

  if (phase === "sprint_complete" && sprintResult) {
    return (
      <>
        <Section title="Sprint Result">
          <RaceResultTable race={sprintResult} driverMap={driverMap} playerDriverId={playerDriverId} />
          <PostSessionSummary race={sprintResult} driverMap={driverMap} playerDriverId={playerDriverId} />
        </Section>
        <Section>
          <div className="card">
            <div className="card-head">
              <div className="card-title">Ready for Feature Race</div>
            </div>
            <p className="t2" style={{ marginBottom: 16 }}>
              The main event. Grid is based on qualifying results.
            </p>
            <button className="btn primary" onClick={onStartFeature}>
              Start Feature Race →
            </button>
          </div>
        </Section>
      </>
    );
  }

  if ((phase === "feature_running" || phase === "feature_decision") && activeRace) {
    return (
      <LiveRaceView
        activeRace={activeRace}
        driverMap={driverMap}
        teamMap={teamMap}
        playerDriverId={playerDriverId}
        raceType="Feature"
        onAdvanceLap={onAdvanceLap}
        isDecisionPending={phase === "feature_decision"}
        pendingDecision={activeRace.pendingDecision}
        onSubmitDecision={onSubmitDecision}
        onAutoComplete={onAutoComplete}
        isSubmitting={isSubmitting}
        startingGrid={weekendPrep?.featureGrid ?? []}
      />
    );
  }

  if (phase === "feature_complete" && featureResult) {
    return (
      <>
        <Section title="Feature Result">
          <RaceResultTable race={featureResult} driverMap={driverMap} playerDriverId={playerDriverId} />
          <PostSessionSummary race={featureResult} driverMap={driverMap} playerDriverId={playerDriverId} />
        </Section>
        <Section>
          <div className="card">
            <div className="card-head">
              <div className="card-title">Weekend Complete</div>
            </div>
            <p className="t2" style={{ marginBottom: 16 }}>
              Finalize the weekend to update standings and generate news.
            </p>
            <button className="btn primary" onClick={onFinalize}>
              Finalize Weekend →
            </button>
          </div>
        </Section>
      </>
    );
  }

  if (phase === "finalizing") {
    return (
      <Section>
        <div className="card" style={{ textAlign: "center", padding: 40 }}>
          <div className="spin" style={{ fontSize: 24, marginBottom: 12 }}>⏳</div>
          <p className="t2">Updating standings and generating news...</p>
        </div>
      </Section>
    );
  }

  return null;
}

function SessionResult({
  label,
  session,
  driverMap,
  playerDriverId,
}: {
  label?: string;
  session: { weather: { condition: string; trackTemp: number }; classification: Array<{ position: number; driverId: string; lapTime: number; note?: string }> };
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
}) {
  const playerRow = session.classification.find((row) => row.driverId === playerDriverId);
  const leader = session.classification[0];
  const playerGap = playerRow && leader ? playerRow.lapTime - leader.lapTime : null;

  return (
    <div>
      <div className="broadcast-session-panel">
        <div>
          <div className="broadcast-kicker">{label ?? "Session"} story</div>
          <div className="broadcast-title">{sessionStory(label, playerRow, playerGap)}</div>
        </div>
        <div className="what-matters">
          <div className="what-title">What matters now</div>
          <ul>
            {sessionWhatMatters(label, playerRow, playerGap).map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
      <div className="flex" style={{ gap: 16, marginBottom: 16 }}>
        <span className="tag">{session.weather.condition.toUpperCase()}</span>
        <span className="t2">Track: {session.weather.trackTemp}°C</span>
      </div>
      <div className="table-scroll">
      <table className="tbl">
        <thead>
          <tr>
            <th style={{ width: 50 }}>Pos</th>
            <th>Driver</th>
            <th className="num">Time</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {session.classification.map((row) => {
            const isPlayer = row.driverId === playerDriverId;
            return (
              <tr key={row.driverId} className={isPlayer ? "player" : ""}>
                <td className="mono strong">P{row.position}</td>
                <td>
                  <DriverCell name={driverMap.get(row.driverId)?.name ?? row.driverId} driverId={row.driverId} isPlayer={isPlayer} />
                </td>
                <td className="num mono">{formatLapTime(row.lapTime)}</td>
                <td className="t2">{row.note ?? ""}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function LiveRaceView({
  activeRace,
  driverMap,
  teamMap,
  playerDriverId,
  raceType,
  onAdvanceLap,
  isDecisionPending,
  pendingDecision,
  onSubmitDecision,
  onAutoComplete,
  isSubmitting,
  startingGrid,
}: {
  activeRace: ActiveRaceState;
  driverMap: Map<string, Driver>;
  teamMap: Map<string, Team>;
  playerDriverId: string | null;
  raceType: string;
  onAdvanceLap: () => void;
  isDecisionPending: boolean;
  pendingDecision: import("@/lib/types").PendingDecision | null;
  onSubmitDecision: (choiceIndex: number) => void;
  onAutoComplete: () => void;
  isSubmitting: boolean;
  startingGrid: string[];
}) {
  const latestSnapshot = activeRace.lapSnapshots.at(-1);
  const allCommentary = activeRace.lapSnapshots
    .slice()
    .reverse()
    .flatMap((snap) =>
      snap.commentary.map((line, i) => ({ lap: snap.lap, line, key: `${snap.lap}-${i}` }))
    );

  // Build running order - either from lap snapshot or starting grid
  const runningOrder: import("@/lib/types").RunningOrderEntry[] = latestSnapshot
    ? latestSnapshot.runningOrder
    : startingGrid.map((driverId, index) => ({
        position: index + 1,
        driverId,
        gapToLeader: 0,
        gapToCarAhead: 0,
        currentLapTime: null,
        previousLapTime: null,
        bestLapTime: null,
        tireCompound: "medium" as const,
        tireAge: 0,
        tireWear: 0,
        componentWear: 0,
        status: "running" as const,
      }));

  const isLapZero = activeRace.currentLap === 0;

  // Get player's running order entry for stats
  const playerEntry = runningOrder.find(
    (entry) => entry.driverId === playerDriverId
  );
  const player = playerDriverId ? driverMap.get(playerDriverId) ?? null : null;
  const playerTeam = player ? teamMap.get(player.teamId) : null;
  const currentWeather = activeRace.lapSnapshots.at(-1)?.weather;
  const engineerMessages = buildEngineerMessages(
    activeRace,
    runningOrder,
    playerEntry,
    playerDriverId,
    driverMap,
    pendingDecision
  );
  const mattersNow = buildRaceMatters(activeRace, runningOrder, playerEntry, playerDriverId, driverMap, isLapZero);

  return (
    <div className="race-fullscreen">
      {/* Compact race control bar */}
      <div className="race-control-compact">
        <div className="race-control-left">
          <span className="race-type">{raceType.toUpperCase()}</span>
          <span className="race-lap">
            LAP <strong>{activeRace.currentLap}</strong>/{activeRace.totalLaps}
          </span>
          {currentWeather && (
            <span className="tag sm">
              {currentWeather.condition.toUpperCase()} · GRIP {currentWeather.trackGrip}%
            </span>
          )}
          {activeRace.safetyCarActive && <span className="tag warn sm">SC</span>}
        </div>
        <div className="race-control-center">
          {activeRace.playerPosition && (
            <span className="player-position">P{activeRace.playerPosition}</span>
          )}
        </div>
        <div className="race-control-right">
          {!isDecisionPending ? (
            <button className="btn primary sm" onClick={onAdvanceLap}>
              Advance Lap →
            </button>
          ) : (
            <span className="tag warn">Decision Required</span>
          )}
        </div>
      </div>

      <BroadcastRaceHeader
        activeRace={activeRace}
        raceType={raceType}
        playerEntry={playerEntry}
        player={player}
        matters={mattersNow}
      />

      {/* Race layout - fills remaining viewport */}
      <div className="race-layout-full">
        {/* Race Tower */}
        <div className="race-tower-panel">
          <RaceTower
            runningOrder={runningOrder}
            currentLap={activeRace.currentLap}
            totalLaps={activeRace.totalLaps}
            driverMap={driverMap}
            teamMap={teamMap}
            playerDriverId={playerDriverId}
            raceType={raceType}
            isStartingGrid={isLapZero}
          />
        </div>

        {/* Player Stats + Race Events Panel */}
        <div className="race-events-panel">
          {/* Player Stats Section - at the top */}
          {playerEntry && (
            <div className="player-stats-section">
              <div className="player-stats-header">
                <span className="player-stats-name">{player?.name ?? "You"}</span>
                <span className="player-stats-team">{playerTeam?.name ?? ""}</span>
              </div>
              <div className="player-stats-grid">
                <PlayerStatItem
                  label={isLapZero ? "Grid Position" : "Position"}
                  value={`P${playerEntry.position}`}
                  highlight
                />
                <PlayerStatItem
                  label="Gap Ahead"
                  value={isLapZero ? "—" : playerEntry.position === 1 ? "Leader" : formatRaceGap(playerEntry.gapToCarAhead)}
                />
                <PlayerStatItem
                  label="Gap to Leader"
                  value={isLapZero ? "—" : playerEntry.position === 1 ? "—" : formatRaceGap(playerEntry.gapToLeader)}
                />
                <PlayerStatItem
                  label="Tire Life"
                  value={`${Math.round(100 - (playerEntry.tireWear ?? 0))}%`}
                  sub={`${playerEntry.tireCompound?.toUpperCase()} · ${playerEntry.tireAge} laps`}
                  color={
                    (playerEntry.tireWear ?? 0) > 70
                      ? "var(--neg)"
                      : (playerEntry.tireWear ?? 0) > 40
                      ? "var(--warn)"
                      : "var(--pos)"
                  }
                />
                <PlayerStatItem
                  label="Power Unit"
                  value={`${Math.round(playerEntry.componentWear ?? 0)}%`}
                  sub={
                    (playerEntry.componentWear ?? 0) > 76
                      ? "Lift-and-coast advised"
                      : "Temperatures stable"
                  }
                  color={
                    (playerEntry.componentWear ?? 0) > 82
                      ? "var(--neg)"
                      : (playerEntry.componentWear ?? 0) > 68
                      ? "var(--warn)"
                      : "var(--pos)"
                  }
                />
                <PlayerStatItem
                  label="Current Lap"
                  value={formatLapTime(playerEntry.currentLapTime)}
                  mono
                />
                <PlayerStatItem
                  label="Previous Lap"
                  value={formatLapTime(playerEntry.previousLapTime)}
                  mono
                />
                <PlayerStatItem
                  label="Best Lap"
                  value={formatLapTime(playerEntry.bestLapTime)}
                  mono
                  color="var(--accent)"
                />
              </div>
            </div>
          )}

          <RaceEngineerPanel messages={engineerMessages} />

          {/* Race Events below */}
          <div className="race-events-header">{isLapZero ? "STARTING GRID" : "RACE EVENTS"}</div>
          <div className="race-events-list">
            {isLapZero ? (
              <div className="race-event-item">
                <span className="race-event-text t2">
                  Lights out! Click "Advance Lap" to begin the race.
                </span>
              </div>
            ) : allCommentary.length > 0 ? (
              allCommentary.map((item) => (
                <div key={item.key} className="race-event-item">
                  <span className="race-event-lap">Lap {item.lap}</span>
                  <span className="race-event-text">{item.line}</span>
                </div>
              ))
            ) : (
              <div className="race-event-item t3">Race in progress...</div>
            )}
          </div>
        </div>
      </div>

      {/* Decision Modal - rendered inside fullscreen to appear on top */}
      {isDecisionPending && pendingDecision && (
        <DecisionPromptModal
          decision={pendingDecision}
          activeRace={activeRace}
          driverMap={driverMap}
          playerDriverId={playerDriverId}
          onSubmit={onSubmitDecision}
          onAutoComplete={onAutoComplete}
          isSubmitting={isSubmitting}
        />
      )}
    </div>
  );
}

function getTeamLogoUrl(teamId: string): string {
  return `/teams/${teamId}.webp`;
}

function getDriverImageUrl(driverId: string): string {
  return `/drivers/faces/${driverId}.webp`;
}

function RaceTower({
  runningOrder,
  driverMap,
  teamMap,
  playerDriverId,
  isStartingGrid,
}: {
  runningOrder: RunningOrderEntry[];
  currentLap: number;
  totalLaps: number;
  driverMap: Map<string, Driver>;
  teamMap: Map<string, Team>;
  playerDriverId: string | null;
  raceType: string;
  isStartingGrid?: boolean;
}) {
  return (
    <div className="race-tower">
      {/* Driver list */}
      <div className="race-tower-list">
        {runningOrder.map((entry) => {
          const driver = driverMap.get(entry.driverId);
          const team = driver ? teamMap.get(driver.teamId) : null;
          const isPlayer = entry.driverId === playerDriverId;
          const isDNF = entry.status === "dnf";
          const teamColor = team ? getTeamColor(team.id) : "#555";
          const driverCode = driver ? getDriverCode(driver.name) : "???";
          const tireCompound = entry.tireCompound?.[0]?.toUpperCase() || "M";

          const interval = isStartingGrid
            ? "—"
            : entry.position === 1
            ? "Interval"
            : isDNF
            ? "OUT"
            : formatRaceGap(entry.gapToCarAhead);

          return (
            <div
              key={entry.driverId}
              className={`race-tower-row ${isPlayer ? "player" : ""} ${isDNF ? "out" : ""}`}
            >
              <div className="race-tower-pos">{entry.position}</div>
              <TeamLogo teamId={team?.id} teamColor={teamColor} teamName={team?.name} />
              <div className="race-tower-driver">
                <DriverFace
                  driverId={driver?.id}
                  driverName={driver?.name}
                  teamColor={teamColor}
                />
                <span className="race-tower-code">{driverCode}</span>
              </div>
              <div className="race-tower-interval">{interval}</div>
              <div className={`race-tower-tire ${tireCompound}`}>{tireCompound}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TeamLogo({
  teamId,
  teamColor,
  teamName,
}: {
  teamId?: string;
  teamColor: string;
  teamName?: string;
}) {
  const [imgError, setImgError] = useState(false);
  const logoUrl = teamId ? getTeamLogoUrl(teamId) : null;

  if (!logoUrl || imgError) {
    // Fallback to colored badge
    const abbrev = teamName ? getTeamAbbrev(teamName).slice(0, 2) : "??";
    return (
      <div
        className="race-tower-team"
        style={{ background: teamColor }}
        title={teamName}
      >
        {abbrev}
      </div>
    );
  }

  return (
    <div className="race-tower-team-logo" title={teamName}>
      <img
        src={logoUrl}
        alt={teamName || "Team"}
        onError={() => setImgError(true)}
      />
    </div>
  );
}

function DriverFace({
  driverId,
  driverName,
  teamColor,
}: {
  driverId?: string;
  driverName?: string;
  teamColor: string;
}) {
  const [imgError, setImgError] = useState(false);
  const imageUrl = driverId ? getDriverImageUrl(driverId) : null;
  const initials = driverName ? getDriverInitials(driverName) : "??";

  if (!imageUrl || imgError) {
    // Fallback to helmet with team color
    return (
      <div className="race-tower-helmet" title={driverName}>
        <svg viewBox="0 0 32 32" width="28" height="28">
          <defs>
            <linearGradient id={`helmet-${driverId}`} x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={teamColor} />
              <stop offset="100%" stopColor={adjustColor(teamColor, -30)} />
            </linearGradient>
          </defs>
          <circle cx="16" cy="16" r="15" fill={`url(#helmet-${driverId})`} />
          <ellipse cx="16" cy="17" rx="11" ry="7" fill="#111" />
          <ellipse cx="16" cy="16" rx="9" ry="5" fill="#1a1a2a" />
          <path d="M8 15 Q16 12 24 15" stroke="rgba(255,255,255,0.2)" strokeWidth="1" fill="none" />
        </svg>
      </div>
    );
  }

  return (
    <div className="race-tower-face" title={driverName}>
      <img
        src={imageUrl}
        alt={driverName || "Driver"}
        onError={() => setImgError(true)}
      />
    </div>
  );
}

function adjustColor(hex: string, amount: number): string {
  const num = parseInt(hex.replace("#", ""), 16);
  const r = Math.min(255, Math.max(0, (num >> 16) + amount));
  const g = Math.min(255, Math.max(0, ((num >> 8) & 0x00ff) + amount));
  const b = Math.min(255, Math.max(0, (num & 0x0000ff) + amount));
  return `#${((r << 16) | (g << 8) | b).toString(16).padStart(6, "0")}`;
}

function formatGapMinutes(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = (seconds % 60).toFixed(1);
  return `${mins}:${secs.padStart(4, "0")}`;
}

function formatLapTime(time?: number | null) {
  if (typeof time !== "number" || !Number.isFinite(time)) return "—";
  const mins = Math.floor(time / 60);
  const secs = (time % 60).toFixed(3).padStart(6, "0");
  return `${mins}:${secs}`;
}

function formatRaceGap(seconds?: number | null) {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `+${seconds.toFixed(3)}s`;
  return `+${formatGapMinutes(seconds)}`;
}

function sessionStory(
  label: string | undefined,
  playerRow: SessionTimingRow | undefined,
  playerGap: number | null
) {
  const sessionName = label ?? "Session";
  if (!playerRow) return `${sessionName} is about reading the track before the next run.`;
  if (playerRow.position <= 3) return `${sessionName}: front-running pace puts you in the main story.`;
  if (playerRow.position <= 8) return `${sessionName}: competitive pace, but the final tenths matter.`;
  if (playerGap !== null && playerGap < 0.85) return `${sessionName}: the timing sheet is tight enough to change quickly.`;
  return `${sessionName}: work to do on balance, execution, or clean track position.`;
}

function sessionWhatMatters(
  label: string | undefined,
  playerRow: SessionTimingRow | undefined,
  playerGap: number | null
) {
  if (!playerRow) return ["Bank a representative lap", "Avoid traffic on the next run", "Build confidence before race trim"];
  const items = [];
  if (label === "Qualifying") {
    items.push(playerRow.position <= 10 ? "Protect track position into Turn 1" : "Plan an aggressive opening stint");
    items.push(playerGap !== null ? `Find ${Math.max(0.05, playerGap).toFixed(2)}s to match the benchmark` : "Read the pole pace");
    items.push("Keep tires in the window for the first racing laps");
  } else {
    items.push(playerRow.position <= 8 ? "Confirm race pace from the long-run notes" : "Improve setup direction before qualifying");
    items.push(playerGap !== null ? `Benchmark gap: ${formatRaceGap(Math.max(0, playerGap))}` : "Set a clean baseline");
    items.push("Watch tire temperature and traffic on out laps");
  }
  return items;
}

function buildEngineerMessages(
  activeRace: ActiveRaceState,
  runningOrder: RunningOrderEntry[],
  playerEntry: RunningOrderEntry | undefined,
  playerDriverId: string | null,
  driverMap: Map<string, Driver>,
  pendingDecision: import("@/lib/types").PendingDecision | null
) {
  if (!playerEntry || !playerDriverId) {
    return [{ type: "info", text: "We are waiting for the first timing reference." }];
  }

  const ahead = runningOrder.find((entry) => entry.position === playerEntry.position - 1);
  const behind = runningOrder.find((entry) => entry.position === playerEntry.position + 1);
  const stintLife = Math.max(0, 100 - playerEntry.tireWear);
  const messages = [
    {
      type: playerEntry.tireWear > 68 ? "warn" : "tire",
      text:
        playerEntry.tireWear > 68
          ? `Tires are fading. ${Math.round(stintLife)}% life remaining, traction exits are the priority.`
          : `Tires look stable. ${playerEntry.tireCompound.toUpperCase()} compound, ${Math.round(stintLife)}% life remaining.`,
    },
  ];

  if (ahead) {
    const name = driverMap.get(ahead.driverId)?.name ?? "the car ahead";
    messages.push({
      type: playerEntry.gapToCarAhead < 1.2 ? "attack" : "gap",
      text:
        playerEntry.gapToCarAhead < 1.2
          ? `${name} is within range. Use battery on the main straight if the exit is clean.`
          : `Gap to ${name}: ${playerEntry.gapToCarAhead.toFixed(1)}s. Target consistent laps before pushing.`,
    });
  }

  if ((playerEntry.componentWear ?? 0) > 76) {
    messages.push({
      type: "warn",
      text: `Power unit wear is ${Math.round(playerEntry.componentWear)}%. Lift and coast if we need to protect the finish.`,
    });
  } else if ((playerEntry.componentWear ?? 0) > 60) {
    messages.push({
      type: "strategy",
      text: `Component wear is ${Math.round(playerEntry.componentWear)}%. Push laps are available, but we should choose them carefully.`,
    });
  }

  if ((activeRace.lapSnapshots.at(-1)?.weather.trackGrip ?? 80) < 68) {
    const grip = activeRace.lapSnapshots.at(-1)?.weather.trackGrip;
    messages.push({
      type: "warn",
      text: `Track grip is ${grip ?? "low"}%. Avoid kerbs and expect longer braking zones.`,
    });
  }

  if (behind && !activeRace.safetyCarActive) {
    const name = driverMap.get(behind.driverId)?.name ?? "the car behind";
    messages.push({
      type: "gap",
      text: `${name} behind is ${behind.gapToCarAhead.toFixed(1)}s back. Keep exits clean and avoid overheating the rears.`,
    });
  }

  if (pendingDecision) {
    messages.push({ type: "strategy", text: `${pendingDecision.prompt.title}: recommendation is to decide before lap ${pendingDecision.expiresAtLap}.` });
  } else if (activeRace.currentLap > activeRace.totalLaps * 0.58 && playerEntry.tireWear > 42) {
    messages.push({ type: "strategy", text: "Strategy window is live. If pace drops another tenth, the undercut becomes attractive." });
  } else {
    const target = playerEntry.previousLapTime ? Math.max(0, playerEntry.previousLapTime - 0.15) : null;
    messages.push({ type: "target", text: target ? `Target lap ${formatLapTime(target)}. Smooth entries, no sliding.` : "Target is a clean first timed lap, then we reassess." });
  }

  return messages.slice(0, 4);
}

function buildRaceMatters(
  activeRace: ActiveRaceState,
  runningOrder: RunningOrderEntry[],
  playerEntry: RunningOrderEntry | undefined,
  playerDriverId: string | null,
  driverMap: Map<string, Driver>,
  isLapZero: boolean
) {
  if (isLapZero) return ["Launch cleanly", "Avoid lap-one contact", "Hold tire temperature through the formation phase"];
  if (!playerEntry) return ["Follow timing deltas", "Watch safety-car risk", "Keep the race plan flexible"];

  const ahead = runningOrder.find((entry) => entry.position === playerEntry.position - 1);
  const behind = runningOrder.find((entry) => entry.position === playerEntry.position + 1);
  const items = [];
  if (activeRace.safetyCarActive) items.push("Safety Car compresses the field");
  if ((activeRace.lapSnapshots.at(-1)?.weather.trackGrip ?? 80) < 68) items.push("Low grip increases mistake risk");
  if ((playerEntry.componentWear ?? 0) > 76) items.push("Save engine without losing DRS");
  if (ahead) {
    const name = driverMap.get(ahead.driverId)?.name ?? "car ahead";
    items.push(playerEntry.gapToCarAhead < 1.1 ? `Attack ${name}` : `Close ${name} by two tenths`);
  }
  if (behind) {
    const name = driverMap.get(behind.driverId)?.name ?? "car behind";
    items.push(`Keep ${name} out of DRS range`);
  }
  items.push(playerEntry.tireWear > 60 ? "Manage tire temperatures" : "Hit target laps without overheating");
  return items.slice(0, 3);
}

function raceHeadline(
  activeRace: ActiveRaceState,
  playerEntry: RunningOrderEntry | undefined,
  player: Driver | null
) {
  if (!playerEntry) return "Timing screens are coming alive as the session settles.";
  if (activeRace.currentLap === 0) return `${player?.name ?? "Your driver"} waits for lights out from P${playerEntry.position}.`;
  if (activeRace.safetyCarActive) return "Safety Car changes the tactical picture.";
  if (playerEntry.position <= 3) return `${player?.name ?? "Your driver"} is in the podium fight with strategy still open.`;
  if (playerEntry.gapToCarAhead < 1.2) return "The next overtake is the story right now.";
  return `Running P${playerEntry.position}: pace, traffic, and tire life define the next stint.`;
}

function buildPostSessionDebrief(
  race: RaceResult,
  driverMap: Map<string, Driver>,
  playerDriverId: string | null
) {
  const player = race.classification.find((row) => row.driverId === playerDriverId);
  const startPosition = playerDriverId ? race.startingGrid.indexOf(playerDriverId) + 1 : 0;
  const finishPosition = player?.position ?? 0;
  const positionsGained = startPosition && finishPosition ? startPosition - finishPosition : 0;
  const fastestRank = player ? fastestLapRank(race.classification, player.driverId) : null;
  const paceRows = buildPaceRows(race.classification, driverMap, playerDriverId);
  const playerSnapshots = playerDriverId ? playerLapSnapshots(race.lapLog, playerDriverId) : [];
  const stints = buildStintSummary(playerSnapshots, player);
  const incidents = buildIncidentSummary(race, driverMap);

  return {
    why: explainFinish(player, startPosition, positionsGained, fastestRank),
    metrics: [
      { label: "Start", value: startPosition ? `P${startPosition}` : "-", detail: "Grid" },
      { label: "Finish", value: player ? (player.status === "dnf" ? "DNF" : `P${player.position}`) : "-", detail: player ? `${player.points} pts` : "No result" },
      { label: "Net", value: positionsGained > 0 ? `+${positionsGained}` : String(positionsGained), detail: "Positions" },
      { label: "Fastest lap", value: fastestRank ? `P${fastestRank}` : "-", detail: player ? formatLapTime(player.fastestLap) : undefined },
    ],
    paceRows,
    stints,
    incidents,
  };
}

function buildPaceRows(
  classification: RaceClassification[],
  driverMap: Map<string, Driver>,
  playerDriverId: string | null
) {
  const sorted = classification
    .filter((row) => Number.isFinite(row.fastestLap) && row.fastestLap > 0)
    .sort((a, b) => a.fastestLap - b.fastestLap);
  const top = sorted.slice(0, 5);
  const player = sorted.find((row) => row.driverId === playerDriverId);
  const rows = player && !top.some((row) => row.driverId === player.driverId) ? [...top.slice(0, 4), player] : top;
  return rows.map((row) => ({
    label: getDriverCode(driverMap.get(row.driverId)?.name ?? row.driverId),
    value: row.fastestLap,
    isPlayer: row.driverId === playerDriverId,
  }));
}

function fastestLapRank(classification: RaceClassification[], driverId: string) {
  const ordered = classification
    .filter((row) => Number.isFinite(row.fastestLap) && row.fastestLap > 0)
    .sort((a, b) => a.fastestLap - b.fastestLap);
  const index = ordered.findIndex((row) => row.driverId === driverId);
  return index >= 0 ? index + 1 : null;
}

function playerLapSnapshots(lapLog: LapSnapshot[], playerDriverId: string) {
  return lapLog
    .map((lap) => lap.runningOrder.find((entry) => entry.driverId === playerDriverId))
    .filter((entry): entry is RunningOrderEntry => Boolean(entry));
}

function buildStintSummary(playerSnapshots: RunningOrderEntry[], player: RaceClassification | undefined) {
  if (playerSnapshots.length === 0) return ["No stint data available for this session."];
  const first = playerSnapshots[0];
  const last = playerSnapshots[playerSnapshots.length - 1];
  const maxWear = Math.max(...playerSnapshots.map((entry) => entry.tireWear));
  const maxComponentWear = Math.max(...playerSnapshots.map((entry) => entry.componentWear ?? 0));
  const compounds = Array.from(new Set(playerSnapshots.map((entry) => entry.tireCompound.toUpperCase())));
  const items = [
    `${compounds.join(" / ")} tire run, ending at ${Math.round(last.tireWear)}% wear.`,
    `Peak tire stress reached ${Math.round(maxWear)}%, ${maxWear > 68 ? "forcing management late on" : "kept under control"}.`,
    `Component wear peaked at ${Math.round(maxComponentWear)}%, ${maxComponentWear > 78 ? "making lift-and-coast meaningful" : "without limiting the stint"}.`,
  ];
  if (player) items.push(`${player.pitStops} stop${player.pitStops === 1 ? "" : "s"} completed.`);
  if (first.position !== last.position) {
    items.push(`Track position moved from P${first.position} to P${last.position} during logged laps.`);
  }
  return items;
}

function buildIncidentSummary(race: RaceResult, driverMap: Map<string, Driver>) {
  const incidents = [];
  if (race.safetyCarLaps.length > 0) {
    incidents.push(`Safety Car on lap${race.safetyCarLaps.length > 1 ? "s" : ""} ${race.safetyCarLaps.join(", ")}.`);
  }
  if (race.dnfs.length > 0) {
    incidents.push(`DNFs: ${race.dnfs.map((id) => driverMap.get(id)?.name ?? id).join(", ")}.`);
  }
  for (const prompt of race.decisionPrompts.slice(0, 3)) {
    incidents.push(`Lap ${prompt.lap}: ${prompt.title}.`);
  }
  return incidents.length ? incidents : ["Clean session with no major incidents recorded."];
}

function explainFinish(
  player: RaceClassification | undefined,
  startPosition: number,
  positionsGained: number,
  fastestRank: number | null
) {
  if (!player) return "No player classification was recorded for this session.";
  if (player.status === "dnf") return "A retirement defined the result, so pace and strategy never reached the final phase.";
  const direction =
    positionsGained > 2
      ? "strong race execution and passing"
      : positionsGained < -2
      ? "lost track position and compromised race pace"
      : "a result close to the starting position";
  const pace =
    fastestRank !== null && fastestRank <= 5
      ? "The pace was competitive on single-lap evidence."
      : fastestRank !== null && fastestRank > 12
      ? "The fastest-lap ranking suggests the car was not consistently quick enough."
      : "Pace was in the middle of the competitive window.";
  return `You started P${startPosition || "?"} and finished P${player.position}: ${direction}. ${pace}`;
}

function PlayerStatItem({
  label,
  value,
  sub,
  mono,
  highlight,
  color,
}: {
  label: string;
  value: string;
  sub?: string;
  mono?: boolean;
  highlight?: boolean;
  color?: string;
}) {
  return (
    <div className={`player-stat-item ${highlight ? "highlight" : ""}`}>
      <div className="player-stat-label">{label}</div>
      <div
        className={`player-stat-value ${mono ? "mono" : ""}`}
        style={color ? { color } : undefined}
      >
        {value}
      </div>
      {sub && <div className="player-stat-sub">{sub}</div>}
    </div>
  );
}

function RaceResultTable({
  race,
  driverMap,
  playerDriverId,
}: {
  race: RaceResult;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
}) {
  return (
    <div className="table-scroll">
    <table className="tbl">
      <thead>
        <tr>
          <th style={{ width: 50 }}>Pos</th>
          <th>Driver</th>
          <th className="num">Gap</th>
          <th className="num">Pts</th>
          <th className="num">Stops</th>
        </tr>
      </thead>
      <tbody>
        {race.classification.map((row) => {
          const isPlayer = row.driverId === playerDriverId;
          return (
            <tr key={row.driverId} className={isPlayer ? "player" : ""}>
              <td className="mono strong">
                {row.status === "dnf" ? "DNF" : `P${row.position}`}
              </td>
              <td>
                <DriverCell
                  name={driverMap.get(row.driverId)?.name ?? row.driverId}
                  driverId={row.driverId}
                  isPlayer={isPlayer}
                />
              </td>
              <td className="num t2">
                {row.status === "dnf"
                  ? "—"
                  : row.position === 1
                  ? "Winner"
                  : formatRaceGap(row.gapToWinner)}
              </td>
              <td className="num" style={{ color: row.points > 0 ? "var(--pos)" : undefined }}>
                {row.points}
              </td>
              <td className="num">{row.pitStops}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
    </div>
  );
}

function BroadcastWeekendIntro({
  round,
  weekendPrep,
  driverMap,
  playerDriverId,
}: {
  round: CalendarRound | undefined;
  weekendPrep: WeekendPrep;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
}) {
  const playerPractice = weekendPrep.practice.classification.find((row) => row.driverId === playerDriverId);
  const playerQuali = weekendPrep.qualifying.classification.find((row) => row.driverId === playerDriverId);
  const pole = weekendPrep.qualifying.classification[0];
  const poleName = pole ? driverMap.get(pole.driverId)?.name ?? pole.driverId : "the polesitter";

  return (
    <Section>
      <div className="broadcast-intro">
        <div>
          <div className="broadcast-kicker">Live weekend build-up</div>
          <h2>{round?.name ?? "Race Weekend"} is on air</h2>
          <p>
            Practice has set the baseline, qualifying has fixed the pressure points, and the next
            session is about converting track position into race control.
          </p>
        </div>
        <div className="broadcast-cards">
          <BroadcastMiniStat label="Pole" value={poleName} detail={formatLapTime(pole?.lapTime)} />
          <BroadcastMiniStat label="Your practice" value={playerPractice ? `P${playerPractice.position}` : "-"} detail={playerPractice?.note ?? "No run"} />
          <BroadcastMiniStat label="Your grid" value={playerQuali ? `P${playerQuali.position}` : "-"} detail={playerQuali?.note ?? "No lap"} />
        </div>
      </div>
    </Section>
  );
}

function BroadcastMiniStat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="broadcast-mini-stat">
      <div>{label}</div>
      <strong>{value}</strong>
      {detail && <span>{detail}</span>}
    </div>
  );
}

function BroadcastRaceHeader({
  activeRace,
  raceType,
  playerEntry,
  player,
  matters,
}: {
  activeRace: ActiveRaceState;
  raceType: string;
  playerEntry: RunningOrderEntry | undefined;
  player: Driver | null;
  matters: string[];
}) {
  return (
    <div className="broadcast-race-header">
      <div>
        <div className="broadcast-kicker">{raceType} storyline</div>
        <div className="broadcast-title">
          {raceHeadline(activeRace, playerEntry, player)}
        </div>
      </div>
      <div className="what-matters race">
        <div className="what-title">What matters now</div>
        <ul>
          {matters.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function RaceEngineerPanel({ messages }: { messages: Array<{ type: string; text: string }> }) {
  return (
    <div className="engineer-panel">
      <div className="race-events-header">RACE ENGINEER</div>
      <div className="engineer-message-list">
        {messages.map((message, index) => (
          <div key={`${message.type}-${index}`} className={`engineer-message ${message.type}`}>
            <span>{message.type}</span>
            <p>{message.text}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function PostSessionSummary({
  race,
  driverMap,
  playerDriverId,
}: {
  race: RaceResult;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
}) {
  const debrief = buildPostSessionDebrief(race, driverMap, playerDriverId);

  return (
    <div className="post-session-summary">
      <div className="summary-card">
        <div className="broadcast-kicker">Why you finished here</div>
        <div className="summary-main">{debrief.why}</div>
        <div className="summary-grid">
          {debrief.metrics.map((metric) => (
            <BroadcastMiniStat key={metric.label} label={metric.label} value={metric.value} detail={metric.detail} />
          ))}
        </div>
      </div>

      <div className="grid cols-3 gap-sm">
        <div className="summary-card">
          <div className="card-title">Pace chart</div>
          <PaceChart rows={debrief.paceRows} />
        </div>
        <div className="summary-card">
          <div className="card-title">Stint analysis</div>
          <ul className="summary-list">
            {debrief.stints.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="summary-card">
          <div className="card-title">Key incidents</div>
          <ul className="summary-list">
            {debrief.incidents.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function PaceChart({ rows }: { rows: Array<{ label: string; value: number; isPlayer: boolean }> }) {
  const best = rows.length ? Math.min(...rows.map((row) => row.value)) : 0;
  const slowest = rows.length ? Math.max(...rows.map((row) => row.value)) : 0;
  const spread = Math.max(0.001, slowest - best);

  return (
    <div className="pace-chart">
      {rows.map((row) => {
        const delta = row.value - best;
        const width = 100 - (delta / spread) * 42;
        return (
          <div key={`${row.label}-${row.value}`} className={`pace-row ${row.isPlayer ? "player" : ""}`}>
            <span>{row.label}</span>
            <div className="pace-bar">
              <i style={{ width: `${Math.max(44, width)}%` }} />
            </div>
            <b>{delta <= 0.001 ? "Best" : `+${delta.toFixed(3)}`}</b>
          </div>
        );
      })}
    </div>
  );
}

function WeekendView({
  weekend,
  driverMap,
  playerDriverId,
}: {
  weekend: WeekendResult;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
}) {
  const playerFeatureResult = weekend.feature.classification.find(
    (c) => c.driverId === playerDriverId
  );
  const playerSprintResult = weekend.sprint.classification.find(
    (c) => c.driverId === playerDriverId
  );
  const hasSprint = weekend.sprint.classification.length > 0;

  return (
    <>
      {/* Headline */}
      <Section>
        <div className="card">
          <div className="t3 tiny" style={{ marginBottom: 8 }}>Weekend Summary</div>
          <div style={{ fontSize: 22, fontWeight: 600, marginBottom: 16 }}>{weekend.headline}</div>
          <StatRow
            items={[
              {
                label: "Feature Position",
                value: playerFeatureResult
                  ? playerFeatureResult.status === "dnf"
                    ? "DNF"
                    : `P${playerFeatureResult.position}`
                  : "—",
                mono: true,
              },
              {
                label: "Sprint Position",
                value: playerSprintResult
                  ? playerSprintResult.status === "dnf"
                    ? "DNF"
                    : `P${playerSprintResult.position}`
                  : hasSprint
                  ? "—"
                  : "No sprint",
                mono: true,
              },
              {
                label: "Points Scored",
                value: String((playerFeatureResult?.points ?? 0) + (playerSprintResult?.points ?? 0)),
                mono: true,
              },
              {
                label: "Decisions Made",
                value: String(weekend.feature.decisionPrompts.length),
                mono: true,
              },
            ]}
          />
        </div>
      </Section>

      {/* Results grid */}
      <div className="grid cols-2">
        <Section title="Practice">
          <SessionResult session={weekend.practice} driverMap={driverMap} playerDriverId={playerDriverId} />
        </Section>
        <Section title="Qualifying">
          <SessionResult session={weekend.qualifying} driverMap={driverMap} playerDriverId={playerDriverId} />
        </Section>
      </div>

      <div className={hasSprint ? "grid cols-2" : ""}>
        <Section title="Feature Result">
          <RaceResultTable race={weekend.feature} driverMap={driverMap} playerDriverId={playerDriverId} />
          <PostSessionSummary race={weekend.feature} driverMap={driverMap} playerDriverId={playerDriverId} />
        </Section>
        {hasSprint && (
          <Section title="Sprint Result">
            <RaceResultTable race={weekend.sprint} driverMap={driverMap} playerDriverId={playerDriverId} />
            <PostSessionSummary race={weekend.sprint} driverMap={driverMap} playerDriverId={playerDriverId} />
          </Section>
        )}
      </div>

      {/* Decision prompts */}
      {weekend.feature.decisionPrompts.length > 0 && (
        <Section title="Race Decisions">
          <div className="grid cols-3 gap-sm">
            {weekend.feature.decisionPrompts.map((prompt) => (
              <div key={prompt.id} className="card" style={{ padding: 16 }}>
                <div className="t3 tiny">Lap {prompt.lap}</div>
                <div style={{ fontWeight: 500, marginTop: 4 }}>{prompt.title}</div>
                <div className="t2 small" style={{ marginTop: 4 }}>{prompt.description}</div>
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

function emptySprintResult(prep: WeekendPrep): RaceResult {
  const trackId = prep.practice.trackId;
  return {
    raceId: `${trackId}_sprint`,
    sessionType: "sprint",
    trackId,
    totalLaps: 0,
    startingGrid: [],
    classification: [],
    lapLog: [],
    decisionPrompts: [],
    safetyCarLaps: [],
    dnfs: [],
  };
}

// Qualifying segment view with stories and eliminations
function QualifyingSegmentView({
  segment,
  driverMap,
  playerDriverId,
}: {
  segment: { segment: string; classification: Array<{ position: number; driverId: string; lapTime: number; gapToPole: number; note: string }>; eliminated: string[]; stories: string[] };
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
}) {
  const playerEntry = segment.classification.find((e) => e.driverId === playerDriverId);

  return (
    <div>
      {/* Stories from this segment */}
      {segment.stories.length > 0 && (
        <div className="broadcast-session-panel" style={{ marginBottom: 20 }}>
          <div>
            <div className="broadcast-kicker">{segment.segment} Highlights</div>
            {segment.stories.map((story, i) => (
              <div key={i} className={i === 0 ? "broadcast-title" : "t2"} style={{ marginBottom: i === 0 ? 8 : 4 }}>
                {story}
              </div>
            ))}
          </div>
          {playerEntry && (
            <div className="what-matters">
              <div className="what-title">Your position</div>
              <div className="mono strong" style={{ fontSize: 28 }}>P{playerEntry.position}</div>
              <div className="t3">{playerEntry.gapToPole > 0 ? `+${playerEntry.gapToPole.toFixed(3)}s` : "POLE"}</div>
            </div>
          )}
        </div>
      )}

      {/* Classification table */}
      <div className="table-scroll">
        <table className="tbl">
          <thead>
            <tr>
              <th style={{ width: 50 }}>Pos</th>
              <th>Driver</th>
              <th className="num">Time</th>
              <th className="num">Gap</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {segment.classification.map((entry) => {
              const isPlayer = entry.driverId === playerDriverId;
              const isEliminated = segment.eliminated.includes(entry.driverId);
              const driver = driverMap.get(entry.driverId);
              return (
                <tr key={entry.driverId} className={isPlayer ? "player" : isEliminated ? "eliminated" : ""} style={isEliminated ? { opacity: 0.6 } : undefined}>
                  <td className="mono strong">P{entry.position}</td>
                  <td>
                    <DriverCell name={driver?.name ?? entry.driverId} driverId={entry.driverId} isPlayer={isPlayer} />
                  </td>
                  <td className="num mono">{formatLapTime(entry.lapTime)}</td>
                  <td className="num mono t2">
                    {entry.gapToPole > 0 ? `+${entry.gapToPole.toFixed(3)}` : "—"}
                  </td>
                  <td>
                    {isEliminated ? (
                      <span className="tag neg" style={{ fontSize: 10 }}>OUT</span>
                    ) : (
                      <span className="tag pos" style={{ fontSize: 10 }}>Q{segment.segment === "Q1" ? "2" : segment.segment === "Q2" ? "3" : ""}</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Pre-race preview showing news, standings implications, and track info
function PreRacePreview({
  round,
  save,
  driverMap,
  teamMap,
}: {
  round: CalendarRound;
  save: { news: Array<{ id: string; headline: string; body: string; category: string; importance: number }>; standings: { driverStandings: Array<{ driverId: string; points: number }> }; playerDriverId: string | null };
  driverMap: Map<string, Driver>;
  teamMap: Map<string, Team>;
}) {
  const player = save.playerDriverId ? driverMap.get(save.playerDriverId) : null;
  const playerStanding = save.standings.driverStandings.find((s) => s.driverId === save.playerDriverId);
  const playerPosition = playerStanding ? save.standings.driverStandings.indexOf(playerStanding) + 1 : null;

  // Get recent relevant news
  const recentNews = save.news
    .filter((n) => n.importance >= 2)
    .slice(-3)
    .reverse();

  // Championship implications
  const implications: string[] = [];
  if (playerPosition === 1) {
    const gap = save.standings.driverStandings[1]
      ? playerStanding!.points - save.standings.driverStandings[1].points
      : 0;
    implications.push(`You lead the championship by ${gap} points.`);
    implications.push("A win here extends your advantage.");
  } else if (playerPosition && playerPosition <= 3) {
    const leader = save.standings.driverStandings[0];
    const gap = leader.points - (playerStanding?.points ?? 0);
    const leaderDriver = driverMap.get(leader.driverId);
    implications.push(`You're ${gap} points behind ${leaderDriver?.name ?? "the leader"}.`);
    implications.push("A strong result keeps you in the title fight.");
  } else if (playerPosition) {
    implications.push(`Currently P${playerPosition} in the championship.`);
    implications.push("Every point matters to climb the standings.");
  }

  // Track characteristics
  const trackInsights: string[] = [];
  if (round.trackId.includes("monaco") || round.trackId.includes("singapore")) {
    trackInsights.push("Street circuit - qualifying position is crucial.");
    trackInsights.push("Overtaking is extremely difficult here.");
  } else if (round.trackId.includes("monza") || round.trackId.includes("spa")) {
    trackInsights.push("High-speed circuit with good overtaking opportunities.");
    trackInsights.push("Slipstream battles expected on the straights.");
  } else if (round.trackId.includes("silverstone") || round.trackId.includes("suzuka")) {
    trackInsights.push("Technical circuit that rewards driver skill.");
    trackInsights.push("High-speed corners test car setup and confidence.");
  } else {
    trackInsights.push("Mixed characteristics - setup balance is key.");
  }

  if (round.hasSprint) {
    trackInsights.push("Sprint weekend format - extra points available.");
  }

  return (
    <>
      {/* Championship implications */}
      <Section title="Championship stakes">
        <div className="grid" style={{ gridTemplateColumns: "1fr 1fr", gap: 20 }}>
          <div className="card">
            <div className="card-title">Going into {round.name}</div>
            <div style={{ marginTop: 12 }}>
              {implications.map((imp, i) => (
                <p key={i} className={i === 0 ? "t1" : "t2"} style={{ marginBottom: 8 }}>
                  {imp}
                </p>
              ))}
            </div>
            {playerPosition && (
              <div style={{ marginTop: 16, padding: "12px 16px", background: "var(--bg-soft)", borderRadius: 8 }}>
                <div className="flex between center">
                  <span className="t3">Your position</span>
                  <span className="mono strong" style={{ fontSize: 20 }}>P{playerPosition}</span>
                </div>
                <div className="flex between center" style={{ marginTop: 8 }}>
                  <span className="t3">Points</span>
                  <span className="mono">{playerStanding?.points ?? 0}</span>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-title">Track notes</div>
            <ul style={{ marginTop: 12, paddingLeft: 20 }}>
              {trackInsights.map((insight, i) => (
                <li key={i} className="t2" style={{ marginBottom: 8 }}>
                  {insight}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </Section>

      {/* Recent news */}
      {recentNews.length > 0 && (
        <Section title="Headlines">
          <div className="grid cols-3 gap-sm">
            {recentNews.map((news) => (
              <div key={news.id} className="card" style={{ padding: 16 }}>
                <div className="flex between" style={{ marginBottom: 8 }}>
                  <span className="tag" style={{ fontSize: 10 }}>
                    {news.category.toUpperCase()}
                  </span>
                  {news.importance >= 4 && <span className="tag accent">Breaking</span>}
                </div>
                <div style={{ fontWeight: 500, marginBottom: 6 }}>{news.headline}</div>
                <p className="t2 small">{news.body}</p>
              </div>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}
