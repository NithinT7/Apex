"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { PageHeader, Card, Chip, Button } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";
import * as api from "@/lib/api";
import {
  getWeekendState,
  initWeekendState,
  clearWeekendState,
  setWeekendState,
  WeekendState,
  DriverSessionResult,
  calculatePoints,
} from "@/lib/weekendState";

type SessionStatus = "locked" | "ready" | "completed";

interface SessionDisplay {
  practice: { status: SessionStatus; position?: number };
  qualifying: { status: SessionStatus; position?: number };
  sprint: { status: SessionStatus; position?: number; points?: number };
  feature: { status: SessionStatus; position?: number; points?: number };
}

export default function RaceWeekendPage() {
  const router = useRouter();
  const { currentSave, getPlayerDriver, getCurrentRound, refreshSave } = useSave();
  const player = getPlayerDriver();
  const currentRound = getCurrentRound();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [weekendStarted, setWeekendStarted] = useState(false);
  const [sessions, setSessions] = useState<SessionDisplay>({
    practice: { status: "locked" },
    qualifying: { status: "locked" },
    sprint: { status: "locked" },
    feature: { status: "locked" },
  });

  // Load weekend state on mount and when returning from sessions
  useEffect(() => {
    loadWeekendState();
  }, [currentSave?.saveId, currentRound?.id]);

  function loadWeekendState() {
    const state = getWeekendState();

    console.log("[RaceWeekend] Loading weekend state:", {
      hasState: !!state,
      stateSaveId: state?.saveId,
      currentSaveId: currentSave?.saveId,
      feature: state?.feature,
      sprint: state?.sprint,
    });

    if (state && currentSave && state.saveId === currentSave.saveId) {
      setWeekendStarted(true);
      updateSessionsFromState(state);
    } else {
      // No active weekend state
      setWeekendStarted(false);
      setSessions({
        practice: { status: "locked" },
        qualifying: { status: "locked" },
        sprint: { status: "locked" },
        feature: { status: "locked" },
      });
    }
  }

  function updateSessionsFromState(state: WeekendState) {
    const hasSprint = currentRound?.hasSprint || false;

    setSessions({
      practice: {
        status: state.practice.complete ? "completed" : "ready",
        position: state.practice.playerPosition,
      },
      qualifying: {
        status: state.qualifying.complete
          ? "completed"
          : state.practice.complete
            ? "ready"
            : "locked",
        position: state.qualifying.playerPosition,
      },
      sprint: {
        status: state.sprint.complete
          ? "completed"
          : state.qualifying.complete && hasSprint
            ? "ready"
            : "locked",
        position: state.sprint.playerPosition,
        points: state.sprint.points,
      },
      feature: {
        status: state.feature.complete
          ? "completed"
          : (state.sprint.complete || (state.qualifying.complete && !hasSprint))
            ? "ready"
            : "locked",
        position: state.feature.playerPosition,
        points: state.feature.points,
      },
    });
  }

  async function handleStartWeekend() {
    if (!currentSave?.saveId || !currentRound) return;
    setLoading(true);
    setError(null);
    try {
      // Initialize local weekend state
      initWeekendState(currentSave.saveId, currentRound.id);

      // Also call backend to track weekend start
      try {
        await api.startWeekend(currentSave.saveId);
      } catch {
        // Backend call is optional, local state is primary
      }

      setWeekendStarted(true);
      setSessions({
        practice: { status: "ready" },
        qualifying: { status: "locked" },
        sprint: { status: "locked" },
        feature: { status: "locked" },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start weekend");
    } finally {
      setLoading(false);
    }
  }

  async function handleCompleteWeekend() {
    if (!currentSave?.saveId) return;
    setLoading(true);
    setError(null);
    try {
      // Get local weekend state to send results to backend
      const state = getWeekendState();

      // Build results from local state
      const localResults: api.LocalRaceResults = {
        qualifying_position: state?.qualifying?.playerPosition,
        sprint_position: state?.sprint?.playerPosition,
        feature_position: state?.feature?.playerPosition,
        sprint_points: state?.sprint?.points || 0,
        feature_points: state?.feature?.points || 0,
      };

      // Call backend to complete weekend with results for DP calculation
      const result = await api.completeWeekend(currentSave.saveId, localResults);
      console.log("[RaceWeekend] Backend complete result:", result);

      // Clear local weekend state only after successful backend call
      clearWeekendState();

      // Refresh save to get updated calendar with completed round
      await refreshSave();
      router.push("/driver");
    } catch (err) {
      console.error("[RaceWeekend] Failed to complete weekend:", err);
      // Still clear local state and try to continue
      clearWeekendState();
      try {
        await refreshSave();
        router.push("/driver");
      } catch {
        setError(err instanceof Error ? err.message : "Failed to complete weekend");
      }
    } finally {
      setLoading(false);
    }
  }

  // Navigate to interactive session pages
  function handleEnterSession(session: "practice" | "qualifying" | "sprint" | "feature") {
    // Reload state first to make sure we have latest
    const state = getWeekendState();

    switch (session) {
      case "practice":
        // For now, skip practice and mark as complete
        if (state) {
          state.practice = { complete: true, playerPosition: 1 };
          // Save updated state
          localStorage.setItem("apex_weekend_state", JSON.stringify(state));
          loadWeekendState(); // Refresh UI
        }
        break;
      case "qualifying":
        router.push("/qualifying");
        break;
      case "sprint":
        router.push("/race?type=sprint");
        break;
      case "feature":
        router.push("/race?type=feature");
        break;
    }
  }

  // Simulate a session without entering the interactive page
  function handleSimSession(session: "qualifying" | "sprint" | "feature") {
    const state = getWeekendState();
    if (!state || !currentSave) return;

    const f2Drivers = currentSave.drivers.filter(d => d.series === "F2");
    const playerDriverId = currentSave.playerDriverId;

    // Generate random results based on driver skill
    const results: DriverSessionResult[] = f2Drivers
      .map(driver => {
        const team = currentSave.teams.find(t => t.id === driver.teamId);
        // Base performance from pace + car + some randomness
        const basePace = driver.attributes.pace + (team?.carPerformance || 70);
        const randomFactor = Math.random() * 30 - 15; // ±15 variance
        return {
          driverId: driver.id,
          code: driver.name.split(" ").slice(-1)[0].substring(0, 3).toUpperCase(),
          name: driver.name,
          teamId: driver.teamId,
          position: 0, // Will be assigned after sorting
          performance: basePace + randomFactor,
          status: "finished" as const,
        };
      })
      .sort((a, b) => b.performance - a.performance)
      .map((driver, idx) => ({
        ...driver,
        position: idx + 1,
        points: session === "qualifying" ? 0 : calculatePoints(idx + 1, session),
      }));

    const playerResult = results.find(r => r.driverId === playerDriverId);
    const playerPosition = playerResult?.position || 15;
    const playerPoints = playerResult?.points || 0;

    // Update the appropriate session in state
    switch (session) {
      case "qualifying":
        state.qualifying = {
          complete: true,
          results,
          playerPosition,
          grid: results,
        };
        break;
      case "sprint":
        state.sprint = {
          complete: true,
          results,
          playerPosition,
          points: playerPoints,
        };
        break;
      case "feature":
        state.feature = {
          complete: true,
          results,
          playerPosition,
          points: playerPoints,
        };
        break;
    }

    setWeekendState(state);
    loadWeekendState(); // Refresh UI
  }

  if (!player || !currentRound) {
    return (
      <div>
        <PageHeader
          eyebrow="Race Weekend"
          title="No Active Weekend"
          question="Start a career to access race weekends"
        />
        <Card style={{ padding: 40, textAlign: "center" }}>
          <p style={{ color: "var(--t-3)" }}>Create a driver to access race weekends.</p>
        </Card>
      </div>
    );
  }

  const roundNumber = currentRound.roundNumber;
  const totalRounds = currentSave?.calendar.length || 0;
  const hasSprint = currentRound.hasSprint;

  const allComplete = sessions.feature.status === "completed";

  // Calculate total points earned this weekend
  const totalPoints = (sessions.sprint.points || 0) + (sessions.feature.points || 0);

  return (
    <div>
      <PageHeader
        eyebrow={`Round ${roundNumber} of ${totalRounds}`}
        title={`${currentRound.name}`}
        question="Select a session to enter"
      />

      {error && (
        <div style={{
          background: "rgba(232,88,88,0.1)",
          border: "1px solid rgba(232,88,88,0.3)",
          borderRadius: "var(--r-2)",
          padding: "10px 14px",
          marginBottom: 10,
          color: "var(--bad)",
          fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {/* Track hero */}
      <Card pad={0} style={{ marginBottom: 16 }}>
        <div style={{
          background: "linear-gradient(135deg, #131822 0%, #0a0d12 100%)",
          padding: "20px 24px",
          display: "flex",
          alignItems: "center",
          gap: 20,
          flexWrap: "wrap",
        }}>
          <div style={{ flex: 1, minWidth: 220 }}>
            <Chip tone="accent" mono>R{roundNumber}</Chip>
            <h2 style={{
              margin: "8px 0 4px",
              fontSize: 28,
              fontWeight: 700,
              letterSpacing: "-0.02em",
              color: "var(--t-1)",
              lineHeight: 1.05,
            }}>
              {currentRound.name}
            </h2>
            <div style={{ color: "var(--t-3)", fontSize: 13 }}>{currentRound.country}</div>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <Chip tone="electric" mono>F2</Chip>
            {hasSprint && <Chip tone="silver" mono>SPRINT WEEKEND</Chip>}
          </div>
        </div>
      </Card>

      {/* Session timeline */}
      {!weekendStarted ? (
        <Card pad={32} style={{ textAlign: "center" }}>
          <div style={{ marginBottom: 20 }}>
            <h3 style={{ margin: 0, fontSize: 18, color: "var(--t-1)" }}>
              Ready for {currentRound.name}?
            </h3>
            <p style={{ color: "var(--t-3)", fontSize: 13, marginTop: 8 }}>
              Enter the weekend to begin practice, qualifying, and racing.
            </p>
          </div>
          <Button kind="primary" size="lg" onClick={handleStartWeekend} disabled={loading}>
            {loading ? "Starting..." : "Enter Race Weekend"}
          </Button>
        </Card>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: hasSprint ? "repeat(4, 1fr)" : "repeat(3, 1fr)",
          gap: 12,
        }}>
          <SessionCard
            session="Practice"
            description="Free practice session"
            status={sessions.practice.status}
            result={sessions.practice.position ? `P${sessions.practice.position}` : undefined}
            onClick={() => handleEnterSession("practice")}
          />
          <SessionCard
            session="Qualifying"
            description="Q1 → Q2 → Q3 shootout"
            status={sessions.qualifying.status}
            result={sessions.qualifying.position ? `P${sessions.qualifying.position}` : undefined}
            isKey
            onClick={() => handleEnterSession("qualifying")}
            onSim={() => handleSimSession("qualifying")}
          />
          {hasSprint && (
            <SessionCard
              session="Sprint"
              description="21 lap race"
              status={sessions.sprint.status}
              result={sessions.sprint.position ? `P${sessions.sprint.position}` : undefined}
              points={sessions.sprint.points}
              onClick={() => handleEnterSession("sprint")}
              onSim={() => handleSimSession("sprint")}
            />
          )}
          <SessionCard
            session="Feature"
            description="35 lap feature race"
            status={sessions.feature.status}
            result={sessions.feature.position ? `P${sessions.feature.position}` : undefined}
            points={sessions.feature.points}
            isKey
            onClick={() => handleEnterSession("feature")}
            onSim={() => handleSimSession("feature")}
          />
        </div>
      )}

      {/* Complete weekend */}
      {allComplete && (
        <Card pad={24} style={{ textAlign: "center", marginTop: 16 }}>
          <h3 style={{ margin: "0 0 8px", fontSize: 18, color: "var(--t-1)" }}>
            Weekend Complete!
          </h3>
          <div style={{ marginBottom: 16 }}>
            <div style={{ color: "var(--t-3)", fontSize: 13 }}>
              Qualifying: P{sessions.qualifying.position} • Feature: P{sessions.feature.position}
              {hasSprint && ` • Sprint: P${sessions.sprint.position}`}
            </div>
            {totalPoints > 0 && (
              <div style={{ color: "var(--good)", fontSize: 16, fontWeight: 600, marginTop: 8 }}>
                +{totalPoints} Championship Points
              </div>
            )}
          </div>
          <Button kind="primary" size="lg" onClick={handleCompleteWeekend} disabled={loading}>
            {loading ? "Completing..." : "Complete Weekend"}
          </Button>
        </Card>
      )}
    </div>
  );
}

function SessionCard({
  session,
  description,
  status,
  result,
  points,
  isKey,
  onClick,
  onSim,
}: {
  session: string;
  description: string;
  status: SessionStatus;
  result?: string;
  points?: number;
  isKey?: boolean;
  onClick: () => void;
  onSim?: () => void;
}) {
  const isCompleted = status === "completed";
  const isReady = status === "ready";
  const isLocked = status === "locked";

  return (
    <div
      style={{
        padding: 16,
        background: isCompleted
          ? "rgba(61,190,115,0.08)"
          : isReady
            ? "rgba(90,169,240,0.08)"
            : "var(--bg-2)",
        border: `1px solid ${
          isCompleted
            ? "rgba(61,190,115,0.3)"
            : isReady
              ? "rgba(90,169,240,0.3)"
              : "var(--line-1)"
        }`,
        borderRadius: "var(--r-3)",
        opacity: isLocked ? 0.5 : 1,
        transition: "all 0.15s",
      }}
    >
      <div style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginBottom: 8,
      }}>
        <span style={{
          fontSize: 16,
          fontWeight: 700,
          color: "var(--t-1)",
        }}>
          {session}
        </span>
        {isKey && !isCompleted && <Chip tone="warn">KEY</Chip>}
        {isCompleted && <Chip tone="good">DONE</Chip>}
      </div>

      {isCompleted && result ? (
        <div style={{ marginBottom: 12 }}>
          <div className="mono" style={{
            fontSize: 32,
            fontWeight: 700,
            color: "var(--good)",
            lineHeight: 1,
          }}>
            {result}
          </div>
          {points !== undefined && points > 0 && (
            <div style={{ fontSize: 12, color: "var(--good)", marginTop: 4 }}>
              +{points} points
            </div>
          )}
        </div>
      ) : (
        <p style={{
          color: "var(--t-3)",
          fontSize: 12,
          margin: "0 0 12px",
        }}>
          {description}
        </p>
      )}

      <div style={{ display: "flex", gap: 8 }}>
        <Button
          kind={isReady ? "primary" : "ghost"}
          size="md"
          disabled={isLocked || isCompleted}
          onClick={() => {
            if (isReady) onClick();
          }}
          style={{ flex: 1 }}
        >
          {isCompleted ? "Done" : isLocked ? "Locked" : "Enter"}
        </Button>
        {onSim && isReady && !isCompleted && (
          <Button
            kind="secondary"
            size="md"
            onClick={() => onSim()}
            style={{ flex: 0 }}
          >
            Sim
          </Button>
        )}
      </div>
    </div>
  );
}
