"use client";

import { Calendar, FastForward, Loader2, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import {
  getAvailableActivities,
  getPlayerStatus,
  getSave,
  getSaves,
  performActivity,
  skipToRaceWeek,
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
        const [acts, status] = await Promise.all([
          getAvailableActivities(saveId),
          getPlayerStatus(saveId),
        ]);
        setActivities(acts);
        setPlayerStatus(status);
      } else {
        setActivities(null);
        setPlayerStatus(null);
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
                {playerStatus.academyTrust !== null && (
                  <div>
                    <dt>Academy Trust</dt>
                    <dd>{playerStatus.academyTrust}%</dd>
                  </div>
                )}
                <div>
                  <dt>Reputation</dt>
                  <dd>{playerStatus.reputation}</dd>
                </div>
              </dl>
            </section>
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
