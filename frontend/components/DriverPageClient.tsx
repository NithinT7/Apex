"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useSave } from "@/components/SaveProvider";
import { DriverCell, PageHead, Section, StatRow } from "@/components/Shell";
import { getDevelopmentStatus, spendDevelopmentPoint } from "@/lib/api";
import type {
  ChampionshipEntry,
  Contract,
  DevelopmentStatus,
  Driver,
  DriverAttributes,
  SaveGame,
  SkillNode,
  WeekendResult,
} from "@/lib/types";

const attributeLabels: Record<keyof DriverAttributes, string> = {
  pace: "Pace",
  qualifying: "Qualifying",
  racecraft: "Racecraft",
  tireManagement: "Tyre Management",
  wetWeather: "Wet Weather",
  consistency: "Consistency",
  starts: "Starts",
  awareness: "Awareness",
  adaptability: "Adaptability",
  technicalFeedback: "Technical Feedback",
  pressure: "Pressure",
  confidence: "Confidence",
  composure: "Composure",
  aggression: "Aggression",
  discipline: "Discipline",
  focus: "Focus",
  reputation: "Reputation",
  marketability: "Marketability",
  sponsorValue: "Sponsor Value",
};

const attributeCategories: Record<string, Array<keyof DriverAttributes>> = {
  Performance: ["pace", "qualifying", "racecraft", "tireManagement", "wetWeather"],
  Execution: ["consistency", "starts", "pressure", "composure", "focus"],
  Intelligence: ["awareness", "adaptability", "technicalFeedback", "discipline"],
  Profile: ["confidence", "aggression", "reputation", "marketability", "sponsorValue"],
};

const skillLabels: Record<string, string> = {
  raw_pace_1: "Raw Pace",
  qualifying_1: "One-Lap Focus",
  racecraft_1: "Racecraft",
  starts_1: "Launch Control",
  tyres_1: "Tyre Management",
  consistency_1: "Consistency",
  pressure_1: "Pressure Handling",
  wet_1: "Wet Weather",
  feedback_1: "Technical Feedback",
  marketability_1: "Marketability",
};

type RecentResult = {
  id: string;
  roundName: string;
  session: "Sprint" | "Feature";
  position: number | null;
  points: number;
  status: string;
};

export function DriverPageClient() {
  const { currentSave: save, selectedSaveId, loading, error, refreshSave } = useSave();
  const [selectedDriverId, setSelectedDriverId] = useState<string | null>(null);
  const [developmentStatus, setDevelopmentStatus] = useState<DevelopmentStatus | null>(null);
  const [developmentError, setDevelopmentError] = useState<string | null>(null);
  const [spendingSkillId, setSpendingSkillId] = useState<string | null>(null);

  const player = useMemo(
    () => save?.drivers.find((driver) => driver.id === save.playerDriverId) ?? null,
    [save]
  );

  const selectedDriver = useMemo(
    () => save?.drivers.find((driver) => driver.id === selectedDriverId) ?? null,
    [save, selectedDriverId]
  );

  const driverRows = useMemo(() => buildDriverRows(save), [save]);
  const recentResults = useMemo(() => buildRecentResults(save), [save]);

  useEffect(() => {
    if (!selectedSaveId || !save?.playerDriverId) {
      setDevelopmentStatus(null);
      return;
    }

    getDevelopmentStatus(selectedSaveId)
      .then((status) => {
        setDevelopmentStatus(status);
        setDevelopmentError(null);
      })
      .catch(() => setDevelopmentError("Could not load development upgrades."));
  }, [selectedSaveId, save?.playerDriverId, save?.development.availablePoints]);

  async function handleSpendDevelopment(skillId: string) {
    if (!selectedSaveId) return;
    setSpendingSkillId(skillId);
    setDevelopmentError(null);
    try {
      await spendDevelopmentPoint(selectedSaveId, skillId);
      await refreshSave();
      const status = await getDevelopmentStatus(selectedSaveId);
      setDevelopmentStatus(status);
    } catch {
      setDevelopmentError("Could not spend that development point.");
    } finally {
      setSpendingSkillId(null);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading driver profile...</p>
      </div>
    );
  }

  if (!save || !player) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>No Career</h2>
          <p>Create a driver to view driver profiles.</p>
          <Link href="/create-driver" className="btn primary">
            Create Driver
          </Link>
        </div>
      </div>
    );
  }

  const playerStanding = save.standings.driverStandings.find(
    (standing) => standing.driverId === player.id
  );
  const playerPosition = playerStanding
    ? save.standings.driverStandings.findIndex((standing) => standing.driverId === player.id) + 1
    : null;
  const playerTeam = getTeamName(save, player.teamId);
  const contract = save.contracts.find((item) => item.driverId === player.id && item.active);
  const academyName = getAcademyName(save, player.academyId);
  const overall = getOverall(player);
  const bestAttributes = getBestAttributes(player, 5);

  return (
    <div className="page">
      <PageHead
        meta="Driver"
        title="Driver Profile"
        sub="Identity, form, progression, and grid scouting."
      />

      {error && <p className="tag neg" style={{ marginBottom: 20 }}>{error}</p>}
      {developmentError && <p className="tag neg" style={{ marginBottom: 20 }}>{developmentError}</p>}

      <PlayerHero
        driver={player}
        teamName={playerTeam}
        academyName={academyName}
        contract={contract}
        overall={overall}
        position={playerPosition}
        points={playerStanding?.points ?? 0}
        season={save.season}
      />

      <Section>
        <StatRow
          items={[
            {
              label: "Championship",
              value: playerPosition ? `P${playerPosition}` : "-",
              detail: `${playerStanding?.points ?? 0} pts`,
              mono: true,
            },
            { label: "Overall", value: String(overall), unit: "/100", mono: true },
            {
              label: "Development",
              value: String(save.development.availablePoints),
              detail: `${save.development.totalEarned} earned total`,
              mono: true,
            },
            {
              label: "Race State",
              value: String(player.currentForm),
              unit: "form",
              detail: `Morale ${player.morale} | Fatigue ${player.fatigue}`,
              mono: true,
            },
          ]}
        />
      </Section>

      <div className="profile-grid">
        <Section title="Attribute Profile">
          <div className="profile-attribute-grid">
            {Object.entries(attributeCategories).map(([category, attrs]) => (
              <div key={category} className="card">
                <div className="card-title" style={{ marginBottom: 16 }}>
                  {category}
                </div>
                <div className="profile-attribute-list">
                  {attrs.map((attr) => (
                    <SegmentedAttribute
                      key={attr}
                      label={attributeLabels[attr]}
                      value={player.attributes[attr]}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>

        <div>
          <Section title="Strengths">
            <div className="card">
              <div className="profile-strengths">
                {bestAttributes.map(([key, value]) => (
                  <div key={key} className="profile-strength-row">
                    <span>{attributeLabels[key]}</span>
                    <strong className="mono">{value}</strong>
                  </div>
                ))}
              </div>
            </div>
          </Section>

          <DevelopmentCard
            save={save}
            development={developmentStatus}
            onSpend={handleSpendDevelopment}
            spendingSkillId={spendingSkillId}
          />
        </div>
      </div>

      <Section title="Recent Results">
        {recentResults.length > 0 ? (
          <table className="tbl">
            <thead>
              <tr>
                <th>Round</th>
                <th>Session</th>
                <th className="num">Finish</th>
                <th className="num">Points</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {recentResults.map((result) => (
                <tr key={result.id}>
                  <td>{result.roundName}</td>
                  <td className="t2">{result.session}</td>
                  <td className="num">{result.position ? `P${result.position}` : "-"}</td>
                  <td className="num">{result.points}</td>
                  <td>
                    <span className={`tag ${result.status === "dnf" ? "neg" : ""}`}>
                      {result.status.toUpperCase()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="card">
            <p className="t2" style={{ margin: 0 }}>
              Complete a race weekend to populate this form guide.
            </p>
          </div>
        )}
      </Section>

      <Section title="Driver Scout">
        <table className="tbl">
          <thead>
            <tr>
              <th>Driver</th>
              <th>Team</th>
              <th>Series</th>
              <th className="num">Age</th>
              <th className="num">OVR</th>
              <th className="num">Points</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {driverRows.map(({ driver, standing, teamName, overall: driverOverall }) => {
              const isPlayer = driver.id === player.id;
              return (
                <tr key={driver.id} className={isPlayer ? "player" : ""}>
                  <td>
                    <DriverCell
                      name={driver.name}
                      driverId={driver.id}
                      num={driver.driverNumber ?? undefined}
                      isPlayer={isPlayer}
                    />
                  </td>
                  <td className="t2">{teamName}</td>
                  <td>
                    <span className="tag">{driver.series}</span>
                  </td>
                  <td className="num">{driver.age}</td>
                  <td className="num">{driverOverall}</td>
                  <td className="num">{standing?.points ?? 0}</td>
                  <td className="right">
                    <button className="btn sm" onClick={() => setSelectedDriverId(driver.id)}>
                      View
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Section>

      {selectedDriver && (
        <DriverDetailModal
          driver={selectedDriver}
          teamName={getTeamName(save, selectedDriver.teamId)}
          standing={save.standings.driverStandings.find(
            (standing) => standing.driverId === selectedDriver.id
          )}
          onClose={() => setSelectedDriverId(null)}
        />
      )}
    </div>
  );
}

function PlayerHero({
  driver,
  teamName,
  academyName,
  contract,
  overall,
  position,
  points,
  season,
}: {
  driver: Driver;
  teamName: string;
  academyName: string | null;
  contract: Contract | undefined;
  overall: number;
  position: number | null;
  points: number;
  season: number;
}) {
  const [imgError, setImgError] = useState(false);
  const initials = getInitials(driver.name);
  const imageUrl = `/drivers/faces/${driver.id}.webp`;
  const showImage = !imgError;

  return (
    <section className="profile-hero">
      <div className="profile-hero-avatar">
        {showImage ? (
          <img
            src={imageUrl}
            alt={driver.name}
            onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }}
          />
        ) : (
          <span>{initials}</span>
        )}
      </div>
      <div className="profile-hero-main">
        <div className="t3 small">
          Season {season} | {driver.series} Driver
        </div>
        <h2>{driver.name}</h2>
        <div className="flex wrap" style={{ gap: 6 }}>
          {driver.driverNumber && <span className="tag accent">#{driver.driverNumber}</span>}
          <span className="tag">{teamName}</span>
          <span className="tag">{driver.nationality}</span>
          {academyName && <span className="tag info">{academyName}</span>}
        </div>
      </div>
      <div className="profile-hero-metrics">
        <div>
          <span>OVR</span>
          <strong>{overall}</strong>
        </div>
        <div>
          <span>Standing</span>
          <strong>{position ? `P${position}` : "-"}</strong>
        </div>
        <div>
          <span>Points</span>
          <strong>{points}</strong>
        </div>
        <div>
          <span>Contract</span>
          <strong>{contract ? `${contract.lengthYears}Y` : "-"}</strong>
        </div>
      </div>
    </section>
  );
}

function DevelopmentCard({
  save,
  development,
  onSpend,
  spendingSkillId,
}: {
  save: SaveGame;
  development: DevelopmentStatus | null;
  onSpend: (skillId: string) => void;
  spendingSkillId: string | null;
}) {
  const spentEntries = Object.entries(save.development.spentPoints)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4);
  const upgradeSkills = development?.skills ?? [];
  const canSpendInPhase = save.phase === "between_races" || save.phase === "offseason";

  return (
    <Section title="Development">
      <div className="card">
        <div className="profile-dev-head">
          <div>
            <div className="card-title">Progression</div>
            <div className="card-sub">
              {canSpendInPhase ? "Spend points here." : "Available between races."}
            </div>
          </div>
          <div className="profile-dev-points mono">{save.development.availablePoints}</div>
        </div>
        <div className="profile-upgrade-list">
          {upgradeSkills.map((skill) => {
            const rank = save.development.spentPoints[skill.id] ?? 0;
            const attribute = development?.attributes[attributeKey(skill.attribute)];
            const canBuy =
              canSpendInPhase &&
              rank < skill.maxRank &&
              save.development.availablePoints >= skill.cost &&
              spendingSkillId === null;

            return (
              <button
                key={skill.id}
                className="profile-upgrade-row"
                type="button"
                disabled={!canBuy}
                onClick={() => onSpend(skill.id)}
              >
                <div>
                  <strong>{skill.name}</strong>
                  <span>
                    {formatSkillAttribute(skill)} {attribute ?? "-"} | Rank {rank}/{skill.maxRank}
                  </span>
                </div>
                <span className="profile-upgrade-cost">
                  {spendingSkillId === skill.id ? "..." : `+1 (${skill.cost})`}
                </span>
              </button>
            );
          })}
        </div>
        {upgradeSkills.length === 0 && (
          <p className="t2" style={{ margin: "14px 0 0" }}>
            Development upgrades are loading.
          </p>
        )}
        {spentEntries.length > 0 && (
          <div className="profile-dev-summary">
            {spentEntries.map(([skillId, rank]) => (
              <span key={skillId} className="tag">
                {skillLabels[skillId] ?? skillId} R{rank}
              </span>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function DriverDetailModal({
  driver,
  teamName,
  standing,
  onClose,
}: {
  driver: Driver;
  teamName: string;
  standing: ChampionshipEntry | undefined;
  onClose: () => void;
}) {
  const [imgError, setImgError] = useState(false);
  const imageUrl = `/drivers/faces/${driver.id}.webp`;
  const showImage = !imgError;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal profile-modal" onClick={(event) => event.stopPropagation()}>
        <div className="modal-header">
          <div className="driver-cell">
            <span className="driver-avatar">
              {showImage ? (
                <img
                  src={imageUrl}
                  alt={driver.name}
                  onError={() => setImgError(true)}
                  style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }}
                />
              ) : (
                getInitials(driver.name)
              )}
            </span>
            <div>
              <div className="modal-title">{driver.name}</div>
              <div className="t2 small">
                {teamName} | {driver.nationality} | Age {driver.age}
              </div>
            </div>
          </div>
          <button className="btn sm" onClick={onClose}>
            Close
          </button>
        </div>

        <StatRow
          items={[
            { label: "Overall", value: String(getOverall(driver)), mono: true },
            { label: "Points", value: String(standing?.points ?? 0), mono: true },
            { label: "Wins", value: String(standing?.wins ?? 0), mono: true },
            { label: "Podiums", value: String(standing?.podiums ?? 0), mono: true },
          ]}
        />

        <div className="divider"></div>

        <div className="profile-attribute-grid">
          {Object.entries(attributeCategories).map(([category, attrs]) => (
            <div key={category}>
              <div className="section-title" style={{ marginBottom: 12 }}>
                {category}
              </div>
              <div className="profile-attribute-list">
                {attrs.map((attr) => (
                  <SegmentedAttribute
                    key={attr}
                    label={attributeLabels[attr]}
                    value={driver.attributes[attr]}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function SegmentedAttribute({ label, value }: { label: string; value: number }) {
  const segments = 20;
  const filledSegments = Math.round((value / 100) * segments);
  const tone = getAttributeTone(value);

  return (
    <div className={`profile-attribute ${tone}`}>
      <div className="meter-row">
        <span className="meter-label">{label}</span>
        <span className="meter-val">{value}</span>
      </div>
      <div className="seg-bar">
        {Array.from({ length: segments }).map((_, index) => (
          <span key={index} className={index < filledSegments ? tone : ""}></span>
        ))}
      </div>
    </div>
  );
}

function getAttributeTone(value: number) {
  if (value >= 85) return "elite";
  if (value >= 75) return "strong";
  if (value >= 60) return "solid";
  return "developing";
}

function attributeKey(attribute: string) {
  return attribute.replace(/_([a-z])/g, (_, char: string) => char.toUpperCase());
}

function formatSkillAttribute(skill: SkillNode) {
  return skill.attribute
    .replace(/_/g, " ")
    .replace(/^./, (char) => char.toUpperCase());
}

function buildDriverRows(save: SaveGame | null) {
  if (!save) return [];
  const standingsMap = new Map(save.standings.driverStandings.map((entry) => [entry.driverId, entry]));
  return [...save.drivers]
    .map((driver) => ({
      driver,
      standing: standingsMap.get(driver.id),
      teamName: getTeamName(save, driver.teamId),
      overall: getOverall(driver),
    }))
    .sort((a, b) => {
      if (a.driver.id === save.playerDriverId) return -1;
      if (b.driver.id === save.playerDriverId) return 1;
      if (a.driver.series !== b.driver.series) return a.driver.series.localeCompare(b.driver.series);
      return (b.standing?.points ?? 0) - (a.standing?.points ?? 0);
    });
}

function buildRecentResults(save: SaveGame | null): RecentResult[] {
  if (!save?.playerDriverId) return [];
  return save.weekendResults
    .slice()
    .reverse()
    .flatMap((weekend) => raceRowsForWeekend(save, weekend))
    .slice(0, 6);
}

function raceRowsForWeekend(save: SaveGame, weekend: WeekendResult): RecentResult[] {
  const roundName = save.calendar.find((round) => round.id === weekend.roundId)?.name ?? weekend.roundId;
  return [
    { session: "Sprint" as const, race: weekend.sprint },
    { session: "Feature" as const, race: weekend.feature },
  ]
    .map(({ session, race }) => {
      const playerRow = race.classification.find((row) => row.driverId === save.playerDriverId);
      return {
        id: `${weekend.roundId}-${session}`,
        roundName,
        session,
        position: playerRow?.position ?? null,
        points: playerRow?.points ?? 0,
        status: playerRow?.status ?? "running",
      };
    })
    .filter((row) => row.position !== null);
}

function getOverall(driver: Driver) {
  const core: Array<keyof DriverAttributes> = [
    "pace",
    "qualifying",
    "racecraft",
    "tireManagement",
    "wetWeather",
    "consistency",
    "starts",
    "pressure",
    "awareness",
    "technicalFeedback",
  ];
  const total = core.reduce((sum, key) => sum + driver.attributes[key], 0);
  return Math.round(total / core.length);
}

function getBestAttributes(driver: Driver, count: number) {
  return (Object.entries(driver.attributes) as Array<[keyof DriverAttributes, number]>)
    .sort((a, b) => b[1] - a[1])
    .slice(0, count);
}

function getTeamName(save: SaveGame, teamId: string) {
  return save.teams.find((team) => team.id === teamId)?.name ?? teamId;
}

function getAcademyName(save: SaveGame, academyId: string | null) {
  if (!academyId) return null;
  return save.academies.find((academy) => academy.id === academyId)?.name ?? academyId;
}

function getInitials(name: string) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
