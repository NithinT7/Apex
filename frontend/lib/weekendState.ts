// Weekend state manager - persists session results across page navigations

export interface DriverSessionResult {
  driverId: string;
  code: string;
  name: string;
  teamId: string;
  position: number;
  time?: number;
  gap?: string;
  points?: number;
  status?: "finished" | "dnf";
}

export interface WeekendState {
  saveId: string;
  roundId: string;
  started: boolean;
  practice: {
    complete: boolean;
    results?: DriverSessionResult[];
    playerPosition?: number;
  };
  qualifying: {
    complete: boolean;
    results?: DriverSessionResult[];
    playerPosition?: number;
    grid?: DriverSessionResult[]; // Final grid order for races
  };
  sprint: {
    complete: boolean;
    results?: DriverSessionResult[];
    playerPosition?: number;
    points?: number;
  };
  feature: {
    complete: boolean;
    results?: DriverSessionResult[];
    playerPosition?: number;
    points?: number;
  };
}

const WEEKEND_STATE_KEY = "apex_weekend_state";

export function getWeekendState(): WeekendState | null {
  if (typeof window === "undefined") return null;
  const stored = localStorage.getItem(WEEKEND_STATE_KEY);
  if (!stored) return null;
  try {
    return JSON.parse(stored);
  } catch {
    return null;
  }
}

export function setWeekendState(state: WeekendState): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(WEEKEND_STATE_KEY, JSON.stringify(state));
}

export function initWeekendState(saveId: string, roundId: string): WeekendState {
  const state: WeekendState = {
    saveId,
    roundId,
    started: true,
    practice: { complete: false },
    qualifying: { complete: false },
    sprint: { complete: false },
    feature: { complete: false },
  };
  setWeekendState(state);
  return state;
}

export function clearWeekendState(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(WEEKEND_STATE_KEY);
}

export function completePractice(results: DriverSessionResult[], playerPosition: number): void {
  const state = getWeekendState();
  if (!state) return;
  state.practice = {
    complete: true,
    results,
    playerPosition,
  };
  setWeekendState(state);
}

export function completeQualifying(results: DriverSessionResult[], playerPosition: number): void {
  const state = getWeekendState();
  if (!state) return;
  state.qualifying = {
    complete: true,
    results,
    playerPosition,
    grid: results, // Grid is the qualifying order
  };
  setWeekendState(state);
}

export function completeSprint(results: DriverSessionResult[], playerPosition: number, points: number): boolean {
  const state = getWeekendState();
  if (!state) {
    console.error("[WeekendState] completeSprint failed: no weekend state found");
    return false;
  }
  state.sprint = {
    complete: true,
    results,
    playerPosition,
    points,
  };
  setWeekendState(state);
  console.log("[WeekendState] Sprint completed:", { playerPosition, points });
  return true;
}

export function completeFeature(results: DriverSessionResult[], playerPosition: number, points: number): boolean {
  const state = getWeekendState();
  if (!state) {
    console.error("[WeekendState] completeFeature failed: no weekend state found");
    return false;
  }
  state.feature = {
    complete: true,
    results,
    playerPosition,
    points,
  };
  setWeekendState(state);
  console.log("[WeekendState] Feature completed:", { playerPosition, points });
  return true;
}

export function getQualifyingGrid(): DriverSessionResult[] | null {
  const state = getWeekendState();
  return state?.qualifying?.grid || null;
}

// F2 points system
export const F2_FEATURE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
export const F2_SPRINT_POINTS = [10, 8, 6, 5, 4, 3, 2, 1];
export const F2_POLE_POINT = 2;
export const F2_FASTEST_LAP_POINT = 1;

export function calculatePoints(position: number, raceType: "sprint" | "feature"): number {
  const pointsTable = raceType === "sprint" ? F2_SPRINT_POINTS : F2_FEATURE_POINTS;
  if (position <= 0 || position > pointsTable.length) return 0;
  return pointsTable[position - 1];
}
