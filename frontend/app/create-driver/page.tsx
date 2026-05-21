import Link from "next/link";
import { DriverCreationForm } from "@/components/DriverCreationForm";

export default function CreateDriverPage() {
  return (
    <main className="page-shell">
      <Link href="/" className="eyebrow-link">
        Back to dashboard
      </Link>
      <h1>Create Driver</h1>
      <p className="lede">
        Build a promising F2 driver, choose a race profile, take a seat, and
        decide whether to join an F1 academy or stay independent.
      </p>
      <DriverCreationForm />
    </main>
  );
}
