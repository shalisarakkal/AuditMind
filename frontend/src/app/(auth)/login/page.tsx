"use client";

import AuthForm from "@/components/AuthForm";
import { useApp } from "@/context/AppContext";

export default function LoginPage() {
  const { login } = useApp();
  return (
    <AuthForm
      title="Sign in"
      fields={[
        { name: "email", label: "Email", type: "email", autoComplete: "email" },
        { name: "password", label: "Password", type: "password", autoComplete: "current-password" },
      ]}
      submitLabel="Sign in"
      onSubmit={(v) => login(v.email, v.password)}
      footer={{ text: "New to AuditMind?", linkLabel: "Create an account", href: "/register" }}
    />
  );
}
