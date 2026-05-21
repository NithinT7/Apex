import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "F1 Career Simulator",
  description: "Personal F1/F2 career simulator",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
