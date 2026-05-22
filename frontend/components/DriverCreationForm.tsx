"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section, StatRow, Meter } from "@/components/Shell";
import { createCareer, getCareerCreationOptions } from "@/lib/api";
import type {
  Academy,
  CareerCreationOptions,
  CreateCareerPayload,
  DriverArchetype,
  DriverBackground,
  SaveGame,
  Team,
} from "@/lib/types";

const basePreview = {
  pace: 72,
  qualifying: 72,
  racecraft: 72,
  tireManagement: 70,
  wetWeather: 68,
  consistency: 70,
  pressure: 70,
  marketability: 58,
  sponsorValue: 45,
};

const previewKeys = [
  "pace",
  "qualifying",
  "racecraft",
  "tireManagement",
  "wetWeather",
  "consistency",
  "pressure",
  "marketability",
  "sponsorValue",
] as const;

const CAREER_START_DATE = "2026-03-01";
const MIN_DRIVER_AGE = 16;
const MAX_DRIVER_AGE = 26;
const DEFAULT_DATE_OF_BIRTH = "2008-01-01";

const nationalities = [
  "American", "Argentine", "Australian", "Austrian", "Belgian", "Brazilian",
  "British", "Bulgarian", "Canadian", "Chinese", "Colombian", "Danish",
  "Dutch", "Finnish", "French", "German", "Indian", "Irish", "Italian",
  "Japanese", "Mexican", "Monegasque", "New Zealander", "Norwegian",
  "Paraguayan", "Polish", "Portuguese", "Spanish", "Swedish", "Swiss", "Thai",
] as const;

export function DriverCreationForm() {
  const router = useRouter();
  const { refreshSaves, selectSave } = useSave();
  const [options, setOptions] = useState<CareerCreationOptions | null>(null);
  const [created, setCreated] = useState<SaveGame | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [dateOfBirth, setDateOfBirth] = useState(DEFAULT_DATE_OF_BIRTH);
  const [form, setForm] = useState<CreateCareerPayload>({
    name: "",
    nationality: "American",
    age: calculateAgeFromDob(DEFAULT_DATE_OF_BIRTH),
    driverNumber: 27,
    backgroundId: "",
    archetypeId: "",
    teamId: "",
    academyId: "academy_independent",
    difficulty: "realistic",
  });

  useEffect(() => {
    getCareerCreationOptions()
      .then((data) => {
        setOptions(data);
        setForm((current) => ({
          ...current,
          backgroundId: data.backgrounds[0]?.id ?? "",
          archetypeId: data.archetypes[0]?.id ?? "",
          teamId: data.f2Teams[0]?.id ?? "",
        }));
      })
      .catch(() => setError("Could not load career creation options."))
      .finally(() => setLoading(false));
  }, []);

  const selectedBackground = options?.backgrounds.find((item) => item.id === form.backgroundId);
  const selectedArchetype = options?.archetypes.find((item) => item.id === form.archetypeId);
  const preview = useMemo(
    () => buildPreview(selectedBackground, selectedArchetype),
    [selectedBackground, selectedArchetype]
  );

  async function submitCareer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const save = await createCareer(form);
      setCreated(save);
      await refreshSaves();
      selectSave(save.saveId);
    } catch {
      setError("Career creation failed. Check that the backend is running.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading career creation options...</p>
      </div>
    );
  }

  if (!options) {
    return (
      <div className="page">
        <div className="empty-state">
          <h2>Error</h2>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (created) {
    const player = created.drivers.find((driver) => driver.id === created.playerDriverId);
    return (
      <div className="page">
        <PageHead
          meta="Career"
          title="Career Created"
          sub={`${player?.name} is ready to race`}
        />
        <Section>
          <div className="card" style={{ borderColor: "var(--pos)" }}>
            <div style={{ fontSize: 32, marginBottom: 16, textAlign: "center" }}>&#127937;</div>
            <div style={{ fontSize: 20, fontWeight: 600, textAlign: "center", marginBottom: 16 }}>
              {player?.name} is signed with {teamName(options.f2Teams, player?.teamId)} for 2026
            </div>
            <StatRow
              items={[
                { label: "Save ID", value: created.saveId.slice(0, 8), mono: true },
                { label: "Academy", value: academyName(options.academies, player?.academyId) },
                { label: "Team", value: teamName(options.f2Teams, player?.teamId) },
                { label: "Phase", value: created.phase },
              ]}
            />
            <div style={{ textAlign: "center", marginTop: 24 }}>
              <button className="btn primary" onClick={() => router.push("/")}>
                Go to Dashboard →
              </button>
            </div>
          </div>
        </Section>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead
        meta="Career"
        title="Create Driver"
        sub="Build your F2 driver and start your journey to F1"
      />

      {error && <p className="tag neg" style={{ marginBottom: 20 }}>{error}</p>}

      <form onSubmit={submitCareer}>
        {/* Identity */}
        <Section title="Identity">
          <div className="card">
            <div className="grid cols-2 gap-sm">
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="t3 tiny">Name</span>
                <input
                  required
                  minLength={2}
                  maxLength={48}
                  placeholder="Enter driver name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="t3 tiny">Nationality</span>
                <select
                  required
                  value={form.nationality}
                  onChange={(e) => setForm({ ...form, nationality: e.target.value })}
                >
                  {nationalities.map((nat) => (
                    <option key={nat} value={nat}>{nat}</option>
                  ))}
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="t3 tiny">Date of Birth</span>
                <input
                  required
                  type="date"
                  max={dobForAge(MIN_DRIVER_AGE)}
                  min={dobForAge(MAX_DRIVER_AGE)}
                  value={dateOfBirth}
                  onChange={(e) => {
                    const dob = e.target.value;
                    if (!dob) return;
                    setDateOfBirth(dob);
                    setForm({ ...form, age: calculateAgeFromDob(dob) });
                  }}
                />
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="t3 tiny">Number</span>
                <select
                  value={form.driverNumber}
                  onChange={(e) => setForm({ ...form, driverNumber: Number(e.target.value) })}
                >
                  {driverNumbers.map((num) => (
                    <option key={num} value={num}>{num.toString().padStart(2, "0")}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </Section>

        {/* Background */}
        <Section title="Background">
          <div className="grid cols-3 gap-sm">
            {options.backgrounds.map((bg) => (
              <div
                key={bg.id}
                className={`card ${form.backgroundId === bg.id ? "selected" : ""}`}
                style={{
                  cursor: "pointer",
                  borderColor: form.backgroundId === bg.id ? "var(--accent)" : undefined,
                  background: form.backgroundId === bg.id ? "var(--accent-bg)" : undefined,
                }}
                onClick={() => setForm({ ...form, backgroundId: bg.id })}
              >
                <div className="card-title">{bg.name}</div>
                <p className="t2 small" style={{ marginTop: 4 }}>{bg.description}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* Archetype */}
        <Section title="Racing Style">
          <div className="grid cols-3 gap-sm">
            {options.archetypes.map((arch) => (
              <div
                key={arch.id}
                className={`card ${form.archetypeId === arch.id ? "selected" : ""}`}
                style={{
                  cursor: "pointer",
                  borderColor: form.archetypeId === arch.id ? "var(--accent)" : undefined,
                  background: form.archetypeId === arch.id ? "var(--accent-bg)" : undefined,
                }}
                onClick={() => setForm({ ...form, archetypeId: arch.id })}
              >
                <div className="card-title">{arch.name}</div>
                <p className="t2 small" style={{ marginTop: 4 }}>{arch.description}</p>
              </div>
            ))}
          </div>
        </Section>

        {/* Team & Academy */}
        <Section title="Seat">
          <div className="card">
            <div className="grid cols-2 gap-sm">
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="t3 tiny">F2 Team</span>
                <select
                  value={form.teamId}
                  onChange={(e) => setForm({ ...form, teamId: e.target.value })}
                >
                  {options.f2Teams.map((team) => (
                    <option key={team.id} value={team.id}>{team.name}</option>
                  ))}
                </select>
              </label>
              <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="t3 tiny">Academy</span>
                <select
                  value={form.academyId}
                  onChange={(e) => setForm({ ...form, academyId: e.target.value })}
                >
                  {options.academies.map((academy) => (
                    <option key={academy.id} value={academy.id}>{academy.name}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>
        </Section>

        {/* Attribute Preview */}
        <Section title="Attribute Preview">
          <div className="card">
            <div className="grid cols-3 gap-sm" style={{ marginBottom: 20 }}>
              {previewKeys.map((key) => (
                <div key={key}>
                  <Meter
                    label={label(key)}
                    value={preview[key]}
                    max={100}
                    tone={preview[key] >= 75 ? "pos" : preview[key] >= 60 ? "accent" : undefined}
                  />
                </div>
              ))}
            </div>
            <button className="btn primary" type="submit" disabled={submitting} style={{ width: "100%" }}>
              {submitting ? "Creating..." : "Create Career"}
            </button>
          </div>
        </Section>
      </form>
    </div>
  );
}

function buildPreview(background?: DriverBackground, archetype?: DriverArchetype) {
  const preview = { ...basePreview };
  for (const effects of [background?.attributeEffects, archetype?.attributeEffects]) {
    if (!effects) continue;
    for (const [key, value] of Object.entries(effects)) {
      if (key in preview) {
        const previewKey = key as keyof typeof preview;
        preview[previewKey] = Math.max(1, Math.min(100, preview[previewKey] + value));
      }
    }
  }
  return preview;
}

function teamName(teams: Team[], teamId?: string) {
  return teams.find((team) => team.id === teamId)?.name ?? "an F2 team";
}

function academyName(academies: Academy[], academyId?: string | null) {
  return academies.find((academy) => academy.id === academyId)?.name ?? "Independent";
}

function label(value: string) {
  return value.replace(/([A-Z])/g, " $1").replace(/^./, (char) => char.toUpperCase());
}

const driverNumbers = Array.from({ length: 98 }, (_, index) => index + 2);

function calculateAgeFromDob(dateOfBirth: string) {
  const [birthYear, birthMonth, birthDay] = dateOfBirth.split("-").map(Number);
  const [seasonYear, seasonMonth, seasonDay] = CAREER_START_DATE.split("-").map(Number);
  const birthdayHasPassed =
    seasonMonth > birthMonth || (seasonMonth === birthMonth && seasonDay >= birthDay);
  return seasonYear - birthYear - (birthdayHasPassed ? 0 : 1);
}

function dobForAge(age: number) {
  const [seasonYear, seasonMonth, seasonDay] = CAREER_START_DATE.split("-").map(Number);
  return [
    seasonYear - age,
    seasonMonth.toString().padStart(2, "0"),
    seasonDay.toString().padStart(2, "0"),
  ].join("-");
}
