"use client";

import { useState, useEffect, useCallback, useRef, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, TimingTower, TimingEntry, LapCounter, Bar, getTeamColor, TireBadge } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";
import {
  getQualifyingGrid,
  getWeekendState,
  initWeekendState,
  completeSprint,
  completeFeature,
  calculatePoints,
  DriverSessionResult,
} from "@/lib/weekendState";

type RaceState = "pre" | "formation" | "racing" | "safety_car" | "vsc" | "finished";
type SafetyCarType = "sc" | "vsc";
type TireCompound = "S" | "M" | "H";

export default function RacePageWrapper() {
  return (
    <Suspense fallback={<div className="apex-fullscreen" style={{ justifyContent: "center", alignItems: "center", background: "#000" }}><p style={{ color: "var(--t-3)" }}>Loading...</p></div>}>
      <RacePage />
    </Suspense>
  );
}

interface DriverRaceState {
  driverId: string;
  code: string;
  name: string;
  teamId: string;
  gridPosition: number;
  currentPosition: number;
  gap: number;
  interval: number;
  tire: TireCompound;
  startTire: TireCompound; // What tire they started on
  tireAge: number;
  tireWear: number;
  pitStops: number;
  usedCompounds: TireCompound[]; // Track which compounds used (for mandatory different compound rule)
  pitWindow: { min: number; max: number }; // AI planned pit window
  lastLap: number | null;
  bestLap: number | null;
  status: "running" | "pit" | "out";
  isPlayer: boolean;
  positionChange: number;
}

// Realistic F2 lap counts by track (based on actual 2024 F2 calendar)
// Feature race: ~170km, Sprint race: ~120km
const TRACK_LAPS: Record<string, { feature: number; sprint: number }> = {
  // Short circuits = more laps
  "monaco": { feature: 42, sprint: 30 },
  "zandvoort": { feature: 40, sprint: 28 },
  "hungary": { feature: 37, sprint: 26 },
  "singapore": { feature: 35, sprint: 25 },
  // Medium circuits
  "bahrain": { feature: 32, sprint: 23 },
  "jeddah": { feature: 27, sprint: 20 },
  "melbourne": { feature: 33, sprint: 24 },
  "imola": { feature: 34, sprint: 24 },
  "barcelona": { feature: 37, sprint: 26 },
  "silverstone": { feature: 29, sprint: 21 },
  "spielberg": { feature: 40, sprint: 28 },
  "austin": { feature: 31, sprint: 22 },
  "mexico": { feature: 38, sprint: 27 },
  "lusail": { feature: 31, sprint: 22 },
  "qatar": { feature: 31, sprint: 22 },
  "abu_dhabi": { feature: 33, sprint: 23 },
  "yas": { feature: 33, sprint: 23 },
  // Long circuits = fewer laps
  "spa": { feature: 25, sprint: 18 },
  "monza": { feature: 30, sprint: 21 },
  "baku": { feature: 29, sprint: 21 },
  "interlagos": { feature: 39, sprint: 28 },
  "las_vegas": { feature: 28, sprint: 20 },
  "suzuka": { feature: 30, sprint: 21 },
};

// Default lap counts if track not found
const DEFAULT_FEATURE_LAPS = 33;
const DEFAULT_SPRINT_LAPS = 23;

// Track degradation levels (affects tire strategy decisions)
// In reality this would come from track data, simulated here per-round
const TRACK_DEG_LEVELS: Record<string, "low" | "medium" | "high"> = {
  // Street circuits tend to be low deg
  "monaco": "low",
  "baku": "low",
  "jeddah": "medium",
  // High-speed circuits with hard braking zones
  "bahrain": "high",
  "barcelona": "high",
  "silverstone": "medium",
  "spa": "medium",
  "monza": "low",
  "singapore": "medium",
  "suzuka": "medium",
  "austin": "high",
  "mexico": "medium",
  "interlagos": "high",
  "las_vegas": "low",
  "qatar": "high",
  "abu_dhabi": "medium",
  "imola": "medium",
  "hungary": "high",
  "zandvoort": "medium",
};

// Team strategic tendencies (affects tire compound choices)
// Ranges from -0.2 (conservative/harder compounds) to +0.2 (aggressive/softer compounds)
const TEAM_STRATEGY_BIAS: Record<string, number> = {
  // F2 teams - some are known for aggressive strategies, others conservative
  "prema": 0.15,           // Aggressive, backs their pace
  "art": 0.1,              // Slightly aggressive
  "carlin": 0.05,          // Balanced-aggressive
  "virtuosi": 0,           // Balanced
  "hitech": -0.05,         // Slightly conservative
  "dams": 0,               // Balanced
  "mp": -0.1,              // Conservative
  "campos": -0.05,         // Slightly conservative
  "trident": 0.1,          // Aggressive
  "van_amersfoort": -0.1,  // Conservative
  "rodin": 0.05,           // Balanced-aggressive
  "invicta": -0.15,        // Very conservative
};

// Tire characteristics
const TIRE_DATA = {
  S: { lapDelta: 0, wearRate: 4.5, cliffPoint: 65, maxLaps: 15 },      // Soft: fastest, wears quickest
  M: { lapDelta: 0.4, wearRate: 2.8, cliffPoint: 75, maxLaps: 25 },    // Medium: balanced
  H: { lapDelta: 0.8, wearRate: 1.8, cliffPoint: 85, maxLaps: 35 },    // Hard: slowest, most durable
};

// Pit stop time loss (seconds)
const PIT_STOP_LOSS = 22;

// Extract last name from full name for race feed
function getLastName(fullName: string): string {
  const parts = fullName.split(" ");
  return parts[parts.length - 1];
}

// Time compression for race simulation
const LAPS_PER_SECOND = 0.5; // Half a lap per real second

function RacePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const raceType = searchParams.get("type") === "sprint" ? "sprint" : "feature";

  const { currentSave, getPlayerDriver, getCurrentRound } = useSave();
  const player = getPlayerDriver();
  const currentRound = getCurrentRound();
  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  // Get track-specific lap count
  const trackKey = currentRound?.name.toLowerCase().replace(/[^a-z]/g, "_") || "";
  const trackLaps = Object.entries(TRACK_LAPS).find(([key]) => trackKey.includes(key))?.[1];
  const totalLaps = raceType === "sprint"
    ? (trackLaps?.sprint || DEFAULT_SPRINT_LAPS)
    : (trackLaps?.feature || DEFAULT_FEATURE_LAPS);

  const [raceState, setRaceState] = useState<RaceState>("pre");
  const [currentLap, setCurrentLap] = useState(0);
  const [drivers, setDrivers] = useState<DriverRaceState[]>([]);
  const [initialized, setInitialized] = useState(false);
  const [simSpeed, setSimSpeed] = useState<1 | 2 | 5>(1);
  const [safetyCar, setSafetyCar] = useState(false);
  const [safetyCarType, setSafetyCarType] = useState<SafetyCarType>("sc");
  const [commentary, setCommentary] = useState<string[]>([]);
  const [showPitPrompt, setShowPitPrompt] = useState(false);
  const [showSafetyCarPrompt, setShowSafetyCarPrompt] = useState(false);
  const [safetyCarReason, setSafetyCarReason] = useState("");
  const [scLapsRemaining, setScLapsRemaining] = useState(0);
  const [engineerMessage, setEngineerMessage] = useState<{
    message: string;
    type: "info" | "warn" | "pit" | "good";
    lap: number;
  } | null>(null);
  const lastEngineerLap = useRef(0);


  // Initialize drivers
  useEffect(() => {
    if (currentSave && !initialized) {
      const qualiGrid = getQualifyingGrid();
      const f2Drivers = currentSave.drivers.filter(d => d.series === "F2");

      let orderedDrivers: typeof f2Drivers;
      if (qualiGrid && qualiGrid.length > 0) {
        orderedDrivers = qualiGrid
          .map(g => f2Drivers.find(d => d.id === g.driverId))
          .filter((d): d is typeof f2Drivers[0] => d !== undefined);
        const qualiIds = new Set(qualiGrid.map(g => g.driverId));
        f2Drivers.forEach(d => {
          if (!qualiIds.has(d.id)) orderedDrivers.push(d);
        });
      } else {
        orderedDrivers = [...f2Drivers].sort(() => Math.random() - 0.5);
      }

      // Determine track degradation level
      const trackKey = currentRound?.name.toLowerCase().replace(/[^a-z]/g, "_") || "";
      const trackDeg = Object.entries(TRACK_DEG_LEVELS).find(([key]) =>
        trackKey.includes(key)
      )?.[1] || "medium";

      // Track deg modifiers: high deg pushes toward harder compounds
      const trackDegModifier = trackDeg === "high" ? -0.15 : trackDeg === "low" ? 0.1 : 0;

      const driverStates: DriverRaceState[] = orderedDrivers.map((d, idx) => {
        // Get team strategy bias
        const teamKey = d.teamId.toLowerCase().replace(/[^a-z]/g, "_");
        const teamBias = Object.entries(TEAM_STRATEGY_BIAS).find(([key]) =>
          teamKey.includes(key)
        )?.[1] || 0;

        // Combined strategy modifier: team tendency + track degradation
        const strategyMod = teamBias + trackDegModifier;

        // AI tire strategy varies by race type, grid position, team, and track
        let startTire: TireCompound;
        if (raceType === "sprint") {
          // Sprint: balance between track position (soft) and tire life (medium)
          // Base probability of choosing soft, modified by factors
          let softProb: number;
          if (idx < 6) {
            softProb = 0.75; // Top 6 lean soft for position
          } else if (idx < 14) {
            softProb = 0.5; // Midfield: balanced
          } else {
            softProb = 0.35; // Back: lean medium to come through late
          }

          // Apply modifiers (positive = more likely soft, negative = more likely medium)
          softProb = Math.max(0.1, Math.min(0.95, softProb + strategyMod));
          startTire = Math.random() < softProb ? "S" : "M";
        } else {
          // Feature race: more strategic variation including hards on high-deg tracks
          let softProb: number;
          let mediumProb: number; // If not soft, probability of medium vs hard

          if (idx < 10) {
            softProb = 0.6;
            mediumProb = 0.85; // Mostly medium if not soft
          } else {
            softProb = 0.4;
            mediumProb = 0.7; // More hards at the back
          }

          // Apply modifiers
          softProb = Math.max(0.1, Math.min(0.9, softProb + strategyMod));

          // On high deg tracks, hards become viable
          if (trackDeg === "high") {
            mediumProb = 0.6; // More likely to choose hard
          } else if (trackDeg === "low") {
            mediumProb = 0.95; // Almost never hard
          }

          const roll = Math.random();
          if (roll < softProb) {
            startTire = "S";
          } else if (Math.random() < mediumProb) {
            startTire = "M";
          } else {
            startTire = "H";
          }
        }

        // Calculate AI pit window based on starting tire
        const pitWindow = calculatePitWindow(startTire, totalLaps);

        // Closer starting gaps - F2 fields are tight
        const startGap = idx * (0.6 + Math.random() * 0.4); // 0.6-1.0s per position
        const startInterval = idx === 0 ? 0 : 0.6 + Math.random() * 0.4;

        return {
          driverId: d.id,
          code: d.name.split(" ").slice(-1)[0].substring(0, 3).toUpperCase(),
          name: d.name,
          teamId: d.teamId,
          gridPosition: idx + 1,
          currentPosition: idx + 1,
          gap: startGap,
          interval: startInterval,
          tire: startTire,
          startTire,
          tireAge: 0,
          tireWear: 0,
          pitStops: 0,
          usedCompounds: [startTire],
          pitWindow,
          lastLap: null,
          bestLap: null,
          status: "running",
          isPlayer: d.id === currentSave.playerDriverId,
          positionChange: 0,
        };
      });

      setDrivers(driverStates);
      setInitialized(true);
    }
  }, [currentSave, initialized, raceType, totalLaps]);

  // Race engineer recommendations
  const checkEngineerAdvice = useCallback((lap: number, playerDriver: DriverRaceState, allDrivers: DriverRaceState[], isSafetyCar: boolean) => {
    // Don't spam messages - at least 3 laps between messages
    if (lap - lastEngineerLap.current < 3) return;

    const tireData = TIRE_DATA[playerDriver.tire];
    const lapsRemaining = totalLaps - lap;
    const hasPitted = playerDriver.pitStops > 0;

    // Find cars around player
    const sortedDrivers = [...allDrivers].filter(d => d.status !== "out").sort((a, b) => a.gap - b.gap);
    const playerIdx = sortedDrivers.findIndex(d => d.isPlayer);
    const carAhead = playerIdx > 0 ? sortedDrivers[playerIdx - 1] : null;
    const carBehind = playerIdx < sortedDrivers.length - 1 ? sortedDrivers[playerIdx + 1] : null;

    // Calculate optimal pit window
    const optimalPitLap = Math.floor(tireData.maxLaps * 0.85);
    const inPitWindow = playerDriver.tireAge >= optimalPitLap - 3 && playerDriver.tireAge <= optimalPitLap + 3;

    let message: { message: string; type: "info" | "warn" | "pit" | "good" } | null = null;

    // SAFETY CAR - best time to pit
    if (isSafetyCar && !hasPitted && raceType === "feature" && lapsRemaining > 5) {
      message = {
        message: "Safety car! This is a great time to pit, we'll lose less time.",
        type: "pit"
      };
    }
    // TIRE CRITICAL - past cliff point
    else if (playerDriver.tireWear > tireData.cliffPoint + 5 && !hasPitted && raceType === "feature") {
      message = {
        message: `Tires are gone! Box this lap, we're losing too much time.`,
        type: "warn"
      };
    }
    // APPROACHING CLIFF
    else if (playerDriver.tireWear > tireData.cliffPoint - 10 && playerDriver.tireWear <= tireData.cliffPoint && !hasPitted && raceType === "feature") {
      message = {
        message: `Tire wear at ${Math.round(playerDriver.tireWear)}%. Approaching the cliff, consider boxing soon.`,
        type: "warn"
      };
    }
    // OPTIMAL PIT WINDOW
    else if (inPitWindow && !hasPitted && raceType === "feature" && lapsRemaining > 8) {
      const recommendedTire = lapsRemaining <= 15 ? "softs" : lapsRemaining <= 22 ? "mediums" : "hards";
      message = {
        message: `Good window to pit. ${recommendedTire.charAt(0).toUpperCase() + recommendedTire.slice(1)} should work well for the remaining ${lapsRemaining} laps.`,
        type: "pit"
      };
    }
    // UNDERCUT OPPORTUNITY
    else if (carAhead && !hasPitted && carAhead.pitStops === 0 && playerDriver.tireAge >= 8 && raceType === "feature") {
      const gap = carAhead.gap - playerDriver.gap;
      if (gap > 0 && gap < 3 && playerDriver.interval < 2) {
        message = {
          message: `${carAhead.code} ahead hasn't pitted. Box now for the undercut, we can jump them.`,
          type: "pit"
        };
      }
    }
    // OVERCUT OPPORTUNITY
    else if (carAhead && carAhead.pitStops > 0 && !hasPitted && playerDriver.tireWear < tireData.cliffPoint - 15 && raceType === "feature") {
      message = {
        message: `${carAhead.code} has pitted. Stay out and push, tires are still good.`,
        type: "good"
      };
    }
    // CAR BEHIND CLOSING
    else if (carBehind && carBehind.interval < 1.0 && playerDriver.tireWear > 50) {
      message = {
        message: `${carBehind.code} is closing fast. Watch your mirrors, defend if needed.`,
        type: "info"
      };
    }
    // MANDATORY PIT REMINDER
    else if (raceType === "feature" && !hasPitted && lapsRemaining <= 8 && lapsRemaining > 5) {
      message = {
        message: `${lapsRemaining} laps to go. Don't forget we still need to pit for a different compound.`,
        type: "warn"
      };
    }
    // GOOD PACE
    else if (playerDriver.positionChange > 0 && Math.random() < 0.3) {
      message = {
        message: `Great move! Keep this pace up, you're doing well.`,
        type: "good"
      };
    }

    if (message) {
      setEngineerMessage({ ...message, lap });
      lastEngineerLap.current = lap;
    }
  }, [totalLaps, raceType]);

  // Calculate optimal pit window based on starting tire
  function calculatePitWindow(startTire: TireCompound, totalLaps: number): { min: number; max: number } {
    const tireData = TIRE_DATA[startTire];
    const optimalStint = Math.floor(tireData.maxLaps * 0.9);
    const min = Math.max(8, optimalStint - 5 + Math.floor(Math.random() * 3));
    const max = Math.min(totalLaps - 5, optimalStint + 3 + Math.floor(Math.random() * 3));
    return { min, max };
  }

  // Calculate lap time
  const calculateLapTime = useCallback((driver: DriverRaceState): number => {
    const driverData = currentSave?.drivers.find(d => d.id === driver.driverId);
    const team = currentSave?.teams.find(t => t.id === driver.teamId);
    if (!driverData || !team) return 95;

    const baseTime = 95;
    const paceBonus = (100 - driverData.attributes.pace) * 0.01;
    const carBonus = (100 - team.carPerformance) * 0.008;

    // Tire performance
    const tireData = TIRE_DATA[driver.tire];
    const tireDelta = tireData.lapDelta;

    // Tire degradation - exponential after cliff point
    let degradation = 0;
    if (driver.tireWear > tireData.cliffPoint) {
      const overCliff = driver.tireWear - tireData.cliffPoint;
      degradation = overCliff * 0.03 + (overCliff * overCliff) * 0.001; // Exponential cliff
    } else {
      degradation = driver.tireWear * 0.008;
    }

    // Fresh tire advantage (first 3 laps)
    const freshBoost = driver.tireAge < 3 ? -0.4 : 0;

    // Safety car - everyone goes much slower
    // VSC - everyone slows but maintains gaps (handled in gap calculation)
    const scPenalty = safetyCar ? (safetyCarType === "sc" ? 25 : 15) : 0;

    // Random variance - more realistic lap-to-lap variation
    // Includes: traffic, minor mistakes, pushing/managing, dirty air
    const baseVariance = (Math.random() - 0.5) * 0.6; // ±0.3s base
    const occasionalMistake = Math.random() < 0.08 ? 0.4 + Math.random() * 0.6 : 0; // 8% chance of losing 0.4-1.0s
    const pushLap = Math.random() < 0.1 ? -0.2 : 0; // 10% chance of a purple sector
    const variance = baseVariance + occasionalMistake + pushLap;

    return baseTime + paceBonus + carBonus + tireDelta + degradation + freshBoost + scPenalty + variance;
  }, [currentSave, safetyCar]);

  // Simulate one lap
  const simulateLap = useCallback(() => {
    if (raceState !== "racing" && raceState !== "safety_car" && raceState !== "vsc") return;

    const newLap = currentLap + 1;

    if (newLap > totalLaps) {
      setRaceState("finished");
      return;
    }

    // Collect events synchronously during computation
    const lapEvents: string[] = [];
    let incidentThisLap: { driver: string; type: string } | null = null;

    // Compute new driver states (synchronous computation on current state)
    const computeNewState = (prevDrivers: DriverRaceState[]): { drivers: DriverRaceState[]; incident: { driver: string; type: string } | null } => {
      let incident: { driver: string; type: string } | null = null;
      const updated = prevDrivers.map(driver => {
        if (driver.status === "out") return driver;

        const tireData = TIRE_DATA[driver.tire];
        const lapTime = calculateLapTime(driver);
        const newWear = Math.min(100, driver.tireWear + tireData.wearRate);

        // === INCIDENTS AND DNFs ===
        // Realistic rates: ~0-2 DNFs per race total across 22 drivers

        // Mechanical failure (engine, gearbox, hydraulics) - ~0.1% per lap per driver
        // Expected: ~0.7 mechanical failures per race
        if (Math.random() < 0.001 && !driver.isPlayer) {
          const failures = ["engine failure", "gearbox issue", "hydraulics problem", "electrical failure"];
          const failure = failures[Math.floor(Math.random() * failures.length)];
          lapEvents.push(`LAP ${newLap}: ${getLastName(driver.name)} RETIRES - ${failure}!`);

          // Mechanical failures can cause safety car if debris on track
          if (Math.random() < 0.25) {
            incident = { driver: getLastName(driver.name), type: "debris on track" };
          }
          return { ...driver, status: "out" as const };
        }

        // Tire failure (only when extremely worn - rare)
        if (newWear > 95 && Math.random() < 0.02) {
          lapEvents.push(`LAP ${newLap}: ${getLastName(driver.name)} TIRE BLOWOUT! Into the barrier!`);
          incident = { driver: getLastName(driver.name), type: "crash at turn " + (Math.floor(Math.random() * 12) + 1) };
          return { ...driver, status: "out" as const };
        }

        // Lap 1 incident (contact, spin, crash) - ~1.5% per driver
        // Expected: ~0.3 lap 1 incidents per race
        if (newLap === 1 && Math.random() < 0.015 && !driver.isPlayer) {
          const lap1Incidents = [
            { text: "collides at turn 1", incidentDesc: "multi-car contact at turn 1" },
            { text: "spins on the opening lap", incidentDesc: "car beached in gravel trap" },
            { text: "contact sends them into the gravel", incidentDesc: "stranded car at turn 3" },
            { text: "gets squeezed and crashes", incidentDesc: "barrier impact at turn 1" }
          ];
          const { text, incidentDesc } = lap1Incidents[Math.floor(Math.random() * lap1Incidents.length)];
          lapEvents.push(`LAP 1: ${getLastName(driver.name)} ${text}! OUT`);
          incident = { driver: getLastName(driver.name), type: incidentDesc };
          return { ...driver, status: "out" as const };
        }

        // Driver error/crash during race (rare, slightly more likely on very worn tires)
        // Expected: ~0.3 crashes per race
        const errorChance = 0.0004 + (newWear > 80 ? 0.0006 : 0);
        if (Math.random() < errorChance && !driver.isPlayer) {
          const errors = [
            { text: "loses it at the chicane", incidentDesc: "car in the barriers at chicane" },
            { text: "spins into the barriers", incidentDesc: "crashed car blocking the track" },
            { text: "locks up and crashes", incidentDesc: "heavy impact at turn " + (Math.floor(Math.random() * 12) + 1) },
            { text: "runs wide and hits the wall", incidentDesc: "car in the wall" }
          ];
          const { text, incidentDesc } = errors[Math.floor(Math.random() * errors.length)];
          lapEvents.push(`LAP ${newLap}: ${getLastName(driver.name)} ${text}!`);
          incident = { driver: getLastName(driver.name), type: incidentDesc };
          return { ...driver, status: "out" as const };
        }

        // AI pit stop decision
        if (!driver.isPlayer && raceType === "feature" && driver.pitStops === 0) {
          const shouldPit =
            (newLap >= driver.pitWindow.min && newLap <= driver.pitWindow.max && Math.random() < 0.3) ||
            (newLap >= driver.pitWindow.max) ||
            (newWear > tireData.cliffPoint + 10) ||
            (safetyCar && newLap >= driver.pitWindow.min - 2); // Pit under safety car if close to window

          if (shouldPit) {
            // Choose new compound (must be different for mandatory rule)
            // Strategy depends on laps remaining and current tire
            const lapsRemaining = totalLaps - newLap;
            let newTire: TireCompound;

            if (driver.tire === "S") {
              // Started soft: medium is standard, hard if many laps left on high deg
              if (lapsRemaining > 20) {
                newTire = Math.random() < 0.4 ? "H" : "M";
              } else {
                newTire = Math.random() < 0.85 ? "M" : "H";
              }
            } else if (driver.tire === "M") {
              // Started medium: soft for pace if few laps, hard if many laps
              if (lapsRemaining <= 12) {
                newTire = Math.random() < 0.8 ? "S" : "H";
              } else {
                newTire = Math.random() < 0.5 ? "S" : "H";
              }
            } else {
              // Started hard (rare): soft for final stint pace
              if (lapsRemaining <= 15) {
                newTire = Math.random() < 0.85 ? "S" : "M";
              } else {
                newTire = Math.random() < 0.5 ? "S" : "M";
              }
            }

            lapEvents.push(`LAP ${newLap}: ${getLastName(driver.name)} pits for ${newTire === "S" ? "Softs" : newTire === "M" ? "Mediums" : "Hards"}`);

            return {
              ...driver,
              tire: newTire,
              tireAge: 0,
              tireWear: 0,
              pitStops: driver.pitStops + 1,
              usedCompounds: [...driver.usedCompounds, newTire],
              gap: driver.gap + PIT_STOP_LOSS,
              lastLap: lapTime + PIT_STOP_LOSS,
            };
          }
        }

        return {
          ...driver,
          tireAge: driver.tireAge + 1,
          tireWear: newWear,
          lastLap: lapTime,
          bestLap: driver.bestLap === null || lapTime < driver.bestLap ? lapTime : driver.bestLap,
        };
      });

      // Sort by current gap to process in race order
      const running = updated.filter(d => d.status !== "out");
      running.sort((a, b) => a.gap - b.gap);

      // SAFETY CAR GAP COMPRESSION
      // Under SC, the field bunches up - gaps compress significantly each lap
      // Under VSC, gaps are maintained (everyone slows proportionally)
      if (safetyCar && safetyCarType === "sc") {
        running.forEach((driver, idx) => {
          if (idx === 0) {
            driver.gap = 0;
            driver.interval = 0;
          } else {
            // SC compresses gaps - each car closes up to ~1-1.5s behind the car ahead
            const targetInterval = 1.0 + Math.random() * 0.5;
            // Gaps compress gradually over multiple laps
            const compressionRate = 0.7; // Close 70% of excess gap each lap
            const excessGap = Math.max(0, driver.interval - targetInterval);
            driver.interval = targetInterval + excessGap * (1 - compressionRate);
            driver.gap = running[idx - 1].gap + driver.interval;
          }
        });
      } else if (safetyCar && safetyCarType === "vsc") {
        // VSC - gaps stay roughly the same (small variance only)
        running.forEach((driver, idx) => {
          if (idx === 0) {
            driver.gap = 0;
          } else {
            // Tiny variance to simulate slight differences in VSC compliance
            const variance = (Math.random() - 0.5) * 0.1;
            driver.interval = Math.max(0.5, driver.interval + variance);
            driver.gap = running[idx - 1].gap + driver.interval;
          }
        });
      } else {
        // Normal racing - update gaps based on lap time differences
        running.forEach((driver, idx) => {
          if (idx === 0) {
            // Leader's gap stays at 0
            driver.gap = 0;
          } else {
            const carAhead = running[idx - 1];
            const lapTimeDiff = (driver.lastLap || 95) - (carAhead.lastLap || 95);

            // Gap changes by the lap time difference
            // Positive diff = car behind is slower, gap increases
            // Negative diff = car behind is faster, gap decreases (catching up)
            const newInterval = driver.interval + lapTimeDiff;

            // Dirty air effect - harder to follow closely, lose some pace
            const dirtyAirPenalty = newInterval < 2.0 ? 0.15 * (2.0 - newInterval) : 0;

            // Apply dirty air to catching rate
            const effectiveInterval = newInterval + dirtyAirPenalty;

          // Check for overtake attempt when within DRS range (under 1 second)
          if (effectiveInterval <= 1.0 && effectiveInterval > 0) {
            // Calculate overtake probability - tuned for realistic ~1 overtake per lap across field
            const driverData = currentSave?.drivers.find(d => d.id === driver.driverId);
            const aheadData = currentSave?.drivers.find(d => d.id === carAhead.driverId);

            // Base chance - overtaking requires advantage
            let overtakeChance = 0.03;

            // LAP 1 CHAOS - much more action at the start
            // Bunched up field, cold brakes, drivers taking risks
            if (newLap <= 2) {
              overtakeChance += 0.15; // Big boost for opening laps
            } else if (newLap <= 5) {
              overtakeChance += 0.06; // Moderate boost in early laps
            }

            // Significant pace advantage
            if (lapTimeDiff < -0.5) overtakeChance += 0.10;
            else if (lapTimeDiff < -0.3) overtakeChance += 0.05;
            else if (lapTimeDiff < -0.15) overtakeChance += 0.02;

            // Fresh tires vs worn tires is a big advantage
            const tireDelta = carAhead.tireWear - driver.tireWear;
            if (tireDelta > 25) overtakeChance += 0.12;
            else if (tireDelta > 15) overtakeChance += 0.06;
            else if (tireDelta > 8) overtakeChance += 0.03;

            // Skill difference
            const skillDiff = (driverData?.attributes.pace || 70) - (aheadData?.attributes.pace || 70);
            overtakeChance += skillDiff * 0.003;

            // DRS zone - helps if close
            if (effectiveInterval < 0.5) overtakeChance += 0.08;
            else if (effectiveInterval < 0.8) overtakeChance += 0.05;

            // Cap the chance
            overtakeChance = Math.max(0.02, Math.min(0.35, overtakeChance));

            if (Math.random() < overtakeChance) {
              // Successful overtake!
              const tempGap = driver.gap;
              driver.gap = carAhead.gap;
              driver.interval = 0.5 + Math.random() * 0.5; // Pull away
              carAhead.gap = tempGap + 0.8;
              carAhead.interval = 0.8 + Math.random() * 0.4;

              lapEvents.push(`LAP ${newLap}: ${getLastName(driver.name)} passes ${getLastName(carAhead.name)}!`);
            } else {
              // Stuck behind in dirty air - gap stabilizes
              driver.interval = Math.max(0.4, effectiveInterval);
              driver.gap = carAhead.gap + driver.interval;
            }
          } else if (effectiveInterval <= 0) {
            // Caught up completely - must attempt pass
            // Easier on lap 1-2 when field is bunched
            const passChance = newLap <= 2 ? 0.45 : 0.28;
            const overtakeSuccess = Math.random() < passChance;
            if (overtakeSuccess) {
              driver.gap = carAhead.gap;
              driver.interval = 0.6;
              carAhead.gap = driver.gap + 0.8;
              carAhead.interval = 0.8;
              lapEvents.push(`LAP ${newLap}: ${getLastName(driver.name)} gets past ${getLastName(carAhead.name)}!`);
            } else {
              // Blocked - lose time in the battle
              driver.interval = 0.5;
              driver.gap = carAhead.gap + 0.5;
            }
          } else {
            // Normal racing - update gap (dirty air already factored in)
            driver.interval = effectiveInterval;
            driver.gap = carAhead.gap + effectiveInterval;
          }
        }
        });
      } // End of normal racing else block

      // Re-sort after potential overtakes and assign final positions
      running.sort((a, b) => a.gap - b.gap);

      // Recalculate clean intervals after sort
      running.forEach((driver, idx) => {
        if (idx === 0) {
          driver.gap = 0;
          driver.interval = 0;
        } else {
          driver.interval = driver.gap - running[idx - 1].gap;
        }

        const oldPos = driver.currentPosition;
        driver.currentPosition = idx + 1;
        driver.positionChange = oldPos - driver.currentPosition;
      });

      // Add DNF drivers at end
      const dnfs = updated.filter(d => d.status === "out");
      dnfs.forEach((d, idx) => {
        d.currentPosition = running.length + idx + 1;
      });

      return { drivers: [...running, ...dnfs], incident };
    };

    // Run the computation synchronously on current drivers state
    const result = computeNewState(drivers);
    const newDriverState = result.drivers;
    incidentThisLap = result.incident;

    // Now update all state together
    setCurrentLap(newLap);
    setDrivers(newDriverState);

    // Process events into commentary
    if (lapEvents.length > 0) {
      setCommentary(prev => [...prev, ...lapEvents].slice(-15));
    }

    // Deploy safety car or VSC if there was a serious incident - pause for player decision
    if (incidentThisLap !== null && !safetyCar && newLap < totalLaps - 3) {
      const incidentDriver = incidentThisLap.driver;
      const incidentType = incidentThisLap.type;

      // Decide SC vs VSC based on incident severity
      // Crashes/collisions = full SC (need marshals on track)
      // Mechanical failures/debris = could be VSC
      const needsFullSC = incidentType.includes("crash") || incidentType.includes("contact") ||
                          incidentType.includes("barrier") || incidentType.includes("impact") ||
                          incidentType.includes("beached");
      const scType: SafetyCarType = needsFullSC ? "sc" : (Math.random() < 0.6 ? "vsc" : "sc");

      setSafetyCar(true);
      setSafetyCarType(scType);
      setRaceState("pre"); // Pause the race
      setSafetyCarReason(`${incidentType} (${incidentDriver})`);
      setShowSafetyCarPrompt(true);

      const scLabel = scType === "sc" ? "SAFETY CAR" : "VIRTUAL SAFETY CAR";
      setCommentary(prev => [...prev, `${scLabel}: ${incidentType} (${incidentDriver})`].slice(-15));
    }

    // Check if player needs to pit (feature race warning)
    if (raceType === "feature") {
      const playerDriver = newDriverState.find(d => d.isPlayer);
      if (playerDriver && playerDriver.pitStops === 0 && newLap >= totalLaps - 5) {
        setShowPitPrompt(true);
      }
    }

    // Race engineer advice
    const playerDriver = newDriverState.find(d => d.isPlayer);
    if (playerDriver) {
      checkEngineerAdvice(newLap, playerDriver, newDriverState, safetyCar);
    }
  }, [raceState, currentLap, totalLaps, safetyCar, safetyCarType, calculateLapTime, raceType, simSpeed, drivers, checkEngineerAdvice]);

  // Run simulation
  useEffect(() => {
    if (raceState === "racing" || raceState === "safety_car" || raceState === "vsc") {
      const interval = 2000 / simSpeed; // 2 seconds per lap at 1x
      intervalRef.current = setInterval(simulateLap, interval);
    } else if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [raceState, simulateLap, simSpeed]);

  // Player pit stop
  const handlePlayerPit = (newTire: TireCompound) => {
    setDrivers(prev => prev.map(driver => {
      if (!driver.isPlayer) return driver;

      setCommentary(c => [...c, `YOUR PIT STOP: Switching to ${newTire === "S" ? "Softs" : newTire === "M" ? "Mediums" : "Hards"}`].slice(-10));

      return {
        ...driver,
        tire: newTire,
        tireAge: 0,
        tireWear: 0,
        pitStops: driver.pitStops + 1,
        usedCompounds: [...driver.usedCompounds, newTire],
        gap: driver.gap + PIT_STOP_LOSS,
      };
    }));
    setShowPitPrompt(false);
  };

  // Handle safety car decision
  const handleSafetyCarDecision = (decision: "pit" | "stay_out", newTire?: TireCompound) => {
    setShowSafetyCarPrompt(false);

    const isSC = safetyCarType === "sc";
    const scLabel = isSC ? "SC" : "VSC";

    if (decision === "pit" && newTire) {
      // SC pit: field bunched = big time savings (~8s)
      // VSC pit: gaps maintained = smaller savings (~3s)
      const pitTimeSaved = isSC ? 8 : 3;
      const pitLoss = PIT_STOP_LOSS - pitTimeSaved;

      setDrivers(prev => prev.map(driver => {
        if (!driver.isPlayer) return driver;
        return {
          ...driver,
          tire: newTire,
          tireAge: 0,
          tireWear: 0,
          pitStops: driver.pitStops + 1,
          usedCompounds: [...driver.usedCompounds, newTire],
          gap: driver.gap + pitLoss,
        };
      }));
      const tireName = newTire === "S" ? "Softs" : newTire === "M" ? "Mediums" : "Hards";
      setCommentary(prev => [...prev, `YOUR PIT STOP under ${scLabel}: ${tireName}`].slice(-15));
    } else {
      setCommentary(prev => [...prev, `Staying out under ${scLabel}`].slice(-15));
    }

    // Resume under SC/VSC, then green flag after delay
    // SC lasts longer (marshal activity), VSC is shorter
    setRaceState(isSC ? "safety_car" : "vsc");
    const baseDuration = isSC ? 4000 : 2500;
    const scDuration = baseDuration + Math.random() * 2000;

    setTimeout(() => {
      setSafetyCar(false);
      setRaceState("racing");
      const resumeMsg = isSC ? "GREEN FLAG! Racing resumes" : "VSC ENDING - Track clear";
      setCommentary(prev => [...prev, resumeMsg].slice(-15));
    }, scDuration / simSpeed);
  };

  const handleStart = () => {
    setRaceState("formation");
    setCommentary(["Formation lap..."]);
    setTimeout(() => {
      setRaceState("racing");
      setCurrentLap(1);
      setCommentary(prev => [...prev, "LIGHTS OUT AND AWAY WE GO!"]);
    }, 2000);
  };

  const handleFastForward = () => {
    // Simulate all remaining laps at once (can't use simulateLap in loop due to React state batching)
    let currentDrivers = [...drivers];
    const events: string[] = [];

    // Auto-pit player if they haven't pitted in feature race
    const playerIdx = currentDrivers.findIndex(d => d.isPlayer);
    if (raceType === "feature" && playerIdx !== -1 && currentDrivers[playerIdx].pitStops === 0) {
      const player = currentDrivers[playerIdx];
      const newTire = player.tire === "S" ? "M" : "H";
      currentDrivers[playerIdx] = {
        ...player,
        tire: newTire,
        tireAge: 0,
        tireWear: 0,
        pitStops: 1,
        usedCompounds: [...player.usedCompounds, newTire],
        gap: player.gap + PIT_STOP_LOSS,
      };
      events.push(`YOUR PIT STOP: ${newTire === "M" ? "Mediums" : "Hards"}`);
    }

    // Simulate each remaining lap
    for (let lap = currentLap + 1; lap <= totalLaps; lap++) {
      currentDrivers = currentDrivers.map(driver => {
        if (driver.status === "out") return driver;

        const tireData = TIRE_DATA[driver.tire];
        const driverData = currentSave?.drivers.find(d => d.id === driver.driverId);
        const team = currentSave?.teams.find(t => t.id === driver.teamId);

        // Calculate lap time
        const baseTime = 95;
        const paceBonus = driverData ? (100 - driverData.attributes.pace) * 0.01 : 0;
        const carBonus = team ? (100 - team.carPerformance) * 0.008 : 0;
        const tireDelta = tireData.lapDelta;
        let degradation = driver.tireWear > tireData.cliffPoint
          ? (driver.tireWear - tireData.cliffPoint) * 0.03
          : driver.tireWear * 0.008;
        const variance = (Math.random() - 0.5) * 0.6;
        const lapTime = baseTime + paceBonus + carBonus + tireDelta + degradation + variance;

        const newWear = Math.min(100, driver.tireWear + tireData.wearRate);

        // === INCIDENTS (same rates as normal simulation) ===

        // Mechanical failure (~0.1% per lap)
        if (Math.random() < 0.001 && !driver.isPlayer) {
          const failures = ["engine failure", "gearbox issue", "hydraulics problem"];
          const failure = failures[Math.floor(Math.random() * failures.length)];
          events.push(`LAP ${lap}: ${getLastName(driver.name)} RETIRES - ${failure}`);
          return { ...driver, status: "out" as const };
        }

        // Tire blowout (2% when extremely worn)
        if (newWear > 95 && Math.random() < 0.02 && !driver.isPlayer) {
          events.push(`LAP ${lap}: ${getLastName(driver.name)} TIRE FAILURE!`);
          return { ...driver, status: "out" as const };
        }

        // Lap 1 incident (1.5% per driver)
        if (lap === currentLap + 1 && Math.random() < 0.015 && !driver.isPlayer) {
          events.push(`LAP ${lap}: ${getLastName(driver.name)} OUT - opening lap contact`);
          return { ...driver, status: "out" as const };
        }

        // Driver error/crash (0.04-0.1% per lap, higher on worn tires)
        const errorChance = 0.0004 + (newWear > 80 ? 0.0006 : 0);
        if (Math.random() < errorChance && !driver.isPlayer) {
          events.push(`LAP ${lap}: ${getLastName(driver.name)} CRASHES OUT!`);
          return { ...driver, status: "out" as const };
        }

        // AI pit stops
        if (!driver.isPlayer && raceType === "feature" && driver.pitStops === 0) {
          if (lap >= driver.pitWindow.min && lap <= driver.pitWindow.max && Math.random() < 0.3 ||
              lap >= driver.pitWindow.max || newWear > tireData.cliffPoint + 10) {
            const lapsLeft = totalLaps - lap;
            const newTire: TireCompound = driver.tire === "S"
              ? (lapsLeft > 20 && Math.random() < 0.4 ? "H" : "M")
              : (lapsLeft <= 12 ? "S" : Math.random() < 0.5 ? "S" : "H");
            return {
              ...driver,
              tire: newTire,
              tireAge: 0,
              tireWear: 0,
              pitStops: 1,
              usedCompounds: [...driver.usedCompounds, newTire],
              gap: driver.gap + PIT_STOP_LOSS,
              lastLap: lapTime + PIT_STOP_LOSS,
            };
          }
        }

        return {
          ...driver,
          tireAge: driver.tireAge + 1,
          tireWear: newWear,
          lastLap: lapTime,
          bestLap: driver.bestLap === null || lapTime < driver.bestLap ? lapTime : driver.bestLap,
        };
      });

      // Update gaps based on lap times
      const running = currentDrivers.filter(d => d.status !== "out");
      running.sort((a, b) => a.gap - b.gap);

      running.forEach((driver, idx) => {
        if (idx === 0) {
          driver.gap = 0;
          driver.interval = 0;
        } else {
          const carAhead = running[idx - 1];
          const lapTimeDiff = (driver.lastLap || 95) - (carAhead.lastLap || 95);
          driver.interval = Math.max(0.3, driver.interval + lapTimeDiff);
          driver.gap = carAhead.gap + driver.interval;

          // Overtake attempts
          if (driver.interval < 1.0 && Math.random() < 0.08) {
            const tempGap = driver.gap;
            driver.gap = carAhead.gap;
            driver.interval = 0.6;
            carAhead.gap = tempGap + 0.8;
            carAhead.interval = 0.8;
            events.push(`LAP ${lap}: ${getLastName(driver.name)} passes ${getLastName(carAhead.name)}!`);
          }
        }
      });

      // Re-sort and update positions
      running.sort((a, b) => a.gap - b.gap);
      running.forEach((d, idx) => {
        d.currentPosition = idx + 1;
        if (idx > 0) d.interval = d.gap - running[idx - 1].gap;
      });

      const dnfs = currentDrivers.filter(d => d.status === "out");
      dnfs.forEach((d, idx) => d.currentPosition = running.length + idx + 1);
      currentDrivers = [...running, ...dnfs];
    }

    // Update final state
    setDrivers(currentDrivers);
    setCurrentLap(totalLaps);
    setCommentary(prev => [...prev, ...events.slice(-10), "CHEQUERED FLAG!"].slice(-15));
    setRaceState("finished");
  };

  const handleComplete = () => {
    const sortedDrivers = [...drivers].sort((a, b) => a.currentPosition - b.currentPosition);

    // Check if player met mandatory pit requirement
    const playerDriver = sortedDrivers.find(d => d.isPlayer);
    if (raceType === "feature" && playerDriver && playerDriver.usedCompounds.length < 2) {
      // DSQ for not using two compounds
      playerDriver.status = "out";
      setCommentary(prev => [...prev, "DISQUALIFIED: Failed to use two different tire compounds"]);
    }

    const results: DriverSessionResult[] = sortedDrivers.map(d => ({
      driverId: d.driverId,
      code: d.code,
      name: d.name,
      teamId: d.teamId,
      position: d.currentPosition,
      points: d.status === "out" ? 0 : calculatePoints(d.currentPosition, raceType),
      status: d.status === "out" ? "dnf" : "finished",
    }));

    // Find player result directly
    const playerDriverState = sortedDrivers.find(d => d.isPlayer);
    const playerPosition = playerDriverState?.currentPosition || 22;
    const playerPoints = playerDriverState && playerDriverState.status !== "out"
      ? calculatePoints(playerPosition, raceType)
      : 0;

    console.log("Race complete:", { raceType, playerPosition, playerPoints, position1Points: calculatePoints(1, raceType) });

    // Ensure weekend state exists before trying to save
    let state = getWeekendState();
    if (!state && currentSave && currentRound) {
      console.warn("[Race] Weekend state was missing, reinitializing...");
      state = initWeekendState(currentSave.saveId, currentRound.id);
    }

    // Save the race result
    let saveSuccess: boolean;
    if (raceType === "sprint") {
      saveSuccess = completeSprint(results, playerPosition, playerPoints);
    } else {
      saveSuccess = completeFeature(results, playerPosition, playerPoints);
    }

    if (!saveSuccess) {
      console.error("[Race] Failed to save race results");
    }

    router.push("/race-weekend");
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = (seconds % 60).toFixed(3);
    return `${mins}:${parseFloat(secs) < 10 ? "0" : ""}${secs}`;
  };

  const formatGap = (gap: number): string => {
    if (gap === 0) return "LEADER";
    if (gap < 60) return `+${gap.toFixed(1)}`;
    return `+${Math.floor(gap / 60)}:${(gap % 60).toFixed(1)}`;
  };

  const buildTimingEntries = (): TimingEntry[] => {
    return drivers
      .sort((a, b) => a.currentPosition - b.currentPosition)
      .map(driver => ({
        position: driver.currentPosition,
        driverId: driver.driverId,
        driverCode: driver.code,
        teamId: driver.teamId,
        time: driver.lastLap ? formatTime(driver.lastLap) : "--:--.---",
        interval: driver.status === "out" ? "OUT" : formatGap(driver.interval),
        gap: formatGap(driver.gap),
        tire: driver.tire,
        tireAge: driver.tireAge,
        status: driver.status,
        isPlayer: driver.isPlayer,
        isFastestLap: driver.bestLap !== null &&
          driver.bestLap === Math.min(...drivers.filter(d => d.bestLap !== null).map(d => d.bestLap!)),
        positionChange: driver.positionChange,
      }));
  };

  if (!player || !currentRound) {
    return (
      <div className="apex-fullscreen" style={{ justifyContent: "center", alignItems: "center" }}>
        <p style={{ color: "var(--t-3)" }}>No active career found.</p>
      </div>
    );
  }

  const playerState = drivers.find(d => d.isPlayer);
  const playerNeedsPit = raceType === "feature" && playerState && playerState.pitStops === 0;

  // Get track degradation for display (reuse trackKey from above)
  const trackDeg = Object.entries(TRACK_DEG_LEVELS).find(([key]) =>
    trackKey.includes(key)
  )?.[1] || "medium";

  return (
    <div className="apex-fullscreen" style={{ background: "#000" }}>
      <div style={{
        position: "fixed",
        inset: 0,
        background: safetyCar
          ? "radial-gradient(ellipse at 50% 0%, rgba(217,162,52,0.2) 0%, transparent 60%)"
          : "radial-gradient(ellipse at 50% 0%, rgba(30,40,60,0.4) 0%, transparent 60%)",
        pointerEvents: "none",
        transition: "background 0.5s",
      }} />

      {safetyCar && (
        <div style={{
          position: "fixed",
          top: 80,
          left: "50%",
          transform: "translateX(-50%)",
          background: safetyCarType === "sc" ? "var(--warn)" : "#1a5fb4",
          color: safetyCarType === "sc" ? "#000" : "#fff",
          padding: "8px 32px",
          borderRadius: 4,
          fontWeight: 700,
          fontSize: 14,
          letterSpacing: "0.1em",
          zIndex: 100,
        }}>
          {safetyCarType === "sc" ? "SAFETY CAR" : "VSC"}
        </div>
      )}

      {/* Pit stop prompt */}
      {showPitPrompt && playerState && (
        <div style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.8)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 200,
        }}>
          <div style={{
            background: "var(--bg-2)",
            borderRadius: 16,
            padding: 24,
            maxWidth: 400,
            border: "1px solid rgba(255,255,255,0.1)",
          }}>
            <h3 style={{ margin: "0 0 8px", fontSize: 18, color: "var(--warn)" }}>
              Mandatory Pit Stop Required
            </h3>
            <p style={{ color: "var(--t-3)", fontSize: 13, marginBottom: 16 }}>
              You must pit and use a different tire compound. Current: {playerState.tire === "S" ? "Soft" : playerState.tire === "M" ? "Medium" : "Hard"}
            </p>
            <div style={{ display: "flex", gap: 10 }}>
              {playerState.tire !== "S" && (
                <Button kind="primary" onClick={() => handlePlayerPit("S")}>
                  Soft Tires
                </Button>
              )}
              {playerState.tire !== "M" && (
                <Button kind="primary" onClick={() => handlePlayerPit("M")}>
                  Medium Tires
                </Button>
              )}
              {playerState.tire !== "H" && (
                <Button kind="primary" onClick={() => handlePlayerPit("H")}>
                  Hard Tires
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Safety car decision prompt */}
      {showSafetyCarPrompt && playerState && (
        <div style={{
          position: "fixed",
          inset: 0,
          background: "rgba(0,0,0,0.9)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 200,
        }}>
          <div style={{
            background: safetyCarType === "sc"
              ? "linear-gradient(135deg, rgba(217,162,52,0.15) 0%, var(--bg-2) 100%)"
              : "linear-gradient(135deg, rgba(26,95,180,0.15) 0%, var(--bg-2) 100%)",
            borderRadius: 16,
            padding: 28,
            maxWidth: 480,
            border: safetyCarType === "sc" ? "2px solid var(--warn)" : "2px solid #1a5fb4",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 16 }}>
              <div style={{
                width: 48,
                height: 48,
                borderRadius: 8,
                background: safetyCarType === "sc" ? "var(--warn)" : "#1a5fb4",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 24,
              }}>
                {safetyCarType === "sc" ? "🚗" : "⚡"}
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: 20, color: safetyCarType === "sc" ? "var(--warn)" : "#5b9bf8" }}>
                  {safetyCarType === "sc" ? "SAFETY CAR" : "VIRTUAL SAFETY CAR"}
                </h3>
                <p style={{ margin: 0, fontSize: 12, color: "var(--t-3)" }}>
                  {safetyCarReason}
                </p>
              </div>
            </div>

            <div style={{
              background: "rgba(0,0,0,0.3)",
              borderRadius: 8,
              padding: 12,
              marginBottom: 16,
            }}>
              <div style={{ fontSize: 11, color: "var(--t-4)", marginBottom: 4 }}>YOUR STATUS</div>
              <div style={{ display: "flex", gap: 20 }}>
                <div>
                  <span style={{ color: "var(--t-3)", fontSize: 12 }}>Position: </span>
                  <span className="mono" style={{ color: "var(--t-1)", fontWeight: 700 }}>P{playerState.currentPosition}</span>
                </div>
                <div>
                  <span style={{ color: "var(--t-3)", fontSize: 12 }}>Tire: </span>
                  <span style={{ color: playerState.tire === "S" ? "var(--tire-soft)" : playerState.tire === "M" ? "var(--tire-medium)" : "var(--tire-hard)", fontWeight: 700 }}>
                    {playerState.tire === "S" ? "Soft" : playerState.tire === "M" ? "Medium" : "Hard"} ({playerState.tireAge}L)
                  </span>
                </div>
                <div>
                  <span style={{ color: "var(--t-3)", fontSize: 12 }}>Wear: </span>
                  <span style={{ color: playerState.tireWear > 60 ? "var(--bad)" : playerState.tireWear > 40 ? "var(--warn)" : "var(--good)", fontWeight: 700 }}>
                    {Math.round(playerState.tireWear)}%
                  </span>
                </div>
              </div>
              {raceType === "feature" && playerState.pitStops === 0 && (
                <div style={{ marginTop: 8, fontSize: 11, color: "var(--electric)" }}>
                  You still need to make a mandatory pit stop
                </div>
              )}
            </div>

            <p style={{ color: "var(--t-2)", fontSize: 13, marginBottom: 16 }}>
              {safetyCarType === "sc"
                ? "Safety Car deployed — field will bunch up. Pitting now saves ~8 seconds vs normal stop."
                : "Virtual Safety Car — gaps maintained. Pitting saves ~3 seconds. Good if you need tires, but less strategic advantage."}
            </p>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <Button kind="secondary" size="lg" onClick={() => handleSafetyCarDecision("stay_out")}>
                Stay Out
              </Button>
              {playerState.tire !== "S" && (
                <Button kind="primary" onClick={() => handleSafetyCarDecision("pit", "S")}>
                  Box for Softs
                </Button>
              )}
              {playerState.tire !== "M" && (
                <Button kind="primary" onClick={() => handleSafetyCarDecision("pit", "M")}>
                  Box for Mediums
                </Button>
              )}
              {playerState.tire !== "H" && (
                <Button kind="primary" onClick={() => handleSafetyCarDecision("pit", "H")}>
                  Box for Hards
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

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
            {currentRound.name} — {raceType === "sprint" ? "Sprint Race" : "Feature Race"}
          </div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 700 }}>
            {raceState === "pre" ? "Ready to Race" :
             raceState === "formation" ? "Formation Lap" :
             raceState === "finished" ? "Race Complete" : "Live"}
          </h1>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <LapCounter currentLap={currentLap} totalLaps={totalLaps} />

          <div style={{
            padding: "6px 12px",
            background: "rgba(255,255,255,0.05)",
            borderRadius: 6,
            textAlign: "center",
          }}>
            <div style={{ fontSize: 9, color: "var(--t-4)", letterSpacing: "0.05em" }}>TIRE DEG</div>
            <div style={{
              fontSize: 12,
              fontWeight: 700,
              color: trackDeg === "high" ? "var(--bad)" : trackDeg === "low" ? "var(--good)" : "var(--warn)",
            }}>
              {trackDeg.toUpperCase()}
            </div>
          </div>

          {playerState && (
            <div style={{
              padding: "8px 16px",
              background: playerState.status === "out" ? "rgba(232,88,88,0.2)" : "rgba(61,190,115,0.2)",
              borderRadius: 8,
              textAlign: "center",
            }}>
              <div style={{ fontSize: 10, color: "var(--t-3)" }}>YOUR POSITION</div>
              <div className="mono" style={{
                fontSize: 28,
                fontWeight: 700,
                color: playerState.status === "out" ? "var(--bad)" : "var(--good)",
              }}>
                P{playerState.currentPosition}
              </div>
            </div>
          )}
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
        <div style={{ flex: "0 0 360px", overflow: "auto" }}>
          <TimingTower
            entries={buildTimingEntries()}
            session="RACE"
            sessionInfo={`LAP ${currentLap}/${totalLaps}`}
          />
        </div>

        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Race Engineer Message */}
          {engineerMessage && currentLap - engineerMessage.lap < 5 && (
            <div style={{
              background: engineerMessage.type === "pit" ? "rgba(90,169,240,0.15)" :
                         engineerMessage.type === "warn" ? "rgba(217,162,52,0.15)" :
                         engineerMessage.type === "good" ? "rgba(61,190,115,0.15)" :
                         "rgba(255,255,255,0.08)",
              borderRadius: 12,
              padding: "14px 20px",
              border: `1px solid ${
                engineerMessage.type === "pit" ? "rgba(90,169,240,0.4)" :
                engineerMessage.type === "warn" ? "rgba(217,162,52,0.4)" :
                engineerMessage.type === "good" ? "rgba(61,190,115,0.4)" :
                "rgba(255,255,255,0.15)"
              }`,
              display: "flex",
              alignItems: "center",
              gap: 14,
            }}>
              <div style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                background: "rgba(255,255,255,0.1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 14,
              }}>
                🎧
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 10, color: "var(--t-4)", letterSpacing: "0.05em", marginBottom: 2 }}>
                  RACE ENGINEER • LAP {engineerMessage.lap}
                </div>
                <div style={{
                  fontSize: 14,
                  color: engineerMessage.type === "pit" ? "var(--electric)" :
                         engineerMessage.type === "warn" ? "var(--warn)" :
                         engineerMessage.type === "good" ? "var(--good)" : "var(--t-1)",
                  fontWeight: 500,
                }}>
                  "{engineerMessage.message}"
                </div>
              </div>
              {engineerMessage.type === "pit" && raceType === "feature" && playerState?.pitStops === 0 && (
                <Button kind="primary" size="sm" onClick={() => setShowPitPrompt(true)}>
                  BOX
                </Button>
              )}
            </div>
          )}

          {/* Controls */}
          <div style={{
            background: "rgba(0,0,0,0.6)",
            borderRadius: 12,
            padding: 20,
            border: "1px solid rgba(255,255,255,0.1)",
          }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 600 }}>Race Control</h2>
              <div style={{ display: "flex", gap: 6 }}>
                {[1, 2, 5].map(speed => (
                  <button
                    key={speed}
                    onClick={() => setSimSpeed(speed as 1 | 2 | 5)}
                    style={{
                      padding: "4px 10px",
                      borderRadius: 6,
                      border: "none",
                      background: simSpeed === speed ? "var(--electric)" : "rgba(255,255,255,0.1)",
                      color: simSpeed === speed ? "#000" : "var(--t-2)",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {speed}x
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {raceState === "pre" && currentLap === 0 && (
                <Button kind="primary" size="lg" onClick={handleStart}>
                  Start Race
                </Button>
              )}

              {raceState === "pre" && currentLap > 0 && (
                <Button kind="primary" size="lg" onClick={() => setRaceState("racing")}>
                  Resume Race
                </Button>
              )}

              {(raceState === "racing" || raceState === "safety_car") && (
                <>
                  <Button kind="secondary" onClick={() => setRaceState("pre")}>
                    Pause
                  </Button>
                  <Button kind="ghost" onClick={handleFastForward}>
                    Skip to Finish →
                  </Button>
                  {playerNeedsPit && (
                    <Button kind="primary" onClick={() => setShowPitPrompt(true)}>
                      PIT NOW
                    </Button>
                  )}
                </>
              )}

              {raceState === "finished" && (
                <Button kind="primary" size="lg" onClick={handleComplete}>
                  Continue to Weekend
                </Button>
              )}
            </div>

            <p style={{ color: "var(--t-4)", fontSize: 11, margin: "12px 0 0" }}>
              {raceType === "feature"
                ? "Mandatory pit stop required — must use two different tire compounds"
                : "No mandatory pit — teams choose between soft and medium strategies"}
            </p>
          </div>

          {/* Player status */}
          {playerState && (
            <div style={{
              background: playerNeedsPit ? "rgba(217,162,52,0.15)" : "rgba(61,190,115,0.1)",
              borderRadius: 12,
              padding: 20,
              border: `1px solid ${playerNeedsPit ? "rgba(217,162,52,0.4)" : "rgba(61,190,115,0.3)"}`,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 16 }}>
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
                    P{playerState.currentPosition}
                  </span>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: "#fff" }}>{playerState.name}</div>
                  <div style={{ fontSize: 12, color: "var(--t-3)" }}>
                    Started P{playerState.gridPosition} •
                    {playerState.currentPosition < playerState.gridPosition
                      ? ` +${playerState.gridPosition - playerState.currentPosition}`
                      : playerState.currentPosition > playerState.gridPosition
                        ? ` ${playerState.currentPosition - playerState.gridPosition}`
                        : " Same position"}
                  </div>
                </div>
                {playerNeedsPit && (
                  <div style={{
                    background: "var(--warn)",
                    color: "#000",
                    padding: "4px 12px",
                    borderRadius: 4,
                    fontSize: 11,
                    fontWeight: 700,
                  }}>
                    PIT REQUIRED
                  </div>
                )}
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 16 }}>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>GAP</div>
                  <div className="mono" style={{ fontSize: 16, color: "var(--t-1)" }}>
                    {formatGap(playerState.gap)}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>TIRE</div>
                  <TireBadge compound={playerState.tire} age={playerState.tireAge} />
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>WEAR</div>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Bar
                      value={100 - playerState.tireWear}
                      max={100}
                      height={6}
                      color={playerState.tireWear > TIRE_DATA[playerState.tire].cliffPoint ? "var(--bad)" :
                             playerState.tireWear > 50 ? "var(--warn)" : "var(--good)"}
                      style={{ width: 50 }}
                    />
                    <span className="mono" style={{ fontSize: 11, color: "var(--t-2)" }}>
                      {Math.round(100 - playerState.tireWear)}%
                    </span>
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>PITS</div>
                  <div className="mono" style={{ fontSize: 16, color: "var(--t-1)" }}>
                    {playerState.pitStops}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 10, color: "var(--t-3)" }}>COMPOUNDS</div>
                  <div style={{ display: "flex", gap: 4 }}>
                    {playerState.usedCompounds.map((c, i) => (
                      <span
                        key={i}
                        style={{
                          width: 16,
                          height: 16,
                          borderRadius: 999,
                          border: `2px solid ${c === "S" ? "var(--tire-soft)" : c === "M" ? "var(--tire-medium)" : "var(--tire-hard)"}`,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: 8,
                          fontWeight: 800,
                          color: c === "S" ? "var(--tire-soft)" : c === "M" ? "var(--tire-medium)" : "var(--tire-hard)",
                        }}
                      >
                        {c}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Commentary */}
          <div style={{
            flex: 1,
            background: "rgba(0,0,0,0.4)",
            borderRadius: 10,
            padding: 16,
            overflow: "auto",
          }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: "var(--t-3)", marginBottom: 10, letterSpacing: "0.05em" }}>
              RACE FEED
            </div>
            {commentary.length === 0 ? (
              <p style={{ color: "var(--t-3)", fontSize: 13 }}>Waiting for race to start...</p>
            ) : (
              [...commentary].reverse().map((msg, idx) => (
                <div
                  key={idx}
                  style={{
                    padding: "6px 0",
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                    fontSize: 13,
                    color: msg.includes("SAFETY CAR") || msg.includes("GREEN FLAG") ? "var(--warn)" :
                           msg.includes("RETIRES") || msg.includes("BLOWOUT") || msg.includes("OUT") || msg.includes("DISQUALIFIED") ? "var(--bad)" :
                           msg.includes("LIGHTS OUT") ? "var(--good)" :
                           msg.includes("passes") || msg.includes("gets past") ? "var(--electric)" :
                           msg.includes("pits") ? "var(--accent)" : "var(--t-2)",
                  }}
                >
                  {msg}
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
