"use client";

import AuthForm from "@/components/AuthForm";
import { useApp } from "@/context/AppContext";
import { useAuthOptions } from "@/lib/useAuthOptions";

export default function LoginPage() {
  const { login, signedOutReason } = useApp();
  // "Create an account" only while anyone may sign up (PUBLIC_SIGNUP).
  const options = useAuthOptions();
  return (
    <AuthForm
      notice={signedOutReason}
      title="Sign in"
      subtitle="Access your organization’s audit workspace."
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        { name: "password", label: "Password", type: "password", autoComplete: "current-password" },
      ]}
      submitLabel="Sign in"
      onSubmit={(v) => login(v.email, v.password)}
      footer={options?.public_signup ? { text: "New to AuditMind?", linkLabel: "Create an account", href: "/register" } : undefined}
    />
  );
}
