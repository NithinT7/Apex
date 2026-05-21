"use client";

import { Flag, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
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

export function DriverCreationForm() {
  const [options, setOptions] = useState<CareerCreationOptions | null>(null);
  const [created, setCreated] = useState<SaveGame | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<CreateCareerPayload>({
    name: "",
    nationality: "",
    age: 18,
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
    [selectedBackground, selectedArchetype],
  );

  async function submitCareer(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const save = await createCareer(form);
      setCreated(save);
    } catch {
      setError("Career creation failed. Check that the backend is running.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return <p className="lede">Loading career creation data...</p>;
  }

  if (!options) {
    return <p className="error-text">{error}</p>;
  }

  if (created) {
    const player = created.drivers.find((driver) => driver.id === created.playerDriverId);
    return (
      <section className="panel success-panel">
        <h2>Career Created</h2>
        <p>
          {player?.name} is signed with {teamName(options.f2Teams, player?.teamId)} for the
          2026 F2 season.
        </p>
        <dl className="stat-grid">
          <div>
            <dt>Save ID</dt>
            <dd>{created.saveId}</dd>
          </div>
          <div>
            <dt>Academy</dt>
            <dd>{academyName(options.academies, player?.academyId)}</dd>
          </div>
          <div>
            <dt>Phase</dt>
            <dd>{created.phase}</dd>
          </div>
        </dl>
      </section>
    );
  }

  return (
    <form className="creation-grid" onSubmit={submitCareer}>
      <section className="panel form-panel">
        <h2>Identity</h2>
        <label>
          Name
          <input
            required
            minLength={2}
            maxLength={48}
            value={form.name}
            onChange={(event) => setForm({ ...form, name: event.target.value })}
          />
        </label>
        <label>
          Nationality
          <input
            required
            minLength={2}
            maxLength={40}
            value={form.nationality}
            onChange={(event) => setForm({ ...form, nationality: event.target.value })}
          />
        </label>
        <div className="field-row">
          <label>
            Age
            <input
              type="number"
              min={16}
              max={30}
              value={form.age}
              onChange={(event) => setForm({ ...form, age: Number(event.target.value) })}
            />
          </label>
          <label>
            Number
            <input
              type="number"
              min={2}
              max={99}
              value={form.driverNumber}
              onChange={(event) => setForm({ ...form, driverNumber: Number(event.target.value) })}
            />
          </label>
        </div>
      </section>

      <OptionPanel
        title="Background"
        options={options.backgrounds}
        value={form.backgroundId}
        onChange={(backgroundId) => setForm({ ...form, backgroundId })}
      />

      <OptionPanel
        title="Archetype"
        options={options.archetypes}
        value={form.archetypeId}
        onChange={(archetypeId) => setForm({ ...form, archetypeId })}
      />

      <section className="panel form-panel">
        <h2>Seat</h2>
        <label>
          F2 Team
          <select value={form.teamId} onChange={(event) => setForm({ ...form, teamId: event.target.value })}>
            {options.f2Teams.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Academy
          <select
            value={form.academyId}
            onChange={(event) => setForm({ ...form, academyId: event.target.value })}
          >
            {options.academies.map((academy) => (
              <option key={academy.id} value={academy.id}>
                {academy.name}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="panel">
        <h2>Attribute Preview</h2>
        <dl className="stat-grid">
          {previewKeys.map((key) => (
            <div key={key}>
              <dt>{label(key)}</dt>
              <dd>{preview[key]}</dd>
            </div>
          ))}
        </dl>
        {error ? <p className="error-text">{error}</p> : null}
        <button className="primary-button" type="submit" disabled={submitting}>
          {submitting ? <Loader2 size={18} className="spin" /> : <Flag size={18} />}
          Create Career
        </button>
      </section>
    </form>
  );
}

function OptionPanel({
  title,
  options,
  value,
  onChange,
}: {
  title: string;
  options: Array<DriverBackground | DriverArchetype>;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <section className="panel option-panel">
      <h2>{title}</h2>
      {options.map((option) => (
        <label className="option-card" key={option.id}>
          <input
            checked={value === option.id}
            name={title}
            type="radio"
            value={option.id}
            onChange={() => onChange(option.id)}
          />
          <span>
            <strong>{option.name}</strong>
            <small>{option.description}</small>
          </span>
        </label>
      ))}
    </section>
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
