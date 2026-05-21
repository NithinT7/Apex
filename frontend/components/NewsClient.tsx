"use client";

import { useEffect, useState } from "react";
import { getSave, getSaves } from "@/lib/api";
import type { SaveGame, SaveSummary } from "@/lib/types";

export function NewsClient() {
  const [saves, setSaves] = useState<SaveSummary[]>([]);
  const [save, setSave] = useState<SaveGame | null>(null);
  const [selectedSaveId, setSelectedSaveId] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSaves()
      .then((loaded) => {
        setSaves(loaded);
        setSelectedSaveId(loaded[0]?.saveId ?? "");
      })
      .catch(() => setError("Could not load saves."));
  }, []);

  useEffect(() => {
    if (!selectedSaveId) return;
    getSave(selectedSaveId)
      .then(setSave)
      .catch(() => setError("Could not load news."));
  }, [selectedSaveId]);

  if (!saves.length) {
    return <p className="lede">Create a career save to see the news feed.</p>;
  }

  return (
    <section className="viewer-stack">
      <div className="panel control-panel">
        <label>
          Save
          <select value={selectedSaveId} onChange={(event) => setSelectedSaveId(event.target.value)}>
            {saves.map((item) => (
              <option key={item.saveId} value={item.saveId}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {error ? <p className="error-text">{error}</p> : null}
      <div className="news-feed">
        {(save?.news ?? []).slice().reverse().map((item) => (
          <article className="panel" key={item.id}>
            <p className="eyebrow-text">
              {item.category} / {item.date}
            </p>
            <h2>{item.headline}</h2>
            <p>{item.body}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
