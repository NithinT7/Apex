import Link from "next/link";
import { RaceWeekendClient } from "@/components/RaceWeekendClient";

export default function RaceWeekendPage() {
  return (
    <main className="page-shell">
      <Link href="/" className="eyebrow-link">
        Back to dashboard
      </Link>
      <h1>Race Weekend</h1>
      <p className="lede">
        The backend can now simulate a complete F2 weekend with practice,
        qualifying, sprint, feature race, lap-by-lap logs, safety cars, DNFs,
        points, standings updates, and a headline.
      </p>
      <RaceWeekendClient />
    </main>
  );
}
