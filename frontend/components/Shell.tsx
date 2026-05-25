"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { useSave } from "@/lib/SaveContext";

// Pages that should always show without the shell (landing/create pages)
const SHELL_EXCLUDED_PATHS = ["/create-driver", "/start"];

const NAV = [
  {
    group: "Career",
    items: [
      { id: "dashboard", name: "Dashboard", href: "/" },
      { id: "driver", name: "Development", href: "/driver" },
      { id: "car", name: "Car Performance", href: "/car" },
    ],
  },
  {
    group: "Weekend",
    items: [
      { id: "weekend", name: "Race Weekend", href: "/race-weekend" },
    ],
  },
  {
    group: "Paddock",
    items: [
      { id: "contracts", name: "Contracts", href: "/contracts" },
      { id: "silly", name: "Silly Season", href: "/silly-season" },
      { id: "news", name: "News", href: "/news" },
    ],
  },
];

const NAV_ICONS: Record<string, string> = {
  dashboard: "◧",
  driver: "◊",
  car: "◉",
  weekend: "◐",
  contracts: "▤",
  silly: "▥",
  news: "▦",
};

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { currentSave, loading } = useSave();

  const isExcludedPath = SHELL_EXCLUDED_PATHS.some((p) => pathname.startsWith(p));
  const hasNoSave = !currentSave && !loading;

  // If no save and not on an excluded path, redirect to start page
  useEffect(() => {
    if (hasNoSave && !isExcludedPath && pathname !== "/") {
      router.replace("/");
    }
  }, [hasNoSave, isExcludedPath, pathname, router]);

  // Show fullscreen layout for excluded paths or when no save is loaded
  if (isExcludedPath || hasNoSave) {
    return (
      <div className="apex-fullscreen">
        {children}
      </div>
    );
  }

  return (
    <div className="apex-app">
      <Sidebar />
      <div className="apex-main" style={{ marginLeft: "var(--sb-w)" }}>
        <TopBar />
        <main className="apex-content">{children}</main>
      </div>
    </div>
  );
}

function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="apex-sidebar">
      {/* Brand */}
      <div
        style={{
          padding: "20px 18px 16px",
          borderBottom: "1px solid var(--line-1)",
          display: "flex",
          alignItems: "center",
          gap: 11,
        }}
      >
        <div
          style={{
            width: 30,
            height: 30,
            borderRadius: 8,
            background: "var(--accent)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <svg viewBox="0 0 24 24" width="22" height="22">
            <path
              d="M 5 21 L 9.5 6.5 Q 10.5 3, 12 3 Q 13.5 3, 14.5 6.5 L 19 21"
              stroke="#fff"
              strokeWidth="2.2"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx="5" cy="21" r="1.2" fill="#fff" />
          </svg>
        </div>
        <div className="sidebar-label">
          <div style={{ fontSize: 15, fontWeight: 700, letterSpacing: "0.04em", color: "var(--t-1)" }}>
            APEX
          </div>
          <div style={{ fontSize: 11, color: "var(--t-3)" }}>Driver Career</div>
        </div>
      </div>

      {/* Nav */}
      <nav style={{ flex: 1, overflowY: "auto", padding: "12px 0" }}>
        {NAV.map((group) => (
          <div key={group.group} style={{ marginBottom: 12 }}>
            <div
              className="sidebar-label"
              style={{
                fontSize: 11,
                fontWeight: 600,
                color: "var(--t-4)",
                padding: "6px 18px",
                letterSpacing: "0.04em",
              }}
            >
              {group.group}
            </div>
            {group.items.map((item) => {
              const active = pathname === item.href;
              return (
                <Link
                  key={item.id}
                  href={item.href}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    padding: "8px 18px",
                    background: active ? "rgba(236,58,76,0.10)" : "transparent",
                    borderLeft: active ? "2px solid var(--accent)" : "2px solid transparent",
                    color: active ? "var(--t-1)" : "var(--t-2)",
                    fontSize: 13,
                    fontWeight: active ? 600 : 500,
                    textDecoration: "none",
                    transition: "background 0.15s",
                  }}
                >
                  <span
                    style={{
                      width: 18,
                      color: active ? "var(--accent)" : "var(--t-3)",
                      fontFamily: "var(--font-mono)",
                      fontSize: 12,
                      textAlign: "center",
                    }}
                  >
                    {NAV_ICONS[item.id]}
                  </span>
                  <span className="sidebar-label">{item.name}</span>
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Footer */}
      <div style={{ padding: "14px 14px 18px", borderTop: "1px solid var(--line-1)" }}>
        <Link
          href="/race-weekend"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            width: "100%",
            padding: "11px 14px",
            background: "var(--accent)",
            color: "#fff",
            borderRadius: "var(--r-2)",
            fontSize: 13,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          <span style={{ fontSize: 10 }}>▶</span>
          <span className="sidebar-label">Continue</span>
        </Link>
      </div>
    </aside>
  );
}

function TopBar() {
  const { currentSave, getPlayerDriver, getPlayerTeam, getCurrentRound } = useSave();
  const player = getPlayerDriver();
  const team = getPlayerTeam();
  const currentRound = getCurrentRound();

  const hasCareer = !!player;
  const totalRounds = currentSave?.calendar.length || 0;
  const roundNumber = currentRound?.roundNumber || 1;
  const series = player?.series || "F2";
  const season = currentSave?.season || 2025;

  return (
    <header className="apex-topbar">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div
          style={{
            width: 34,
            height: 34,
            borderRadius: 8,
            background: "var(--bg-3)",
            border: "1px solid var(--line-2)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontFamily: "var(--font-mono)",
            fontWeight: 700,
            color: "var(--accent)",
            fontSize: 14,
          }}
        >
          {player?.driverNumber || "?"}
        </div>
        <div>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--t-1)", lineHeight: 1.2 }}>
            {player?.name || "No Career"}
          </div>
          <div style={{ fontSize: 11, color: "var(--t-3)", lineHeight: 1.2, marginTop: 1 }}>
            {team?.name || "Create a driver to start"}
          </div>
        </div>
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 14, color: "var(--t-3)", fontSize: 13 }}>
        <span>{season} Formula {series === "F1" ? "1" : "2"}</span>
        <span style={{ color: "var(--t-4)" }}>·</span>
        <span>Round {roundNumber} of {totalRounds}</span>
      </div>

      {!hasCareer && (
        <Link
          href="/create-driver"
          className="btn primary"
          style={{ textDecoration: "none" }}
        >
          Create Driver
        </Link>
      )}
    </header>
  );
}
