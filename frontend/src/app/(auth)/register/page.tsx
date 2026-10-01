"use client";

import Link from "next/link";

import AuthForm from "@/components/AuthForm";
import { useApp } from "@/context/AppContext";
import { useAuthOptions } from "@/lib/useAuthOptions";

export default function RegisterPage() {
  const { register } = useApp();
  const options = useAuthOptions();
  if (options && !options.public_signup) {
    return (
      <div className="space-y-4 rounded-xl border border-white/10 bg-white/5 p-6 text-sm">
        <h1 className="text-lg font-semibold text-white">Sign-up is closed</h1>
        <p className="text-white/70">Accounts are made by an organization&apos;s administrator. Ask yours for one.</p>
        <Link href="/login" className="text-cyan hover:underline">
          Sign in
        </Link>
      </div>
    );
  }
  return (
    <AuthForm
      title="Create your account"
      fields={[
        { name: "orgName", label: "Organization name", autoComplete: "organization" },
        { name: "name", label: "Your name", autoComplete: "name", required: false },
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        { name: "password", label: "Password", type: "password", autoComplete: "new-password" },
      ]}
      submitLabel="Create account"
      onSubmit={(v) => register({ orgName: v.orgName, name: v.name, email: v.email, password: v.password })}
      footer={{ text: "Already have an account?", linkLabel: "Sign in", href: "/login" }}
    />
  );
}
