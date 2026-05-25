"use client";

import { PageHeader, Card } from "@/components/ui";

export default function NewsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Paddock · latest updates"
        title="News"
        question="What's happening in the paddock?"
      />

      <Card pad={40} style={{ textAlign: "center" }}>
        <p style={{ color: "var(--t-3)" }}>
          Paddock news coming soon.
        </p>
      </Card>
    </div>
  );
}
