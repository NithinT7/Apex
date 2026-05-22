"use client";

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { getSave, getSaves } from "@/lib/api";
import type { SaveGame, SaveSummary } from "@/lib/types";

type SaveContextType = {
  saves: SaveSummary[];
  currentSave: SaveGame | null;
  selectedSaveId: string;
  loading: boolean;
  error: string | null;
  selectSave: (saveId: string) => void;
  refreshSave: () => Promise<void>;
  refreshSaves: () => Promise<void>;
};

const SaveContext = createContext<SaveContextType | null>(null);

export function SaveProvider({ children }: { children: React.ReactNode }) {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [currentSave, setCurrentSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshSaves = useCallback(async () => {
    try {
      const loaded = await getSaves();
      setSaves(loaded);
      if (!selectedSaveId && loaded.length > 0) {
        setSelectedSaveId(loaded[0].saveId);
      }
    } catch {
      setError("Could not load saves.");
    }
  }, [selectedSaveId]);

  const refreshSave = useCallback(async () => {
    if (!selectedSaveId) {
      setCurrentSave(null);
      return;
    }
    try {
      const save = await getSave(selectedSaveId);
      setCurrentSave(save);
      setError(null);
    } catch {
      setError("Could not load selected save.");
    }
  }, [selectedSaveId]);

  useEffect(() => {
    setLoading(true);
    refreshSaves().finally(() => setLoading(false));
  }, [refreshSaves]);

  useEffect(() => {
    if (selectedSaveId) {
      refreshSave();
    }
  }, [selectedSaveId, refreshSave]);

  const selectSave = (saveId: string) => {
    setSelectedSaveId(saveId);
  };

  return (
    <SaveContext.Provider
      value={{
        saves,
        currentSave,
        selectedSaveId,
        loading,
        error,
        selectSave,
        refreshSave,
        refreshSaves,
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
