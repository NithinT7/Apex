"use client";

import { ReactNode, CSSProperties, useEffect, useState } from "react";

// F2 Team colors map
export const TEAM_COLORS: Record<string, string> = {
  prema: "#e80020",
  virtuosi: "#0032ff",
  carlin: "#1e90ff",
  art: "#c20e1a",
  hitech: "#ffffff",
  dams: "#00a8e8",
  mp: "#ff6600",
  campos: "#f39200",
  trident: "#0033a0",
  van_amersfoort: "#ff6b00",
  rodin: "#990033",
  invicta: "#4b0082",
  // F1 teams
  red_bull: "#3671c6",
  ferrari: "#e80020",
  mercedes: "#27f4d2",
  mclaren: "#ff8000",
  aston_martin: "#229971",
  alpine: "#ff87bc",
  williams: "#64c4ff",
  racing_bulls: "#6692ff",
  haas: "#b6babd",
  audi: "#1f1f1f",
  cadillac: "#d4af37",
};

export function getTeamColor(teamId: string): string {
  const normalized = teamId.toLowerCase().replace(/[\s-]/g, "_");
  return TEAM_COLORS[normalized] || "#5a6473";
}

// Card component
export function Card({
  title,
  eyebrow,
  action,
  children,
  pad = 14,
  style = {},
  className = "",
}: {
  title?: string;
  eyebrow?: string;
  action?: ReactNode;
  children: ReactNode;
  pad?: number | string;
  style?: CSSProperties;
  className?: string;
}) {
  return (
    <div className={`card ${className}`} style={style}>
      {(title || eyebrow || action) && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "10px 14px",
            borderBottom: "1px solid var(--line-1)",
            gap: 12,
          }}
        >
          <div style={{ minWidth: 0 }}>
            {eyebrow && (
              <div style={{ color: "var(--t-3)", fontSize: 11, fontWeight: 500, marginBottom: 2 }}>
                {eyebrow}
              </div>
            )}
            {title && (
              <div style={{ fontWeight: 600, fontSize: 14, color: "var(--t-1)" }}>{title}</div>
            )}
          </div>
          {action}
        </div>
      )}
      <div style={{ padding: pad }}>{children}</div>
    </div>
  );
}

// Chip / pill component
type ChipTone = "good" | "warn" | "bad" | "accent" | "electric" | "silver" | "muted";

export function Chip({
  tone = "muted",
  children,
  mono = false,
  style = {},
}: {
  tone?: ChipTone;
  children: ReactNode;
  mono?: boolean;
  style?: CSSProperties;
}) {
  const tones: Record<ChipTone, { background: string; color: string }> = {
    good: { background: "var(--good-soft)", color: "var(--good)" },
    warn: { background: "var(--warn-soft)", color: "var(--warn)" },
    bad: { background: "var(--bad-soft)", color: "var(--bad)" },
    accent: { background: "var(--accent-soft)", color: "var(--accent)" },
    electric: { background: "var(--electric-soft)", color: "var(--electric)" },
    silver: { background: "rgba(214,220,230,0.08)", color: "var(--silver)" },
    muted: { background: "rgba(125,133,147,0.10)", color: "var(--t-2)" },
  };
  const t = tones[tone] || tones.muted;

  return (
    <span
      className={mono ? "mono" : ""}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: "3px 9px",
        borderRadius: 999,
        fontSize: 11,
        lineHeight: 1.4,
        fontWeight: 500,
        ...t,
        ...style,
      }}
    >
      {children}
    </span>
  );
}

// Progress bar
export function Bar({
  value = 0,
  max = 100,
  height = 6,
  color = "var(--electric)",
  track = "rgba(255,255,255,0.06)",
  style = {},
}: {
  value?: number;
  max?: number;
  height?: number;
  color?: string;
  track?: string;
  style?: CSSProperties;
}) {
  return (
    <div style={{ background: track, borderRadius: 999, overflow: "hidden", height, ...style }}>
      <div
        style={{
          width: `${Math.min(100, (value / max) * 100)}%`,
          height: "100%",
          background: color,
          transition: "width 0.25s",
        }}
      />
    </div>
  );
}

// Stat block
export function Stat({
  label,
  value,
  sub,
  tone,
  trend,
  mono = true,
  size = 22,
}: {
  label: string;
  value: string | number;
  sub?: string;
  tone?: "good" | "bad" | "warn";
  trend?: string;
  mono?: boolean;
  size?: number;
}) {
  const toneCol =
    tone === "good"
      ? "var(--good)"
      : tone === "bad"
        ? "var(--bad)"
        : tone === "warn"
          ? "var(--warn)"
          : "var(--t-1)";

  return (
    <div>
      <div style={{ color: "var(--t-3)", fontSize: 10, marginBottom: 4, letterSpacing: "0.02em" }}>
        {label}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
        <span
          className={mono ? "mono" : ""}
          style={{ fontSize: size, fontWeight: 600, color: toneCol, lineHeight: 1 }}
        >
          {value}
        </span>
        {trend && (
          <span
            className="mono"
            style={{
              fontSize: 11,
              color:
                trend.startsWith("+") || trend === "▲"
                  ? "var(--good)"
                  : trend.startsWith("-") || trend === "▼"
                    ? "var(--bad)"
                    : "var(--t-3)",
            }}
          >
            {trend}
          </span>
        )}
      </div>
      {sub && <div style={{ color: "var(--t-3)", fontSize: 10.5, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// Team badge
export function TeamBadge({
  team,
  color = "#5a6473",
  size = 18,
}: {
  team: string;
  color?: string;
  size?: number;
}) {
  const initials = team
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: 3,
        background: color + "26",
        borderLeft: `3px solid ${color}`,
        color: "var(--t-1)",
        fontWeight: 700,
        fontSize: 9.5,
        fontFamily: "var(--font-mono)",
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {initials}
    </span>
  );
}

// Tire badge
export function TireBadge({ compound, age }: { compound: "S" | "M" | "H" | "I" | "W"; age?: number }) {
  const colors: Record<string, string> = {
    S: "var(--tire-soft)",
    M: "var(--tire-medium)",
    H: "var(--tire-hard)",
    I: "var(--tire-inter)",
    W: "var(--tire-wet)",
  };
  const c = colors[compound] || colors.M;

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span
        style={{
          width: 14,
          height: 14,
          borderRadius: 999,
          border: `2px solid ${c}`,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          color: c,
          fontSize: 8.5,
          fontWeight: 800,
          fontFamily: "var(--font-mono)",
        }}
      >
        {compound}
      </span>
      {age != null && (
        <span className="mono" style={{ color: "var(--t-2)", fontSize: 11 }}>
          {age}L
        </span>
      )}
    </span>
  );
}

// Confidence dots (1-5)
export function ConfidenceDots({
  level = 1,
  labels = ["Weak", "Growing", "Serious", "Near-Confirmed", "Confirmed"],
}: {
  level?: number;
  labels?: string[];
}) {
  const colors = ["var(--conf-1)", "var(--conf-2)", "var(--conf-3)", "var(--conf-4)", "var(--conf-5)"];

  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{ display: "inline-flex", gap: 2 }}>
        {[1, 2, 3, 4, 5].map((i) => (
          <span
            key={i}
            style={{
              width: 6,
              height: 6,
              borderRadius: 1,
              background: i <= level ? colors[level - 1] : "rgba(255,255,255,0.08)",
            }}
          />
        ))}
      </span>
      <span style={{ color: colors[level - 1], fontSize: 9.5, letterSpacing: "0.02em" }}>
        {labels[level - 1]}
      </span>
    </span>
  );
}

// Button
export function Button({
  children,
  kind = "ghost",
  size = "md",
  full = false,
  disabled = false,
  onClick,
  style = {},
}: {
  children: ReactNode;
  kind?: "primary" | "ghost" | "secondary" | "danger";
  size?: "sm" | "md" | "lg";
  full?: boolean;
  disabled?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
}) {
  const kinds: Record<string, CSSProperties> = {
    primary: { background: "var(--accent)", color: "#fff", borderColor: "var(--accent)" },
    secondary: { background: "var(--bg-3)", color: "var(--t-1)", borderColor: "var(--line-2)" },
    ghost: { background: "transparent", color: "var(--t-2)", borderColor: "var(--line-2)" },
    danger: { background: "transparent", color: "var(--bad)", borderColor: "rgba(232,88,88,0.35)" },
  };
  const sizes: Record<string, CSSProperties> = {
    sm: { padding: "5px 10px", fontSize: 12, borderRadius: 7 },
    md: { padding: "8px 14px", fontSize: 13, borderRadius: 9 },
    lg: { padding: "11px 18px", fontSize: 14, borderRadius: 10 },
  };

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        gap: 6,
        cursor: disabled ? "default" : "pointer",
        fontWeight: 500,
        opacity: disabled ? 0.5 : 1,
        width: full ? "100%" : "auto",
        border: "1px solid transparent",
        transition: "background 0.15s",
        ...kinds[kind],
        ...sizes[size],
        ...style,
      }}
    >
      {children}
    </button>
  );
}

// Page header
export function PageHeader({
  eyebrow,
  title,
  question,
  actions,
}: {
  eyebrow?: string;
  title: string;
  question?: string;
  actions?: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "space-between",
        gap: 20,
        marginBottom: 16,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        {eyebrow && (
          <div style={{ fontSize: 11.5, fontWeight: 500, color: "var(--t-3)", marginBottom: 4 }}>
            {eyebrow}
          </div>
        )}
        <h1
          style={{
            margin: 0,
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: "-0.02em",
            color: "var(--t-1)",
            lineHeight: 1.15,
          }}
        >
          {title}
        </h1>
        {question && (
          <div style={{ marginTop: 4, color: "var(--t-3)", fontSize: 12.5 }}>{question}</div>
        )}
      </div>
      {actions && <div style={{ display: "flex", gap: 8 }}>{actions}</div>}
    </div>
  );
}

// Section with title
export function Section({
  title,
  sub,
  action,
  children,
  style = {},
}: {
  title?: string;
  sub?: string;
  action?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
}) {
  return (
    <section style={{ marginBottom: 14, ...style }}>
      {(title || action) && (
        <div
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: 10,
            gap: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
            <h2 style={{ margin: 0, fontSize: 14, fontWeight: 600, color: "var(--t-1)" }}>{title}</h2>
            {sub && <span style={{ color: "var(--t-3)", fontSize: 12 }}>{sub}</span>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

// KV row
export function KV({
  k,
  v,
  mono = true,
  tone,
}: {
  k: string;
  v: string | number;
  mono?: boolean;
  tone?: "good" | "bad" | "warn";
}) {
  const tcol =
    tone === "good"
      ? "var(--good)"
      : tone === "bad"
        ? "var(--bad)"
        : tone === "warn"
          ? "var(--warn)"
          : "var(--t-1)";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        padding: "5px 0",
        borderBottom: "1px dashed var(--line-1)",
      }}
    >
      <span style={{ color: "var(--t-3)", fontSize: 11.5 }}>{k}</span>
      <span className={mono ? "mono" : ""} style={{ color: tcol, fontSize: 12, fontWeight: 500 }}>
        {v}
      </span>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Timing Tower Components (F1 Broadcast Style)
// ─────────────────────────────────────────────────────────────

export interface TimingEntry {
  position: number;
  driverId: string;
  driverCode: string; // 3-letter code like VER, HAM
  teamId: string;
  time: string; // lap time or gap string
  gap?: string; // gap to leader
  interval?: string; // gap to car ahead
  tire?: "S" | "M" | "H" | "I" | "W";
  tireAge?: number;
  status?: "running" | "pit" | "out" | "eliminated";
  isPlayer?: boolean;
  isFastestLap?: boolean;
  isPurpleSector?: boolean;
  isGreenSector?: boolean;
  positionChange?: number; // positive = gained, negative = lost
}

export function TimingTower({
  entries,
  session,
  sessionInfo,
  eliminationZone,
  compact = false,
  onDriverClick,
}: {
  entries: TimingEntry[];
  session: "Q1" | "Q2" | "Q3" | "SPRINT" | "RACE" | "PRACTICE";
  sessionInfo?: string; // e.g., "LAP 45/52" or remaining time
  eliminationZone?: number; // position where elimination starts (e.g., 16 for Q1)
  compact?: boolean;
  onDriverClick?: (driverId: string) => void;
}) {
  return (
    <div
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: compact ? 11 : 12,
        minWidth: compact ? 300 : 340,
      }}
    >
      {/* F1-style header bar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "8px 12px",
          background: "linear-gradient(90deg, #e10600 0%, #900 100%)",
          borderRadius: "4px 4px 0 0",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{
            color: "#fff",
            fontWeight: 800,
            fontSize: compact ? 14 : 16,
            letterSpacing: "0.02em",
          }}>
            {session}
          </span>
        </div>
        {sessionInfo && (
          <span style={{
            color: "rgba(255,255,255,0.9)",
            fontSize: compact ? 11 : 12,
            fontWeight: 600,
          }}>
            {sessionInfo}
          </span>
        )}
      </div>

      {/* Timing rows */}
      <div style={{
        background: "#111",
        borderRadius: "0 0 4px 4px",
        overflow: "hidden",
      }}>
        {entries.map((entry, idx) => {
          const isEliminated = eliminationZone && entry.position >= eliminationZone;
          const showEliminationLine = eliminationZone && entry.position === eliminationZone;

          return (
            <div key={entry.driverId}>
              {showEliminationLine && (
                <div
                  style={{
                    height: 2,
                    background: "linear-gradient(90deg, var(--bad), transparent)",
                  }}
                />
              )}
              <TimingRow
                entry={entry}
                compact={compact}
                isEliminated={!!isEliminated}
                isEven={idx % 2 === 0}
                onClick={onDriverClick ? () => onDriverClick(entry.driverId) : undefined}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TimingRow({
  entry,
  compact,
  isEliminated,
  isEven,
  onClick,
}: {
  entry: TimingEntry;
  compact: boolean;
  isEliminated?: boolean;
  isEven?: boolean;
  onClick?: () => void;
}) {
  const teamColor = getTeamColor(entry.teamId);
  const isOut = entry.status === "out";
  const isPit = entry.status === "pit";
  const height = compact ? 26 : 30;

  // Position colors (F1 style - gold/silver/bronze for podium)
  const getPositionStyle = () => {
    if (entry.position === 1) return { bg: "#FFD700", color: "#000" };
    if (entry.position === 2) return { bg: "#C0C0C0", color: "#000" };
    if (entry.position === 3) return { bg: "#CD7F32", color: "#000" };
    return { bg: "#333", color: "#fff" };
  };
  const posStyle = getPositionStyle();

  return (
    <div
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        height,
        background: entry.isPlayer
          ? "linear-gradient(90deg, rgba(61,190,115,0.25) 0%, rgba(61,190,115,0.08) 100%)"
          : isEliminated
            ? "rgba(232, 88, 88, 0.08)"
            : isEven
              ? "rgba(255,255,255,0.02)"
              : "transparent",
        borderLeft: entry.isPlayer ? "3px solid var(--good)" : "3px solid transparent",
        opacity: isOut ? 0.45 : 1,
        cursor: onClick ? "pointer" : "default",
        transition: "all 0.15s",
      }}
    >
      {/* Position badge */}
      <div style={{
        width: compact ? 24 : 28,
        height: height - 4,
        marginLeft: 4,
        marginRight: 2,
        background: isOut ? "#333" : posStyle.bg,
        borderRadius: 2,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
      }}>
        <span style={{
          color: isOut ? "#666" : posStyle.color,
          fontWeight: 700,
          fontSize: compact ? 11 : 12,
        }}>
          {entry.position}
        </span>
        {/* Position change indicator */}
        {entry.positionChange !== undefined && entry.positionChange !== 0 && !isOut && (
          <span style={{
            position: "absolute",
            right: -2,
            top: -2,
            fontSize: 7,
            color: entry.positionChange > 0 ? "#00ff00" : "#ff0000",
            fontWeight: 700,
            textShadow: "0 0 2px rgba(0,0,0,0.8)",
          }}>
            {entry.positionChange > 0 ? "▲" : "▼"}
          </span>
        )}
      </div>

      {/* Team color bar */}
      <div style={{
        width: 5,
        height: height - 6,
        background: teamColor,
        borderRadius: 1,
        marginRight: 6,
        boxShadow: `0 0 4px ${teamColor}60`,
      }} />

      {/* Driver code */}
      <div style={{
        flex: "0 0 42px",
        color: entry.isPlayer ? "#4ade80" : "#fff",
        fontWeight: 700,
        fontSize: compact ? 12 : 13,
        letterSpacing: "0.04em",
      }}>
        {entry.driverCode}
      </div>

      {/* Tire indicator */}
      {entry.tire && !isOut && (
        <div style={{
          flex: "0 0 20px",
          marginRight: 6,
        }}>
          <div style={{
            width: 16,
            height: 16,
            borderRadius: 999,
            background: entry.tire === "S" ? "var(--tire-soft)" :
                       entry.tire === "M" ? "var(--tire-medium)" :
                       entry.tire === "H" ? "var(--tire-hard)" :
                       entry.tire === "I" ? "var(--tire-inter)" :
                       "var(--tire-wet)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 9,
            fontWeight: 800,
            color: "#000",
          }}>
            {entry.tire}
          </div>
        </div>
      )}

      {/* Gap/Interval */}
      <div style={{
        flex: 1,
        textAlign: "right",
        paddingRight: 10,
        color: entry.isFastestLap
          ? "#a855f7"
          : entry.isPurpleSector
            ? "#a855f7"
            : entry.isGreenSector
              ? "#22c55e"
              : isPit
                ? "#fbbf24"
                : isOut
                  ? "#666"
                  : entry.position === 1
                    ? "#fff"
                    : "#aaa",
        fontWeight: entry.position === 1 || entry.isFastestLap ? 600 : 400,
        fontSize: compact ? 11 : 12,
      }}>
        {isOut ? "OUT" : isPit ? "PIT" : entry.position === 1 ? "LEADER" : entry.interval || entry.gap || entry.time}
      </div>

      {/* Fastest lap indicator */}
      {entry.isFastestLap && !isOut && (
        <div style={{
          width: 14,
          height: 14,
          borderRadius: 2,
          background: "#a855f7",
          marginRight: 8,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}>
          <span style={{ fontSize: 9, color: "#fff", fontWeight: 700 }}>F</span>
        </div>
      )}
    </div>
  );
}

// Session timer display
export function SessionTimer({
  timeRemaining,
  isRunning,
  phase,
}: {
  timeRemaining: number; // seconds
  isRunning: boolean;
  phase?: string;
}) {
  const minutes = Math.floor(timeRemaining / 60);
  const seconds = timeRemaining % 60;
  const isLow = timeRemaining < 60;

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: 12,
      padding: "8px 16px",
      background: "rgba(0,0,0,0.6)",
      borderRadius: 8,
    }}>
      {phase && (
        <span style={{
          color: "var(--t-2)",
          fontSize: 12,
          fontWeight: 500,
          letterSpacing: "0.05em",
        }}>
          {phase}
        </span>
      )}
      <span
        className="mono"
        style={{
          fontSize: 28,
          fontWeight: 700,
          color: isLow ? "var(--bad)" : "#fff",
          letterSpacing: "-0.02em",
        }}
      >
        {minutes}:{seconds.toString().padStart(2, "0")}
      </span>
      {!isRunning && (
        <span style={{
          color: "var(--warn)",
          fontSize: 10,
          fontWeight: 600,
          letterSpacing: "0.1em",
        }}>
          PAUSED
        </span>
      )}
    </div>
  );
}

// Lap counter for races
export function LapCounter({
  currentLap,
  totalLaps,
}: {
  currentLap: number;
  totalLaps: number;
}) {
  const progress = (currentLap / totalLaps) * 100;

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      gap: 6,
      padding: "10px 16px",
      background: "rgba(0,0,0,0.6)",
      borderRadius: 8,
      minWidth: 120,
    }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
        <span style={{ color: "var(--t-3)", fontSize: 11 }}>LAP</span>
        <span className="mono" style={{ fontSize: 24, fontWeight: 700, color: "#fff" }}>
          {currentLap}
        </span>
        <span className="mono" style={{ fontSize: 14, color: "var(--t-3)" }}>
          /{totalLaps}
        </span>
      </div>
      <Bar value={currentLap} max={totalLaps} height={3} color="var(--electric)" />
    </div>
  );
}

// Driver focus panel (shows details for selected driver)
export function DriverFocusPanel({
  driverCode,
  driverName,
  teamName,
  teamColor,
  position,
  gap,
  tire,
  tireAge,
  lastLap,
  bestLap,
  pitStops,
  isPlayer,
}: {
  driverCode: string;
  driverName: string;
  teamName: string;
  teamColor: string;
  position: number;
  gap?: string;
  tire?: "S" | "M" | "H" | "I" | "W";
  tireAge?: number;
  lastLap?: string;
  bestLap?: string;
  pitStops?: number;
  isPlayer?: boolean;
}) {
  return (
    <div style={{
      background: "rgba(0,0,0,0.85)",
      borderRadius: 10,
      padding: 16,
      borderLeft: `4px solid ${teamColor}`,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <div style={{
          width: 48,
          height: 48,
          borderRadius: 8,
          background: isPlayer ? "rgba(61,190,115,0.2)" : "rgba(255,255,255,0.1)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}>
          <span className="mono" style={{
            fontSize: 20,
            fontWeight: 700,
            color: isPlayer ? "var(--good)" : "#fff",
          }}>
            P{position}
          </span>
        </div>
        <div>
          <div style={{
            fontSize: 18,
            fontWeight: 700,
            color: "#fff",
            letterSpacing: "-0.01em",
          }}>
            {driverCode}
          </div>
          <div style={{ fontSize: 12, color: "var(--t-3)" }}>{driverName}</div>
          <div style={{ fontSize: 11, color: teamColor }}>{teamName}</div>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        {gap && (
          <div>
            <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 2 }}>GAP</div>
            <div className="mono" style={{ fontSize: 14, color: "var(--t-1)" }}>{gap}</div>
          </div>
        )}
        {tire && (
          <div>
            <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 2 }}>TIRE</div>
            <TireBadge compound={tire} age={tireAge} />
          </div>
        )}
        {lastLap && (
          <div>
            <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 2 }}>LAST</div>
            <div className="mono" style={{ fontSize: 14, color: "var(--t-1)" }}>{lastLap}</div>
          </div>
        )}
        {bestLap && (
          <div>
            <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 2 }}>BEST</div>
            <div className="mono" style={{ fontSize: 14, color: "#a855f7" }}>{bestLap}</div>
          </div>
        )}
        {pitStops !== undefined && (
          <div>
            <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 2 }}>PITS</div>
            <div className="mono" style={{ fontSize: 14, color: "var(--t-1)" }}>{pitStops}</div>
          </div>
        )}
      </div>
    </div>
  );
}
