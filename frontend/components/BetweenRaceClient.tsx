"use client";

import { useEffect, useState, useCallback } from "react";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section, StatRow, Meter } from "@/components/Shell";
import {
  advanceSeason,
  getAcademyStatus,
  getAvailableActivities,
  getDevelopmentStatus,
  getF1Offers,
  getPlayerStatus,
  getRivalryStatus,
  getSeasonSummary,
  makeF1Decision,
  performActivity,
  spendDevelopmentPoint,
  simulateDriverMarket,
  skipToRaceWeek,
  type AcademyStatus,
  type F1OffersResponse,
  type RivalryStatusResponse,
  type SeasonSummary,
} from "@/lib/api";
import type {
  Activity,
  ActivityOutcome,
  AvailableActivities,
  DevelopmentStatus,
  PlayerStatus,
} from "@/lib/types";

export function BetweenRaceClient() {
  const { currentSave: save, selectedSaveId, loading, refreshSave } = useSave();
  const [error, setError] = useState<string | null>(null);

  // Activity state
  const [activities, setActivities] = useState<AvailableActivities | null>(null);
  const [playerStatus, setPlayerStatus] = useState<PlayerStatus | null>(null);
  const [academyStatus, setAcademyStatus] = useState<AcademyStatus | null>(null);
  const [rivalryStatus, setRivalryStatus] = useState<RivalryStatusResponse | null>(null);
  const [developmentStatus, setDevelopmentStatus] = useState<DevelopmentStatus | null>(null);
  const [seasonSummary, setSeasonSummary] = useState<SeasonSummary | null>(null);
  const [f1Offers, setF1Offers] = useState<F1OffersResponse | null>(null);
  const [lastOutcome, setLastOutcome] = useState<ActivityOutcome | null>(null);
  const [performing, setPerforming] = useState(false);

  const loadActivityData = useCallback(async () => {
    if (!selectedSaveId || !save) return;
    try {
      if (save.phase === "between_races") {
        const [acts, status, academy, rivalries, development] = await Promise.all([
          getAvailableActivities(selectedSaveId),
          getPlayerStatus(selectedSaveId),
          getAcademyStatus(selectedSaveId).catch(() => null),
          getRivalryStatus(selectedSaveId).catch(() => null),
          getDevelopmentStatus(selectedSaveId).catch(() => null),
        ]);
        setActivities(acts);
        setPlayerStatus(status);
        setAcademyStatus(academy);
        setRivalryStatus(rivalries);
        setDevelopmentStatus(development);
        setSeasonSummary(null);
      } else if (save.phase === "offseason") {
        const [summary, offers] = await Promise.all([
          getSeasonSummary(selectedSaveId).catch(() => null),
          getF1Offers(selectedSaveId).catch(() => null),
        ]);
        setSeasonSummary(summary);
        setF1Offers(offers);
        setActivities(null);
        setPlayerStatus(null);
        setAcademyStatus(null);
        setRivalryStatus(null);
        setDevelopmentStatus(null);
      }
    } catch {
      setError("Could not load activity data.");
    }
  }, [selectedSaveId, save?.phase]);

  useEffect(() => {
    loadActivityData();
  }, [loadActivityData]);

  async function handlePerformActivity(activityId: string) {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      const outcome = await performActivity(selectedSaveId, activityId);
      setLastOutcome(outcome);
      await refreshSave();
      await loadActivityData();
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
      await refreshSave();
      await loadActivityData();
    } catch {
      setError("Failed to skip to race week.");
    } finally {
      setPerforming(false);
    }
  }

  async function handleSpendDevelopment(skillId: string) {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      await spendDevelopmentPoint(selectedSaveId, skillId);
      await refreshSave();
      await loadActivityData();
    } catch {
      setError("Failed to spend development point.");
    } finally {
      setPerforming(false);
    }
  }

  async function handleAdvanceSeason() {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      await simulateDriverMarket(selectedSaveId);
      await advanceSeason(selectedSaveId);
      await refreshSave();
      await loadActivityData();
    } catch {
      setError("Failed to advance to next season.");
    } finally {
      setPerforming(false);
    }
  }

  async function handleF1Decision(accept: boolean, teamId?: string) {
    if (!selectedSaveId) return;
    setPerforming(true);
    setError(null);
    try {
      await makeF1Decision(selectedSaveId, accept, teamId);
      await refreshSave();
      await loadActivityData();
    } catch {
      setError("Failed to process F1 decision.");
    } finally {
      setPerforming(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading...</p>
      </div>
    );
  }

  if (!save) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>No Career Save</h2>
          <p>Create a driver first, then return here after completing a race weekend.</p>
        </div>
      </div>
    );
  }

  const nextRound = save.calendar.find((r) => !r.completed);

  return (
    <div className="page">
      <PageHead
        meta="Career"
        title="Between Races"
        sub={`Phase: ${save.phase} · ${activities?.daysUntilNextRace ?? "?"} days to race`}
      />

      {error && <p className="tag neg" style={{ marginBottom: 20 }}>{error}</p>}

      {save.phase === "offseason" && seasonSummary ? (
        <SeasonSummaryView
          summary={seasonSummary}
          f1Offers={f1Offers}
          onAdvance={handleAdvanceSeason}
          onF1Decision={handleF1Decision}
          advancing={performing}
        />
      ) : save.phase !== "between_races" ? (
        <Section>
          <div className="card">
            <div className="card-title">Not Between Races</div>
            <p className="t2" style={{ marginTop: 8 }}>
              Activities are only available during the between-races phase.
              Current phase: <strong>{save.phase}</strong>
            </p>
            {save.phase === "race_week" && (
              <p className="t2">Head to the Race Weekend page to run the next race.</p>
            )}
          </div>
        </Section>
      ) : (
        <>
          {/* Player Status */}
          {playerStatus && (
            <Section>
              <StatRow
                items={[
                  {
                    label: "Fatigue",
                    value: String(playerStatus.fatigue),
                    unit: "%",
                    mono: true,
                    color: playerStatus.fatigue > 60 ? "var(--neg)" : undefined,
                  },
                  { label: "Morale", value: String(playerStatus.morale), unit: "%", mono: true },
                  { label: "Form", value: String(playerStatus.form), unit: "%", mono: true },
                  {
                    label: "Days to Race",
                    value: String(playerStatus.daysUntilRace),
                    mono: true,
                    detail: `Reputation: ${playerStatus.reputation}`,
                  },
                ]}
              />
            </Section>
          )}

          {/* Last Activity Outcome */}
          {lastOutcome && (
            <Section>
              <div className={`decision ${lastOutcome.success ? "pos" : "neg"}`} style={{ borderColor: lastOutcome.success ? "var(--pos)" : "var(--neg)" }}>
                <div className="decision-title">{lastOutcome.success ? "Success" : "Setback"}</div>
                <h3>{lastOutcome.activityName}</h3>
                <div className="decision-body">{lastOutcome.narrative}</div>
                <div className="flex" style={{ gap: 12 }}>
                  {lastOutcome.effectsApplied.fatigue !== 0 && (
                    <span className={`tag ${lastOutcome.effectsApplied.fatigue < 0 ? "pos" : "neg"}`}>
                      Fatigue {lastOutcome.effectsApplied.fatigue > 0 ? "+" : ""}{lastOutcome.effectsApplied.fatigue}
                    </span>
                  )}
                  {lastOutcome.effectsApplied.morale !== 0 && (
                    <span className={`tag ${lastOutcome.effectsApplied.morale > 0 ? "pos" : "neg"}`}>
                      Morale {lastOutcome.effectsApplied.morale > 0 ? "+" : ""}{lastOutcome.effectsApplied.morale}
                    </span>
                  )}
                  {lastOutcome.effectsApplied.form !== 0 && (
                    <span className={`tag ${lastOutcome.effectsApplied.form > 0 ? "pos" : "neg"}`}>
                      Form {lastOutcome.effectsApplied.form > 0 ? "+" : ""}{lastOutcome.effectsApplied.form}
                    </span>
                  )}
                </div>
              </div>
            </Section>
          )}

          {/* Development */}
          {developmentStatus && (
            <DevelopmentSection
              development={developmentStatus}
              onSpend={handleSpendDevelopment}
              disabled={performing}
            />
          )}

          {/* Academy Status */}
          {academyStatus && academyStatus.trust !== null && (
            <AcademySection academyStatus={academyStatus} />
          )}

          {/* Rivalries */}
          {rivalryStatus && rivalryStatus.rivalries.length > 0 && (
            <RivalrySection rivalryStatus={rivalryStatus} />
          )}

          {/* Next Race / Skip */}
          {nextRound && (
            <Section title="Next Race">
              <div className="card">
                <div className="flex between center">
                  <div>
                    <div className="t3 tiny">Round {nextRound.roundNumber}</div>
                    <div style={{ fontSize: 18, fontWeight: 600 }}>{nextRound.name}</div>
                    <div className="t2 small">{activities?.daysUntilNextRace} days away</div>
                  </div>
                  <button className="btn primary" onClick={handleSkipToRace} disabled={performing}>
                    Skip to Race Week →
                  </button>
                </div>
              </div>
            </Section>
          )}

          {/* Activities */}
          <Section title="Available Activities">
            {activities && activities.activities.length > 0 ? (
              <div className="grid cols-3 gap-sm">
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
              <p className="t2">No activities available. You may need to skip to race week.</p>
            )}
          </Section>
        </>
      )}
    </div>
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
    <div className="card" style={{ opacity: completed ? 0.6 : 1 }}>
      <div className="flex between center" style={{ marginBottom: 8 }}>
        <div className="card-title">{activity.name}</div>
        <span className="tag">{activity.durationDays}d</span>
      </div>
      <p className="t2 small" style={{ marginBottom: 12 }}>{activity.description}</p>
      <div className="flex wrap" style={{ gap: 6, marginBottom: 12 }}>
        {activity.baseEffects.fatigue !== 0 && (
          <span className={`tag ${activity.baseEffects.fatigue < 0 ? "pos" : "neg"}`} style={{ fontSize: 10 }}>
            Fatigue {activity.baseEffects.fatigue > 0 ? "+" : ""}{activity.baseEffects.fatigue}
          </span>
        )}
        {activity.baseEffects.morale !== 0 && (
          <span className={`tag ${activity.baseEffects.morale > 0 ? "pos" : "neg"}`} style={{ fontSize: 10 }}>
            Morale {activity.baseEffects.morale > 0 ? "+" : ""}{activity.baseEffects.morale}
          </span>
        )}
        {activity.baseEffects.form !== 0 && (
          <span className={`tag ${activity.baseEffects.form > 0 ? "pos" : "neg"}`} style={{ fontSize: 10 }}>
            Form {activity.baseEffects.form > 0 ? "+" : ""}{activity.baseEffects.form}
          </span>
        )}
      </div>
      {activity.riskChance > 0 && (
        <p className="t3 tiny" style={{ marginBottom: 8 }}>
          {Math.round(activity.riskChance * 100)}% chance of setback
        </p>
      )}
      <button className="btn primary" onClick={onPerform} disabled={disabled || completed} style={{ width: "100%" }}>
        {completed ? "Completed" : "Do Activity"}
      </button>
    </div>
  );
}

function DevelopmentSection({
  development,
  onSpend,
  disabled,
}: {
  development: DevelopmentStatus;
  onSpend: (skillId: string) => void;
  disabled: boolean;
}) {
  const branches = Array.from(new Set(development.skills.map((skill) => skill.branch)));

  return (
    <Section
      title="Driver Development"
      link={development.availablePoints > 0 ? `${development.availablePoints} pts available` : undefined}
    >
      <div className="grid cols-2 gap-sm">
        {branches.map((branch) => (
          <div key={branch} className="card">
            <div className="card-title" style={{ marginBottom: 12 }}>{branch}</div>
            {development.skills
              .filter((skill) => skill.branch === branch)
              .map((skill) => {
                const rank = development.spentPoints[skill.id] ?? 0;
                const canBuy = development.availablePoints >= skill.cost && rank < skill.maxRank;
                return (
                  <div key={skill.id} className="flex between center" style={{ padding: "8px 0", borderBottom: "1px solid var(--line-soft)" }}>
                    <div>
                      <div style={{ fontWeight: 500, fontSize: 13 }}>{skill.name}</div>
                      <div className="t3 tiny">Rank {rank}/{skill.maxRank}</div>
                    </div>
                    <button
                      className="btn sm"
                      disabled={disabled || !canBuy}
                      onClick={() => onSpend(skill.id)}
                    >
                      +1 ({skill.cost}pts)
                    </button>
                  </div>
                );
              })}
          </div>
        ))}
      </div>
    </Section>
  );
}

function AcademySection({ academyStatus }: { academyStatus: AcademyStatus }) {
  const getTrustTone = (level: string | null) => {
    switch (level) {
      case "excellent": return "pos";
      case "good": return "pos";
      case "neutral": return "warn";
      case "warning": return "warn";
      case "critical": return "neg";
      default: return "";
    }
  };

  return (
    <Section title="Academy Status">
      <div className="card">
        <div className="flex between center" style={{ marginBottom: 16 }}>
          <div className="card-title">{academyStatus.academyName}</div>
          <span className={`tag ${getTrustTone(academyStatus.trustLevel)}`}>
            {academyStatus.trust}% Trust
          </span>
        </div>
        <div className="grid cols-3 gap-sm">
          <div>
            <div className="t3 tiny">Expected Position</div>
            <div style={{ fontWeight: 500 }}>P{academyStatus.expectedPosition} or better</div>
          </div>
          <div>
            <div className="t3 tiny">Seat Security</div>
            <div style={{ fontWeight: 500, color: academyStatus.seatSecurity === "at_risk" ? "var(--neg)" : undefined }}>
              {academyStatus.seatSecurity}
            </div>
          </div>
          <div>
            <div className="t3 tiny">F1 Pathway</div>
            <div style={{ fontWeight: 500 }}>{academyStatus.f1Pathway}</div>
          </div>
        </div>
        {academyStatus.warnings.length > 0 && (
          <div style={{ marginTop: 16 }}>
            {academyStatus.warnings.map((warning, i) => (
              <p key={i} className="tag neg" style={{ display: "block", marginBottom: 4 }}>
                {warning}
              </p>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function RivalrySection({ rivalryStatus }: { rivalryStatus: RivalryStatusResponse }) {
  const getIntensityTone = (level: string) => {
    switch (level) {
      case "bitter": return "neg";
      case "intense": return "warn";
      case "moderate": return "info";
      default: return "";
    }
  };

  return (
    <Section title="Rivalries">
      <div className="grid cols-2 gap-sm">
        {rivalryStatus.rivalries.map((rivalry) => (
          <div key={rivalry.id} className="card">
            <div className="flex between center" style={{ marginBottom: 8 }}>
              <div className="card-title">{rivalry.opponentName}</div>
              <span className={`tag ${getIntensityTone(rivalry.intensityLevel)}`}>
                {rivalry.intensityLevel}
              </span>
            </div>
            <div className="t2 small">
              {rivalry.rivalryType} rivalry · Intensity: {rivalry.intensity}%
            </div>
            {rivalry.recentEvents.length > 0 && (
              <div className="t3 tiny" style={{ marginTop: 8 }}>
                Recent: {rivalry.recentEvents[0].description}
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function SeasonSummaryView({
  summary,
  f1Offers,
  onAdvance,
  onF1Decision,
  advancing,
}: {
  summary: SeasonSummary;
  f1Offers: F1OffersResponse | null;
  onAdvance: () => void;
  onF1Decision: (accept: boolean, teamId?: string) => void;
  advancing: boolean;
}) {
  return (
    <>
      <Section>
        <div className="card" style={{ textAlign: "center", borderColor: "var(--warn)" }}>
          <div style={{ fontSize: 32, marginBottom: 16 }}>&#127942;</div>
          <div style={{ fontSize: 24, fontWeight: 600 }}>Season {summary.season} Complete</div>
          <p className="t1" style={{ fontSize: 18, marginTop: 8 }}>
            <strong>{summary.champion.name}</strong> is the F2 Champion
          </p>
          <p className="t3">{summary.champion.points} points</p>
        </div>
      </Section>

      {summary.playerSummary && (
        <Section title="Your Season">
          <div className="card">
            <div style={{ fontSize: 18, fontWeight: 600, marginBottom: 16 }}>{summary.playerSummary.headline}</div>
            <StatRow
              items={[
                { label: "Position", value: `P${summary.playerSummary.championshipPosition}`, mono: true },
                { label: "Points", value: String(summary.playerSummary.points), mono: true },
                { label: "Wins", value: String(summary.playerSummary.wins), mono: true },
                { label: "Podiums", value: String(summary.playerSummary.podiums), mono: true },
              ]}
            />
          </div>
        </Section>
      )}

      {f1Offers && f1Offers.hasOffers && (
        <Section title="F1 Opportunities">
          <div className="decision" style={{ marginBottom: 20 }}>
            <div className="decision-title">F1 Interest</div>
            <h3>Your F2 performance has attracted F1 interest!</h3>
            <div className="decision-body">
              {f1Offers.offers.map((offer) => (
                <div
                  key={offer.teamId}
                  className="decision-option"
                  onClick={() => onF1Decision(true, offer.teamId)}
                  style={{ cursor: advancing ? "not-allowed" : "pointer" }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <img
                      src={`/teams/${offer.teamId}.webp`}
                      alt={offer.teamName}
                      style={{ width: 32, height: 32, objectFit: "contain" }}
                      onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
                    />
                    <div className="lbl">
                      <strong>{offer.teamName}</strong>
                      <span className="t2 small" style={{ display: "block" }}>
                        Car Performance: {offer.carPerformance}
                        {offer.isAcademyTeam && " · Your Academy Team"}
                      </span>
                    </div>
                  </div>
                  <span className="tag pos">{offer.likelihood}% chance</span>
                </div>
              ))}
            </div>
            <button className="btn" onClick={() => onF1Decision(false)} disabled={advancing}>
              Stay in F2 Another Season
            </button>
          </div>
        </Section>
      )}

      {(!f1Offers || !f1Offers.hasOffers) && (
        <Section>
          <div className="card" style={{ textAlign: "center" }}>
            <button className="btn primary" onClick={onAdvance} disabled={advancing}>
              {advancing ? "Advancing..." : "Start Next Season →"}
            </button>
          </div>
        </Section>
      )}
    </>
  );
}
