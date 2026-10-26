"use client";

import Link from "next/link";
import ProductBrand from "./ProductBrand";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export type AuthField = {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  required?: boolean;
};

type AuthFormProps = {
  title: string;
  fields: AuthField[];
  submitLabel: string;
  onSubmit(values: Record<string, string>): Promise<void>;
  footer?: { text: string; linkLabel: string; href: string };
  /** Shown above the fields, e.g. why the user was signed out. */
  notice?: string | null;
};

/** Shared form for the login and register pages. */
export default function AuthForm({ title, fields, submitLabel, onSubmit, footer, notice }: AuthFormProps) {
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
    <form method="post" onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-6">
      <ProductBrand />
      <h1 className="text-lg font-semibold text-white">{title}</h1>
      {notice && !error && <p className="text-sm text-amber-200">{notice}</p>}
      {fields.map((field) => (
        <div key={field.name}>
          <label htmlFor={field.name} className="block text-sm text-white/70">
            {field.label}
          </label>
          <input
            id={field.name}
            name={field.name}
            type={field.type ?? "text"}
            autoComplete={field.autoComplete}
            required={field.required ?? true}
            value={values[field.name] ?? ""}
            onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            className="mt-1 w-full rounded-md border border-white/15 bg-white/5 px-3 py-2 text-sm text-white focus:border-cyan focus:outline-none"
          />
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
        className="w-full rounded-md bg-cyan py-2 text-sm font-medium text-navy disabled:opacity-60"
      >
        {submitting ? "Please wait…" : submitLabel}
      </button>
      {footer && (
        <p className="text-center text-sm text-white/60">
          {footer.text}{" "}
          <Link href={footer.href} className="text-cyan hover:underline">
            {footer.linkLabel}
          </Link>
        </p>
      )}
    </form>
  );
}
