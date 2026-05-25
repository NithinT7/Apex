"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  ReactNode,
} from "react";
import type { SaveGame, SaveSummary, Driver, Team, CalendarRound } from "./types";
import * as api from "./api";

interface SaveContextValue {
  // State
  saves: SaveSummary[];
  currentSave: SaveGame | null;
  loading: boolean;
  error: string | null;

  // Actions
  loadSaves: () => Promise<void>;
  loadSave: (saveId: string) => Promise<void>;
  createSave: (name: string) => Promise<SaveGame>;
  deleteSave: (saveId: string) => Promise<void>;
  refreshSave: () => Promise<void>;

  // Helpers
  getPlayerDriver: () => Driver | null;
  getPlayerTeam: () => Team | null;
  getCurrentRound: () => CalendarRound | null;
  getDriver: (id: string) => Driver | undefined;
  getTeam: (id: string) => Team | undefined;
}

const SaveContext = createContext<SaveContextValue | null>(null);

const ACTIVE_SAVE_KEY = "apex_active_save_id";

export function SaveProvider({ children }: { children: ReactNode }) {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [currentSave, setCurrentSave] = useState<SaveGame | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load all saves and restore active save on mount
  useEffect(() => {
    async function init() {
      try {
        setLoading(true);
        const data = await api.listSaves();
        setSaves(data);

        // Restore previously active save
        const storedSaveId = localStorage.getItem(ACTIVE_SAVE_KEY);
        if (storedSaveId && data.some((s) => s.saveId === storedSaveId)) {
          const save = await api.getSave(storedSaveId);
          setCurrentSave(save);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load saves");
      } finally {
        setLoading(false);
      }
    }
    init();
  }, []);

  const loadSaves = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listSaves();
      setSaves(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load saves");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSave = useCallback(async (saveId: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.getSave(saveId);
      setCurrentSave(data);
      localStorage.setItem(ACTIVE_SAVE_KEY, saveId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load save");
    } finally {
      setLoading(false);
    }
  }, []);

  const createSave = useCallback(async (name: string) => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.createSave(name);
      setSaves((prev) => [...prev, {
        saveId: data.saveId,
        name: data.name,
        updatedAt: data.updatedAt,
        season: data.season,
        phase: data.phase,
        playerDriverId: data.playerDriverId,
      }]);
      setCurrentSave(data);
      localStorage.setItem(ACTIVE_SAVE_KEY, data.saveId);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create save");
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const deleteSave = useCallback(async (saveId: string) => {
    try {
      setLoading(true);
      setError(null);
      await api.deleteSave(saveId);
      setSaves((prev) => prev.filter((s) => s.saveId !== saveId));
      if (currentSave?.saveId === saveId) {
        setCurrentSave(null);
        localStorage.removeItem(ACTIVE_SAVE_KEY);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete save");
      throw err;
    } finally {
      setLoading(false);
    }
  }, [currentSave]);

  const refreshSave = useCallback(async () => {
    if (currentSave) {
      await loadSave(currentSave.saveId);
    }
  }, [currentSave, loadSave]);

  // Helper functions
  const getPlayerDriver = useCallback(() => {
    if (!currentSave?.playerDriverId) return null;
    return currentSave.drivers.find(
      (d) => d.id === currentSave.playerDriverId
    ) || null;
  }, [currentSave]);

  const getPlayerTeam = useCallback(() => {
    const player = getPlayerDriver();
    if (!player) return null;
    return currentSave?.teams.find((t) => t.id === player.teamId) || null;
  }, [currentSave, getPlayerDriver]);

  const getCurrentRound = useCallback(() => {
    if (!currentSave) return null;
    return currentSave.calendar.find((r) => !r.completed) || null;
  }, [currentSave]);

  const getDriver = useCallback(
    (id: string) => currentSave?.drivers.find((d) => d.id === id),
    [currentSave]
  );

  const getTeam = useCallback(
    (id: string) => currentSave?.teams.find((t) => t.id === id),
    [currentSave]
  );

  return (
    <SaveContext.Provider
      value={{
        saves,
        currentSave,
        loading,
        error,
        loadSaves,
        loadSave,
        createSave,
        deleteSave,
        refreshSave,
        getPlayerDriver,
        getPlayerTeam,
        getCurrentRound,
        getDriver,
        getTeam,
      }}
    >
      {children}
    </SaveContext.Provider>
  );
}

export function useSave() {
  const context = useContext(SaveContext);
  if (!context) {
    throw new Error("useSave must be used within a SaveProvider");
  }
  return context;
}
