"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, Field, PasswordField, SubmitButton } from "@/components/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        const detail = await errorDetail(res, "Login failed");
        // Unverified account -> send them to enter the emailed code.
        if (res.status === 403 && /verify/i.test(detail)) {
          router.push(`/verify-email?email=${encodeURIComponent(email)}`);
          return;
        }
        throw new Error(detail);
      }
      router.push("/summarize");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Welcome back"
      subtitle="Log in to summarize videos and view your history."
      footer={
        <>
          Need an account?{" "}
          <Link href="/signup" className="font-medium text-accent-text hover:underline">
            Sign up
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" placeholder="you@example.com" />
        <div className="flex flex-col gap-1.5">
          <PasswordField label="Password" value={password} onChange={setPassword} autoComplete="current-password" />
          <Link href="/forgot-password" className="self-end text-xs text-muted hover:text-accent-text">
            Forgot password?
          </Link>
        </div>
        {error && <AuthError>{error}</AuthError>}
        <SubmitButton busy={busy}>Log in</SubmitButton>
      </form>
    </AuthShell>
  );
}
