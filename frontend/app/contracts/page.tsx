"use client";

import { PageHeader, Card } from "@/components/ui";

export default function ContractsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Paddock · career moves"
        title="Contracts"
        question="What opportunities are available?"
      />

      <Card pad={40} style={{ textAlign: "center" }}>
        <p style={{ color: "var(--t-3)" }}>
          Contract negotiations coming soon.
        </p>
      </Card>
    </div>
  );
}
