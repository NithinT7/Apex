"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section, StatRow, Meter, DriverCell } from "@/components/Shell";
import type { Driver, SaveGame, NewsItem } from "@/lib/types";

export function CareerDashboardClient() {
  const { currentSave: save, loading, error } = useSave();

  const player = useMemo(
    () => save?.drivers.find((driver) => driver.id === save.playerDriverId) ?? null,
    [save]
  );

  const driverMap = useMemo(() => {
    const map = new Map<string, Driver>();
    for (const driver of save?.drivers ?? []) {
      map.set(driver.id, driver);
    }
    return map;
  }, [save]);

  const playerStanding = save?.standings.driverStandings.find(
    (standing) => standing.driverId === save.playerDriverId
  );

  const nextRound = save?.calendar.find((round) => !round.completed);
  const completedRounds = save?.calendar.filter((r) => r.completed).length ?? 0;
  const latestNews = save?.news.slice(-4).reverse() ?? [];

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading dashboard...</p>
      </div>
    );
  }

  if (!save) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>No Career Save</h2>
          <p>Create a driver to unlock the dashboard, standings, race weekends, and news feed.</p>
          <Link href="/create-driver" className="btn primary">
            Create Driver
          </Link>
        </div>
      </div>
    );
  }

  const initials = player
    ? player.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "??";

  const standingPosition = playerStanding
    ? save.standings.driverStandings.indexOf(playerStanding) + 1
    : 0;

  const heroStats = [
    {
      label: "Championship",
      value: `P${standingPosition}`,
      unit: `of ${save.standings.driverStandings.length}`,
      detail: `${playerStanding?.points ?? 0} pts`,
      mono: true,
    },
    {
      label: "Form",
      value: String(player?.currentForm ?? 50),
      unit: "/100",
      detail: player?.currentForm && player.currentForm >= 75 ? "Rising" : "Stable",
      mono: true,
    },
    {
      label: "Morale",
      value: String(player?.morale ?? 50),
      unit: "/100",
      detail: player?.morale && player.morale >= 75 ? "Confident" : "Steady",
      mono: true,
    },
    {
      label: "Fatigue",
      value: String(player?.fatigue ?? 0),
      unit: "/100",
      detail: player?.fatigue && player.fatigue <= 25 ? "Fresh" : "Managing",
      mono: true,
    },
  ];

  return (
    <div className="page">
      {/* Profile Hero */}
      <ProfileHero
        player={player}
        save={save}
        initials={initials}
        nextRound={nextRound}
      />

      {/* Error display */}
      {error && <p className="tag neg">{error}</p>}

      {/* Hero Stats */}
      <Section>
        <StatRow items={heroStats} />
      </Section>

      {/* Next Race + Standings */}
      <Section title="Up next">
        <div className="grid" style={{ gridTemplateColumns: "1.6fr 1fr" }}>
          <NextRaceCard
            nextRound={nextRound}
            completedRounds={completedRounds}
            totalRounds={save.calendar.length}
          />
          <TopStandingsCard
            standings={save.standings.driverStandings.slice(0, 5)}
            driverMap={driverMap}
            playerDriverId={save.playerDriverId}
            save={save}
          />
        </div>
      </Section>

      {/* News */}
      <Section title="Latest news" link="All news">
        <NewsBlock news={latestNews} />
      </Section>
    </div>
  );
}

function ProfileHero({
  player,
  save,
  initials,
  nextRound,
}: {
  player: Driver | null;
  save: SaveGame;
  initials: string;
  nextRound: typeof save.calendar[0] | undefined;
}) {
  const [imgError, setImgError] = useState(false);
  const teamName = save.teams.find((t) => t.id === player?.teamId)?.name ?? "No team";
  const imageUrl = player?.id ? `/drivers/faces/${player.id}.webp` : null;
  const showImage = imageUrl && !imgError;

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "auto 1fr auto",
        gap: 24,
        alignItems: "center",
        padding: "8px 0 32px",
        marginBottom: 24,
        borderBottom: "1px solid var(--line-soft)",
      }}
    >
      {/* Avatar */}
      <div
        style={{
          width: 84,
          height: 84,
          borderRadius: 50,
          background: "var(--bg-soft)",
          border: "1px solid var(--line)",
          display: "grid",
          placeItems: "center",
          position: "relative",
          overflow: "hidden",
          flexShrink: 0,
        }}
      >
        {showImage ? (
          <img
            src={imageUrl}
            alt={player?.name ?? "Driver"}
            onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
          />
        ) : (
          <span
            style={{
              fontSize: 30,
              fontWeight: 500,
              letterSpacing: "-0.02em",
              color: "var(--t1)",
            }}
          >
            {initials}
          </span>
        )}
      </div>

      {/* Identity */}
      <div className="col" style={{ gap: 4, minWidth: 0 }}>
        <div className="t3 small">
          Season {save.season} · {player?.series ?? "F2"}
        </div>
        <h1
          style={{
            margin: 0,
            fontSize: 26,
            fontWeight: 600,
            letterSpacing: "-0.02em",
            lineHeight: 1.15,
          }}
        >
          {player?.name ?? "Unknown Driver"}
        </h1>
        <div className="flex wrap" style={{ gap: 6, alignItems: "center", marginTop: 4 }}>
          <span className="tag" style={{ fontSize: 11 }}>
            {teamName}
          </span>
          {player?.nationality && (
            <span className="t3 small">{player.nationality} · Age {player.age}</span>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex" style={{ gap: 8, flexShrink: 0 }}>
        <Link href="/race-weekend" className="btn">
          Open weekend hub
        </Link>
        {nextRound && (
          <Link href="/race-weekend" className="btn primary">
            Continue to {nextRound.name} →
          </Link>
        )}
      </div>
    </div>
  );
}

function NextRaceCard({
  nextRound,
  completedRounds,
  totalRounds,
}: {
  nextRound: { name: string; country: string; roundNumber: number; trackId: string } | undefined;
  completedRounds: number;
  totalRounds: number;
}) {
  if (!nextRound) {
    return (
      <div className="card">
        <div className="card-title">Season Complete</div>
        <p className="t2">All rounds have been completed. Check the standings for final results.</p>
        <Link href="/standings" className="btn" style={{ marginTop: 16 }}>
          View Final Standings
        </Link>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="flex between" style={{ alignItems: "flex-start", marginBottom: 18 }}>
        <div>
          <div className="t3 small" style={{ marginBottom: 4 }}>
            Round {nextRound.roundNumber} of {totalRounds}
          </div>
          <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: "-0.01em" }}>
            {nextRound.name}
          </div>
          <div className="t2 small" style={{ marginTop: 2 }}>
            {nextRound.country}
          </div>
        </div>
        <span className="tag accent">Next</span>
      </div>

      <div className="grid cols-3 gap-sm" style={{ marginBottom: 18 }}>
        <div>
          <div className="t3 tiny" style={{ marginBottom: 4 }}>
            Track
          </div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{nextRound.trackId}</div>
        </div>
        <div>
          <div className="t3 tiny" style={{ marginBottom: 4 }}>
            Completed
          </div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>
            {completedRounds} / {totalRounds}
          </div>
        </div>
        <div>
          <div className="t3 tiny" style={{ marginBottom: 4 }}>
            Remaining
          </div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{totalRounds - completedRounds}</div>
        </div>
      </div>

      <div className="divider"></div>

      <div className="flex" style={{ justifyContent: "flex-end" }}>
        <Link href="/race-weekend" className="btn">
          Prepare for weekend →
        </Link>
      </div>
    </div>
  );
}

function TopStandingsCard({
  standings,
  driverMap,
  playerDriverId,
  save,
}: {
  standings: Array<{ driverId: string; points: number; wins: number }>;
  driverMap: Map<string, Driver>;
  playerDriverId: string | null;
  save: SaveGame;
}) {
  return (
    <div className="card tight" style={{ display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "16px 20px 4px" }}>
        <div className="card-title">Championship Standings</div>
        <div className="card-sub" style={{ marginTop: 2 }}>
          Top 5 · {save.calendar.filter((r) => r.completed).length} races completed
        </div>
      </div>
      <table className="tbl" style={{ margin: "8px 0" }}>
        <tbody>
          {standings.map((s, i) => {
            const driver = driverMap.get(s.driverId);
            const isPlayer = s.driverId === playerDriverId;
            return (
              <tr key={s.driverId} className={isPlayer ? "player" : ""}>
                <td className="mono" style={{ width: 40, fontWeight: 600 }}>
                  P{i + 1}
                </td>
                <td>
                  <DriverCell name={driver?.name ?? s.driverId} driverId={s.driverId} isPlayer={isPlayer} />
                </td>
                <td className="num" style={{ fontWeight: 500 }}>
                  {s.points}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div style={{ padding: "8px 20px 16px" }}>
        <Link href="/standings" className="btn ghost sm">
          Full standings →
        </Link>
      </div>
    </div>
  );
}

function NewsBlock({ news }: { news: NewsItem[] }) {
  if (news.length === 0) {
    return <p className="t2">No news yet. Complete a race weekend to generate news.</p>;
  }

  const categoryLabels: Record<string, string> = {
    race: "Race",
    media: "Media",
    academy: "Academy",
    rumor: "Rumor",
    contract: "Contract",
    incident: "Incident",
    system: "System",
    rivalry: "Rivalry",
  };

  const [lead, ...rest] = news;

  return (
    <div>
      <Link href="/news" className="dashboard-news-lead">
        <div className="news-meta">
          <span className="tag solid" style={{ fontSize: 10 }}>
            {lead.importance >= 4 ? "Breaking" : categoryLabels[lead.category] ?? lead.category}
          </span>
          <span>{lead.date}</span>
        </div>
        <div className="news-headline">{lead.headline}</div>
        <div className="news-summary">{lead.body}</div>
      </Link>
      {rest.map((n) => (
        <div key={n.id} className="news-row">
          <div className="news-thumb">{categoryLabels[n.category]?.toUpperCase() ?? "NEWS"}</div>
          <div className="news-body">
            <div className="news-meta">
              <span className="tag" style={{ fontSize: 10 }}>
                {categoryLabels[n.category] ?? n.category}
              </span>
              <span>{n.date}</span>
            </div>
            <div className="news-headline">{n.headline}</div>
            <div className="news-summary">{n.body}</div>
          </div>
        </div>
      ))}
    </div>
  );
}
