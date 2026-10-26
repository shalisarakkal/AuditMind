import type { Metadata } from "next";
import { connection } from "next/server";

import { AppProvider } from "@/context/AppContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "AuditMind AI",
  description: "AI-powered cyber resilience auditing platform",
  icons: { icon: "/brand.svg" },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Rendered for each request, so Next.js can mark its scripts with the
  // request's CSP nonce (src/proxy.ts).
  await connection();
  return (
    <html lang="en">
      <body className="min-h-screen bg-navy">
        <AppProvider>{children}</AppProvider>
      </body>
    </html>
  );
}
