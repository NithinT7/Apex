"use client";

import { Calendar, FastForward, Loader2, Trophy, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import {
  advanceSeason,
  getAcademyStatus,
  getAvailableActivities,
  getPlayerStatus,
  getRivalryStatus,
  getSave,
  getSaves,
  getSeasonSummary,
  performActivity,
  skipToRaceWeek,
  type AcademyStatus,
  type RivalryStatusResponse,
  type SeasonSummary,
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
  const [seasonSummary, setSeasonSummary] = useState<SeasonSummary | null>(null);
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
        setSeasonSummary(null);
      } else if (loadedSave.phase === "offseason") {
        const summary = await getSeasonSummary(saveId).catch(() => null);
        setSeasonSummary(summary);
        setActivities(null);
        setPlayerStatus(null);
        setAcademyStatus(null);
        setRivalryStatus(null);
      } else {
        setActivities(null);
        setPlayerStatus(null);
        setAcademyStatus(null);
        setRivalryStatus(null);
        setSeasonSummary(null);
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

  async function handleAdvanceSeason() {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      await advanceSeason(selectedSaveId);
      await loadSaveData(selectedSaveId);
    } catch {
      setError("Failed to advance to next season.");
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

      {save?.phase === "offseason" && seasonSummary ? (
        <SeasonSummaryPanel
          summary={seasonSummary}
          onAdvance={handleAdvanceSeason}
          advancing={performing}
        />
      ) : save?.phase !== "between_races" ? (
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

function SeasonSummaryPanel({
  summary,
  onAdvance,
  advancing,
}: {
  summary: SeasonSummary;
  onAdvance: () => void;
  advancing: boolean;
}) {
  const getRatingColor = (rating: string) => {
    switch (rating) {
      case "champion": return "#ffd700";
      case "excellent": return "#22c55e";
      case "good": return "#84cc16";
      case "moderate": return "#eab308";
      case "poor": return "#ef4444";
      default: return "var(--muted)";
    }
  };

  return (
    <>
      {/* Season Champion */}
      <section className="panel" style={{ textAlign: "center", borderColor: "#ffd700", borderWidth: 2 }}>
        <Trophy size={48} style={{ color: "#ffd700", marginBottom: 16 }} />
        <h2>Season {summary.season} Complete</h2>
        <p className="lede" style={{ fontSize: "1.5rem", marginTop: 8 }}>
          <strong>{summary.champion.name}</strong> is the F2 Champion
        </p>
        <p style={{ color: "var(--muted)" }}>{summary.champion.points} points</p>
      </section>

      {/* Player Summary */}
      {summary.playerSummary && (
        <section
          className="panel"
          style={{
            borderLeftColor: getRatingColor(summary.playerSummary.rating),
            borderLeftWidth: 4,
          }}
        >
          <h2>Your Season</h2>
          <p className="lede">{summary.playerSummary.headline}</p>
          <dl className="stat-grid" style={{ marginTop: 16 }}>
            <div>
              <dt>Championship</dt>
              <dd style={{ fontSize: "1.5rem" }}>P{summary.playerSummary.championshipPosition}</dd>
            </div>
            <div>
              <dt>Points</dt>
              <dd>{summary.playerSummary.points}</dd>
            </div>
            <div>
              <dt>Wins</dt>
              <dd>{summary.playerSummary.wins}</dd>
            </div>
            <div>
              <dt>Podiums</dt>
              <dd>{summary.playerSummary.podiums}</dd>
            </div>
            <div>
              <dt>Poles</dt>
              <dd>{summary.playerSummary.poles}</dd>
            </div>
            <div>
              <dt>Fastest Laps</dt>
              <dd>{summary.playerSummary.fastestLaps}</dd>
            </div>
            <div>
              <dt>DNFs</dt>
              <dd>{summary.playerSummary.dnfs}</dd>
            </div>
            <div>
              <dt>Points Finishes</dt>
              <dd>{summary.playerSummary.pointsFinishes}/{summary.playerSummary.totalRaces}</dd>
            </div>
          </dl>
        </section>
      )}

      {/* Final Standings */}
      <section className="panel">
        <h2>Final Championship Standings</h2>
        <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
          <thead>
            <tr style={{ textAlign: "left", borderBottom: "1px solid var(--border)" }}>
              <th style={{ padding: "8px 0" }}>Pos</th>
              <th style={{ padding: "8px 0" }}>Driver</th>
              <th style={{ padding: "8px 0", textAlign: "right" }}>Pts</th>
              <th style={{ padding: "8px 0", textAlign: "right" }}>Wins</th>
              <th style={{ padding: "8px 0", textAlign: "right" }}>Podiums</th>
            </tr>
          </thead>
          <tbody>
            {summary.finalStandings.slice(0, 10).map((entry) => (
              <tr
                key={entry.driverId}
                style={{
                  borderBottom: "1px solid var(--border)",
                  backgroundColor:
                    entry.driverId === summary.playerSummary?.driverId
                      ? "rgba(255, 255, 255, 0.05)"
                      : undefined,
                }}
              >
                <td style={{ padding: "8px 0", fontWeight: entry.position <= 3 ? "bold" : "normal" }}>
                  {entry.position}
                </td>
                <td style={{ padding: "8px 0" }}>
                  {entry.driverName}
                  {entry.position === 1 && " \u{1F3C6}"}
                </td>
                <td style={{ padding: "8px 0", textAlign: "right" }}>{entry.points}</td>
                <td style={{ padding: "8px 0", textAlign: "right" }}>{entry.wins}</td>
                <td style={{ padding: "8px 0", textAlign: "right" }}>{entry.podiums}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Team Champion */}
      <section className="panel">
        <h3>Teams' Champion: {summary.teamChampion.name}</h3>
        <p style={{ color: "var(--muted)" }}>{summary.teamChampion.points} points</p>
      </section>

      {/* Advance Button */}
      <section className="panel" style={{ textAlign: "center" }}>
        <button
          className="primary-button"
          onClick={onAdvance}
          disabled={advancing}
          style={{ padding: "12px 24px", fontSize: "1.1rem" }}
        >
          {advancing ? (
            <Loader2 size={20} className="spin" />
          ) : (
            <FastForward size={20} />
          )}
          {advancing ? "Advancing..." : "Start Next Season"}
        </button>
      </section>
    </>
  );
}
