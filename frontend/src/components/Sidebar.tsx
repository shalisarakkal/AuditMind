"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import OrgPicker from "@/components/OrgPicker";
import { useApp } from "@/context/AppContext";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/assets", label: "Assets" },
  { href: "/findings", label: "Findings" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout } = useApp();

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
