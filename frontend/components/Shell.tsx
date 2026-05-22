"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { Driver, SaveGame, NewsItem } from "@/lib/types";

// Icons as simple SVG components
const Icons = {
  Dashboard: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" /><rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
    </svg>
  ),
  Calendar: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" /><line x1="16" y1="2" x2="16" y2="6" /><line x1="8" y1="2" x2="8" y2="6" /><line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  ),
  Flag: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" /><line x1="4" y1="22" x2="4" y2="15" />
    </svg>
  ),
  Trophy: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6" /><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18" /><path d="M4 22h16" /><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20 7 22" /><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20 17 22" /><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z" />
    </svg>
  ),
  Team: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  ),
  News: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2" /><path d="M18 14h-8" /><path d="M15 18h-5" /><path d="M10 6h8v4h-8V6Z" />
    </svg>
  ),
  Activity: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  ),
  Settings: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
  Plus: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  ),
  Save: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" /><polyline points="17 21 17 13 7 13 7 21" /><polyline points="7 3 7 8 15 8" />
    </svg>
  ),
  User: () => (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" /><circle cx="12" cy="7" r="4" />
    </svg>
  ),
};

type NavItem = {
  id: string;
  label: string;
  href: string;
  icon: keyof typeof Icons;
  badge?: string;
  live?: boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

const NAV_GROUPS: NavGroup[] = [
  {
    label: "Career",
    items: [
      { id: "dashboard", label: "Dashboard", href: "/", icon: "Dashboard" },
      { id: "driver", label: "Driver", href: "/driver", icon: "User" },
      { id: "calendar", label: "Calendar", href: "/calendar", icon: "Calendar" },
      { id: "activities", label: "Activities", href: "/activities", icon: "Activity" },
    ],
  },
  {
    label: "Race Weekend",
    items: [
      { id: "weekend", label: "Race Weekend", href: "/race-weekend", icon: "Flag" },
      { id: "standings", label: "Standings", href: "/standings", icon: "Trophy" },
    ],
  },
  {
    label: "Paddock",
    items: [
      { id: "news", label: "News", href: "/news", icon: "News" },
    ],
  },
  {
    label: "Management",
    items: [
      { id: "saves", label: "Saves", href: "/saves", icon: "Save" },
      { id: "create", label: "New Career", href: "/create-driver", icon: "Plus" },
    ],
  },
];

type TopBarProps = {
  player: Driver | null;
  season?: { year: number; round: number; totalRounds: number };
  nextEvent?: { name: string; days: number };
};

export function TopBar({ player, season, nextEvent }: TopBarProps) {
  const initials = player
    ? player.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .slice(0, 2)
        .toUpperCase()
    : "??";

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <div className="mark"></div>
        <span>Apex</span>
      </div>
      <div className="topbar-context">
        {season && (
          <div className="item">
            <span className="label">Season</span>
            <span className="value">
              {season.year} · Round {season.round} of {season.totalRounds}
            </span>
          </div>
        )}
        {nextEvent && (
          <div className="item">
            <span className="label">Next event</span>
            <span className="value">
              {nextEvent.name} <span className="t3">· in {nextEvent.days} days</span>
            </span>
          </div>
        )}
        {player && (
          <div className="item">
            <span className="label">Team</span>
            <span className="value">{player.teamId}</span>
          </div>
        )}
      </div>
      <div className="topbar-actions">
        <div className="player-chip">
          <div className="avatar">{initials}</div>
          {player ? (
            <div>
              <div className="nm">{player.name}</div>
              <div className="sub">{player.nationality}</div>
            </div>
          ) : (
            <div>
              <div className="nm">No Driver</div>
              <div className="sub">Create one to start</div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

type SideBarProps = {
  saveName?: string;
  showLive?: boolean;
};

export function SideBar({ saveName, showLive }: SideBarProps) {
  const pathname = usePathname();

  const isActive = (href: string) => {
    if (href === "/") return pathname === "/";
    return pathname.startsWith(href);
  };

  return (
    <aside className="sidebar">
      {NAV_GROUPS.map((group, gi) => (
        <div key={gi}>
          <div className="sidebar-section">{group.label}</div>
          <div className="col" style={{ gap: 1 }}>
            {group.items.map((item) => {
              const Icon = Icons[item.icon];
              const active = isActive(item.href);
              return (
                <Link
                  key={item.id}
                  href={item.href}
                  className={`nav-item ${active ? "active" : ""}`}
                >
                  <span className="icon">
                    <Icon />
                  </span>
                  <span>{item.label}</span>
                  {item.live && showLive && <span className="live-dot" title="Race in progress" />}
                  {item.badge && !item.live && <span className="badge">{item.badge}</span>}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
      <div className="sidebar-foot">
        <div className="row">
          <span>Save</span>
          <span className="v">{saveName || "—"}</span>
        </div>
      </div>
    </aside>
  );
}

type AppShellProps = {
  children: React.ReactNode;
  save?: SaveGame | null;
};

export function AppShell({ children, save }: AppShellProps) {
  const player = save?.drivers.find((d) => d.id === save.playerDriverId) ?? null;
  const nextRound = save?.calendar.find((r) => !r.completed);
  const completedRounds = save?.calendar.filter((r) => r.completed).length ?? 0;
  const breakingNews = useMemo(() => getBreakingNews(save), [save]);

  const season = save
    ? {
        year: save.season,
        round: completedRounds + 1,
        totalRounds: save.calendar.length,
      }
    : undefined;

  const nextEvent = nextRound
    ? {
        name: nextRound.name,
        days: 3, // simplified - could calculate from dates
      }
    : undefined;

  return (
    <div className="app-shell">
      <TopBar player={player} season={season} nextEvent={nextEvent} />
      <SideBar saveName={save?.name} />
      <main className="main-content">
        {save && <BreakingNewsTicker news={breakingNews.slice(0, 3)} />}
        {children}
      </main>
      {save && <BreakingNewsModal saveId={save.saveId} news={breakingNews[0]} />}
    </div>
  );
}

function getBreakingNews(save?: SaveGame | null) {
  if (!save) return [];
  return dedupeNewsById(save.news)
    .reverse()
    .filter((item) => item.importance >= 4 || item.category === "rumor" || item.category === "contract");
}

function dedupeNewsById(news: NewsItem[]) {
  const seen = new Set<string>();
  const dedupedReversed: NewsItem[] = [];
  for (let index = news.length - 1; index >= 0; index -= 1) {
    const item = news[index];
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    dedupedReversed.push(item);
  }
  return dedupedReversed.reverse();
}

function isModalBreaking(news?: NewsItem) {
  return Boolean(
    news &&
      (news.importance >= 5 ||
        news.category === "contract" ||
        news.category === "incident" ||
        (news.category === "rumor" && news.importance >= 4))
  );
}

function BreakingNewsTicker({ news }: { news: NewsItem[] }) {
  if (news.length === 0) return null;

  return (
    <div className="breaking-ticker">
      <div className="breaking-label">Breaking</div>
      <div className="breaking-items">
        {news.map((item) => (
          <Link href="/news" key={item.id} className="breaking-item">
            <span>{item.headline}</span>
            <span className="breaking-date">{item.date}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

function BreakingNewsModal({ saveId, news }: { saveId: string; news?: NewsItem }) {
  const [visibleNews, setVisibleNews] = useState<NewsItem | null>(null);

  useEffect(() => {
    if (!news || !isModalBreaking(news)) {
      setVisibleNews(null);
      return;
    }

    const storageKey = `apex:breaking-news:${saveId}:${news.id}`;
    if (window.localStorage.getItem(storageKey)) {
      setVisibleNews(null);
      return;
    }
    setVisibleNews(news);
  }, [saveId, news]);

  if (!visibleNews) return null;

  const close = () => {
    window.localStorage.setItem(`apex:breaking-news:${saveId}:${visibleNews.id}`, "seen");
    setVisibleNews(null);
  };

  return (
    <div className="modal-overlay breaking-overlay" onClick={close}>
      <div className="modal breaking-modal" onClick={(event) => event.stopPropagation()}>
        <div className="breaking-modal-kicker">Breaking News</div>
        <div className="breaking-modal-title">{visibleNews.headline}</div>
        <p>{visibleNews.body}</p>
        <div className="breaking-modal-meta">
          <span className="tag accent">{visibleNews.category}</span>
          <span>{visibleNews.date}</span>
        </div>
        <div className="breaking-modal-actions">
          <Link href="/news" className="btn primary" onClick={close}>
            Open news feed
          </Link>
          <button className="btn" onClick={close}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}

// Page-level primitives

type PageHeadProps = {
  meta?: string;
  title: string;
  sub?: string;
  actions?: React.ReactNode;
};

export function PageHead({ meta, title, sub, actions }: PageHeadProps) {
  return (
    <div className="page-head">
      <div>
        {meta && <div className="meta">{meta}</div>}
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  );
}

type SectionProps = {
  title?: string;
  link?: string;
  onLink?: () => void;
  children: React.ReactNode;
  style?: React.CSSProperties;
};

export function Section({ title, link, onLink, children, style }: SectionProps) {
  return (
    <section className="section" style={style}>
      {(title || link) && (
        <div className="section-head">
          {title && <div className="section-title">{title}</div>}
          {link && (
            <div className="section-link" onClick={onLink}>
              {link} →
            </div>
          )}
        </div>
      )}
      {children}
    </section>
  );
}

type StatRowProps = {
  items: Array<{
    label: string;
    value: string | number;
    unit?: string;
    mono?: boolean;
    sm?: boolean;
    color?: string;
    detail?: string;
  }>;
};

export function StatRow({ items }: StatRowProps) {
  return (
    <div className="stat-row">
      {items.map((s, i) => (
        <div key={i} className="stat-cell">
          <div className="stat-label">{s.label}</div>
          <div
            className={`stat-value${s.mono ? " mono" : ""}${s.sm ? " sm" : ""}`}
            style={s.color ? { color: s.color } : undefined}
          >
            {s.value}
            {s.unit && <span className="small"> {s.unit}</span>}
          </div>
          {s.detail && <div className="stat-detail">{s.detail}</div>}
        </div>
      ))}
    </div>
  );
}

type TireProps = {
  compound: string;
  age?: number;
};

export function Tire({ compound, age }: TireProps) {
  if (!compound || compound === "—") return <span className="muted mono">—</span>;
  const c = compound[0].toUpperCase();
  return (
    <span className={`tire ${c}`}>
      <span className="dot"></span>
      <span>
        {c}
        {age != null && <span className="muted" style={{ marginLeft: 4 }}>{age}L</span>}
      </span>
    </span>
  );
}

type MeterProps = {
  label: string;
  value: number;
  max?: number;
  tone?: "accent" | "pos" | "warn" | "neg";
  note?: string;
};

export function Meter({ label, value, max = 100, tone, note }: MeterProps) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div>
      <div className="meter-row">
        <span className="meter-label">{label}</span>
        <span className="meter-val">
          {value}
          {max === 100 ? "" : `/${max}`}
        </span>
      </div>
      <div className={`bar${tone ? ` ${tone}` : ""}`}>
        <span style={{ width: `${pct}%` }}></span>
      </div>
      {note && (
        <div className="tiny t3" style={{ marginTop: 6 }}>
          {note}
        </div>
      )}
    </div>
  );
}

// Driver cell for tables
type DriverCellProps = {
  name: string;
  num?: number;
  isPlayer?: boolean;
  driverId?: string;
};

export function DriverCell({ name, num, isPlayer, driverId }: DriverCellProps) {
  const [imgError, setImgError] = useState(false);
  const initials = name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const imageUrl = driverId ? `/drivers/faces/${driverId}.webp` : null;
  const showImage = imageUrl && !imgError;

  return (
    <div className="driver-cell">
      {num !== undefined && <span className="driver-num">{num}</span>}
      <span
        className="driver-avatar"
        style={
          isPlayer
            ? { background: "var(--accent-bg)", borderColor: "var(--accent-line)", color: "var(--accent)" }
            : undefined
        }
      >
        {showImage ? (
          <img
            src={imageUrl}
            alt={name}
            onError={() => setImgError(true)}
            style={{ width: "100%", height: "100%", objectFit: "cover", borderRadius: "inherit" }}
          />
        ) : (
          initials
        )}
      </span>
      <span className="driver-name">{name}</span>
    </div>
  );
}
