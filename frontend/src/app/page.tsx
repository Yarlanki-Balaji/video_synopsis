"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";

type Me = { id: string; email: string; status: string };

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/auth/me");
        const data = res.ok ? ((await res.json()) as Me) : null;
        if (active) setMe(data);
      } catch {
        if (active) setMe(null);
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    setMe(null);
  }

  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-24 font-sans dark:bg-black">
      <main className="flex w-full max-w-xl flex-col gap-8 rounded-2xl border border-black/[.06] bg-white p-10 shadow-sm dark:border-white/[.08] dark:bg-zinc-950">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-widest text-zinc-400">
            M1 · Auth
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
            Video Synopsis AI
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Sign in to summarize videos.
          </p>
        </div>

        <div className="rounded-xl border border-black/[.06] bg-zinc-50 px-5 py-4 dark:border-white/[.08] dark:bg-black">
          {loading ? (
            <p className="text-sm text-zinc-500">Checking session…</p>
          ) : me ? (
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
                <span className="text-sm">
                  Signed in as <span className="font-medium">{me.email}</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Link
                  href="/summarize"
                  className="rounded-full bg-foreground px-4 py-1.5 text-sm font-medium text-background hover:opacity-90"
                >
                  Summarize
                </Link>
                <button
                  onClick={logout}
                  className="rounded-full border border-black/[.1] px-4 py-1.5 text-sm font-medium hover:bg-black/[.04] dark:border-white/[.15] dark:hover:bg-white/[.06]"
                >
                  Log out
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm text-zinc-500">Not signed in</span>
              <div className="flex gap-2">
                <Link
                  href="/login"
                  className="rounded-full bg-foreground px-4 py-1.5 text-sm font-medium text-background hover:opacity-90"
                >
                  Log in
                </Link>
                <Link
                  href="/signup"
                  className="rounded-full border border-black/[.1] px-4 py-1.5 text-sm font-medium hover:bg-black/[.04] dark:border-white/[.15] dark:hover:bg-white/[.06]"
                >
                  Sign up
                </Link>
              </div>
            </div>
          )}
        </div>

        <p className="text-xs text-zinc-400">
          Next: M2 job engine + Groq, then M3 transcript capture, then the summarize page.
        </p>
      </main>
    </div>
  );
}
