"use client";

import { Calendar, FastForward, Loader2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import {
  getAcademyStatus,
  getAvailableActivities,
  getPlayerStatus,
  getRivalryStatus,
  getSave,
  getSaves,
  performActivity,
  skipToRaceWeek,
  type AcademyStatus,
  type RivalryStatusResponse,
} from "@/lib/api";
import type {
  Activity,
  ActivityOutcome,
  AvailableActivities,
  PlayerStatus,
  SaveGame,
  SaveSummary,
} from "@/lib/types";

export function BetweenRaceClient() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [save, setSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Activity state
  const [activities, setActivities] = useState<AvailableActivities | null>(null);
  const [playerStatus, setPlayerStatus] = useState<PlayerStatus | null>(null);
  const [academyStatus, setAcademyStatus] = useState<AcademyStatus | null>(null);
  const [rivalryStatus, setRivalryStatus] = useState<RivalryStatusResponse | null>(null);
  const [lastOutcome, setLastOutcome] = useState<ActivityOutcome | null>(null);
  const [performing, setPerforming] = useState(false);

  useEffect(() => {
    getSaves()
      .then((loaded) => {
        setSaves(loaded);
        setSelectedSaveId(loaded[0]?.saveId ?? "");
      })
      .catch(() => setError("Could not load saves."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedSaveId) {
      setSave(null);
      return;
    }
    loadSaveData(selectedSaveId);
  }, [selectedSaveId]);

  async function loadSaveData(saveId: string) {
    try {
      const loadedSave = await getSave(saveId);
      setSave(loadedSave);
      setLastOutcome(null);

      if (loadedSave.phase === "between_races") {
        const [acts, status, academy, rivalries] = await Promise.all([
          getAvailableActivities(saveId),
          getPlayerStatus(saveId),
          getAcademyStatus(saveId).catch(() => null),
          getRivalryStatus(saveId).catch(() => null),
        ]);
        setActivities(acts);
        setPlayerStatus(status);
        setAcademyStatus(academy);
        setRivalryStatus(rivalries);
      } else {
        setActivities(null);
        setPlayerStatus(null);
        setAcademyStatus(null);
        setRivalryStatus(null);
      }
    } catch {
      setError("Could not load save data.");
    }
  }

  async function handlePerformActivity(activityId: string) {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      const outcome = await performActivity(selectedSaveId, activityId);
      setLastOutcome(outcome);
      // Reload data after activity
      await loadSaveData(selectedSaveId);
    } catch {
      setError("Failed to perform activity.");
    } finally {
      setPerforming(false);
    }
  }

  async function handleSkipToRace() {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      await skipToRaceWeek(selectedSaveId);
      await loadSaveData(selectedSaveId);
    } catch {
      setError("Failed to skip to race week.");
    } finally {
      setPerforming(false);
    }
  }

  if (loading) {
    return <p className="lede">Loading saves...</p>;
  }

  if (!saves.length) {
    return (
      <section className="panel">
        <h2>No Saves Yet</h2>
        <p>Create a driver first, then return here after completing a race weekend.</p>
      </section>
    );
  }

  const nextRound = save?.calendar.find((r) => !r.completed);

  return (
    <section className="viewer-stack">
      <div className="panel control-panel" style={{ gridTemplateColumns: "1fr 1fr" }}>
        <label>
          Save
          <select
            value={selectedSaveId}
            onChange={(e) => setSelectedSaveId(e.target.value)}
            disabled={performing}
          >
            {saves.map((item) => (
              <option key={item.saveId} value={item.saveId}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        <div style={{ display: "flex", alignItems: "end" }}>
          <span className="lede">
            Phase: <strong>{save?.phase ?? "unknown"}</strong>
          </span>
        </div>
      </div>

      {error && <p className="error-text">{error}</p>}

      {save?.phase !== "between_races" ? (
        <section className="panel">
          <h2>Not Between Races</h2>
          <p>
            Activities are only available during the between-races phase. Current phase:{" "}
            <strong>{save?.phase}</strong>
          </p>
          {save?.phase === "race_week" && (
            <p>Head to the Race Weekend page to run the next race.</p>
          )}
        </section>
      ) : (
        <>
          {/* Player Status */}
          {playerStatus && (
            <section className="panel">
              <h2>Driver Status</h2>
              <dl className="stat-grid">
                <div>
                  <dt>Fatigue</dt>
                  <dd className={playerStatus.fatigue > 60 ? "error-text" : ""}>
                    {playerStatus.fatigue}%
                  </dd>
                </div>
                <div>
                  <dt>Morale</dt>
                  <dd>{playerStatus.morale}%</dd>
                </div>
                <div>
                  <dt>Form</dt>
                  <dd>{playerStatus.form}%</dd>
                </div>
                <div>
                  <dt>Days to Race</dt>
                  <dd>{playerStatus.daysUntilRace}</dd>
                </div>
                <div>
                  <dt>Reputation</dt>
                  <dd>{playerStatus.reputation}</dd>
                </div>
              </dl>
            </section>
          )}

          {/* Academy Status */}
          {academyStatus && academyStatus.trust !== null && (
            <AcademyStatusPanel academyStatus={academyStatus} />
          )}

          {/* Rivalry Status */}
          {rivalryStatus && rivalryStatus.rivalries.length > 0 && (
            <RivalryStatusPanel rivalryStatus={rivalryStatus} />
          )}

          {/* Last Activity Outcome */}
          {lastOutcome && (
            <section className="panel" style={{ borderColor: lastOutcome.success ? "#22c55e" : "#ef4444" }}>
              <p className="eyebrow-text">{lastOutcome.success ? "Success" : "Setback"}</p>
              <h2>{lastOutcome.activityName}</h2>
              <p>{lastOutcome.narrative}</p>
              <div className="effect-summary">
                {lastOutcome.effectsApplied.fatigue !== 0 && (
                  <span>Fatigue: {lastOutcome.effectsApplied.fatigue > 0 ? "+" : ""}{lastOutcome.effectsApplied.fatigue}</span>
                )}
                {lastOutcome.effectsApplied.morale !== 0 && (
                  <span>Morale: {lastOutcome.effectsApplied.morale > 0 ? "+" : ""}{lastOutcome.effectsApplied.morale}</span>
                )}
                {lastOutcome.effectsApplied.form !== 0 && (
                  <span>Form: {lastOutcome.effectsApplied.form > 0 ? "+" : ""}{lastOutcome.effectsApplied.form}</span>
                )}
              </div>
            </section>
          )}

          {/* Next Race Info */}
          {nextRound && (
            <div className="panel compact-action-row">
              <p>
                <Calendar size={18} style={{ verticalAlign: "middle", marginRight: 8 }} />
                Next Race: <strong>R{nextRound.roundNumber} {nextRound.name}</strong>
                {" "}({activities?.daysUntilNextRace} days)
              </p>
              <button
                className="secondary-button"
                onClick={handleSkipToRace}
                disabled={performing}
              >
                <FastForward size={18} />
                Skip to Race Week
              </button>
            </div>
          )}

          {/* Available Activities */}
          <section className="panel">
            <h2>Available Activities</h2>
            {activities && activities.activities.length > 0 ? (
              <div className="activity-grid">
                {activities.activities.map((activity) => (
                  <ActivityCard
                    key={activity.id}
                    activity={activity}
                    completed={activities.completedActivities.includes(activity.id)}
                    onPerform={() => handlePerformActivity(activity.id)}
                    disabled={performing}
                  />
                ))}
              </div>
            ) : (
              <p>No activities available. You may need to skip to race week.</p>
            )}
          </section>
        </>
      )}
    </section>
  );
}

function AcademyStatusPanel({ academyStatus }: { academyStatus: AcademyStatus }) {
  const getTrustColor = (level: string | null) => {
    switch (level) {
      case "excellent": return "#22c55e";
      case "good": return "#84cc16";
      case "neutral": return "#eab308";
      case "warning": return "#f97316";
      case "critical": return "#ef4444";
      default: return "var(--muted)";
    }
  };

  const getSeatSecurityText = (security: string) => {
    switch (security) {
      case "strong": return "Secure";
      case "stable": return "Stable";
      case "uncertain": return "Uncertain";
      case "at_risk": return "At Risk";
      default: return security;
    }
  };

  const getF1PathwayText = (pathway: string) => {
    switch (pathway) {
      case "promising": return "Promising";
      case "possible": return "Possible";
      case "needs_work": return "Needs Work";
      case "unlikely": return "Unlikely";
      case "none": return "No F1 Link";
      case "open": return "Open Market";
      default: return pathway;
    }
  };

  return (
    <section className="panel" style={{ borderLeftColor: getTrustColor(academyStatus.trustLevel), borderLeftWidth: 3 }}>
      <h2>{academyStatus.academyName}</h2>
      <dl className="stat-grid">
        <div>
          <dt>Trust</dt>
          <dd style={{ color: getTrustColor(academyStatus.trustLevel) }}>
            {academyStatus.trust}% ({academyStatus.trustLevel})
          </dd>
        </div>
        <div>
          <dt>Expected Position</dt>
          <dd>P{academyStatus.expectedPosition} or better</dd>
        </div>
        <div>
          <dt>Seat Security</dt>
          <dd style={{ color: academyStatus.seatSecurity === "at_risk" ? "#ef4444" : undefined }}>
            {getSeatSecurityText(academyStatus.seatSecurity)}
          </dd>
        </div>
        <div>
          <dt>F1 Pathway</dt>
          <dd>{getF1PathwayText(academyStatus.f1Pathway)}</dd>
        </div>
      </dl>
      {academyStatus.warnings.length > 0 && (
        <div className="academy-warnings">
          {academyStatus.warnings.map((warning, i) => (
            <p key={i} className="error-text" style={{ margin: "4px 0" }}>
              ⚠ {warning}
            </p>
          ))}
        </div>
      )}
      {academyStatus.opportunities.length > 0 && (
        <div className="academy-opportunities">
          {academyStatus.opportunities.map((opportunity, i) => (
            <p key={i} style={{ margin: "4px 0", color: "#22c55e" }}>
              ✓ {opportunity}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

function RivalryStatusPanel({ rivalryStatus }: { rivalryStatus: RivalryStatusResponse }) {
  const getIntensityColor = (level: string) => {
    switch (level) {
      case "bitter": return "#ef4444";
      case "intense": return "#f97316";
      case "moderate": return "#eab308";
      case "mild": return "#84cc16";
      default: return "var(--muted)";
    }
  };

  const getRivalryTypeLabel = (type: string) => {
    switch (type) {
      case "teammate": return "Teammate";
      case "championship": return "Championship";
      case "promotional": return "F1 Seat";
      case "historical": return "Historical";
      case "personal": return "Personal";
      default: return type;
    }
  };

  return (
    <section className="panel">
      <h2>Rivalries</h2>
      <div className="rivalry-list">
        {rivalryStatus.rivalries.map((rivalry) => (
          <div
            key={rivalry.id}
            className="rivalry-card"
            style={{
              borderLeftColor: getIntensityColor(rivalry.intensityLevel),
              borderLeftWidth: 3,
              borderLeftStyle: "solid",
              padding: "12px",
              marginBottom: "8px",
              background: "var(--panel-bg)",
              borderRadius: "4px",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <strong>{rivalry.opponentName}</strong>
              <span
                style={{
                  color: getIntensityColor(rivalry.intensityLevel),
                  fontSize: "0.875rem",
                  textTransform: "capitalize",
                }}
              >
                {rivalry.intensityLevel}
              </span>
            </div>
            <div style={{ fontSize: "0.875rem", color: "var(--muted)", marginTop: "4px" }}>
              {getRivalryTypeLabel(rivalry.rivalryType)} Rivalry • Intensity: {rivalry.intensity}%
            </div>
            {rivalry.recentEvents.length > 0 && (
              <div style={{ fontSize: "0.75rem", color: "var(--muted)", marginTop: "8px" }}>
                Recent: {rivalry.recentEvents[0].description}
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function ActivityCard({
  activity,
  completed,
  onPerform,
  disabled,
}: {
  activity: Activity;
  completed: boolean;
  onPerform: () => void;
  disabled: boolean;
}) {
  return (
    <article className={`activity-card ${completed ? "completed" : ""}`}>
      <div className="activity-header">
        <h3>{activity.name}</h3>
        <span className="activity-duration">{activity.durationDays} day{activity.durationDays > 1 ? "s" : ""}</span>
      </div>
      <p>{activity.description}</p>
      <div className="activity-effects">
        {activity.baseEffects.fatigue !== 0 && (
          <span className={activity.baseEffects.fatigue > 0 ? "effect-negative" : "effect-positive"}>
            Fatigue {activity.baseEffects.fatigue > 0 ? "+" : ""}{activity.baseEffects.fatigue}
          </span>
        )}
        {activity.baseEffects.morale !== 0 && (
          <span className={activity.baseEffects.morale > 0 ? "effect-positive" : "effect-negative"}>
            Morale {activity.baseEffects.morale > 0 ? "+" : ""}{activity.baseEffects.morale}
          </span>
        )}
        {activity.baseEffects.form !== 0 && (
          <span className={activity.baseEffects.form > 0 ? "effect-positive" : "effect-negative"}>
            Form {activity.baseEffects.form > 0 ? "+" : ""}{activity.baseEffects.form}
          </span>
        )}
        {activity.baseEffects.academyTrust !== 0 && (
          <span className="effect-positive">
            Academy +{activity.baseEffects.academyTrust}
          </span>
        )}
      </div>
      {activity.riskChance > 0 && (
        <p className="activity-risk">
          {Math.round(activity.riskChance * 100)}% chance of setback
        </p>
      )}
      <button
        className="primary-button"
        onClick={onPerform}
        disabled={disabled || completed}
        style={{ marginTop: 12 }}
      >
        {completed ? "Completed" : disabled ? <Loader2 size={18} className="spin" /> : <Zap size={18} />}
        {completed ? "" : "Do Activity"}
      </button>
    </article>
  );
}
