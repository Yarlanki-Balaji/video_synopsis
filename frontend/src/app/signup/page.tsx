"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { AuthShell, Field, SubmitButton } from "@/components/auth";

function SignupForm() {
  const router = useRouter();
  // Invite links look like /signup?email=...&invite=... — prefill from them.
  const params = useSearchParams();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [inviteToken, setInviteToken] = useState(params.get("invite") ?? "");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, invite_token: inviteToken }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Signup failed"));
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Closed beta — you need an invite to sign up."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="font-medium underline">
            Log in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <Field label="Email" type="email" value={email} onChange={setEmail} autoComplete="email" />
        <Field label="Invite token" value={inviteToken} onChange={setInviteToken} placeholder="From your invite email" />
        <Field label="Password" type="password" value={password} onChange={setPassword} autoComplete="new-password" hint="At least 8 characters" />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <SubmitButton busy={busy}>Create account</SubmitButton>
      </form>
    </AuthShell>
  );
}

export default function SignupPage() {
  // useSearchParams requires a Suspense boundary in the app router.
  return (
    <Suspense fallback={null}>
      <SignupForm />
    </Suspense>
  );
}
