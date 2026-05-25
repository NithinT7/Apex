// API client for communicating with the FastAPI backend

import type {
  SaveGame,
  SaveSummary,
  CareerOptions,
  CreateCareerRequest,
  WeekendPreview,
  WeekendResult,
  SessionResult,
  RaceResult,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API Error (${res.status}): ${error}`);
  }

  return res.json();
}

// ─────────────────────────────────────────────────────────────
// Save Management
// ─────────────────────────────────────────────────────────────

export async function listSaves(): Promise<SaveSummary[]> {
  return fetchAPI("/saves");
}

export async function getSave(saveId: string): Promise<SaveGame> {
  return fetchAPI(`/saves/${saveId}`);
}

export async function createSave(name: string): Promise<SaveGame> {
  return fetchAPI("/saves", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function deleteSave(saveId: string): Promise<void> {
  await fetchAPI(`/saves/${saveId}`, { method: "DELETE" });
}

// ─────────────────────────────────────────────────────────────
// Career Creation
// ─────────────────────────────────────────────────────────────

export async function getCareerOptions(): Promise<CareerOptions> {
  return fetchAPI("/career/new/options");
}

export async function createCareer(
  request: CreateCareerRequest
): Promise<SaveGame> {
  return fetchAPI("/career/new", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// ─────────────────────────────────────────────────────────────
// Race Weekend
// ─────────────────────────────────────────────────────────────

export async function getWeekendPreview(saveId: string): Promise<WeekendPreview> {
  return fetchAPI(`/career/${saveId}/weekend/next/preview`);
}

export async function simulateWeekend(saveId: string): Promise<SaveGame> {
  return fetchAPI(`/career/${saveId}/weekend/next/simulate`, { method: "POST" });
}

export async function getWeekendResult(saveId: string, roundId: string): Promise<WeekendResult> {
  return fetchAPI(`/career/${saveId}/weekend/${roundId}`);
}

// Session-by-session weekend simulation
export interface SessionSimResult {
  success: boolean;
  session: string;
  playerPosition: number | null;
  playerGap?: string;
  playerPoints?: number;
  playerSetupScore?: number;
  classification: Array<{
    position: number;
    driverId: string;
    lapTime?: number;
    gapToPole?: number;
    points?: number;
    note?: string;
  }>;
}

export async function startWeekend(saveId: string): Promise<{
  success: boolean;
  roundId: string;
  phase: string;
  hasSprint: boolean;
}> {
  return fetchAPI(`/career/${saveId}/weekend/session/start`, { method: "POST" });
}

export async function runPractice(saveId: string): Promise<SessionSimResult> {
  return fetchAPI(`/career/${saveId}/weekend/session/practice`, { method: "POST" });
}

export async function runQualifying(saveId: string): Promise<SessionSimResult> {
  return fetchAPI(`/career/${saveId}/weekend/session/qualifying`, { method: "POST" });
}

export async function runSprint(saveId: string): Promise<SessionSimResult> {
  return fetchAPI(`/career/${saveId}/weekend/session/sprint`, { method: "POST" });
}

export async function runFeature(saveId: string): Promise<SessionSimResult> {
  return fetchAPI(`/career/${saveId}/weekend/session/feature`, { method: "POST" });
}

export interface LocalRaceResults {
  qualifying_position?: number;
  sprint_position?: number;
  feature_position?: number;
  sprint_points?: number;
  feature_points?: number;
}

export async function completeWeekend(saveId: string, results?: LocalRaceResults): Promise<{
  success: boolean;
  headline: string;
  qualifyingPosition: number | null;
  featurePosition: number | null;
  pointsEarned: number;
  developmentPointsEarned?: number;
}> {
  return fetchAPI(`/career/${saveId}/weekend/session/complete`, {
    method: "POST",
    body: results ? JSON.stringify(results) : undefined,
  });
}

export async function getWeekendStatus(saveId: string): Promise<{
  active: boolean;
  roundId?: string;
  phase?: string;
  hasSprint?: boolean;
  practiceComplete?: boolean;
  qualifyingComplete?: boolean;
  sprintComplete?: boolean;
  featureComplete?: boolean;
}> {
  return fetchAPI(`/career/${saveId}/weekend/session/status`);
}

// ─────────────────────────────────────────────────────────────
// Race Decisions
// ─────────────────────────────────────────────────────────────

export async function submitDecision(
  saveId: string,
  decisionId: string,
  choiceId: string
): Promise<{ success: boolean; outcome: string }> {
  return fetchAPI(`/saves/${saveId}/decisions/${decisionId}`, {
    method: "POST",
    body: JSON.stringify({ choice_id: choiceId }),
  });
}

// ─────────────────────────────────────────────────────────────
// Activity / Between Races
// ─────────────────────────────────────────────────────────────

export async function getActivities(saveId: string): Promise<{
  available_activities: Array<{
    id: string;
    name: string;
    description: string;
    cost: number;
    effects: Record<string, number>;
  }>;
  activity_points: number;
}> {
  return fetchAPI(`/saves/${saveId}/activities`);
}

export async function performActivity(
  saveId: string,
  activityId: string
): Promise<{ success: boolean; message: string; effects: Record<string, number> }> {
  return fetchAPI(`/saves/${saveId}/activities/${activityId}`, {
    method: "POST",
  });
}

export async function advanceToNextRound(saveId: string): Promise<SaveGame> {
  return fetchAPI(`/saves/${saveId}/advance`, { method: "POST" });
}

// ─────────────────────────────────────────────────────────────
// Development
// ─────────────────────────────────────────────────────────────

export async function getDevelopmentTree(saveId: string): Promise<{
  branches: Record<string, {
    id: string;
    name: string;
    nodes: Array<{
      id: string;
      name: string;
      description: string;
      cost: number;
      unlocked: boolean;
      available: boolean;
      effects: Record<string, number>;
    }>;
  }>;
  available_points: number;
}> {
  return fetchAPI(`/saves/${saveId}/development`);
}

export async function unlockNode(
  saveId: string,
  nodeId: string
): Promise<{ success: boolean; message: string }> {
  return fetchAPI(`/saves/${saveId}/development/${nodeId}`, {
    method: "POST",
  });
}

// ─────────────────────────────────────────────────────────────
// Weekly Focus
// ─────────────────────────────────────────────────────────────

export interface WeeklyFocus {
  id: string;
  name: string;
  description: string;
  category: string;
  primaryXpBranch: string;
  primaryXpAmount: number;
  flavorText?: string;
}

export interface FocusItem {
  focus: WeeklyFocus;
  isAvailable: boolean;
  unmetRequirements: string[];
  isRecommended: boolean;
  recommendationReason: string;
}

export interface FocusListResponse {
  availableFocuses: FocusItem[];
  daysUntilNextRace: number;
  focusSlotsAvailable: number;
  activeFocusId: string | null;
  completedFocusIds: string[];
}

export async function getAvailableFocuses(saveId: string): Promise<FocusListResponse> {
  return fetchAPI(`/career/${saveId}/development/focuses`);
}

export async function selectFocus(
  saveId: string,
  focusId: string
): Promise<{ success: boolean; activeFocusId: string | null; message: string }> {
  return fetchAPI(`/career/${saveId}/development/focus`, {
    method: "POST",
    body: JSON.stringify({ focus_id: focusId }),
  });
}

export async function getDevelopmentProfile(saveId: string): Promise<{
  currentPoints: number;
  totalPointsEarned: number;
  branchXp: Record<string, number>;
  activeFocusId: string | null;
}> {
  return fetchAPI(`/career/${saveId}/development/profile`);
}

export interface FocusOutcome {
  focusId: string;
  focusName: string;
  success: boolean;
  xpGained: Record<string, number>;
  attributeChanges: Record<string, number>;
  relationshipChanges: Record<string, number>;
  marketabilityChange: number;
  academyChange: number;
  narrative: string;
}

export async function applyFocus(saveId: string): Promise<{
  success: boolean;
  outcome?: FocusOutcome;
  message?: string;
}> {
  return fetchAPI(`/career/${saveId}/development/focus/apply`, {
    method: "POST",
  });
}

export async function skipToRaceWeek(saveId: string): Promise<SaveGame> {
  return fetchAPI(`/career/${saveId}/activities/skip`, {
    method: "POST",
  });
}

export async function getSkillTree(saveId: string): Promise<{
  branches: Array<{
    branchId: string;
    name: string;
    currentXp: number;
    nodes: Array<{
      node: {
        id: string;
        name: string;
        description: string;
        cost: number;
        tier: number;
        xpRequired: number;
        effects: {
          attributeBonuses: Record<string, number>;
        };
        unlocksTraitId: string | null;
      };
      state: "locked" | "available" | "unlocked";
      canAfford: boolean;
    }>;
  }>;
  currentPoints: number;
  totalPointsEarned: number;
  recommendedNodes: string[];
}> {
  return fetchAPI(`/career/${saveId}/development/skill-tree`);
}

export async function unlockSkillNode(
  saveId: string,
  nodeId: string
): Promise<{ success: boolean; message: string }> {
  return fetchAPI(`/career/${saveId}/development/unlock-node`, {
    method: "POST",
    body: JSON.stringify({ node_id: nodeId }),
  });
}

// ─────────────────────────────────────────────────────────────
// Scouting
// ─────────────────────────────────────────────────────────────

export interface SeatStatus {
  driverId: string;
  driverName: string;
  contractYearsRemaining: number | null;
  seatRisk: number;
  isAtRisk: boolean;
  statusNote: string;
}

export interface TeamScoutingInterest {
  teamId: string;
  teamName: string;
  interestLevel: number;
  interestTier: "none" | "watching" | "interested" | "very_interested" | "pursuing";
  reasons: string[];
  concerns: string[];
  requirements: string[];
  carPerformance: number;
  teamTier: string;
  isAcademyTeam: boolean;
  hiringProfile: string;
  seatAvailable: boolean;
  seatAvailabilityNote: string;
  currentDrivers: SeatStatus[];
}

export interface ScoutingSummary {
  available: boolean;
  message?: string;
  heatScore?: number;
  tierCounts?: {
    pursuing: number;
    very_interested: number;
    interested: number;
    watching: number;
    none: number;
  };
  topTeams?: TeamScoutingInterest[];
  allTeams?: TeamScoutingInterest[];
  playerPosition?: number | null;
  teamsWithInterest?: number;
  teamsWatching?: number;
  seatsAvailable?: number;
  realisticOpportunities?: number;
}

export async function getScoutingSummary(saveId: string): Promise<ScoutingSummary> {
  return fetchAPI(`/career/${saveId}/season/scouting`);
}

export async function getTeamScoutingDetail(
  saveId: string,
  teamId: string
): Promise<TeamScoutingInterest> {
  return fetchAPI(`/career/${saveId}/season/scouting/${teamId}`);
}
