import type { Metadata } from "next";

import { AppProvider } from "@/context/AppContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "AuditMind AI",
  description: "AI-powered cyber resilience auditing platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-navy">
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
