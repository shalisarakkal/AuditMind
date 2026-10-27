"use client";

import { useState } from "react";

import { formatDateTime } from "@/lib/domain";
import PasswordInput from "./PasswordInput";

/** A temporary password to show an admin, once: for someone added, or
 * whose password was reset. */
export type Handover = { who: string; password: string; expiresAt: string | null; added: boolean };

const BUTTON = "rounded-md bg-cyan px-3 py-1.5 text-sm font-medium text-navy hover:opacity-90 disabled:opacity-50";

/** The temporary password, shown once: the admin passes it on. */
export default function TemporaryPassword({ handover, onDone }: { handover: Handover; onDone(): void }) {
  const [copiedFor, setCopiedFor] = useState<Handover | null>(null);
  const [copyErrorFor, setCopyErrorFor] = useState<Handover | null>(null);
  async function copy() {
    setCopyErrorFor(null);
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(handover.password);
      setCopiedFor(handover);
    } catch {
      setCopyErrorFor(handover);
    }
  }
  return (
    <div role="group" aria-label="Temporary password" className="space-y-2 rounded-lg border border-cyan/30 bg-cyan/5 p-4 text-sm">
      <p className="text-white">
        {handover.added ? `${handover.who} is added.` : `${handover.who}'s password is reset.`} Give them this temporary
        password: it&apos;s shown only once{handover.expiresAt ? `, and works until ${formatDateTime(handover.expiresAt)}` : ""}.
        They choose their own when they sign in.
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 max-w-full flex-1">
          <PasswordInput label="Temporary password" aria-label="Temporary password value" resetOn={handover}
            value={handover.password} readOnly autoComplete="off"
            className="h-11 w-full rounded-md border border-white/20 bg-navy px-3 font-mono text-base text-cyan" />
        </div>
        <button
          type="button"
          onClick={() => void copy()}
          className="text-xs text-cyan hover:underline"
        >
          {copiedFor === handover ? "Copied" : "Copy"}
        </button>
        <button type="button" onClick={onDone} className={BUTTON}>
          Done
        </button>
      </div>
      {copyErrorFor === handover && <p role="alert" className="text-amber-200">Copy unavailable. Reveal and copy the temporary password manually.</p>}
    </div>
  );
}
