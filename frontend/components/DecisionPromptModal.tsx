"use client";

import { useState } from "react";
import type { ActiveRaceState, DecisionChoice, Driver, PendingDecision } from "@/lib/types";

type Props = {
  decision: PendingDecision;
  activeRace: ActiveRaceState;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null | undefined;
  onSubmit: (choiceIndex: number) => void;
  onAutoComplete: () => void;
  isSubmitting: boolean;
};

const typeLabels: Record<string, string> = {
  start: "Race Start",
  attack: "Attack Opportunity",
  defend: "Defensive Situation",
  tires: "Tire Strategy",
  strategy: "Strategy Call",
  safety_car: "Safety Car",
  weather: "Weather Change",
  late_pressure: "Late Race Pressure",
};

function getRiskTone(risk: number): string {
  if (risk <= 30) return "pos";
  if (risk <= 55) return "info";
  if (risk <= 75) return "warn";
  return "neg";
}

function getRiskLabel(risk: number): string {
  if (risk <= 30) return "Low";
  if (risk <= 55) return "Medium";
  if (risk <= 75) return "High";
  return "Very High";
}

export function DecisionPromptModal({
  decision,
  activeRace,
  driverMap,
  playerDriverId,
  onSubmit,
  onAutoComplete,
  isSubmitting,
}: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const { prompt } = decision;
  const latestSnapshot = activeRace.lapSnapshots.at(-1);
  const playerEntry = latestSnapshot?.runningOrder.find(
    (entry) => entry.driverId === playerDriverId
  );

  function handleSubmit() {
    if (selectedIndex !== null) {
      onSubmit(selectedIndex);
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal" style={{ maxWidth: 640 }}>
        {/* Header */}
        <div className="modal-header">
          <div>
            <div className="decision-title">{typeLabels[prompt.type] ?? "Decision"}</div>
            <div className="modal-title">{prompt.title}</div>
          </div>
          <span className="tag accent">Lap {prompt.lap}</span>
        </div>

        {/* Description */}
        <div className="decision-body">{prompt.description}</div>

        {/* Context */}
        {playerEntry && (
          <div className="flex" style={{ gap: 24, marginBottom: 20 }}>
            <div>
              <div className="t3 tiny">Position</div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
                P{playerEntry.position}
              </div>
            </div>
            <div>
              <div className="t3 tiny">Gap Ahead</div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
                {playerEntry.position === 1 ? "Leader" : `+${playerEntry.gapToCarAhead.toFixed(1)}s`}
              </div>
            </div>
            <div>
              <div className="t3 tiny">Gap to Leader</div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
                {playerEntry.position === 1 ? "—" : `+${playerEntry.gapToLeader.toFixed(1)}s`}
              </div>
            </div>
          </div>
        )}

        {/* Choices */}
        <div style={{ marginBottom: 20 }}>
          {prompt.choices.map((choice, index) => (
            <div
              key={choice.id}
              className={`decision-option ${selectedIndex === index ? "selected" : ""}`}
              onClick={() => setSelectedIndex(index)}
            >
              <div className="key">{index + 1}</div>
              <div className="lbl">{choice.label}</div>
              <div className="tags">
                <span className={`tag ${getRiskTone(choice.risk)}`} style={{ fontSize: 10 }}>
                  {getRiskLabel(choice.risk)} risk
                </span>
                {choice.id === prompt.defaultChoiceId && (
                  <span className="tag" style={{ fontSize: 10 }}>Default</span>
                )}
              </div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div className="flex" style={{ gap: 12, justifyContent: "flex-end" }}>
          <button className="btn" onClick={onAutoComplete} disabled={isSubmitting}>
            Skip All Decisions
          </button>
          <button
            className="btn primary"
            onClick={handleSubmit}
            disabled={selectedIndex === null || isSubmitting}
          >
            {isSubmitting ? "Confirming..." : "Confirm Choice"}
          </button>
        </div>
      </div>
    </div>
  );
}
