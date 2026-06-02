"use client";

import { useState } from "react";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, AuthSuccess, Field, SubmitButton } from "@/components/auth";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // The backend always returns 202 (no account enumeration).
      const res = await api("/auth/request-password-reset", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Could not send the reset email"));
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email and we'll send you a link to set a new password."
      footer={
        <>
          Remembered it?{" "}
          <Link href="/login" className="font-medium text-accent-text hover:underline">
            Back to log in
          </Link>
        </>
      }
    >
      {sent ? (
        <div className="flex flex-col gap-4">
          <AuthSuccess>
            If an account exists for <span className="font-medium">{email}</span>, a reset link is on its way. The
            link expires in 60 minutes.
          </AuthSuccess>
          <Link
            href="/login"
            className="inline-flex h-11 items-center justify-center rounded-[var(--radius-button)] border border-border bg-surface font-medium text-fg transition-colors hover:bg-surface-2"
          >
            Back to log in
          </Link>
        </div>
      ) : (
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" placeholder="you@example.com" />
          {error && <AuthError>{error}</AuthError>}
          <SubmitButton busy={busy}>Send reset link</SubmitButton>
        </form>
      )}
    </AuthShell>
  );
}
