import type { Metadata } from "next";
import "./globals.css";
import { SaveProvider } from "@/components/SaveProvider";
import { ShellWrapper } from "@/components/ShellWrapper";

export const metadata: Metadata = {
  title: "Apex — F1 Career Simulator",
  description: "Personal F1/F2 career simulator",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <SaveProvider>
          <ShellWrapper>{children}</ShellWrapper>
        </SaveProvider>
      </body>
    </html>
  );
}
