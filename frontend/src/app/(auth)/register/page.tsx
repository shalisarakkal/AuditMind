"use client";

import AuthForm from "@/components/AuthForm";
import { useApp } from "@/context/AppContext";

export default function RegisterPage() {
  const { register } = useApp();
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
