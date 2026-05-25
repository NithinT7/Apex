"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PageHeader, Card, Stat, Chip, Bar, Button, ConfidenceDots } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";
import * as api from "@/lib/api";

export default function DashboardPage() {
  const { currentSave, getPlayerDriver, getPlayerTeam, getCurrentRound, refreshSave } = useSave();
  const router = useRouter();
  const player = getPlayerDriver();
  const team = getPlayerTeam();
  const currentRound = getCurrentRound();

  const [showFocusModal, setShowFocusModal] = useState(false);
  const [showScoutingModal, setShowScoutingModal] = useState(false);
  const [showFocusOutcome, setShowFocusOutcome] = useState<api.FocusOutcome | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const [activeFocus, setActiveFocus] = useState<api.WeeklyFocus | null>(null);

  // Load active focus on mount
  useEffect(() => {
    if (currentSave?.saveId) {
      loadActiveFocus();
    }
  }, [currentSave?.saveId, currentSave?.developmentProfile?.activeFocusId]);

  async function loadActiveFocus() {
    if (!currentSave?.saveId) return;
    try {
      const data = await api.getAvailableFocuses(currentSave.saveId);
      if (data.activeFocusId) {
        const activeItem = data.availableFocuses.find(f => f.focus.id === data.activeFocusId);
        setActiveFocus(activeItem?.focus || null);
      } else {
        setActiveFocus(null);
      }
    } catch (err) {
      console.error("Failed to load active focus:", err);
    }
  }

  async function handleAdvanceWeek() {
    if (!currentSave?.saveId || advancing) return;

    try {
      setAdvancing(true);

      // If there's an active focus, apply it first to get the outcome
      if (activeFocus) {
        const focusResult = await api.applyFocus(currentSave.saveId);
        if (focusResult.success && focusResult.outcome) {
          setShowFocusOutcome(focusResult.outcome);
        }
      }

      // Skip to race week
      await api.skipToRaceWeek(currentSave.saveId);
      await refreshSave();
      setActiveFocus(null);

      // If no focus outcome to show, navigate to race weekend
      if (!activeFocus) {
        router.push("/race-weekend");
      }
    } catch (err) {
      console.error("Failed to advance week:", err);
    } finally {
      setAdvancing(false);
    }
  }

  // If no career, show empty state
  if (!player) {
    return <EmptyState />;
  }

  const standings = currentSave?.standings.driverStandings || [];
  const playerStanding = standings.find((s) => s.driverId === player.id);
  const playerPosition = playerStanding
    ? standings.indexOf(playerStanding) + 1
    : null;
  const leader = standings[0];
  const pointsToLeader = leader && playerStanding
    ? leader.points - playerStanding.points
    : 0;

  const totalRounds = currentSave?.calendar.length || 0;
  const roundNumber = currentRound?.roundNumber || 1;

  const canAdvance = currentSave?.phase === "between_races" || currentSave?.phase === "preseason";

  return (
    <div>
      <PageHeader
        title={`Good morning, ${player.name.split(" ")[0]}.`}
        question={`Round ${roundNumber} of ${totalRounds} · ${currentRound?.name || "Next Race"}`}
        actions={
          canAdvance ? (
            <Button kind="primary" size="md" onClick={handleAdvanceWeek} disabled={advancing}>
              {advancing ? "Advancing..." : "Advance week"}
            </Button>
          ) : (
            <Link href="/race-weekend" style={{ textDecoration: "none" }}>
              <Button kind="primary" size="md">Enter race weekend</Button>
            </Link>
          )
        }
      />

      {/* Hero - compact single row */}
      <div style={{
        background: "var(--bg-2)",
        border: "1px solid var(--line-1)",
        borderRadius: "var(--r-3)",
        padding: "20px 24px",
        marginBottom: 16,
        display: "grid",
        gridTemplateColumns: "minmax(0, 1.4fr) repeat(3, minmax(0, 1fr))",
        gap: 24,
        alignItems: "center",
      }}>
        <div style={{
          fontSize: 17, color: "var(--t-1)", lineHeight: 1.4, fontWeight: 500,
          letterSpacing: "-0.01em",
        }}>
          You're <span style={{ color: "var(--accent)" }}>P{playerPosition || "?"}</span> in {player.series}.
          {" "}Keep pushing this weekend.
        </div>
        <QuietStat label="Championship" value={`P${playerPosition || "?"}`} sub={pointsToLeader > 0 ? `−${pointsToLeader} to leader` : "Leading"} />
        <QuietStat label="Form" value={player.currentForm.toString()} max="/100" sub="Current form" />
        <QuietStat label="Morale" value={player.morale.toString()} max="/100" sub="Driver morale" />
      </div>

      {/* Three-column main */}
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
        <NextRaceCard round={currentRound} />
        <WeeklyFocusCard
          saveId={currentSave?.saveId}
          phase={currentSave?.phase}
          activeFocus={activeFocus}
          onActivate={() => setShowFocusModal(true)}
        />
        <RumorCard onOpen={() => setShowScoutingModal(true)} />
      </div>

      {/* Focus Selection Modal */}
      {showFocusModal && currentSave && (
        <FocusModal
          saveId={currentSave.saveId}
          onClose={() => setShowFocusModal(false)}
          onSelect={async () => {
            await refreshSave();
            await loadActiveFocus();
            setShowFocusModal(false);
          }}
        />
      )}

      {/* Focus Outcome Modal */}
      {showFocusOutcome && (
        <FocusOutcomeModal
          outcome={showFocusOutcome}
          onClose={() => {
            setShowFocusOutcome(null);
            router.push("/race-weekend");
          }}
        />
      )}

      {/* Scouting Modal */}
      {showScoutingModal && (
        <ScoutingModal onClose={() => setShowScoutingModal(false)} />
      )}

      {/* Compact standings strip */}
      <StandingsStrip standings={standings} playerId={player.id} />
    </div>
  );
}

function EmptyState() {
  const { saves, loadSave, loading } = useSave();
  const router = useRouter();
  const [loadingSaveId, setLoadingSaveId] = useState<string | null>(null);

  async function handleLoadSave(saveId: string) {
    setLoadingSaveId(saveId);
    try {
      await loadSave(saveId);
      router.push("/");
    } catch (err) {
      console.error("Failed to load save:", err);
      setLoadingSaveId(null);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: 40,
    }}>
      {/* Logo */}
      <div style={{
        width: 64,
        height: 64,
        borderRadius: 16,
        background: "var(--accent)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        marginBottom: 24,
      }}>
        <svg viewBox="0 0 24 24" width="40" height="40">
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

      <h1 style={{
        margin: "0 0 8px",
        fontSize: 36,
        fontWeight: 700,
        color: "var(--t-1)",
        letterSpacing: "-0.03em",
      }}>
        APEX
      </h1>
      <p style={{
        color: "var(--t-3)",
        fontSize: 15,
        marginBottom: 40,
        textAlign: "center",
        maxWidth: 400,
        lineHeight: 1.5,
      }}>
        Your journey from Formula 2 to Formula 1.
        Make decisions, develop your skills, and chase the championship.
      </p>

      <div style={{ display: "flex", gap: 16, marginBottom: 48 }}>
        <Link href="/create-driver" style={{ textDecoration: "none" }}>
          <Button kind="primary" size="lg">
            New Career
          </Button>
        </Link>
      </div>

      {/* Existing saves */}
      {saves.length > 0 && (
        <div style={{ width: "100%", maxWidth: 500 }}>
          <div style={{
            fontSize: 11,
            fontWeight: 600,
            color: "var(--t-4)",
            letterSpacing: "0.05em",
            marginBottom: 12,
            textAlign: "center",
          }}>
            CONTINUE CAREER
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {saves.slice(0, 5).map((save) => (
              <button
                key={save.saveId}
                onClick={() => handleLoadSave(save.saveId)}
                disabled={loadingSaveId !== null}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "14px 18px",
                  background: "var(--bg-2)",
                  border: "1px solid var(--line-1)",
                  borderRadius: "var(--r-2)",
                  cursor: loadingSaveId ? "wait" : "pointer",
                  opacity: loadingSaveId && loadingSaveId !== save.saveId ? 0.5 : 1,
                  transition: "all 0.15s",
                }}
              >
                <div style={{ textAlign: "left" }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: "var(--t-1)" }}>
                    {save.name}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--t-3)", marginTop: 2 }}>
                    Season {save.season} · {save.phase.replace("_", " ")}
                  </div>
                </div>
                <div style={{ fontSize: 12, color: "var(--t-3)" }}>
                  {loadingSaveId === save.saveId ? "Loading..." : "→"}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QuietStat({ label, value, max, sub }: { label: string; value: string; max?: string; sub: string }) {
  return (
    <div>
      <div style={{ color: "var(--t-3)", fontSize: 11.5, marginBottom: 6, fontWeight: 500 }}>{label}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 3 }}>
        <span className="mono" style={{ fontSize: 32, color: "var(--t-1)", fontWeight: 600, lineHeight: 1, letterSpacing: "-0.025em" }}>{value}</span>
        {max && <span className="mono" style={{ color: "var(--t-3)", fontSize: 14 }}>{max}</span>}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--t-3)", marginTop: 6 }}>{sub}</div>
    </div>
  );
}

function NextRaceCard({ round }: { round: { name: string; country: string } | null }) {
  return (
    <div style={{
      background: "var(--bg-2)",
      border: "1px solid var(--line-1)",
      borderRadius: "var(--r-3)",
      overflow: "hidden",
      display: "flex", flexDirection: "column",
    }}>
      <div style={{
        padding: "18px 20px 14px",
        borderBottom: "1px solid var(--line-1)",
        flexShrink: 0,
      }}>
        <div style={{ fontSize: 10.5, color: "var(--t-3)", fontWeight: 500, marginBottom: 6 }}>Up next</div>
        <div style={{ fontSize: 22, fontWeight: 600, color: "var(--t-1)", letterSpacing: "-0.02em", lineHeight: 1.1 }}>
          {round?.name || "Next Race"}
        </div>
      </div>

      <div style={{ padding: "14px 18px", flex: 1, display: "flex", flexDirection: "column" }}>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 0, marginBottom: 14 }}>
          <FactCell label="Car fit" value="Strong" first />
          <FactCell label="Overtaking" value="Medium" />
          <FactCell label="Qualifying" value="Important" />
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: "auto" }}>
          <Link href="/race-weekend" style={{ flex: 1, textDecoration: "none" }}>
            <Button kind="secondary" size="sm" full>Weekend hub</Button>
          </Link>
          <Link href="/race-weekend" style={{ flex: 1, textDecoration: "none" }}>
            <Button kind="primary" size="sm" full>Enter practice</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

function FactCell({ label, value, first }: { label: string; value: string; first?: boolean }) {
  return (
    <div style={{ paddingLeft: first ? 0 : 12, paddingRight: 12, borderLeft: first ? "none" : "1px solid var(--line-1)" }}>
      <div style={{ fontSize: 10.5, color: "var(--t-3)", marginBottom: 4, fontWeight: 500 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t-1)" }}>{value}</div>
    </div>
  );
}

function WeeklyFocusCard({
  phase,
  activeFocus,
  onActivate,
}: {
  saveId?: string;
  phase?: string;
  activeFocus: api.WeeklyFocus | null;
  onActivate: () => void;
}) {
  const canActivate = phase === "between_races" || phase === "preseason";
  const hasActiveFocus = !!activeFocus;

  return (
    <div style={{
      background: "var(--bg-2)",
      border: hasActiveFocus ? "1px solid var(--electric)" : "1px solid var(--line-1)",
      borderRadius: "var(--r-3)",
      padding: 18,
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ fontSize: 10.5, color: hasActiveFocus ? "var(--electric)" : "var(--t-3)", marginBottom: 6, fontWeight: 500 }}>
        {hasActiveFocus ? "Focus active" : "This week, focus on"}
      </div>
      <h3 style={{ margin: "0 0 10px", fontSize: 18, fontWeight: 600, color: "var(--t-1)", letterSpacing: "-0.015em" }}>
        {activeFocus?.name || "Choose a focus"}
      </h3>
      <p style={{ margin: "0 0 14px", fontSize: 12.5, color: "var(--t-2)", lineHeight: 1.5, flex: 1 }}>
        {activeFocus?.description || activeFocus?.flavorText || "Select a training focus to gain XP and improve your skills before the race weekend."}
      </p>
      <Button
        kind={hasActiveFocus ? "secondary" : "primary"}
        size="sm"
        full
        onClick={onActivate}
        disabled={!canActivate}
      >
        {!canActivate ? "Focus locked during race week" : hasActiveFocus ? "Change focus" : "Choose focus"}
      </Button>
    </div>
  );
}

function RumorCard({ onOpen }: { onOpen: () => void }) {
  return (
    <div style={{
      background: "var(--bg-2)",
      border: "1px solid var(--line-1)",
      borderRadius: "var(--r-3)",
      padding: 18,
      display: "flex", flexDirection: "column",
    }}>
      <div style={{ fontSize: 10.5, color: "var(--t-3)", marginBottom: 6, fontWeight: 500 }}>On your radar</div>
      <h3 style={{ margin: "0 0 10px", fontSize: 17, fontWeight: 600, color: "var(--t-1)", letterSpacing: "-0.015em", lineHeight: 1.3 }}>
        F1 teams watching.
      </h3>
      <div style={{ marginBottom: 10 }}>
        <ConfidenceDots level={2} />
      </div>
      <p style={{ margin: "0 0 14px", fontSize: 12.5, color: "var(--t-2)", lineHeight: 1.5, flex: 1 }}>
        Keep performing well to attract more attention from F1 scouts.
      </p>
      <Button kind="secondary" size="sm" full onClick={onOpen}>Open scouting</Button>
    </div>
  );
}

interface StandingEntry {
  driverId: string;
  points: number;
}

function StandingsStrip({ standings, playerId }: { standings: StandingEntry[]; playerId: string }) {
  const { getDriver, getTeam } = useSave();

  return (
    <div style={{
      background: "var(--bg-2)",
      border: "1px solid var(--line-1)",
      borderRadius: "var(--r-3)",
      padding: "10px 14px",
      display: "flex", alignItems: "center", gap: 22, overflowX: "auto",
    }}>
      <div style={{ fontSize: 11, color: "var(--t-3)", fontWeight: 500, flexShrink: 0, paddingRight: 8, borderRight: "1px solid var(--line-1)" }}>
        Standings
      </div>
      {standings.slice(0, 6).map((entry, index) => {
        const driver = getDriver(entry.driverId);
        const team = driver ? getTeam(driver.teamId) : null;
        const isPlayer = entry.driverId === playerId;
        const pos = index + 1;

        return (
          <div key={entry.driverId} style={{
            display: "flex", alignItems: "baseline", gap: 8, flexShrink: 0,
            background: isPlayer ? "rgba(61,190,115,0.07)" : "transparent",
            padding: isPlayer ? "4px 10px" : "4px 0",
            borderRadius: 6, whiteSpace: "nowrap",
          }}>
            <span className="mono" style={{ color: pos <= 3 ? "var(--t-1)" : "var(--t-3)", fontWeight: 600, fontSize: 12 }}>P{pos}</span>
            <span style={{ color: isPlayer ? "var(--t-1)" : "var(--t-2)", fontWeight: isPlayer ? 600 : 500, fontSize: 13 }}>
              {driver?.name.split(" ").pop() || "Unknown"}
            </span>
            <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: 999, background: "#666" }} />
            <span className="mono" style={{ color: "var(--t-1)", fontWeight: 500, fontSize: 12 }}>{entry.points}</span>
          </div>
        );
      })}
      <Link href="/standings" style={{ marginLeft: "auto", color: "var(--electric)", fontSize: 12, cursor: "pointer", flexShrink: 0, textDecoration: "none" }}>
        Full table
      </Link>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Modals
// ─────────────────────────────────────────────────────────────

function FocusModal({
  saveId,
  onClose,
  onSelect,
}: {
  saveId: string;
  onClose: () => void;
  onSelect: () => void;
}) {
  const [focusItems, setFocusItems] = useState<api.FocusItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selecting, setSelecting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeFocusId, setActiveFocusId] = useState<string | null>(null);

  useEffect(() => {
    loadFocuses();
  }, [saveId]);

  async function loadFocuses() {
    try {
      setLoading(true);
      const data = await api.getAvailableFocuses(saveId);
      setFocusItems(data.availableFocuses || []);
      setActiveFocusId(data.activeFocusId);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load focuses");
    } finally {
      setLoading(false);
    }
  }

  async function handleSelect(focusId: string) {
    try {
      setSelecting(focusId);
      await api.selectFocus(saveId, focusId);
      onSelect();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to select focus");
      setSelecting(null);
    }
  }

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.7)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: "var(--bg-1)",
        border: "1px solid var(--line-1)",
        borderRadius: "var(--r-3)",
        padding: 24,
        width: "100%",
        maxWidth: 500,
        maxHeight: "80vh",
        overflow: "auto",
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: "var(--t-1)" }}>Weekly Focus</h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--t-3)",
              cursor: "pointer",
              fontSize: 20,
              padding: 4,
            }}
          >
            ×
          </button>
        </div>

        {error && (
          <div style={{
            background: "rgba(232,88,88,0.1)",
            border: "1px solid rgba(232,88,88,0.3)",
            borderRadius: "var(--r-2)",
            padding: "10px 14px",
            marginBottom: 16,
            color: "var(--bad)",
            fontSize: 13,
          }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--t-3)" }}>Loading focuses...</div>
        ) : focusItems.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--t-3)" }}>No focuses available</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {focusItems.map((item) => {
              const focus = item.focus;
              const isActive = activeFocusId === focus.id;
              return (
                <button
                  key={focus.id}
                  onClick={() => handleSelect(focus.id)}
                  disabled={selecting !== null || !item.isAvailable}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: "14px 16px",
                    background: isActive ? "rgba(90,169,240,0.1)" : "var(--bg-2)",
                    border: `1px solid ${isActive ? "var(--electric)" : "var(--line-1)"}`,
                    borderRadius: "var(--r-2)",
                    textAlign: "left",
                    cursor: selecting || !item.isAvailable ? "not-allowed" : "pointer",
                    opacity: (selecting && selecting !== focus.id) || !item.isAvailable ? 0.5 : 1,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <span style={{ fontSize: 14, fontWeight: 600, color: "var(--t-1)" }}>
                      {focus.name}
                    </span>
                    {isActive && (
                      <span style={{ fontSize: 10, color: "var(--good)", fontWeight: 600, background: "rgba(61,190,115,0.15)", padding: "2px 6px", borderRadius: 4 }}>ACTIVE</span>
                    )}
                    {item.isRecommended && !isActive && (
                      <span style={{ fontSize: 10, color: "var(--electric)", fontWeight: 600, background: "rgba(90,169,240,0.15)", padding: "2px 6px", borderRadius: 4 }}>RECOMMENDED</span>
                    )}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--t-2)", lineHeight: 1.4 }}>
                    {focus.description}
                  </div>
                  <div style={{ fontSize: 11, color: "var(--t-3)", marginTop: 6 }}>
                    +{focus.primaryXpAmount} XP · {focus.category}
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function FocusOutcomeModal({
  outcome,
  onClose,
}: {
  outcome: api.FocusOutcome;
  onClose: () => void;
}) {
  const totalXp = Object.values(outcome.xpGained).reduce((a, b) => a + b, 0);
  const hasAttributeChanges = Object.keys(outcome.attributeChanges).length > 0;

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.7)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: "var(--bg-1)",
        border: `1px solid ${outcome.success ? "var(--good)" : "var(--bad)"}`,
        borderRadius: "var(--r-3)",
        padding: 24,
        width: "100%",
        maxWidth: 450,
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
          <div style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: outcome.success ? "rgba(61,190,115,0.15)" : "rgba(232,88,88,0.15)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 18,
          }}>
            {outcome.success ? "✓" : "!"}
          </div>
          <div>
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: "var(--t-1)" }}>
              {outcome.focusName}
            </h2>
            <div style={{ fontSize: 11, color: outcome.success ? "var(--good)" : "var(--bad)", fontWeight: 500 }}>
              {outcome.success ? "Focus completed" : "Something went wrong"}
            </div>
          </div>
        </div>

        <p style={{ color: "var(--t-2)", fontSize: 13, marginBottom: 20, lineHeight: 1.6, fontStyle: "italic" }}>
          "{outcome.narrative}"
        </p>

        {/* XP Gains */}
        {totalXp > 0 && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "var(--t-3)", fontWeight: 500, marginBottom: 8 }}>XP Gained</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {Object.entries(outcome.xpGained).map(([branch, amount]) => (
                <div key={branch} style={{
                  background: "rgba(90,169,240,0.1)",
                  border: "1px solid rgba(90,169,240,0.3)",
                  borderRadius: 6,
                  padding: "6px 10px",
                  fontSize: 12,
                }}>
                  <span style={{ color: "var(--electric)", fontWeight: 600 }}>+{amount}</span>
                  <span style={{ color: "var(--t-2)", marginLeft: 4 }}>{branch.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Attribute Changes */}
        {hasAttributeChanges && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "var(--t-3)", fontWeight: 500, marginBottom: 8 }}>Attribute Changes</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {Object.entries(outcome.attributeChanges).map(([attr, change]) => (
                <div key={attr} style={{
                  background: change > 0 ? "rgba(61,190,115,0.1)" : "rgba(232,88,88,0.1)",
                  border: `1px solid ${change > 0 ? "rgba(61,190,115,0.3)" : "rgba(232,88,88,0.3)"}`,
                  borderRadius: 6,
                  padding: "6px 10px",
                  fontSize: 12,
                }}>
                  <span style={{ color: change > 0 ? "var(--good)" : "var(--bad)", fontWeight: 600 }}>
                    {change > 0 ? "+" : ""}{change}
                  </span>
                  <span style={{ color: "var(--t-2)", marginLeft: 4 }}>{attr.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Relationship/Academy Changes */}
        {(outcome.academyChange !== 0 || outcome.marketabilityChange !== 0) && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: "var(--t-3)", fontWeight: 500, marginBottom: 8 }}>Other Effects</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {outcome.academyChange !== 0 && (
                <div style={{
                  background: outcome.academyChange > 0 ? "rgba(61,190,115,0.1)" : "rgba(232,88,88,0.1)",
                  border: `1px solid ${outcome.academyChange > 0 ? "rgba(61,190,115,0.3)" : "rgba(232,88,88,0.3)"}`,
                  borderRadius: 6,
                  padding: "6px 10px",
                  fontSize: 12,
                }}>
                  <span style={{ color: outcome.academyChange > 0 ? "var(--good)" : "var(--bad)", fontWeight: 600 }}>
                    {outcome.academyChange > 0 ? "+" : ""}{outcome.academyChange}
                  </span>
                  <span style={{ color: "var(--t-2)", marginLeft: 4 }}>Academy Trust</span>
                </div>
              )}
              {outcome.marketabilityChange !== 0 && (
                <div style={{
                  background: outcome.marketabilityChange > 0 ? "rgba(61,190,115,0.1)" : "rgba(232,88,88,0.1)",
                  border: `1px solid ${outcome.marketabilityChange > 0 ? "rgba(61,190,115,0.3)" : "rgba(232,88,88,0.3)"}`,
                  borderRadius: 6,
                  padding: "6px 10px",
                  fontSize: 12,
                }}>
                  <span style={{ color: outcome.marketabilityChange > 0 ? "var(--good)" : "var(--bad)", fontWeight: 600 }}>
                    {outcome.marketabilityChange > 0 ? "+" : ""}{outcome.marketabilityChange}
                  </span>
                  <span style={{ color: "var(--t-2)", marginLeft: 4 }}>Marketability</span>
                </div>
              )}
            </div>
          </div>
        )}

        <Button kind="primary" size="md" full onClick={onClose}>
          Continue to Race Weekend
        </Button>
      </div>
    </div>
  );
}

function ScoutingModal({ onClose }: { onClose: () => void }) {
  const { currentSave, getPlayerDriver } = useSave();
  const player = getPlayerDriver();
  const [scoutingData, setScoutingData] = useState<api.ScoutingSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [expandedTeam, setExpandedTeam] = useState<string | null>(null);

  useEffect(() => {
    if (currentSave?.saveId) {
      loadScoutingData();
    }
  }, [currentSave?.saveId]);

  async function loadScoutingData() {
    if (!currentSave?.saveId) return;
    try {
      setLoading(true);
      const data = await api.getScoutingSummary(currentSave.saveId);
      setScoutingData(data);
    } catch (err) {
      console.error("Failed to load scouting data:", err);
    } finally {
      setLoading(false);
    }
  }

  function getInterestDots(level: number): number {
    if (level >= 75) return 4;
    if (level >= 55) return 3;
    if (level >= 35) return 2;
    if (level >= 15) return 1;
    return 0;
  }

  function getTierColor(tier: string): string {
    switch (tier) {
      case "pursuing": return "var(--good)";
      case "very_interested": return "var(--electric)";
      case "interested": return "var(--accent)";
      case "watching": return "var(--t-2)";
      default: return "var(--t-3)";
    }
  }

  function getTierLabel(tier: string): string {
    switch (tier) {
      case "pursuing": return "Pursuing";
      case "very_interested": return "Very Interested";
      case "interested": return "Interested";
      case "watching": return "Watching";
      default: return "No Interest";
    }
  }

  // Not an F2 driver
  if (player?.series !== "F2") {
    return (
      <div style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
      }} onClick={onClose}>
        <div style={{
          background: "var(--bg-1)",
          border: "1px solid var(--line-1)",
          borderRadius: "var(--r-3)",
          padding: 24,
          width: "100%",
          maxWidth: 450,
          textAlign: "center",
        }} onClick={(e) => e.stopPropagation()}>
          <div style={{ fontSize: 40, marginBottom: 16 }}>🏎️</div>
          <h2 style={{ margin: "0 0 12px", fontSize: 18, fontWeight: 600, color: "var(--t-1)" }}>
            You're already in F1!
          </h2>
          <p style={{ color: "var(--t-2)", fontSize: 13, marginBottom: 20, lineHeight: 1.5 }}>
            Scouting reports are for F2 drivers looking to move up. Focus on proving yourself in Formula 1.
          </p>
          <Button kind="secondary" size="md" onClick={onClose}>Close</Button>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      position: "fixed",
      inset: 0,
      background: "rgba(0,0,0,0.7)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
    }} onClick={onClose}>
      <div style={{
        background: "var(--bg-1)",
        border: "1px solid var(--line-1)",
        borderRadius: "var(--r-3)",
        padding: 24,
        width: "100%",
        maxWidth: 550,
        maxHeight: "85vh",
        overflow: "auto",
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <h2 style={{ margin: 0, fontSize: 20, fontWeight: 600, color: "var(--t-1)" }}>F1 Scouting Report</h2>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "var(--t-3)",
              cursor: "pointer",
              fontSize: 20,
              padding: 4,
            }}
          >
            ×
          </button>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--t-3)" }}>Loading scouting data...</div>
        ) : !scoutingData?.available ? (
          <div style={{ textAlign: "center", padding: 40, color: "var(--t-3)" }}>
            {scoutingData?.message || "No scouting data available"}
          </div>
        ) : (
          <>
            {/* Summary Stats */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: 12,
              marginBottom: 20,
              padding: "14px 16px",
              background: "var(--bg-2)",
              borderRadius: "var(--r-2)",
            }}>
              <div>
                <div style={{ fontSize: 10, color: "var(--t-3)", fontWeight: 500, marginBottom: 4 }}>
                  Championship
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, color: "var(--t-1)" }}>
                  P{scoutingData.playerPosition || "?"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--t-3)", fontWeight: 500, marginBottom: 4 }}>
                  Seats Open
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, color: scoutingData.seatsAvailable ? "var(--good)" : "var(--bad)" }}>
                  {scoutingData.seatsAvailable || 0}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--t-3)", fontWeight: 500, marginBottom: 4 }}>
                  Realistic Chances
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, color: scoutingData.realisticOpportunities ? "var(--good)" : "var(--t-2)" }}>
                  {scoutingData.realisticOpportunities || 0}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: "var(--t-3)", fontWeight: 500, marginBottom: 4 }}>
                  Teams Watching
                </div>
                <div style={{ fontSize: 18, fontWeight: 600, color: "var(--t-2)" }}>
                  {scoutingData.teamsWatching || 0}
                </div>
              </div>
            </div>

            {/* Heat Score */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 12, color: "var(--t-2)", fontWeight: 500 }}>Overall F1 Interest</span>
                <span style={{ fontSize: 12, color: "var(--t-1)", fontWeight: 600 }}>{scoutingData.heatScore || 0}%</span>
              </div>
              <div style={{
                height: 6,
                background: "var(--bg-3)",
                borderRadius: 3,
                overflow: "hidden",
              }}>
                <div style={{
                  height: "100%",
                  width: `${scoutingData.heatScore || 0}%`,
                  background: (scoutingData.heatScore || 0) >= 50 ? "var(--good)" : (scoutingData.heatScore || 0) >= 25 ? "var(--accent)" : "var(--t-3)",
                  borderRadius: 3,
                  transition: "width 0.3s ease",
                }} />
              </div>
            </div>

            {/* Team List */}
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {scoutingData.allTeams?.map((team) => (
                <div key={team.teamId}>
                  <button
                    onClick={() => setExpandedTeam(expandedTeam === team.teamId ? null : team.teamId)}
                    style={{
                      width: "100%",
                      padding: "12px 14px",
                      background: "var(--bg-2)",
                      border: team.interestLevel >= 35 ? `1px solid ${getTierColor(team.interestTier)}` : "1px solid var(--line-1)",
                      borderRadius: expandedTeam === team.teamId ? "var(--r-2) var(--r-2) 0 0" : "var(--r-2)",
                      textAlign: "left",
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: "var(--t-1)" }}>{team.teamName}</span>
                        {team.isAcademyTeam && (
                          <span style={{
                            fontSize: 9,
                            color: "var(--electric)",
                            background: "rgba(90,169,240,0.15)",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontWeight: 600,
                          }}>ACADEMY</span>
                        )}
                        {team.seatAvailable ? (
                          <span style={{
                            fontSize: 9,
                            color: "var(--good)",
                            background: "rgba(61,190,115,0.15)",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontWeight: 600,
                          }}>SEAT OPEN</span>
                        ) : (
                          <span style={{
                            fontSize: 9,
                            color: "var(--t-3)",
                            background: "var(--bg-3)",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontWeight: 600,
                          }}>NO SEAT</span>
                        )}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                        <span style={{
                          fontSize: 11,
                          color: getTierColor(team.interestTier),
                          fontWeight: 500,
                        }}>
                          {getTierLabel(team.interestTier)}
                        </span>
                        <ConfidenceDots level={getInterestDots(team.interestLevel)} />
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: "var(--t-3)", marginTop: 6 }}>
                      {team.seatAvailabilityNote}
                    </div>
                  </button>

                  {/* Expanded Details */}
                  {expandedTeam === team.teamId && (
                    <div style={{
                      padding: "12px 14px",
                      background: "var(--bg-3)",
                      border: "1px solid var(--line-1)",
                      borderTop: "none",
                      borderRadius: "0 0 var(--r-2) var(--r-2)",
                    }}>
                      {/* Current Drivers */}
                      {team.currentDrivers && team.currentDrivers.length > 0 && (
                        <div style={{ marginBottom: 12 }}>
                          <div style={{ fontSize: 10, color: "var(--t-3)", fontWeight: 500, marginBottom: 6 }}>Current Drivers</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                            {team.currentDrivers.map((driver) => (
                              <div key={driver.driverId} style={{
                                display: "flex",
                                justifyContent: "space-between",
                                alignItems: "center",
                                padding: "6px 10px",
                                background: driver.isAtRisk ? "rgba(232,88,88,0.08)" : "var(--bg-2)",
                                border: driver.isAtRisk ? "1px solid rgba(232,88,88,0.2)" : "1px solid var(--line-1)",
                                borderRadius: 6,
                              }}>
                                <div>
                                  <span style={{ fontSize: 12, fontWeight: 500, color: "var(--t-1)" }}>
                                    {driver.driverName}
                                  </span>
                                  {driver.isAtRisk && (
                                    <span style={{
                                      fontSize: 9,
                                      color: "var(--bad)",
                                      background: "rgba(232,88,88,0.15)",
                                      padding: "1px 5px",
                                      borderRadius: 3,
                                      fontWeight: 600,
                                      marginLeft: 6,
                                    }}>AT RISK</span>
                                  )}
                                </div>
                                <div style={{ fontSize: 10, color: "var(--t-3)", textAlign: "right" }}>
                                  {driver.statusNote}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
                        <div>
                          <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 4 }}>Car Performance</div>
                          <div style={{ fontSize: 13, color: "var(--t-1)", fontWeight: 500 }}>{team.carPerformance}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 10, color: "var(--t-3)", marginBottom: 4 }}>Team Tier</div>
                          <div style={{ fontSize: 13, color: "var(--t-1)", fontWeight: 500, textTransform: "capitalize" }}>
                            {team.teamTier.replace(/_/g, " ")}
                          </div>
                        </div>
                      </div>

                      {team.reasons.length > 0 && (
                        <div style={{ marginBottom: 10 }}>
                          <div style={{ fontSize: 10, color: "var(--good)", fontWeight: 500, marginBottom: 4 }}>Positives</div>
                          {team.reasons.map((reason, i) => (
                            <div key={i} style={{ fontSize: 11, color: "var(--t-2)", marginBottom: 2 }}>+ {reason}</div>
                          ))}
                        </div>
                      )}

                      {team.concerns.length > 0 && (
                        <div style={{ marginBottom: 10 }}>
                          <div style={{ fontSize: 10, color: "var(--bad)", fontWeight: 500, marginBottom: 4 }}>Concerns</div>
                          {team.concerns.map((concern, i) => (
                            <div key={i} style={{ fontSize: 11, color: "var(--t-2)", marginBottom: 2 }}>- {concern}</div>
                          ))}
                        </div>
                      )}

                      {team.requirements.length > 0 && (
                        <div>
                          <div style={{ fontSize: 10, color: "var(--electric)", fontWeight: 500, marginBottom: 4 }}>To Improve Interest</div>
                          {team.requirements.map((req, i) => (
                            <div key={i} style={{ fontSize: 11, color: "var(--t-2)", marginBottom: 2 }}>→ {req}</div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Tips */}
            <div style={{ marginTop: 16, padding: "12px 14px", background: "rgba(90,169,240,0.08)", borderRadius: "var(--r-2)" }}>
              <div style={{ fontSize: 12, color: "var(--t-2)", lineHeight: 1.5 }}>
                <strong style={{ color: "var(--t-1)" }}>How it works:</strong> F1 teams evaluate your championship position, overall rating, marketability, and academy connections. Top teams are very selective - only exceptional F2 champions get direct offers from title contenders.
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
