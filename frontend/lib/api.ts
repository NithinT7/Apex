import type {
  Academy,
  ActiveRaceState,
  ActivityOutcome,
  AvailableActivities,
  CalendarRound,
  CareerCreationOptions,
  CreateCareerPayload,
  DataBootstrap,
  DecisionResponse,
  HealthResponse,
  PlayerStatus,
  RaceResult,
  SaveGame,
  SaveSummary,
  WeekendPrep,
  WeekendResult,
  Team,
} from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`API request failed for ${path}: ${response.status}`);
  }

  return response.json();
}

export async function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export async function getDataBootstrap(): Promise<DataBootstrap> {
  return getJson<DataBootstrap>("/data/bootstrap");
}

export async function getF2Teams(): Promise<Team[]> {
  return getJson<Team[]>("/data/teams/f2");
}

export async function getAcademies(): Promise<Academy[]> {
  return getJson<Academy[]>("/data/academies");
}

export async function getF2Calendar(): Promise<CalendarRound[]> {
  return getJson<CalendarRound[]>("/data/calendar/f2");
}

export async function createSave(name?: string): Promise<SaveGame> {
  const response = await fetch(`${API_BASE_URL}/saves`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  if (!response.ok) {
    throw new Error(`API request failed for /saves: ${response.status}`);
  }

  return response.json();
}

export async function getSaves(): Promise<SaveSummary[]> {
  return getJson<SaveSummary[]>("/saves");
}

export async function getSave(saveId: string): Promise<SaveGame> {
  return getJson<SaveGame>(`/saves/${saveId}`);
}

export async function deleteSave(saveId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/saves/${saveId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw new Error(`API request failed for /saves/${saveId}: ${response.status}`);
  }
}

export async function getCareerCreationOptions(): Promise<CareerCreationOptions> {
  return getJson<CareerCreationOptions>("/career/new/options");
}

export async function createCareer(payload: CreateCareerPayload): Promise<SaveGame> {
  const response = await fetch(`${API_BASE_URL}/career/new`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`API request failed for /career/new: ${response.status}`);
  }

  return response.json();
}

export async function simulateWeekend(saveId: string, roundId: string): Promise<SaveGame> {
  const response = await fetch(`${API_BASE_URL}/career/${saveId}/weekend/${roundId}/simulate`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`API request failed for weekend simulation: ${response.status}`);
  }

  return response.json();
}

export async function simulateNextWeekend(saveId: string): Promise<SaveGame> {
  const response = await fetch(`${API_BASE_URL}/career/${saveId}/weekend/next/simulate`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`API request failed for next weekend simulation: ${response.status}`);
  }

  return response.json();
}

export async function getWeekend(saveId: string, roundId: string): Promise<WeekendResult> {
  return getJson<WeekendResult>(`/career/${saveId}/weekend/${roundId}`);
}

// Interactive race decision endpoints

export async function prepareWeekend(saveId: string, roundId: string): Promise<WeekendPrep> {
  const response = await fetch(`${API_BASE_URL}/career/${saveId}/race/${roundId}/prepare`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`API request failed for weekend prep: ${response.status}`);
  }

  return response.json();
}

export async function startRace(
  saveId: string,
  roundId: string,
  raceType: "sprint" | "feature"
): Promise<ActiveRaceState> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/race/${roundId}/${raceType}/start`,
    { method: "POST" }
  );

  if (!response.ok) {
    throw new Error(`API request failed for race start: ${response.status}`);
  }

  return response.json();
}

export async function simulateToDecision(
  saveId: string,
  roundId: string,
  raceType: "sprint" | "feature"
): Promise<ActiveRaceState> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/race/${roundId}/${raceType}/simulate`,
    { method: "POST" }
  );

  if (!response.ok) {
    throw new Error(`API request failed for race simulation: ${response.status}`);
  }

  return response.json();
}

export async function submitDecision(
  saveId: string,
  roundId: string,
  raceType: "sprint" | "feature",
  decision: DecisionResponse
): Promise<ActiveRaceState> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/race/${roundId}/${raceType}/decide`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decision),
    }
  );

  if (!response.ok) {
    throw new Error(`API request failed for decision submission: ${response.status}`);
  }

  return response.json();
}

export async function autoCompleteRace(
  saveId: string,
  roundId: string,
  raceType: "sprint" | "feature"
): Promise<RaceResult> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/race/${roundId}/${raceType}/auto-complete`,
    { method: "POST" }
  );

  if (!response.ok) {
    throw new Error(`API request failed for race auto-complete: ${response.status}`);
  }

  return response.json();
}

export async function completeRace(
  saveId: string,
  roundId: string,
  raceType: "sprint" | "feature"
): Promise<RaceResult> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/race/${roundId}/${raceType}/complete`,
    { method: "POST" }
  );

  if (!response.ok) {
    throw new Error(`API request failed for race completion: ${response.status}`);
  }

  return response.json();
}

export async function finalizeWeekend(
  saveId: string,
  roundId: string,
  sprint: RaceResult,
  feature: RaceResult
): Promise<SaveGame> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/race/${roundId}/finalize`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sprint, feature }),
    }
  );

  if (!response.ok) {
    throw new Error(`API request failed for weekend finalization: ${response.status}`);
  }

  return response.json();
}

// Between-race activity endpoints

export async function getAvailableActivities(saveId: string): Promise<AvailableActivities> {
  return getJson<AvailableActivities>(`/career/${saveId}/activities`);
}

export async function performActivity(
  saveId: string,
  activityId: string
): Promise<ActivityOutcome> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/activities/${activityId}`,
    { method: "POST" }
  );

  if (!response.ok) {
    throw new Error(`API request failed for activity: ${response.status}`);
  }

  return response.json();
}

export async function skipToRaceWeek(saveId: string): Promise<SaveGame> {
  const response = await fetch(
    `${API_BASE_URL}/career/${saveId}/activities/skip`,
    { method: "POST" }
  );

  if (!response.ok) {
    throw new Error(`API request failed for skip to race: ${response.status}`);
  }

  return response.json();
}

export async function getPlayerStatus(saveId: string): Promise<PlayerStatus> {
  return getJson<PlayerStatus>(`/career/${saveId}/activities/status`);
}

export async function getAcademyStatus(saveId: string): Promise<AcademyStatus> {
  return getJson<AcademyStatus>(`/career/${saveId}/activities/academy`);
}

export type AcademyStatus = {
  academyName: string;
  academyStyle?: string;
  trust: number | null;
  trustLevel: string | null;
  expectedPosition: number | null;
  seatSecurity: string;
  f1Pathway: string;
  f1Team?: string;
  warnings: string[];
  opportunities: string[];
  pressure?: number;
  patience?: number;
  supportLevel?: number;
};

export async function getRivalryStatus(saveId: string): Promise<RivalryStatusResponse> {
  return getJson<RivalryStatusResponse>(`/career/${saveId}/activities/rivalries`);
}

export type RivalryResponse = {
  id: string;
  opponentId: string;
  opponentName: string;
  rivalryType: string;
  intensity: number;
  intensityLevel: string;
  respect: number;
  recentEvents: Array<{
    description: string;
    intensityChange: number;
  }>;
};

export type RivalryStatusResponse = {
  rivalries: RivalryResponse[];
  mostIntenseId: string | null;
  teammateRivalryId: string | null;
};

// Season endpoints

export type SeasonStatus = {
  season: number;
  phase: string;
  totalRounds: number;
  completedRounds: number;
  remainingRounds: number;
  isSeasonComplete: boolean;
  nextRound: { id: string; name: string; roundNumber: number } | null;
};

export type PlayerSeasonSummary = {
  driverId: string;
  driverName: string;
  championshipPosition: number;
  points: number;
  wins: number;
  podiums: number;
  poles: number;
  fastestLaps: number;
  dnfs: number;
  totalRaces: number;
  pointsFinishes: number;
  rating: string;
  headline: string;
};

export type SeasonSummary = {
  season: number;
  champion: {
    driverId: string | null;
    name: string;
    points: number;
  };
  teamChampion: {
    teamId: string | null;
    name: string;
    points: number;
  };
  finalStandings: Array<{
    position: number;
    driverId: string;
    driverName: string;
    points: number;
    wins: number;
    podiums: number;
  }>;
  playerSummary: PlayerSeasonSummary | null;
};

export async function getSeasonStatus(saveId: string): Promise<SeasonStatus> {
  return getJson<SeasonStatus>(`/career/${saveId}/season/status`);
}

export async function getSeasonSummary(saveId: string): Promise<SeasonSummary> {
  return getJson<SeasonSummary>(`/career/${saveId}/season/summary`);
}

export async function advanceSeason(saveId: string): Promise<SaveGame> {
  const response = await fetch(`${API_BASE_URL}/career/${saveId}/season/advance`, {
    method: "POST",
  });

  if (!response.ok) {
    throw new Error(`API request failed for season advance: ${response.status}`);
  }

  return response.json();
}
