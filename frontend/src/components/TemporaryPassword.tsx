"use client";

import { useState } from "react";

import { formatDateTime } from "@/lib/domain";

/** A temporary password to show an admin, once: for someone added, or
 * whose password was reset. */
export type Handover = { who: string; password: string; expiresAt: string | null; added: boolean };

const BUTTON = "rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50";

/** The temporary password, shown once: the admin passes it on. */
export default function TemporaryPassword({ handover, onDone }: { handover: Handover; onDone(): void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div role="group" aria-label="Temporary password" className="space-y-2 rounded-lg border border-cyan/30 bg-cyan/5 p-4 text-sm">
      <p className="text-white">
        {handover.added ? `${handover.who} is added.` : `${handover.who}'s password is reset.`} Give them this temporary
        password: it&apos;s shown only once{handover.expiresAt ? `, and works until ${formatDateTime(handover.expiresAt)}` : ""}.
        They choose their own when they sign in.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <code className="rounded bg-navy px-3 py-1.5 font-mono text-base text-cyan select-all">{handover.password}</code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(handover.password).then(() => setCopied(true));
          }}
          className="text-xs text-cyan hover:underline"
        >
          {copied ? "Copied" : "Copy"}
        </button>
        <button type="button" onClick={onDone} className={BUTTON}>
          Done
        </button>
      </div>
    </div>
  );
}
