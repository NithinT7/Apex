"use client";

import { AlertTriangle, CheckCircle, Shield, Zap } from "lucide-react";
import { useState } from "react";
import type { DecisionChoice, PendingDecision } from "@/lib/types";

type Props = {
  decision: PendingDecision;
  onSubmit: (choiceIndex: number) => void;
  onAutoComplete: () => void;
  isSubmitting: boolean;
};

const typeIcons: Record<string, typeof Zap> = {
  start: Zap,
  attack: Zap,
  defend: Shield,
  tires: AlertTriangle,
  strategy: AlertTriangle,
  safety_car: AlertTriangle,
  weather: AlertTriangle,
  late_pressure: Zap,
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

function getRiskLabel(risk: number): string {
  if (risk <= 2) return "Low Risk";
  if (risk <= 5) return "Medium Risk";
  if (risk <= 7) return "High Risk";
  return "Very High Risk";
}

function getRiskClass(risk: number): string {
  if (risk <= 2) return "risk-low";
  if (risk <= 5) return "risk-medium";
  if (risk <= 7) return "risk-high";
  return "risk-extreme";
}

export function DecisionPromptModal({ decision, onSubmit, onAutoComplete, isSubmitting }: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const { prompt } = decision;
  const Icon = typeIcons[prompt.type] ?? AlertTriangle;

  function handleSubmit() {
    if (selectedIndex !== null) {
      onSubmit(selectedIndex);
    }
  }

  return (
    <div className="decision-modal-overlay">
      <div className="decision-modal">
        <header className="decision-header">
          <div className="decision-type">
            <Icon size={20} />
            <span>{typeLabels[prompt.type] ?? prompt.type}</span>
          </div>
          <span className="decision-lap">Lap {prompt.lap}</span>
        </header>

        <div className="decision-content">
          <h2>{prompt.title}</h2>
          <p>{prompt.description}</p>
        </div>

        <div className="decision-choices">
          {prompt.choices.map((choice, index) => (
            <ChoiceCard
              key={choice.id}
              choice={choice}
              index={index}
              isSelected={selectedIndex === index}
              isDefault={choice.id === prompt.defaultChoiceId}
              onSelect={() => setSelectedIndex(index)}
            />
          ))}
        </div>

        <footer className="decision-footer">
          <button
            type="button"
            className="secondary-button"
            onClick={onAutoComplete}
            disabled={isSubmitting}
          >
            Skip All Decisions
          </button>
          <button
            type="button"
            className="primary-button"
            onClick={handleSubmit}
            disabled={selectedIndex === null || isSubmitting}
          >
            {isSubmitting ? "Confirming..." : "Confirm Choice"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function ChoiceCard({
  choice,
  index,
  isSelected,
  isDefault,
  onSelect,
}: {
  choice: DecisionChoice;
  index: number;
  isSelected: boolean;
  isDefault: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`choice-card ${isSelected ? "selected" : ""}`}
      onClick={onSelect}
    >
      <div className="choice-header">
        <span className="choice-label">{choice.label}</span>
        {isDefault && (
          <span className="choice-default">
            <CheckCircle size={14} />
            Default
          </span>
        )}
      </div>
      <div className="choice-meta">
        <span className={`choice-risk ${getRiskClass(choice.risk)}`}>
          {getRiskLabel(choice.risk)}
        </span>
      </div>
    </button>
  );
}
