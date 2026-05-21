import Link from "next/link";
import { BetweenRaceClient } from "@/components/BetweenRaceClient";

export default function ActivitiesPage() {
  return (
    <main className="page-shell">
      <Link href="/" className="eyebrow-link">
        Back to dashboard
      </Link>
      <h1>Between Races</h1>
      <p className="lede">
        Manage your time between race weekends. Choose activities to recover
        fatigue, build form, maintain sponsor relationships, and strengthen your
        academy standing.
      </p>
      <BetweenRaceClient />
    </main>
  );
}
