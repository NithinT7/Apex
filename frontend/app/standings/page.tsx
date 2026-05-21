import Link from "next/link";
import { StandingsClient } from "@/components/StandingsClient";

export default function StandingsPage() {
  return (
    <main className="page-shell">
      <Link href="/" className="eyebrow-link">
        Back to dashboard
      </Link>
      <h1>Standings</h1>
      <p className="lede">Track the F2 championship table as weekend results are applied.</p>
      <StandingsClient />
    </main>
  );
}
