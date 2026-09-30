"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import OrgPicker from "@/components/OrgPicker";
import { useApp } from "@/context/AppContext";
import { importHome, isRunning, jobTitle, useImports } from "@/context/ImportsContext";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/assets", label: "Assets" },
  { href: "/findings", label: "Findings" },
  { href: "/imports", label: "Imports" },
  { href: "/archived", label: "Archived" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useApp();
  const imports = useImports();
  const running = imports.scans.filter(isRunning);
  const runningJobs = imports.jobs.filter(isRunning);

  return (
    <nav className="sticky top-0 flex h-screen w-56 shrink-0 flex-col overflow-y-auto border-r border-white/10 bg-navy/60 p-4">
      <div className="mb-6 text-lg font-semibold tracking-wide text-white">
        Audit<span className="text-cyan">Mind</span>
      </div>
      <div className="mb-6">
        <OrgPicker />
      </div>
      <ul className="space-y-1">
        {NAV_ITEMS.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-md px-3 py-2 text-sm transition-colors hover:bg-cyan/10 hover:text-cyan ${
                  active ? "bg-cyan/10 text-cyan" : "text-white/80"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
      {running.length > 0 && (
        <ul aria-label="Imports in progress" className="mt-6 space-y-1">
          {running.map((scan) => (
            <li key={scan.id}>
              <Link
                href={`/${importHome(scan)}`}
                title={scan.filename ?? undefined}
                className="block truncate rounded-md px-3 py-2 text-xs text-cyan hover:bg-cyan/10"
              >
                <span aria-hidden className="mr-1 inline-block animate-pulse">●</span>
                Importing {scan.filename ?? "a file"}…
              </Link>
            </li>
          ))}
        </ul>
      )}
      {runningJobs.length > 0 && (
        <ul aria-label="Archive jobs in progress" className="mt-6 space-y-1">
          {runningJobs.map((job) => (
            <li key={job.id}>
              <Link
                href={job.action === "archive" ? "/imports" : "/archived"}
                title={job.label}
                className="block truncate rounded-md px-3 py-2 text-xs text-cyan hover:bg-cyan/10"
              >
                <span aria-hidden className="mr-1 inline-block animate-pulse">●</span>
                {jobTitle(job)}…
              </Link>
            </li>
          ))}
        </ul>
      )}
      <button
        type="button"
        onClick={() => {
          logout();
          router.replace("/login");
        }}
        className="mt-auto rounded-md px-3 py-2 text-left text-sm text-white/60 transition-colors hover:bg-white/5 hover:text-white"
      >
        Log out
      </button>
    </nav>
  );
}
