"use client";

import { useMemo, useState } from "react";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section, DriverCell } from "@/components/Shell";
import type { ChampionshipState, Driver, Team, WeekendResult } from "@/lib/types";

type ViewMode = "drivers" | "teams";
type SeriesMode = "F2" | "F1";

export function StandingsClient() {
  const { currentSave: save, loading, error } = useSave();
  const [viewMode, setViewMode] = useState<ViewMode>("drivers");
  const [seriesMode, setSeriesMode] = useState<SeriesMode>("F2");

  const driverMap = useMemo(() => {
    const map = new Map<string, Driver>();
    for (const driver of save?.drivers ?? []) {
      map.set(driver.id, driver);
    }
    return map;
  }, [save]);

  const teamMap = useMemo(() => {
    const map = new Map<string, Team>();
    for (const team of save?.teams ?? []) {
      map.set(team.id, team);
    }
    return map;
  }, [save]);

  const activeStandings = useMemo<ChampionshipState | null>(() => {
    if (!save) return null;
    return seriesMode === "F1" ? save.f1Standings ?? null : save.standings;
  }, [save, seriesMode]);

  const teamStandings = useMemo(() => {
    if (!save || !activeStandings) return [];
    const teamPoints = new Map<string, { points: number; wins: number; team: Team }>();

    for (const standing of activeStandings.driverStandings) {
      const driver = driverMap.get(standing.driverId);
      if (!driver?.teamId || driver.series !== seriesMode) continue;
      const team = teamMap.get(driver.teamId);
      if (!team) continue;

      const existing = teamPoints.get(driver.teamId);
      if (existing) {
        existing.points += standing.points;
        existing.wins += standing.wins;
      } else {
        teamPoints.set(driver.teamId, {
          points: standing.points,
          wins: standing.wins,
          team,
        });
      }
    }

    return Array.from(teamPoints.values()).sort((a, b) => b.points - a.points);
  }, [save, activeStandings, driverMap, teamMap, seriesMode]);

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading standings...</p>
      </div>
    );
  }

  if (!save) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>No Career Save</h2>
          <p>Create a career save to see standings.</p>
        </div>
      </div>
    );
  }

  const completedRounds =
    seriesMode === "F1"
      ? save.f1WeekendResults?.length ?? 0
      : save.calendar.filter((r) => r.completed).length;
  const totalRounds = seriesMode === "F1" ? "parallel" : `${save.calendar.length}`;
  const driverStandings = activeStandings?.driverStandings ?? [];

  return (
    <div className="page">
      <PageHead
        meta="Championship"
        title={`${save.season} ${seriesMode} Standings`}
        sub={
          seriesMode === "F1"
            ? `${completedRounds} F1 weekends completed in parallel`
            : `${completedRounds} of ${totalRounds} rounds completed`
        }
      />

      <div className="page-tabs">
        <div
          className={`page-tab ${seriesMode === "F2" ? "active" : ""}`}
          onClick={() => setSeriesMode("F2")}
        >
          F2
          <span className="count">{save.standings.driverStandings.length}</span>
        </div>
        <div
          className={`page-tab ${seriesMode === "F1" ? "active" : ""}`}
          onClick={() => setSeriesMode("F1")}
        >
          F1
          <span className="count">{save.f1WeekendResults?.length ?? 0}</span>
        </div>
      </div>

      {/* View toggle tabs */}
      <div className="page-tabs">
        <div
          className={`page-tab ${viewMode === "drivers" ? "active" : ""}`}
          onClick={() => setViewMode("drivers")}
        >
          Drivers
          <span className="count">{driverStandings.length}</span>
        </div>
        <div
          className={`page-tab ${viewMode === "teams" ? "active" : ""}`}
          onClick={() => setViewMode("teams")}
        >
          Constructors
          <span className="count">{teamStandings.length}</span>
        </div>
      </div>

      {error && <p className="tag neg">{error}</p>}

      {viewMode === "drivers" ? (
        <Section>
          {driverStandings.length > 0 ? (
            <DriversTable
              standings={driverStandings}
              driverMap={driverMap}
              teamMap={teamMap}
              playerDriverId={seriesMode === "F2" ? save.playerDriverId : null}
            />
          ) : (
            <p className="t2">F1 standings will populate after the first F1 Grand Prix.</p>
          )}
        </Section>
      ) : (
        <Section>
          <TeamsTable standings={teamStandings} />
        </Section>
      )}

      {seriesMode === "F1" && (
        <Section title="Recent F1 Results">
          <RecentF1Results results={save.f1WeekendResults ?? []} driverMap={driverMap} teamMap={teamMap} />
        </Section>
      )}
    </div>
  );
}

function DriversTable({
  standings,
  driverMap,
  teamMap,
  playerDriverId,
}: {
  standings: Array<{
    driverId: string;
    points: number;
    wins: number;
    podiums: number;
    poles: number;
    fastestLaps: number;
    dnfs: number;
  }>;
  driverMap: Map<string, Driver>;
  teamMap: Map<string, Team>;
  playerDriverId: string | null;
}) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th style={{ width: 50 }}>Pos</th>
          <th>Driver</th>
          <th>Team</th>
          <th className="num">Pts</th>
          <th className="num">Wins</th>
          <th className="num">Podiums</th>
          <th className="num">Poles</th>
          <th className="num">FL</th>
          <th className="num">DNF</th>
        </tr>
      </thead>
      <tbody>
        {standings.map((s, i) => {
          const driver = driverMap.get(s.driverId);
          const team = driver?.teamId ? teamMap.get(driver.teamId) : undefined;
          const isPlayer = s.driverId === playerDriverId;

          return (
            <tr key={s.driverId} className={isPlayer ? "player" : ""}>
              <td className="mono strong">P{i + 1}</td>
              <td>
                <DriverCell name={driver?.name ?? s.driverId} driverId={s.driverId} isPlayer={isPlayer} />
              </td>
              <td className="t2">{team?.name ?? "—"}</td>
              <td className="num strong">{s.points}</td>
              <td className="num">{s.wins}</td>
              <td className="num">{s.podiums}</td>
              <td className="num">{s.poles}</td>
              <td className="num">{s.fastestLaps}</td>
              <td className="num" style={{ color: s.dnfs > 0 ? "var(--neg)" : undefined }}>
                {s.dnfs}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function RecentF1Results({
  results,
  driverMap,
  teamMap,
}: {
  results: WeekendResult[];
  driverMap: Map<string, Driver>;
  teamMap: Map<string, Team>;
}) {
  const recent = results.slice(-6).reverse();

  if (recent.length === 0) {
    return <p className="t2">No F1 race has been completed yet.</p>;
  }

  return (
    <table className="tbl">
      <thead>
        <tr>
          <th>Round</th>
          <th>Race</th>
          <th>Winner</th>
          <th>Team</th>
          <th className="num">Laps</th>
          <th className="num">DNF</th>
        </tr>
      </thead>
      <tbody>
        {recent.map((weekend) => {
          const winnerId = weekend.feature.classification[0]?.driverId;
          const winner = winnerId ? driverMap.get(winnerId) : undefined;
          const team = winner?.teamId ? teamMap.get(winner.teamId) : undefined;

          return (
            <tr key={weekend.roundId}>
              <td className="mono strong">{formatRoundId(weekend.roundId)}</td>
              <td>{weekend.headline}</td>
              <td>{winner?.name ?? "TBD"}</td>
              <td className="t2">{team?.name ?? "—"}</td>
              <td className="num">{weekend.feature.totalLaps}</td>
              <td className="num">{weekend.feature.dnfs.length}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function formatRoundId(roundId: string) {
  const match = roundId.match(/round_(\d+)/);
  return match ? `R${Number(match[1])}` : roundId;
}

function TeamCell({ teamId, name }: { teamId: string; name: string }) {
  const [imgError, setImgError] = useState(false);
  const imageUrl = `/teams/${teamId}.webp`;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      {!imgError ? (
        <img
          src={imageUrl}
          alt={name}
          onError={() => setImgError(true)}
          style={{ width: 24, height: 24, objectFit: "contain" }}
        />
      ) : (
        <span style={{ width: 24, height: 24, background: "var(--bg2)", borderRadius: 4, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600 }}>
          {name.slice(0, 2).toUpperCase()}
        </span>
      )}
      <span style={{ fontWeight: 500 }}>{name}</span>
    </div>
  );
}

function TeamsTable({
  standings,
}: {
  standings: Array<{ points: number; wins: number; team: Team }>;
}) {
  return (
    <table className="tbl">
      <thead>
        <tr>
          <th style={{ width: 50 }}>Pos</th>
          <th>Team</th>
          <th>Country</th>
          <th className="num">Pts</th>
          <th className="num">Wins</th>
          <th className="num">Car Perf</th>
        </tr>
      </thead>
      <tbody>
        {standings.map((s, i) => (
          <tr key={s.team.id}>
            <td className="mono strong">P{i + 1}</td>
            <td><TeamCell teamId={s.team.id} name={s.team.name} /></td>
            <td className="t2">{s.team.country}</td>
            <td className="num strong">{s.points}</td>
            <td className="num">{s.wins}</td>
            <td className="num">{s.team.carPerformance}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
