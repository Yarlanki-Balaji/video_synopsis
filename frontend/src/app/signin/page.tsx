"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, Field, SubmitButton } from "@/components/auth";

export default function SigninPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api("/auth/signin", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Sign in failed"));
      router.push("/summarize");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Welcome to Video Synopsis"
      subtitle="Enter your email to get started. No password needed."
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field
          label="Email address"
          type="email"
          value={email}
          onChange={setEmail}
          autoComplete="email"
          placeholder="you@example.com"
        />
        {error && <AuthError>{error}</AuthError>}
        <SubmitButton busy={busy}>Continue with email</SubmitButton>
      </form>
    </AuthShell>
  );
}
