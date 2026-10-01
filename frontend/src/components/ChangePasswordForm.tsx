"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useApp } from "@/context/AppContext";
import { api, ApiError } from "@/lib/apiClient";
import type { PasswordRules } from "@/lib/types";

/** What the rule asks for, as lines to show above the form. */
export function describeRules(rules: PasswordRules): string[] {
  // The org(s) asking for these settings' stricter values, if any.
  const by = (...settings: string[]) => {
    const orgs = [...new Set(settings.map((s) => rules.required_by[s]).filter(Boolean))];
    return orgs.length > 0 ? ` (required by ${orgs.join(", ")})` : "";
  };
  const lines = [`${rules.min_length} to ${rules.max_length} characters, in any language${by("min_length")}`];
  const kinds = (
    [
      ["require_upper", "an upper-case letter (A-Z, or any script with capitals)"],
      ["require_lower", "a lower-case letter"],
      ["require_digit", "a digit"],
      ["require_symbol", "a symbol (such as ! or #)"],
    ] as const
  ).filter(([setting]) => rules[setting]);
  if (kinds.length > 0) {
    lines.push(`At least ${kinds.map(([, kind]) => kind).join(", ")}${by(...kinds.map(([setting]) => setting))}`);
  }
  lines.push("Not your email address, nor your current password");
  if (rules.history_count > 0) lines.push(`Not one of your last ${rules.history_count} passwords${by("history_count")}`);
  if (rules.expiry_days > 0) lines.push(`It must be changed every ${rules.expiry_days} days${by("expiry_days")}`);
  return lines;
}

type Problem = { code: string; message: string };

/** Change one's own password: the current one, then the new one twice. When
 * it's required (a temporary or expired password) there's no way around it
 * but Sign out. */
export default function ChangePasswordForm({ onDone }: { onDone(): void }) {
  const { changePassword, mustChangePassword, logout } = useApp();
  const [rules, setRules] = useState<PasswordRules | null>(null);
  const [values, setValues] = useState({ current: "", next: "", confirm: "" });
  const [problems, setProblems] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api
      .get<PasswordRules>("/auth/password-rules")
      .then(setRules)
      .catch(() => undefined); // the form works without them
  }, []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (values.next !== values.confirm) {
      setProblems(["The new passwords don't match"]);
      return;
    }
    setSubmitting(true);
    setProblems([]);
    try {
      await changePassword(values.current, values.next);
      onDone();
    } catch (err) {
      const listed = (err instanceof ApiError && (err.detail as { problems?: Problem[] } | undefined)?.problems) || null;
      setProblems(listed ? listed.map((p) => p.message) : [(err as Error).message]);
      setSubmitting(false);
    }
  }

  const field = (name: keyof typeof values, label: string, autoComplete: string) => (
    <div>
      <label htmlFor={name} className="block text-sm text-white/70">
        {label}
      </label>
      <input
        id={name}
        name={name}
        type="password"
        autoComplete={autoComplete}
        required
        value={values[name]}
        onChange={(e) => setValues({ ...values, [name]: e.target.value })}
        className="mt-1 w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none"
      />
    </div>
  );

  return (
    <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-6">
      <h1 className="text-lg font-semibold text-white">Change password</h1>
      {mustChangePassword && (
        <p className="text-sm text-amber-200">
          Your password must be changed before you continue (it is temporary, or has expired).
        </p>
      )}
      {rules && (
        <ul aria-label="Password rules" className="list-disc space-y-0.5 pl-5 text-xs text-white/60">
          {describeRules(rules).map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      {field("current", mustChangePassword ? "Current (temporary) password" : "Current password", "current-password")}
      {field("next", "New password", "new-password")}
      {field("confirm", "New password again", "new-password")}
      {problems.length > 0 && (
        <ul role="alert" className="space-y-0.5 text-sm text-red-300">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-md bg-cyan py-2 text-sm font-medium text-navy disabled:opacity-60"
      >
        {submitting ? "Please wait…" : "Change password"}
      </button>
      <p className="text-center text-sm text-white/60">
        {mustChangePassword ? (
          <button type="button" onClick={() => void logout()} className="text-cyan hover:underline">
            Sign out
          </button>
        ) : (
          <Link href="/" className="text-cyan hover:underline">
            Cancel
          </Link>
        )}
      </p>
    </form>
  );
}
