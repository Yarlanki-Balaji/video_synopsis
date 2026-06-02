"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, AuthError, AuthSuccess, PasswordField, SubmitButton } from "@/components/auth";
import { Spinner } from "@/components/ui";

function ResetForm() {
  const router = useRouter();
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    if (!token) return setError("This reset link is missing its token. Request a new one.");
    if (password !== confirm) return setError("Passwords don't match.");
    setBusy(true);
    try {
      const res = await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
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

  if (done) {
    return (
      <AuthSuccess>Password updated. Taking you to the log in page…</AuthSuccess>
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {!token && (
        <AuthError>
          This reset link is invalid or incomplete.{" "}
          <Link href="/forgot-password" className="font-medium underline">
            Request a new one
          </Link>
          .
        </AuthError>
      )}
      <PasswordField label="New password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 8 characters" />
      <PasswordField label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
      {error && <AuthError>{error}</AuthError>}
      <SubmitButton busy={busy}>Update password</SubmitButton>
    </form>
  );
}

export default function ResetPasswordPage() {
  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Set a new password for your account."
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
