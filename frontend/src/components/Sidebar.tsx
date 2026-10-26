"use client";
import ProductBrand from "./ProductBrand";

import Link from "next/link";
import { usePathname } from "next/navigation";

import AccountMenu from "@/components/AccountMenu";
import OrgPicker from "@/components/OrgPicker";
import { useApp } from "@/context/AppContext";
import { importHome, isInterrupted, isRunning, jobTitle, useImports } from "@/context/ImportsContext";
import { PLATFORM_PATH } from "@/lib/paths";
import { useMe } from "@/lib/useMe";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/assets", label: "Assets" },
  { href: "/findings", label: "Findings" },
  { href: "/uploads", label: "Uploads" },
  { href: "/archived", label: "Archived" },
  { href: "/activity", label: "Activity" },
  { href: "/reports", label: "Reports" },
  { href: "/documents", label: "Documents" },
  { href: "/people", label: "People" },
  { href: "/settings", label: "Settings" },
];

// The Sysadmin's.
const PLATFORM_ITEMS = [
  { href: `${PLATFORM_PATH}/organizations`, label: "Organizations" },
  { href: `${PLATFORM_PATH}/accounts`, label: "Accounts" },
  { href: `${PLATFORM_PATH}/activity`, label: "Platform activity" },
  { href: `${PLATFORM_PATH}/security`, label: "Security defaults" },
  { href: `${PLATFORM_PATH}/documents`, label: "Shared standards" },
];

export default function Sidebar() {
  const pathname = usePathname() ?? "";
  const imports = useImports();
  const { orgs } = useApp();
  const me = useMe();
  const running = imports.scans.filter(isRunning);
  // The one running first, then those queued.
  const runningJobs = imports.jobs.filter(isRunning).sort((a, b) => Number(b.status === "running") - Number(a.status === "running"));

  return (
    <nav className="sticky top-0 flex h-screen w-56 shrink-0 flex-col overflow-y-auto border-r border-white/10 bg-navy/60 p-4">
      <div className="mb-6 text-lg font-semibold tracking-wide text-white">
        <ProductBrand />
      </div>
      <div className="mb-6">
        <OrgPicker />
      </div>
      {orgs.length > 0 && <NavList items={NAV_ITEMS} pathname={pathname} />}
      {me?.is_sysadmin && (
        <div className={orgs.length > 0 ? "mt-6" : ""}>
          <p className="mb-1 px-3 text-xs uppercase tracking-wide text-white/50">Platform</p>
          <NavList items={PLATFORM_ITEMS} pathname={pathname} label="Platform" />
        </div>
      )}
      {running.length > 0 && (
        <ul aria-label="Uploads in progress" className="mt-6 space-y-1">
          {running.map((scan) => (
            <li key={scan.id}>
              <Link
                href={`/${importHome(scan)}`}
                title={scan.filename ?? undefined}
                className={`block truncate rounded-md px-3 py-2 text-xs hover:bg-cyan/10 ${isInterrupted(scan, imports.workerDown) ? "text-violet-200" : "text-cyan"}`}
              >
                <Indicator interrupted={isInterrupted(scan, imports.workerDown)} />
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
                className={`block truncate rounded-md px-3 py-2 text-xs hover:bg-cyan/10 ${isInterrupted(job, imports.workerDown) ? "text-violet-200" : "text-cyan"}`}
              >
                <Indicator interrupted={isInterrupted(job, imports.workerDown)} />
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
        <p role="alert" className="mt-6 rounded-md border border-violet-400/40 bg-violet-400/10 px-3 py-2 text-xs text-violet-200">
          The background worker isn&apos;t running, so large uploads and archive jobs are waiting. Start it with
          start-dev.ps1, or <code>python -m app.worker</code> in the backend folder.
        </p>
      )}
      <AccountMenu />
    </nav>
  );
}

function NavList({ items, pathname, label }: { items: { href: string; label: string }[]; pathname: string; label?: string }) {
  return (
    <ul aria-label={label} className="space-y-1">
      {items.map((item) => {
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
  );
}

/** A pulsing dot while it runs; a warning sign while the worker is down. */
function Indicator({ interrupted }: { interrupted: boolean }) {
  return interrupted ? (
    <span aria-hidden className="mr-1">⚠</span>
  ) : (
    <span aria-hidden className="mr-1 inline-block animate-pulse">●</span>
  );
}
