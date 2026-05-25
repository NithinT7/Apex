"use client";

import { PageHeader, Card } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";

export default function CarPerformancePage() {
  const { currentSave, getPlayerTeam } = useSave();
  const team = getPlayerTeam();

  return (
    <div>
      <PageHeader
        eyebrow="Engineering · car development"
        title="Car Performance"
        question="How fast is my car?"
      />

      <Card pad={40} style={{ textAlign: "center" }}>
        <p style={{ color: "var(--t-3)", marginBottom: 8 }}>
          Car performance tracking coming soon.
        </p>
        <p style={{ color: "var(--t-4)", fontSize: 12 }}>
          {team ? `Current team: ${team.name}` : "No team assigned"}
        </p>
      </Card>
    </div>
  );
}
