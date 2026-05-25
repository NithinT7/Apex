"use client";

import { useState, useEffect } from "react";
import { PageHeader, Card, Section, Button, Chip, Bar, Stat } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";
import * as api from "@/lib/api";

interface NodeData {
  id: string;
  name: string;
  description: string;
  cost: number;
  tier: number;
  xpRequired: number;
  effects: {
    attributeBonuses: Record<string, number>;
  };
  unlocksTraitId: string | null;
}

interface NodeWrapper {
  node: NodeData;
  state: "locked" | "available" | "unlocked";
  canAfford: boolean;
}

interface SkillBranch {
  branchId: string;
  name: string;
  currentXp: number;
  nodes: NodeWrapper[];
}

interface SkillTreeState {
  branches: SkillBranch[];
  currentPoints: number;
  totalPointsEarned: number;
  recommendedNodes: string[];
}

export default function DevelopmentPage() {
  const { currentSave, getPlayerDriver, refreshSave } = useSave();
  const player = getPlayerDriver();
  const [branch, setBranch] = useState<string | null>(null);
  const [skillTree, setSkillTree] = useState<SkillTreeState | null>(null);
  const [loading, setLoading] = useState(true);
  const [unlocking, setUnlocking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (currentSave?.saveId) {
      loadSkillTree();
    }
  }, [currentSave?.saveId]);

  async function loadSkillTree() {
    if (!currentSave?.saveId) return;
    try {
      setLoading(true);
      const data = await api.getSkillTree(currentSave.saveId);
      setSkillTree(data);
      // Set default branch to first one
      if (data.branches.length > 0 && !branch) {
        setBranch(data.branches[0].branchId);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load skill tree");
    } finally {
      setLoading(false);
    }
  }

  async function handleUnlock(nodeId: string) {
    if (!currentSave?.saveId) return;
    try {
      setUnlocking(nodeId);
      const result = await api.unlockSkillNode(currentSave.saveId, nodeId);
      if (result.success) {
        await refreshSave();
        await loadSkillTree();
      } else {
        setError(result.message || "Failed to unlock");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to unlock skill");
    } finally {
      setUnlocking(null);
    }
  }

  if (!player) {
    return (
      <div>
        <PageHeader
          eyebrow="Driver Development"
          title="Development"
          question="How am I becoming a better driver?"
        />
        <Card style={{ padding: 40, textAlign: "center" }}>
          <p style={{ color: "var(--t-3)" }}>Create a driver to access development.</p>
        </Card>
      </div>
    );
  }

  const devProfile = currentSave?.developmentProfile;
  const devPoints = skillTree?.currentPoints ?? devProfile?.availablePoints ?? 0;
  const branches = skillTree?.branches || [];
  const currentBranch = branches.find((b) => b.branchId === branch) || branches[0];

  // Find the first recommended node from all branches
  const recommendedNodeIds = skillTree?.recommendedNodes || [];
  const recommendedWrapper = branches
    .flatMap((b) => b.nodes)
    .find((n) => recommendedNodeIds.includes(n.node.id) && n.state === "available");

  if (loading) {
    return (
      <div>
        <PageHeader
          eyebrow="RPG growth · your career progression"
          title="Development"
          question="How am I becoming a better driver?"
        />
        <Card style={{ padding: 40, textAlign: "center" }}>
          <p style={{ color: "var(--t-3)" }}>Loading skill tree...</p>
        </Card>
      </div>
    );
  }

  // Get nodes by state for current branch
  const unlockedNodes = currentBranch?.nodes.filter((n) => n.state === "unlocked") || [];
  const availableNodes = currentBranch?.nodes.filter((n) => n.state === "available") || [];
  const lockedNodes = currentBranch?.nodes.filter((n) => n.state === "locked") || [];

  // Get all unlocked traits across all branches
  const allTraits = branches.flatMap((b) =>
    b.nodes.filter((n) => n.node.unlocksTraitId && n.state === "unlocked")
  );

  return (
    <div>
      <PageHeader
        eyebrow="RPG growth · your career progression"
        title="Development"
        question="How am I becoming a better driver?"
      />

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

      {/* Hero: dev points + recommended unlock */}
      <Card pad={0} style={{
        marginBottom: 10,
        background: "linear-gradient(135deg, rgba(236,58,76,0.08), var(--bg-2) 60%)",
        borderColor: "rgba(236,58,76,0.25)",
      }}>
        <div style={{ padding: "16px 22px", display: "grid", gridTemplateColumns: "1fr 2fr", gap: 24, alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 11, color: "var(--t-3)", marginBottom: 4 }}>You have</div>
            <div className="mono" style={{ fontSize: 48, lineHeight: 1, fontWeight: 700, color: "var(--accent)", letterSpacing: "-0.025em" }}>
              {devPoints}
            </div>
            <div style={{ fontSize: 13, color: "var(--t-1)", marginTop: 4, fontWeight: 600 }}>development points</div>
            <div style={{ fontSize: 11, color: "var(--t-3)", marginTop: 2 }}>Spend on skills below.</div>
          </div>

          {recommendedWrapper ? (
            <div>
              <div style={{ fontSize: 11, color: "var(--t-3)", marginBottom: 6 }}>Recommended unlock</div>
              <div style={{ background: "var(--bg-3)", border: "1px solid rgba(236,58,76,0.35)", borderLeft: "3px solid var(--accent)", borderRadius: 6, padding: "12px 16px" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                  <span style={{ color: "var(--accent)", fontSize: 14 }}>★</span>
                  <h3 style={{ margin: 0, fontSize: 16, color: "var(--t-1)", fontWeight: 600 }}>{recommendedWrapper.node.name}</h3>
                  {recommendedWrapper.node.unlocksTraitId && <Chip tone="accent" style={{ marginLeft: "auto" }}>TRAIT</Chip>}
                </div>
                <div style={{ fontSize: 12, color: "var(--t-2)", marginBottom: 10, lineHeight: 1.4 }}>
                  {recommendedWrapper.node.description}
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                  <Button
                    kind="primary"
                    size="md"
                    onClick={() => handleUnlock(recommendedWrapper.node.id)}
                    disabled={unlocking !== null || devPoints < recommendedWrapper.node.cost}
                  >
                    {unlocking === recommendedWrapper.node.id ? "Unlocking..." : `Unlock for ${recommendedWrapper.node.cost} DP`}
                  </Button>
                  <span style={{ fontSize: 11, color: "var(--t-3)" }}>
                    {devPoints >= recommendedWrapper.node.cost ? `${devPoints - recommendedWrapper.node.cost} DP left` : `Need ${recommendedWrapper.node.cost - devPoints} more DP`}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div style={{ color: "var(--t-3)", fontSize: 13 }}>
              No recommendations available. Race more to earn XP and unlock new skills!
            </div>
          )}
        </div>
      </Card>

      {/* Branch picker + nodes */}
      <Section title="Browse skill branches" sub="Pick a discipline to develop">
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 18 }}>
          {branches.map((b) => {
            const active = b.branchId === branch;
            return (
              <button key={b.branchId} onClick={() => setBranch(b.branchId)} style={{
                padding: "8px 14px", borderRadius: "var(--r-2)",
                background: active ? "var(--accent)" : "var(--bg-3)",
                color: active ? "#fff" : "var(--t-2)",
                border: `1px solid ${active ? "var(--accent)" : "var(--line-2)"}`,
                cursor: "pointer", fontSize: 12, fontWeight: 600,
                display: "inline-flex", alignItems: "center", gap: 8,
                whiteSpace: "nowrap",
              }}>
                {b.name}
              </button>
            );
          })}
        </div>

        {currentBranch && (
          <Card pad={18}>
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 18 }}>
              <div style={{ flex: 1 }}>
                <h3 style={{ margin: 0, fontSize: 18, color: "var(--t-1)" }}>{currentBranch.name}</h3>
                <div style={{ fontSize: 11.5, color: "var(--t-3)", marginTop: 4 }}>Earn XP from races to unlock higher tiers</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
                <span className="mono" style={{ fontSize: 22, color: "var(--t-1)", fontWeight: 700 }}>
                  {currentBranch.currentXp}<span style={{ color: "var(--t-3)", fontSize: 13 }}> XP</span>
                </span>
              </div>
            </div>

            {/* Available skills to unlock */}
            {availableNodes.length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 11, color: "var(--electric)", fontWeight: 600, marginBottom: 8 }}>READY TO UNLOCK</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {availableNodes.map((wrapper) => (
                    <div key={wrapper.node.id} style={{
                      background: "var(--bg-3)",
                      border: "1px solid var(--line-2)",
                      borderLeft: "3px solid var(--electric)",
                      borderRadius: 6,
                      padding: "12px 16px",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                    }}>
                      <div>
                        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--t-1)", marginBottom: 2 }}>
                          {wrapper.node.name}
                          {wrapper.node.unlocksTraitId && <span style={{ marginLeft: 8, fontSize: 10, color: "var(--accent)" }}>TRAIT</span>}
                        </div>
                        <div style={{ fontSize: 12, color: "var(--t-3)" }}>{wrapper.node.description}</div>
                      </div>
                      <Button
                        kind="secondary"
                        size="sm"
                        onClick={() => handleUnlock(wrapper.node.id)}
                        disabled={unlocking !== null || devPoints < wrapper.node.cost}
                      >
                        {unlocking === wrapper.node.id ? "..." : `${wrapper.node.cost} DP`}
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Summary cards */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
              <TierCard state="unlocked" count={unlockedNodes.length} items={unlockedNodes.slice(0, 3).map((n) => n.node.name)} />
              <TierCard state="available" count={availableNodes.length} items={availableNodes.slice(0, 3).map((n) => n.node.name)} />
              <TierCard state="locked" count={lockedNodes.length} items={lockedNodes.slice(0, 3).map((n) => n.node.name)} />
            </div>
          </Card>
        )}
      </Section>

      {/* Active traits */}
      {allTraits.length > 0 && (
        <Section title="Active traits" sub="Permanent abilities you've earned">
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {allTraits.map((trait) => (
              <TraitCard key={trait.node.id} name={trait.node.name} desc={trait.node.description} />
            ))}
          </div>
        </Section>
      )}

      {/* Driver attributes */}
      <Section title="Current attributes" sub="Your driver's skill levels">
        <Card pad={16}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
            <AttributeRow label="Pace" value={player.attributes.pace} />
            <AttributeRow label="Qualifying" value={player.attributes.qualifying} />
            <AttributeRow label="Racecraft" value={player.attributes.racecraft} />
            <AttributeRow label="Consistency" value={player.attributes.consistency} />
            <AttributeRow label="Tire Management" value={player.attributes.tireManagement} />
            <AttributeRow label="Wet Weather" value={player.attributes.wetWeather} />
            <AttributeRow label="Starts" value={player.attributes.starts} />
            <AttributeRow label="Overtaking" value={player.attributes.overtaking} />
            <AttributeRow label="Defending" value={player.attributes.defending} />
          </div>
        </Card>
      </Section>
    </div>
  );
}

function TierCard({ state, count, items }: { state: "unlocked" | "available" | "locked"; count: number; items: string[] }) {
  const meta = {
    unlocked: { color: "var(--good)", label: "Already yours", icon: "✓" },
    available: { color: "var(--electric)", label: "Ready to unlock", icon: "▶" },
    locked: { color: "var(--t-3)", label: "Need more XP", icon: "🔒" },
  }[state];

  return (
    <div style={{ background: "var(--bg-3)", borderRadius: 4, padding: 14, borderLeft: `2px solid ${meta.color}` }}>
      <div className="tracked" style={{ fontSize: 9.5, color: "var(--t-3)", marginBottom: 6 }}>{meta.label}</div>
      <div className="mono" style={{ fontSize: 28, color: meta.color, fontWeight: 700, lineHeight: 1, marginBottom: 10 }}>{count}</div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {items.slice(0, 3).map((name) => (
          <div key={name} style={{ fontSize: 11.5, color: state === "locked" ? "var(--t-3)" : "var(--t-1)", display: "flex", alignItems: "center", gap: 6 }}>
            {name}
          </div>
        ))}
      </div>
    </div>
  );
}

function TraitCard({ name, desc }: { name: string; desc: string }) {
  return (
    <div style={{
      background: "var(--bg-2)", border: "1px solid var(--line-1)",
      borderLeft: "3px solid var(--accent)",
      borderRadius: 4, padding: "12px 14px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ color: "var(--accent)" }}>★</span>
        <span style={{ fontSize: 13.5, color: "var(--t-1)", fontWeight: 600 }}>{name}</span>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--t-2)" }}>{desc}</div>
    </div>
  );
}

function AttributeRow({ label, value }: { label: string; value: number }) {
  const tone = value >= 80 ? "good" : value >= 60 ? "warn" : "bad";
  const color = tone === "good" ? "var(--good)" : tone === "warn" ? "var(--warn)" : "var(--bad)";

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
        <span style={{ fontSize: 12, color: "var(--t-2)" }}>{label}</span>
        <span className="mono" style={{ fontSize: 12, color, fontWeight: 600 }}>{value}</span>
      </div>
      <Bar value={value} max={100} color={color} height={4} />
    </div>
  );
}
