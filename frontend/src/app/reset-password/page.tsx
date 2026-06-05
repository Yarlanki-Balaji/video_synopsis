"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, AuthSuccess, Field, PasswordField, SubmitButton } from "@/components/auth";
import { Spinner } from "@/components/ui";

function ResetForm() {
  const router = useRouter();
  const email = useSearchParams().get("email") ?? "";
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [resent, setResent] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!email) return setError("Missing email — start again from the forgot-password page.");
    if (password !== confirm) return setError("Passwords don't match.");
    setBusy(true);
    try {
      const res = await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ email, code: code.trim(), password }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Could not reset your password"));
      setDone(true);
      setTimeout(() => router.push("/login"), 1600);
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
      await api("/auth/request-password-reset", { method: "POST", body: JSON.stringify({ email }) });
      setResent(true);
    } catch {
      /* best-effort */
    }
  }

  if (done) {
    return <AuthSuccess>Password updated. Taking you to the log in page…</AuthSuccess>;
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {email && (
        <p className="text-sm text-muted">
          Enter the code sent to <span className="font-medium text-fg">{email}</span>.
        </p>
      )}
      {resent && <AuthSuccess>A new code is on its way — check your inbox.</AuthSuccess>}
      <Field label="Reset code" value={code} onChange={setCode} placeholder="123456" autoComplete="one-time-code" />
      <PasswordField label="New password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 8 characters" />
      <PasswordField label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
      {error && <AuthError>{error}</AuthError>}
      <SubmitButton busy={busy}>Update password</SubmitButton>
      <button type="button" onClick={resend} className="self-center text-sm text-muted transition-colors hover:text-accent-text">
        Didn&apos;t get it? Resend code
      </button>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell
      title="Set a new password"
      subtitle="Enter the code we emailed you and choose a new password."
      footer={
        <Link href="/login" className="font-medium text-accent-text hover:underline">
          Back to log in
        </Link>
      }
    >
      <Suspense fallback={<div className="grid h-24 place-items-center text-muted"><Spinner className="h-5 w-5" /></div>}>
        <ResetForm />
      </Suspense>
    </AuthShell>
  );
}
