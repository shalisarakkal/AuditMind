"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import PasswordInput from "./PasswordInput";

export type AuthField = {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  required?: boolean;
};

type AuthFormProps = {
  title: string;
  subtitle?: string;
  fields: AuthField[];
  submitLabel: string;
  onSubmit(values: Record<string, string>): Promise<void>;
  footer?: { text: string; linkLabel: string; href: string };
  /** Shown above the fields, e.g. why the user was signed out. */
  notice?: string | null;
};

/** Shared form for the login and register pages. */
export default function AuthForm({ title, subtitle, fields, submitLabel, onSubmit, footer, notice }: AuthFormProps) {
  const router = useRouter();
  const [values, setValues] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Until React has hydrated, a submit would be a native GET with the
  // password in the URL; keep the button disabled until then.
  const [ready, setReady] = useState(false);
  useEffect(() => setReady(true), []);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit(values);
      router.replace("/");
    } catch (err) {
      setError((err as Error).message);
      setSubmitting(false);
    }
  }

  return (
    <form method="post" onSubmit={handleSubmit} className="space-y-5 rounded-2xl border border-white/15 bg-white/5 p-6 shadow-2xl shadow-black/20 sm:p-8">
      <div className="space-y-2">
        <h1 className="text-xl font-semibold tracking-tight text-white">{title}</h1>
        {subtitle && <p className="text-sm leading-6 text-white/65">{subtitle}</p>}
      </div>
      {notice && !error && <p className="text-sm text-amber-200">{notice}</p>}
      {fields.map((field) => (
        <div key={field.name}>
          <label htmlFor={field.name} className="block text-sm text-white/70">
            {field.label}
          </label>
          {field.type === "password" ? <PasswordInput
            label={field.label}
            containerClassName="mt-2"
            id={field.name} name={field.name} autoComplete={field.autoComplete}
            required={field.required ?? true} value={values[field.name] ?? ""}
            onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            className="h-11 min-w-0 w-full rounded-lg border border-white/20 bg-white/5 px-3 text-sm text-white focus:border-cyan focus:outline-none focus:ring-2 focus:ring-cyan/25"
          /> : <input
            id={field.name}
            name={field.name}
            type={field.type ?? "text"}
            autoComplete={field.autoComplete}
            required={field.required ?? true}
            value={values[field.name] ?? ""}
            onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            className="mt-2 h-11 min-w-0 w-full rounded-lg border border-white/20 bg-white/5 px-3 text-sm text-white focus:border-cyan focus:outline-none focus:ring-2 focus:ring-cyan/25"
          />}
        </div>
      ))}
      {error && (
        <p role="alert" className="text-sm text-red-300">
          {error}
        </p>
      )}
      <button
        type="submit"
        disabled={!ready || submitting}
        className="h-11 w-full rounded-lg bg-cyan text-sm font-semibold text-navy hover:bg-cyan/90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan disabled:cursor-not-allowed disabled:opacity-60"
      >
        {submitting ? "Please wait…" : submitLabel}
      </button>
      {footer && (
        <p className="text-center text-sm text-white/60">
          {footer.text}{" "}
          <Link href={footer.href} className="rounded text-cyan underline decoration-cyan/60 underline-offset-4 hover:decoration-cyan focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan">
            {footer.linkLabel}
          </Link>
        </p>
      )}
    </form>
  );
}
