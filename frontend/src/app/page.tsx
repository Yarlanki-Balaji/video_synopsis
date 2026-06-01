"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function Landing() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/auth/me");
        if (!active) return;
        if (res.ok) {
          router.replace("/summarize");
          return;
        }
        setChecking(false);
      } catch {
        if (active) setChecking(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg text-muted">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg text-fg">
      <header className="flex items-center justify-between px-6 py-5">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-accent text-accent-contrast">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
              <rect x="3" y="4" width="18" height="16" rx="3" />
              <path d="m10 8 6 4-6 4V8z" />
            </svg>
          </span>
          <span className="font-semibold tracking-tight">Video Synopsis</span>
        </div>
        <div className="flex items-center gap-2">
          <Link href="/login" className="rounded-lg px-4 py-2 text-sm text-muted transition-colors hover:text-fg">
            Log in
          </Link>
          <Link
            href="/signup"
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-contrast transition-opacity hover:opacity-90"
          >
            Sign up
          </Link>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 pb-24 text-center">
        <span className="mb-5 rounded-full border border-border px-3 py-1 text-xs text-muted">
          AI video summaries
        </span>
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Summarize any video in seconds
        </h1>
        <p className="mt-4 max-w-md text-muted">
          Paste a transcript and get brief, detailed, bullet, chapter, and ELI5 summaries — plus complete
          study notes. Long videos handled automatically.
        </p>
        <div className="mt-8 flex gap-3">
          <Link
            href="/signup"
            className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-accent-contrast transition-opacity hover:opacity-90"
          >
            Get started
          </Link>
          <Link
            href="/login"
            className="rounded-lg border border-border px-5 py-2.5 text-sm font-medium transition-colors hover:bg-surface-2"
          >
            Log in
          </Link>
        </div>
      </main>
    </div>
  );
}
