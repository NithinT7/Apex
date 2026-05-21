import Link from "next/link";

export default function HomePage() {
  return (
    <main className="page-shell">
      <p style={{ color: "var(--accent-strong)", fontWeight: 700, margin: 0 }}>
        F2 to F1 Career
      </p>
      <h1 style={{ fontSize: 48, lineHeight: 1.05, margin: "12px 0 16px" }}>
        Build a driver, race the ladder, earn the seat.
      </h1>
      <p style={{ color: "var(--muted)", fontSize: 18, maxWidth: 680 }}>
        A text-first racing career sim with realistic F2 weekends, lap-by-lap
        timing, academy pressure, driver markets, and F1 promotion paths.
      </p>
      <Link
        href="/create-driver"
        style={{
          display: "inline-block",
          marginTop: 28,
          borderRadius: 6,
          background: "var(--accent)",
          color: "white",
          fontWeight: 700,
          padding: "12px 18px",
        }}
      >
        Create Driver
      </Link>
    </main>
  );
}
