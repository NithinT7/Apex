"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { PageHeader, Card, Button, Chip } from "@/components/ui";
import { useSave } from "@/lib/SaveContext";
import * as api from "@/lib/api";
import type { CareerOptions, DifficultyPreset } from "@/lib/types";

// Fallback data when backend is unavailable (must match backend IDs)
const FALLBACK_OPTIONS: CareerOptions = {
  backgrounds: [
    { id: "karting_prodigy", name: "Karting Prodigy", description: "High raw pace and early hype, but less polished with media.", attributeEffects: { pace: 8, qualifying: 3 }, hiddenEffects: { potential: 5 } },
    { id: "wealthy_backed_driver", name: "Wealthy Backed Driver", description: "Strong sponsor value and easier seat access, with more scrutiny.", attributeEffects: { sponsorValue: 12, marketability: 4 }, hiddenEffects: { loyalty: -2 } },
    { id: "late_bloomer", name: "Late Bloomer", description: "Lower starting pace but stronger mentality and long-term growth.", attributeEffects: { pressure: 4, composure: 5 }, hiddenEffects: { developmentRate: 6 } },
    { id: "technical_driver", name: "Technical Driver", description: "Excellent feedback and tire understanding with calmer racecraft.", attributeEffects: { technicalFeedback: 7, tireManagement: 5 }, hiddenEffects: { developmentRate: 3 } },
  ],
  archetypes: [
    { id: "smooth_operator", name: "Smooth Operator", description: "Strong over long races with low tire wear and fewer mistakes.", attributeEffects: { tireManagement: 7, consistency: 5 }, hiddenEffects: {} },
    { id: "one_lap_monster", name: "One-Lap Monster", description: "Qualifying specialist who can put the car higher than expected.", attributeEffects: { qualifying: 11, pace: 5 }, hiddenEffects: {} },
    { id: "wheel_to_wheel_fighter", name: "Wheel-to-Wheel Fighter", description: "Aggressive in combat and popular with fans, with higher incident risk.", attributeEffects: { racecraft: 7, aggression: 6 }, hiddenEffects: {} },
    { id: "rain_specialist", name: "Rain Specialist", description: "Can steal big results when weather disrupts the field.", attributeEffects: { wetWeather: 8, adaptability: 4 }, hiddenEffects: {} },
    { id: "technical_developer", name: "Technical Developer", description: "Improves setup direction and becomes valuable to academies.", attributeEffects: { technicalFeedback: 8, adaptability: 4 }, hiddenEffects: {} },
    { id: "high_risk_prodigy", name: "High-Risk Prodigy", description: "Huge upside and speed, with volatile race execution.", attributeEffects: { pace: 7, qualifying: 5 }, hiddenEffects: { potential: 7 } },
  ],
  f2Teams: [
    { id: "f2_invicta", name: "Invicta Racing", series: "F2" as const, country: "United Kingdom", carPerformance: 87, reliability: 84, strategy: 83, developmentRate: 81, financialHealth: 86 },
    { id: "f2_campos", name: "Campos Racing", series: "F2" as const, country: "Spain", carPerformance: 88, reliability: 83, strategy: 83, developmentRate: 80, financialHealth: 82 },
    { id: "f2_mp", name: "MP Motorsport", series: "F2" as const, country: "Netherlands", carPerformance: 86, reliability: 82, strategy: 82, developmentRate: 79, financialHealth: 82 },
    { id: "f2_hitech", name: "Hitech", series: "F2" as const, country: "United Kingdom", carPerformance: 83, reliability: 81, strategy: 79, developmentRate: 77, financialHealth: 78 },
    { id: "f2_trident", name: "Trident", series: "F2" as const, country: "Italy", carPerformance: 81, reliability: 78, strategy: 76, developmentRate: 75, financialHealth: 77 },
    { id: "f2_prema", name: "PREMA Racing", series: "F2" as const, country: "Italy", carPerformance: 76, reliability: 82, strategy: 80, developmentRate: 83, financialHealth: 88 },
  ],
  academies: [
    { id: "academy_red_bull", name: "Red Bull Junior Team", style: "brutal_ladder", f1TeamId: "f1_red_bull", supportLevel: 88, pressure: 96, patience: 34, politicalStability: 62, testingOpportunities: 86, contractStrictness: 92, mediaExpectations: 88 },
    { id: "academy_ferrari", name: "Ferrari Driver Academy", style: "prestige", f1TeamId: "f1_ferrari", supportLevel: 84, pressure: 88, patience: 70, politicalStability: 72, testingOpportunities: 74, contractStrictness: 78, mediaExpectations: 95 },
    { id: "academy_mercedes", name: "Mercedes Junior Team", style: "technical_development", f1TeamId: "f1_mercedes", supportLevel: 86, pressure: 82, patience: 76, politicalStability: 84, testingOpportunities: 82, contractStrictness: 80, mediaExpectations: 82 },
    { id: "academy_mclaren", name: "McLaren Driver Development", style: "balanced_modern", f1TeamId: "f1_mclaren", supportLevel: 82, pressure: 78, patience: 72, politicalStability: 86, testingOpportunities: 78, contractStrictness: 72, mediaExpectations: 84 },
    { id: "academy_alpine", name: "Alpine Academy", style: "flexible_pathway", f1TeamId: "f1_alpine", supportLevel: 76, pressure: 74, patience: 58, politicalStability: 48, testingOpportunities: 72, contractStrictness: 66, mediaExpectations: 68 },
    { id: "academy_independent", name: "Independent", style: "independent", f1TeamId: null, supportLevel: 35, pressure: 45, patience: 90, politicalStability: 80, testingOpportunities: 20, contractStrictness: 10, mediaExpectations: 45 },
  ],
  difficultyPresets: [
    { id: "prodigy", name: "Prodigy", description: "Generational talent destined for greatness." },
    { id: "realistic_prospect", name: "Realistic Prospect", description: "Strong junior destined for F1, but must earn elite status." },
    { id: "underdog", name: "Underdog", description: "Late bloomer with hidden potential." },
    { id: "brutal_realism", name: "Brutal Realism", description: "Harsh simulation - every point must be earned." },
  ],
};

export default function CreateDriverPage() {
  const router = useRouter();
  const { loadSave } = useSave();
  const [options, setOptions] = useState<CareerOptions>(FALLBACK_OPTIONS);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [name, setName] = useState("");
  const [nationality, setNationality] = useState("American");
  const [dob, setDob] = useState("2006-03-15");
  const [driverNumber, setDriverNumber] = useState(7);
  const [backgroundId, setBackgroundId] = useState("karting_prodigy");
  const [archetypeId, setArchetypeId] = useState("smooth_operator");
  const [teamId, setTeamId] = useState("f2_invicta");
  const [academyId, setAcademyId] = useState("academy_red_bull");
  const [difficulty, setDifficulty] = useState<DifficultyPreset>("realistic_prospect");

  useEffect(() => {
    loadOptions();
  }, []);

  async function loadOptions() {
    try {
      const data = await api.getCareerOptions();
      setOptions(data);
      // Set defaults from API data
      if (data.backgrounds.length > 0) setBackgroundId(data.backgrounds[0].id);
      if (data.archetypes.length > 0) setArchetypeId(data.archetypes[0].id);
      if (data.f2Teams.length > 0) setTeamId(data.f2Teams[0].id);
      if (data.academies.length > 0) setAcademyId(data.academies[0].id);
      setError(null);
    } catch (err) {
      // Use fallback data, show warning
      console.warn("Using fallback options - backend unavailable");
    } finally {
      setLoading(false);
    }
  }

  // Calculate age from DOB
  const age = dob ? Math.floor((Date.now() - new Date(dob).getTime()) / (365.25 * 24 * 60 * 60 * 1000)) : 19;

  async function handleCreate() {
    if (!name.trim()) {
      setError("Please enter a driver name");
      return;
    }

    setCreating(true);
    setError(null);

    try {
      const save = await api.createCareer({
        name,
        nationality,
        age,
        driver_number: driverNumber,
        background_id: backgroundId,
        archetype_id: archetypeId,
        team_id: teamId,
        academy_id: academyId,
        difficulty,
      });

      // Load the new save into context
      await loadSave(save.saveId);

      // Navigate to dashboard
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create career");
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: "40px 28px", maxWidth: 1200, margin: "0 auto" }}>
        <PageHeader
          eyebrow="New Career"
          title="Create Driver"
          question="Define your journey"
        />
        <Card style={{ padding: 40, textAlign: "center" }}>
          <p style={{ color: "var(--t-3)" }}>Loading options...</p>
        </Card>
      </div>
    );
  }

  return (
    <div style={{ padding: "40px 28px", maxWidth: 1200, margin: "0 auto" }}>
      <PageHeader
        eyebrow="New Career"
        title="Create Driver"
        question="Define your journey from F2 to F1"
        actions={
          <Link href="/" style={{ textDecoration: "none" }}>
            <Button kind="ghost" size="md">Back</Button>
          </Link>
        }
      />

      {error && (
        <div style={{
          background: "rgba(232,88,88,0.1)",
          border: "1px solid rgba(232,88,88,0.3)",
          borderRadius: "var(--r-2)",
          padding: "12px 16px",
          marginBottom: 16,
          color: "var(--bad)",
          fontSize: 13,
        }}>
          {error}
        </div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Basic Info */}
        <Card eyebrow="Identity" title="Driver Info" pad={16}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <FormField label="Full Name">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter driver name"
                style={inputStyle}
              />
            </FormField>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <FormField label="Nationality">
                <select
                  value={nationality}
                  onChange={(e) => setNationality(e.target.value)}
                  style={inputStyle}
                >
                  {["American", "British", "German", "French", "Italian", "Spanish", "Dutch", "Australian", "Japanese", "Brazilian", "Mexican", "Canadian", "Finnish", "Danish", "Monegasque", "Thai"].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </FormField>

              <FormField label="Driver Number">
                <input
                  type="number"
                  value={driverNumber}
                  onChange={(e) => setDriverNumber(parseInt(e.target.value) || 1)}
                  min={1}
                  max={99}
                  style={inputStyle}
                />
              </FormField>
            </div>

            <FormField label="Date of Birth">
              <input
                type="date"
                value={dob}
                onChange={(e) => setDob(e.target.value)}
                max="2008-01-01"
                min="1998-01-01"
                style={inputStyle}
              />
              <div style={{ fontSize: 11, color: "var(--t-3)", marginTop: 4 }}>
                Age at season start: <span style={{ color: "var(--t-1)", fontWeight: 600 }}>{age} years old</span>
              </div>
            </FormField>
          </div>
        </Card>

        {/* Background */}
        <Card eyebrow="Origin" title="Background" pad={16}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 280, overflowY: "auto" }}>
            {options.backgrounds.map((bg) => (
              <OptionCard
                key={bg.id}
                selected={backgroundId === bg.id}
                onClick={() => setBackgroundId(bg.id)}
                title={bg.name}
                description={bg.description}
              />
            ))}
          </div>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Archetype */}
        <Card eyebrow="Style" title="Driving Style" pad={16}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 280, overflowY: "auto" }}>
            {options.archetypes.map((arch) => (
              <OptionCard
                key={arch.id}
                selected={archetypeId === arch.id}
                onClick={() => setArchetypeId(arch.id)}
                title={arch.name}
                description={arch.description}
              />
            ))}
          </div>
        </Card>

        {/* Team */}
        <Card eyebrow="Contract" title="F2 Team" pad={16}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 280, overflowY: "auto" }}>
            {options.f2Teams.map((team) => (
              <OptionCard
                key={team.id}
                selected={teamId === team.id}
                onClick={() => setTeamId(team.id)}
                title={team.name}
                description={`Car performance: ${team.carPerformance}/100`}
              />
            ))}
          </div>
        </Card>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Academy */}
        <Card eyebrow="Development" title="F1 Academy" pad={16}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 280, overflowY: "auto" }}>
            {options.academies.map((acad) => (
              <OptionCard
                key={acad.id}
                selected={academyId === acad.id}
                onClick={() => setAcademyId(acad.id)}
                title={acad.name}
                description={`Support: ${acad.supportLevel}/100 · Pressure: ${acad.pressure}/100`}
              />
            ))}
          </div>
        </Card>

        {/* Difficulty */}
        <Card eyebrow="Challenge" title="Difficulty" pad={16}>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {options.difficultyPresets.map((diff) => (
              <OptionCard
                key={diff.id}
                selected={difficulty === diff.id}
                onClick={() => setDifficulty(diff.id as DifficultyPreset)}
                title={diff.name}
                description={diff.description}
              />
            ))}
          </div>
        </Card>
      </div>

      {/* Create Button */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
        <Button kind="ghost" size="lg" onClick={() => router.push("/")}>
          Cancel
        </Button>
        <Button kind="primary" size="lg" onClick={handleCreate} disabled={creating}>
          {creating ? "Creating..." : "Start Career"}
        </Button>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 14px",
  background: "var(--bg-3)",
  border: "1px solid var(--line-2)",
  borderRadius: "var(--r-2)",
  color: "var(--t-1)",
  fontSize: 14,
};

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 11, color: "var(--t-3)", marginBottom: 6, fontWeight: 500 }}>
        {label}
      </label>
      {children}
    </div>
  );
}

function OptionCard({
  selected,
  onClick,
  title,
  description,
  color,
}: {
  selected: boolean;
  onClick: () => void;
  title: string;
  description: string;
  color?: string;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        padding: "12px 14px",
        background: selected ? "rgba(90,169,240,0.08)" : "var(--bg-3)",
        border: `1px solid ${selected ? "var(--electric)" : "var(--line-2)"}`,
        borderLeft: color ? `3px solid ${color}` : selected ? "3px solid var(--electric)" : undefined,
        borderRadius: "var(--r-2)",
        textAlign: "left",
        cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--t-1)", marginBottom: 2 }}>
        {title}
      </div>
      <div style={{ fontSize: 11.5, color: "var(--t-3)", lineHeight: 1.4 }}>
        {description}
      </div>
    </button>
  );
}
