"use client";

import { useEffect, useState } from "react";

// Inlined at build time; falls back to the local backend in dev.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Health = { status: string; service: string; environment: string };

export default function Home() {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/healthz`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json() as Promise<Health>;
      })
      .then((data) => {
        if (!active) return;
        setHealth(data);
        setState("ok");
      })
      .catch(() => active && setState("error"));
    return () => {
      active = false;
    };
  }, []);

  const pill = {
    loading: { dot: "bg-amber-400", text: "Connecting…", tone: "text-amber-600" },
    ok: { dot: "bg-emerald-500", text: "Backend connected", tone: "text-emerald-600" },
    error: { dot: "bg-red-500", text: "Backend unreachable", tone: "text-red-600" },
  }[state];

  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 px-6 py-24 font-sans dark:bg-black">
      <main className="flex w-full max-w-xl flex-col gap-8 rounded-2xl border border-black/[.06] bg-white p-10 shadow-sm dark:border-white/[.08] dark:bg-zinc-950">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-medium uppercase tracking-widest text-zinc-400">
            M0 · Scaffold
          </span>
          <h1 className="text-3xl font-semibold tracking-tight text-black dark:text-zinc-50">
            Video Synopsis AI
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400">
            Frontend (Next.js) and backend (FastAPI) are wired up. The card below
            pings the API&apos;s <code className="rounded bg-black/[.05] px-1 dark:bg-white/[.08]">/healthz</code>{" "}
            to confirm they talk to each other.
          </p>
        </div>

        <div className="flex items-center justify-between rounded-xl border border-black/[.06] bg-zinc-50 px-5 py-4 dark:border-white/[.08] dark:bg-black">
          <div className="flex items-center gap-3">
            <span className={`h-2.5 w-2.5 rounded-full ${pill.dot}`} />
            <span className={`font-medium ${pill.tone}`}>{pill.text}</span>
          </div>
          <code className="text-xs text-zinc-500">{API_URL}</code>
        </div>

        {health && (
          <pre className="overflow-x-auto rounded-xl bg-black/[.04] p-4 text-xs text-zinc-700 dark:bg-white/[.06] dark:text-zinc-300">
            {JSON.stringify(health, null, 2)}
          </pre>
        )}

        {state === "error" && (
          <p className="text-sm text-zinc-500">
            Start the API: <code>cd backend</code> →{" "}
            <code>uvicorn app.main:app --reload --port 8000</code>
          </p>
        )}
      </main>
    </div>
  );
}
