"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { Button, TimingTower, TimingEntry, getTeamColor } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";
import { completeQualifying, DriverSessionResult } from "@/lib/weekendState";

type QualifyingPhase = "pre" | "Q1" | "Q2" | "Q3" | "complete";
type SessionState = "waiting" | "green" | "paused" | "finished";
type LapState = "garage" | "out_lap" | "flying" | "in_lap";

interface DriverQualifyingState {
  driverId: string;
  code: string;
  name: string;
  teamId: string;
  bestTime: number | null;
  currentLapState: LapState;
  lapProgress: number; // 0-100, how far through current lap
  lapsCompleted: number;
  isPlayer: boolean;
  eliminated: boolean;
  eliminatedIn?: "Q1" | "Q2";
  expectedLapTime: number; // What their flying lap time will be
  lastLapTime: number | null;
}

// Simulation constants
const Q1_DURATION = 18 * 60; // 18 minutes in seconds
const Q2_DURATION = 15 * 60;
const Q3_DURATION = 12 * 60;
const Q1_ELIMINATIONS = 6;
const Q2_ELIMINATIONS = 6;

// Lap timing (in session seconds)
const OUT_LAP_TIME = 100; // Out lap is slower
const FLYING_LAP_TIME = 90; // ~1:30 for a flying lap
const IN_LAP_TIME = 110; // In lap is slowest
const GARAGE_MIN_TIME = 60; // Minimum time in garage between runs
const GARAGE_MAX_TIME = 180; // Maximum time in garage

// Time compression: 1 real second = X session seconds
const TIME_COMPRESSION = 10;

export default function QualifyingPage() {
  const router = useRouter();
  const { currentSave, getPlayerDriver, getCurrentRound } = useSave();
  const player = getPlayerDriver();
  const currentRound = getCurrentRound();
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const [phase, setPhase] = useState<QualifyingPhase>("pre");
  const [sessionState, setSessionState] = useState<SessionState>("waiting");
  const [timeRemaining, setTimeRemaining] = useState(Q1_DURATION);
  const [drivers, setDrivers] = useState<DriverQualifyingState[]>([]);
  const [initialized, setInitialized] = useState(false);

  // Generate expected lap time based on driver attributes
  const generateExpectedLapTime = useCallback((driverId: string, session: "Q1" | "Q2" | "Q3"): number => {
    const driver = currentSave?.drivers.find(d => d.id === driverId);
    const team = currentSave?.teams.find(t => t.id === driver?.teamId);
    if (!driver || !team) return 90 + Math.random() * 3;

    const baseTime = 90;
    const skillBonus = (100 - driver.attributes.qualifying) * 0.015;
    const carBonus = (100 - team.carPerformance) * 0.012;
    const variance = session === "Q3" ? 0.3 : session === "Q2" ? 0.5 : 0.8;
    const randomFactor = (Math.random() - 0.5) * variance;
    const sessionBonus = session === "Q3" ? -0.3 : session === "Q2" ? -0.15 : 0;

    return baseTime + skillBonus + carBonus + randomFactor + sessionBonus;
  }, [currentSave]);

  // Initialize drivers
  useEffect(() => {
    if (currentSave && !initialized) {
      const driverStates: DriverQualifyingState[] = currentSave.drivers
        .filter(d => d.series === "F2")
        .map(d => ({
          driverId: d.id,
          code: d.name.split(" ").slice(-1)[0].substring(0, 3).toUpperCase(),
          name: d.name,
          teamId: d.teamId,
          bestTime: null,
          currentLapState: "garage" as const,
          lapProgress: Math.random() * 50, // Stagger when they leave garage
          lapsCompleted: 0,
          isPlayer: d.id === currentSave.playerDriverId,
          eliminated: false,
          expectedLapTime: 92, // Will be set when they start flying lap
          lastLapTime: null,
        }));
      setDrivers(driverStates);
      setInitialized(true);
    }
  }, [currentSave, initialized]);

  // Main simulation tick
  const simulateTick = useCallback(() => {
    if (sessionState !== "green" || phase === "pre" || phase === "complete") return;

    const sessionSeconds = TIME_COMPRESSION; // How many session seconds per real second

    // Update session timer
    setTimeRemaining(prev => {
      const newTime = prev - sessionSeconds;
      if (newTime <= 0) {
        setSessionState("finished");
        return 0;
      }
      return newTime;
    });

    // Update each driver's lap progress
    setDrivers(prev => {
      return prev.map(driver => {
        if (driver.eliminated) return driver;

        let newProgress = driver.lapProgress;
        let newState = driver.currentLapState;
        let newBestTime = driver.bestTime;
        let newLapsCompleted = driver.lapsCompleted;
        let newExpectedTime = driver.expectedLapTime;
        let newLastLapTime = driver.lastLapTime;

        // Calculate progress increment based on current state
        let lapDuration: number;
        switch (driver.currentLapState) {
          case "garage":
            lapDuration = GARAGE_MIN_TIME + Math.random() * (GARAGE_MAX_TIME - GARAGE_MIN_TIME);
            break;
          case "out_lap":
            lapDuration = OUT_LAP_TIME;
            break;
          case "flying":
            lapDuration = FLYING_LAP_TIME;
            break;
          case "in_lap":
            lapDuration = IN_LAP_TIME;
            break;
        }

        const progressPerTick = (sessionSeconds / lapDuration) * 100;
        newProgress += progressPerTick;

        // Handle state transitions
        if (newProgress >= 100) {
          newProgress = 0;

          switch (driver.currentLapState) {
            case "garage":
              // Leave garage, start out lap
              newState = "out_lap";
              break;
            case "out_lap":
              // Finished out lap, start flying lap
              newState = "flying";
              newExpectedTime = generateExpectedLapTime(driver.driverId, phase as "Q1" | "Q2" | "Q3");
              break;
            case "flying":
              // Completed flying lap - record time
              newLastLapTime = newExpectedTime;
              if (newBestTime === null || newExpectedTime < newBestTime) {
                newBestTime = newExpectedTime;
              }
              newLapsCompleted++;
              // Decide whether to do another lap or pit
              // Late in session or improved significantly = pit
              const shouldPit = timeRemaining < 180 || // Less than 3 mins left
                (newBestTime === newExpectedTime && Math.random() < 0.4) || // Just set best time
                newLapsCompleted >= 3; // Done enough laps
              newState = shouldPit ? "in_lap" : "flying";
              if (newState === "flying") {
                newExpectedTime = generateExpectedLapTime(driver.driverId, phase as "Q1" | "Q2" | "Q3");
              }
              break;
            case "in_lap":
              // Back in garage
              newState = "garage";
              break;
          }
        }

        return {
          ...driver,
          lapProgress: newProgress,
          currentLapState: newState,
          bestTime: newBestTime,
          lapsCompleted: newLapsCompleted,
          expectedLapTime: newExpectedTime,
          lastLapTime: newLastLapTime,
        };
      });
    });
  }, [sessionState, phase, timeRemaining, generateExpectedLapTime]);

  // Run simulation loop (tick every 100ms for smooth progress, but update timer every second)
  useEffect(() => {
    if (sessionState === "green") {
      intervalRef.current = setInterval(simulateTick, 1000);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [sessionState, simulateTick]);

  // Start session
  const handleStartSession = () => {
    if (phase === "pre") {
      setPhase("Q1");
      setTimeRemaining(Q1_DURATION);
    }
    setSessionState("green");
  };

  // Advance to next session
  const handleNextSession = () => {
    const sorted = [...drivers]
      .filter(d => !d.eliminated)
      .sort((a, b) => {
        if (a.bestTime === null) return 1;
        if (b.bestTime === null) return -1;
        return a.bestTime - b.bestTime;
      });

    if (phase === "Q1") {
      const eliminated = sorted.slice(-Q1_ELIMINATIONS).map(d => d.driverId);
      setDrivers(prev => prev.map(d => ({
        ...d,
        eliminated: eliminated.includes(d.driverId) || d.eliminated,
        eliminatedIn: eliminated.includes(d.driverId) ? "Q1" : d.eliminatedIn,
        bestTime: eliminated.includes(d.driverId) ? d.bestTime : null,
        currentLapState: "garage" as const,
        lapProgress: Math.random() * 30,
        lapsCompleted: 0,
        lastLapTime: null,
      })));
      setPhase("Q2");
      setTimeRemaining(Q2_DURATION);
      setSessionState("waiting");
    } else if (phase === "Q2") {
      const eliminated = sorted.slice(-Q2_ELIMINATIONS).map(d => d.driverId);
      setDrivers(prev => prev.map(d => ({
        ...d,
        eliminated: eliminated.includes(d.driverId) || d.eliminated,
        eliminatedIn: eliminated.includes(d.driverId) ? "Q2" : d.eliminatedIn,
        bestTime: eliminated.includes(d.driverId) ? d.bestTime : null,
        currentLapState: "garage" as const,
        lapProgress: Math.random() * 30,
        lapsCompleted: 0,
        lastLapTime: null,
      })));
      setPhase("Q3");
      setTimeRemaining(Q3_DURATION);
      setSessionState("waiting");
    } else if (phase === "Q3") {
      setPhase("complete");
      setSessionState("finished");
    }
  };

  // Fast forward
  const handleFastForward = () => {
    // Simulate all drivers completing laps
    setDrivers(prev => {
      return prev.map(driver => {
        if (driver.eliminated) return driver;

        // Give everyone 2-3 more laps worth of times
        let bestTime = driver.bestTime;
        for (let i = 0; i < 3; i++) {
          const lapTime = generateExpectedLapTime(driver.driverId, phase as "Q1" | "Q2" | "Q3");
          if (bestTime === null || lapTime < bestTime) {
            bestTime = lapTime;
          }
        }
        return {
          ...driver,
          bestTime,
          currentLapState: "garage" as const,
          lapProgress: 0,
          lapsCompleted: driver.lapsCompleted + 3,
        };
      });
    });
    setTimeRemaining(0);
    setSessionState("finished");
  };

  // Format time
  const formatLapTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return `${mins}:${parseFloat(secs) < 10 ? "0" : ""}${secs}`;
  };

  const formatSessionTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const formatGap = (gap: number): string => {
    if (gap === 0) return "";
    return `+${gap.toFixed(3)}`;
  };

  // Build timing entries
  const buildTimingEntries = (): TimingEntry[] => {
    const activeDrivers = drivers.filter(d => !d.eliminated);
    const eliminatedDrivers = drivers.filter(d => d.eliminated);

    const sortedActive = [...activeDrivers].sort((a, b) => {
      if (a.bestTime === null) return 1;
      if (b.bestTime === null) return -1;
      return a.bestTime - b.bestTime;
    });

    const leaderTime = sortedActive[0]?.bestTime || 0;

    const entries: TimingEntry[] = sortedActive.map((driver, idx) => {
      // Determine display based on lap state
      let displayTime: string;
      let status: "running" | "pit" | "out" = "running";

      if (driver.bestTime === null) {
        displayTime = "NO TIME";
      } else if (driver.currentLapState === "garage") {
        displayTime = formatGap(driver.bestTime - leaderTime) || formatLapTime(driver.bestTime);
        status = "pit";
      } else if (driver.currentLapState === "flying") {
        // Show they're on a flying lap
        displayTime = formatGap(driver.bestTime - leaderTime) || formatLapTime(driver.bestTime);
      } else {
        displayTime = formatGap(driver.bestTime - leaderTime) || formatLapTime(driver.bestTime);
      }

      return {
        position: idx + 1,
        driverId: driver.driverId,
        driverCode: driver.code,
        teamId: driver.teamId,
        time: idx === 0 && driver.bestTime ? formatLapTime(driver.bestTime) : displayTime,
        interval: displayTime,
        tire: "S" as const,
        status: driver.currentLapState === "garage" || driver.currentLapState === "in_lap" ? "pit" : "running",
        isPlayer: driver.isPlayer,
        isPurpleSector: idx === 0 && driver.bestTime !== null,
      };
    });

    eliminatedDrivers.forEach((driver, idx) => {
      entries.push({
        position: activeDrivers.length + idx + 1,
        driverId: driver.driverId,
        driverCode: driver.code,
        teamId: driver.teamId,
        time: driver.bestTime ? formatLapTime(driver.bestTime) : "NO TIME",
        status: "eliminated",
        isPlayer: driver.isPlayer,
      });
    });

    return entries;
  };

  const getEliminationZone = (): number | undefined => {
    if (phase === "Q1") return drivers.filter(d => !d.eliminated).length - Q1_ELIMINATIONS + 1;
    if (phase === "Q2") return drivers.filter(d => !d.eliminated).length - Q2_ELIMINATIONS + 1;
    return undefined;
  };

  const handleComplete = () => {
    const entries = buildTimingEntries();
    const results: DriverSessionResult[] = entries
      .filter(e => e.status !== "eliminated")
      .map(e => {
        const driver = drivers.find(d => d.driverId === e.driverId);
        return {
          driverId: e.driverId,
          code: e.driverCode,
          name: driver?.name || e.driverCode,
          teamId: e.teamId,
          position: e.position,
          time: driver?.bestTime || undefined,
          gap: e.interval,
        };
      });

    const playerEntry = entries.find(e => e.isPlayer);
    const playerPos = playerEntry?.position || 22;
    completeQualifying(results, playerPos);
    router.push("/race-weekend");
  };

  if (!player || !currentRound) {
    return (
      <div className="apex-fullscreen" style={{ justifyContent: "center", alignItems: "center" }}>
        <p style={{ color: "var(--t-3)" }}>No active career found.</p>
      </div>
    );
  }

  const playerState = drivers.find(d => d.isPlayer);
  const playerPosition = buildTimingEntries().find(e => e.isPlayer)?.position || "--";

  // Get lap state description
  const getLapStateText = (state: LapState, progress: number): string => {
    switch (state) {
      case "garage": return "IN GARAGE";
      case "out_lap": return `OUT LAP (${Math.round(progress)}%)`;
      case "flying": return `FLYING LAP (${Math.round(progress)}%)`;
      case "in_lap": return `IN LAP (${Math.round(progress)}%)`;
    }
  };

  return (
    <div className="apex-fullscreen" style={{ background: "#000" }}>
      <div style={{
        position: "fixed",
        inset: 0,
        background: "radial-gradient(ellipse at 50% 0%, rgba(30,40,60,0.4) 0%, transparent 60%)",
        pointerEvents: "none",
      }} />

      {/* Top bar */}
      <div style={{
        position: "relative",
        zIndex: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "16px 24px",
        borderBottom: "1px solid rgba(255,255,255,0.1)",
      }}>
        <div>
          <div style={{ fontSize: 12, color: "var(--t-3)", marginBottom: 2 }}>
            {currentRound.name} — Qualifying
          </div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>
            {phase === "pre" ? "Ready to Qualify" : phase === "complete" ? "Qualifying Complete" : `Session ${phase}`}
          </h1>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {phase !== "pre" && phase !== "complete" && (
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "8px 16px",
              background: "rgba(0,0,0,0.6)",
              borderRadius: 8,
            }}>
              <span style={{ color: "var(--t-3)", fontSize: 12 }}>{phase}</span>
              <span className="mono" style={{
                fontSize: 28,
                fontWeight: 700,
                color: timeRemaining < 120 ? "var(--bad)" : "#fff",
              }}>
                {formatSessionTime(timeRemaining)}
              </span>
              {sessionState === "paused" && (
                <span style={{ color: "var(--warn)", fontSize: 10, fontWeight: 600 }}>PAUSED</span>
              )}
            </div>
          )}

          <div style={{
            padding: "8px 16px",
            background: playerState?.eliminated ? "rgba(232,88,88,0.2)" : "rgba(61,190,115,0.2)",
            borderRadius: 8,
            textAlign: "center",
          }}>
            <div style={{ fontSize: 10, color: "var(--t-3)" }}>YOUR POSITION</div>
            <div className="mono" style={{
              fontSize: 28,
              fontWeight: 700,
              color: playerState?.eliminated ? "var(--bad)" : "var(--good)",
            }}>
              P{playerPosition}
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div style={{
        flex: 1,
        display: "flex",
        gap: 24,
        padding: 24,
        overflow: "hidden",
      }}>
        {/* Timing tower */}
        <div style={{ flex: "0 0 360px", overflow: "auto" }}>
          <TimingTower
            entries={buildTimingEntries()}
            session={phase === "pre" ? "Q1" : phase === "complete" ? "Q3" : phase}
            sessionInfo={phase !== "pre" && phase !== "complete" ? `${formatSessionTime(timeRemaining)} remaining` : undefined}
            eliminationZone={getEliminationZone()}
          />
        </div>

        {/* Right side */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Session info */}
          <div style={{
            background: "rgba(0,0,0,0.6)",
            borderRadius: 12,
            padding: 20,
            border: "1px solid rgba(255,255,255,0.1)",
          }}>
            <h2 style={{ margin: "0 0 12px", fontSize: 16, fontWeight: 600 }}>
              {phase === "pre" ? "Pre-Session" :
               phase === "complete" ? "Final Results" :
               `${phase} — ${phase === "Q1" ? "18" : phase === "Q2" ? "15" : "12"} Minutes`}
            </h2>
            <p style={{ color: "var(--t-3)", fontSize: 13, margin: "0 0 8px" }}>
              {phase === "pre" && "Press Start when ready to begin Q1. The bottom 6 drivers will be eliminated each session."}
              {phase === "Q1" && `Q1: 22 drivers compete. Bottom ${Q1_ELIMINATIONS} will be eliminated.`}
              {phase === "Q2" && `Q2: 16 drivers compete. Bottom ${Q2_ELIMINATIONS} will be eliminated.`}
              {phase === "Q3" && "Q3: Top 10 shootout for pole position!"}
              {phase === "complete" && "Qualifying is complete. Grid positions have been set."}
            </p>
            <p style={{ color: "var(--t-4)", fontSize: 11, margin: 0 }}>
              Time runs at {TIME_COMPRESSION}x speed
            </p>

            <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
              {phase === "pre" && (
                <Button kind="primary" size="lg" onClick={handleStartSession}>
                  Start Q1
                </Button>
              )}

              {sessionState === "waiting" && phase !== "pre" && phase !== "complete" && (
                <Button kind="primary" size="lg" onClick={handleStartSession}>
                  Start {phase}
                </Button>
              )}

              {sessionState === "green" && (
                <>
                  <Button kind="secondary" onClick={() => setSessionState("paused")}>
                    Pause
                  </Button>
                  <Button kind="ghost" onClick={handleFastForward}>
                    Fast Forward →
                  </Button>
                </>
              )}

              {sessionState === "paused" && (
                <Button kind="primary" onClick={() => setSessionState("green")}>
                  Resume
                </Button>
              )}

              {sessionState === "finished" && phase !== "complete" && (
                <Button kind="primary" size="lg" onClick={handleNextSession}>
                  {phase === "Q3" ? "View Results" : `Continue to ${phase === "Q1" ? "Q2" : "Q3"}`}
                </Button>
              )}

              {phase === "complete" && (
                <Button kind="primary" size="lg" onClick={handleComplete}>
                  Continue to Race Weekend
                </Button>
              )}
            </div>
          </div>

          {/* Player focus */}
          {playerState && (
            <div style={{
              background: "rgba(61,190,115,0.1)",
              borderRadius: 12,
              padding: 20,
              border: "1px solid rgba(61,190,115,0.3)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
                <div style={{
                  width: 56,
                  height: 56,
                  borderRadius: 10,
                  background: `linear-gradient(135deg, ${getTeamColor(playerState.teamId)}40 0%, ${getTeamColor(playerState.teamId)}20 100%)`,
                  borderLeft: `4px solid ${getTeamColor(playerState.teamId)}`,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}>
                  <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--good)" }}>
                    P{playerPosition}
                  </span>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>{playerState.name}</div>
                  <div style={{ fontSize: 12, color: "var(--t-3)" }}>
                    {playerState.eliminated ? `Eliminated in ${playerState.eliminatedIn}` : "In session"}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 2 }}>BEST LAP</div>
                  <div className="mono" style={{ fontSize: 20, fontWeight: 600, color: "#a855f7" }}>
                    {playerState.bestTime ? formatLapTime(playerState.bestTime) : "--:--.---"}
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: 24, marginTop: 16 }}>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>LAPS</div>
                  <div className="mono" style={{ fontSize: 16, color: "var(--t-1)" }}>{playerState.lapsCompleted}</div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>STATUS</div>
                  <div style={{
                    fontSize: 14,
                    color: playerState.currentLapState === "flying" ? "var(--good)" :
                           playerState.currentLapState === "garage" ? "var(--t-3)" : "var(--warn)"
                  }}>
                    {getLapStateText(playerState.currentLapState, playerState.lapProgress)}
                  </div>
                </div>
                {playerState.lastLapTime && (
                  <div>
                    <div style={{ fontSize: 10, color: "var(--t-3)" }}>LAST LAP</div>
                    <div className="mono" style={{ fontSize: 14, color: "var(--t-1)" }}>
                      {formatLapTime(playerState.lastLapTime)}
                    </div>
                  </div>
                )}
              </div>

              {/* Lap progress bar */}
              {playerState.currentLapState !== "garage" && (
                <div style={{ marginTop: 12 }}>
                  <div style={{
                    height: 4,
                    background: "rgba(255,255,255,0.1)",
                    borderRadius: 2,
                    overflow: "hidden",
                  }}>
                    <div style={{
                      width: `${playerState.lapProgress}%`,
                      height: "100%",
                      background: playerState.currentLapState === "flying" ? "var(--good)" : "var(--warn)",
                      transition: "width 0.1s linear",
                    }} />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Session phases */}
          <div style={{
            display: "flex",
            gap: 8,
            padding: 16,
            background: "rgba(0,0,0,0.4)",
            borderRadius: 10,
          }}>
            {["Q1", "Q2", "Q3"].map((q, idx) => {
              const isCurrent = phase === q;
              const isComplete = (phase === "Q2" && q === "Q1") ||
                                (phase === "Q3" && (q === "Q1" || q === "Q2")) ||
                                (phase === "complete");
              return (
                <div
                  key={q}
                  style={{
                    flex: 1,
                    padding: "10px 16px",
                    borderRadius: 8,
                    background: isCurrent ? "rgba(90,169,240,0.2)" :
                               isComplete ? "rgba(61,190,115,0.15)" : "rgba(255,255,255,0.05)",
                    border: `1px solid ${isCurrent ? "rgba(90,169,240,0.4)" :
                            isComplete ? "rgba(61,190,115,0.3)" : "transparent"}`,
                    textAlign: "center",
                  }}
                >
                  <div style={{
                    fontSize: 14,
                    fontWeight: 700,
                    color: isCurrent ? "var(--electric)" : isComplete ? "var(--good)" : "var(--t-3)",
                  }}>
                    {q}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--t-3)", marginTop: 2 }}>
                    {idx === 0 ? "22 → 16" : idx === 1 ? "16 → 10" : "TOP 10"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
