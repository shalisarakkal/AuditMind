"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { useApp } from "@/context/AppContext";
import { api } from "@/lib/apiClient";
import { CHANGE_PASSWORD_PATH } from "@/lib/paths";
import type { Me } from "@/lib/types";

/** The signed-in user, at the foot of the sidebar: Change password and Sign
 * out (the page's AuthGuard then shows the sign-in page). */
export default function AccountMenu() {
  const { logout } = useApp();
  const [user, setUser] = useState<Me | null>(null);
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<Me>("/auth/me")
      .then(setUser)
      .catch(() => setUser(null));
  }, []);

  useEffect(() => {
    if (!open) return;
    const clickOutside = (event: MouseEvent) => {
      if (!menu.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", clickOutside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", clickOutside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  const item = "block w-full rounded px-3 py-2 text-left text-sm text-white/80 hover:bg-white/10 hover:text-white";
  return (
    <div ref={menu} className="relative mt-auto border-t border-white/10 pt-3">
      {open && (
        <div role="menu" className="absolute bottom-full left-0 right-0 mb-1 rounded-md border border-white/10 bg-navy p-1 shadow-lg">
          <Link role="menuitem" href={CHANGE_PASSWORD_PATH} className={item} onClick={() => setOpen(false)}>
            Change password
          </Link>
          <button
            role="menuitem"
            type="button"
            className={item}
            onClick={() => {
              setOpen(false);
              void logout();
            }}
          >
            Sign out
          </button>
        </div>
      )}
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm text-white/80 transition-colors hover:bg-white/5 hover:text-white"
        title={user?.email}
      >
        <span className="min-w-0 flex-1">
          <span className="block truncate">{user ? user.name || user.email : "Account"}</span>
          {user?.name && <span className="block truncate text-xs text-white/50">{user.email}</span>}
        </span>
        <span aria-hidden>{open ? "▾" : "▴"}</span>
      </button>
    </div>
  );
}
