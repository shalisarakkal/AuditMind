import Link from "next/link";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard" },
  { href: "/assets", label: "Assets" },
  { href: "/findings", label: "Findings" },
  { href: "/reports", label: "Reports" },
  { href: "/settings", label: "Settings" },
];

export default function Sidebar() {
  return (
    <nav className="w-56 shrink-0 border-r border-white/10 bg-navy/60 p-4">
      <div className="mb-8 text-lg font-semibold tracking-wide text-white">
        Audit<span className="text-cyan">Mind</span>
      </div>
      <ul className="space-y-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.href}>
            <Link
              href={item.href}
              className="block rounded-md px-3 py-2 text-sm text-white/80 transition-colors hover:bg-cyan/10 hover:text-cyan"
            >
              {item.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
