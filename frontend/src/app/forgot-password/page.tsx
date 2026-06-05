"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, Field, SubmitButton } from "@/components/auth";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      // Always 202 (no account enumeration). On success we go enter the code.
      const res = await api("/auth/request-password-reset", {
        method: "POST",
        body: JSON.stringify({ email }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Could not send the reset code"));
      router.push(`/reset-password?email=${encodeURIComponent(email)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter your email and we'll send you a 6-digit reset code."
      footer={
        <>
          Remembered it?{" "}
          <Link href="/login" className="font-medium text-accent-text hover:underline">
            Back to log in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" placeholder="you@example.com" />
        {error && <AuthError>{error}</AuthError>}
        <SubmitButton busy={busy}>Send reset code</SubmitButton>
      </form>
    </AuthShell>
  );
}
