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
  { href: "/uploads", label: "Uploads" },
  { href: "/archived", label: "Archived" },
  { href: "/activity", label: "Activity" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useApp();
  const imports = useImports();
  const running = imports.scans.filter(isRunning);
  // The one running first, then those queued.
  const runningJobs = imports.jobs.filter(isRunning).sort((a, b) => Number(b.status === "running") - Number(a.status === "running"));

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
        <ul aria-label="Uploads in progress" className="mt-6 space-y-1">
          {running.map((scan) => (
            <li key={scan.id}>
              <Link
                href={`/${importHome(scan)}`}
                title={scan.filename ?? undefined}
                className="block truncate rounded-md px-3 py-2 text-xs text-cyan hover:bg-cyan/10"
              >
                <span aria-hidden className="mr-1 inline-block animate-pulse">●</span>
                Processing {scan.filename ?? "a file"}…
              </Link>
            </li>
          ))}
        </ul>
      )}
      {runningJobs.length > 0 && (
        <ul aria-label="Archive jobs in progress" className="mt-6 space-y-1">
          {runningJobs.slice(0, 3).map((job) => (
            <li key={job.id}>
              <Link
                href={job.action === "archive" ? "/uploads" : "/archived"}
                title={job.label}
                className="block truncate rounded-md px-3 py-2 text-xs text-cyan hover:bg-cyan/10"
              >
                <span aria-hidden className="mr-1 inline-block animate-pulse">●</span>
                {jobTitle(job)}…
              </Link>
            </li>
          ))}
          {runningJobs.length > 3 && (
            <li className="px-3 py-1 text-xs text-white/60">and {(runningJobs.length - 3).toLocaleString("en-US")} more queued</li>
          )}
        </ul>
      )}
      {imports.workerDown && (
        <p role="alert" className="mt-6 rounded-md border border-yellow-400/30 bg-yellow-400/5 px-3 py-2 text-xs text-yellow-200">
          The background worker isn&apos;t running, so large uploads and archive jobs are waiting. Start it with
          start-dev.ps1, or <code>python -m app.worker</code> in the backend folder.
        </p>
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
