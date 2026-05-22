"use client";

import Link from "next/link";
import { useSave } from "@/components/SaveProvider";
import { PageHead, Section, StatRow } from "@/components/Shell";

export function SavesPageClient() {
  const { saves, currentSave, selectedSaveId, selectSave, loading, error } = useSave();

  if (loading) {
    return (
      <div className="page">
        <p className="loading">Loading saves...</p>
      </div>
    );
  }

  return (
    <div className="page">
      <PageHead
        meta="Management"
        title="Save Games"
        sub={`${saves.length} saves available`}
        actions={
          <Link href="/create-driver" className="btn primary">
            New Career
          </Link>
        }
      />

      {error && <p className="tag neg" style={{ marginBottom: 20 }}>{error}</p>}

      <Section title="Available Saves">
        {saves.length === 0 ? (
          <div className="empty-state">
            <h2>No Saves Yet</h2>
            <p>Create a new career to get started.</p>
            <Link href="/create-driver" className="btn primary">
              Create Career
            </Link>
          </div>
        ) : (
          <table className="tbl">
            <thead>
              <tr>
                <th>Name</th>
                <th>Save ID</th>
                <th>Season</th>
                <th>Phase</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {saves.map((save) => (
                <tr
                  key={save.saveId}
                  className={save.saveId === selectedSaveId ? "player" : ""}
                >
                  <td style={{ fontWeight: 500 }}>{save.name}</td>
                  <td className="mono t2">{save.saveId.slice(0, 8)}</td>
                  <td className="mono">{save.season}</td>
                  <td>
                    <span className="tag">{save.phase}</span>
                  </td>
                  <td>
                    {save.saveId !== selectedSaveId && (
                      <button className="btn sm" onClick={() => selectSave(save.saveId)}>
                        Load
                      </button>
                    )}
                    {save.saveId === selectedSaveId && (
                      <span className="tag accent">Active</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {currentSave && (
        <Section title="Current Save Details">
          <StatRow
            items={[
              { label: "Save ID", value: currentSave.saveId.slice(0, 8), mono: true },
              { label: "Season", value: String(currentSave.season), mono: true },
              { label: "Rounds", value: `${currentSave.calendar.filter((r) => r.completed).length} / ${currentSave.calendar.length}`, mono: true },
              { label: "Drivers", value: String(currentSave.drivers.length), mono: true },
            ]}
          />
        </Section>
      )}
    </div>
  );
}
