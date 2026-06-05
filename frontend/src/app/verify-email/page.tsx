"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, AuthSuccess, Field, SubmitButton } from "@/components/auth";
import { Spinner } from "@/components/ui";

function VerifyForm() {
  const router = useRouter();
  const email = useSearchParams().get("email") ?? "";
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resent, setResent] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!email) return setError("Missing email — please sign up again.");
    setBusy(true);
    try {
      const res = await api("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify({ email, code: code.trim() }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Verification failed"));
      // verify-email signs the user in (sets cookies) on success.
      router.push("/summarize");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  async function resend() {
    setError(null);
    setResent(false);
    try {
      await api("/auth/resend-verification", { method: "POST", body: JSON.stringify({ email }) });
      setResent(true);
    } catch {
      /* always best-effort */
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {email && (
        <p className="text-sm text-muted">
          We sent a 6-digit code to <span className="font-medium text-fg">{email}</span>.
        </p>
      )}
      {resent && <AuthSuccess>A new code is on its way — check your inbox.</AuthSuccess>}
      <Field
        label="Verification code"
        value={code}
        onChange={setCode}
        placeholder="123456"
        autoComplete="one-time-code"
      />
      {error && <AuthError>{error}</AuthError>}
      <SubmitButton busy={busy}>Verify email</SubmitButton>
      <button type="button" onClick={resend} className="self-center text-sm text-muted transition-colors hover:text-accent-text">
        Didn&apos;t get it? Resend code
      </button>
    </form>
  );
}

export default function VerifyEmailPage() {
  return (
    <AuthShell
      title="Verify your email"
      subtitle="Enter the code we emailed you to activate your account."
      footer={
        <Link href="/login" className="font-medium text-accent-text hover:underline">
          Back to log in
        </Link>
      }
    >
      <Suspense fallback={<div className="grid h-24 place-items-center text-muted"><Spinner className="h-5 w-5" /></div>}>
        <VerifyForm />
      </Suspense>
    </AuthShell>
  );
}
