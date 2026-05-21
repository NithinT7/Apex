import type {
  Academy,
  CalendarRound,
  CareerCreationOptions,
  CreateCareerPayload,
  DataBootstrap,
  HealthResponse,
  SaveGame,
  SaveSummary,
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
