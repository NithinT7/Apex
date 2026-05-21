import type {
  Academy,
  CalendarRound,
  DataBootstrap,
  HealthResponse,
  SaveGame,
  SaveSummary,
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
