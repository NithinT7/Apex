"use client";

import { PageHeader, Card } from "@/components/ui";

export default function SillySeasonPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Paddock · driver market"
        title="Silly Season"
        question="Who's moving where?"
      />

      <Card pad={40} style={{ textAlign: "center" }}>
        <p style={{ color: "var(--t-3)" }}>
          Driver market rumors coming soon.
        </p>
      </Card>
    </div>
  );
}
