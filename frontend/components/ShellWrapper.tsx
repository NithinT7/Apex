"use client";

import { useSave } from "@/components/SaveProvider";
import { AppShell } from "@/components/Shell";

export function ShellWrapper({ children }: { children: React.ReactNode }) {
  const { currentSave } = useSave();

  return <AppShell save={currentSave}>{children}</AppShell>;
}
