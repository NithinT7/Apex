import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { SaveProvider } from "@/lib/SaveContext";
import { Shell } from "@/components/Shell";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Apex - F1 Driver Career",
  description: "Formula 2 to Formula 1 driver career simulator",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        <SaveProvider>
          <Shell>{children}</Shell>
        </SaveProvider>
      </body>
    </html>
  );
}
