"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api, errorDetail } from "@/lib/api";
import { Markdown } from "@/components/markdown";

const TYPES = [
  { key: "brief", label: "Brief" },
  { key: "detailed", label: "Detailed" },
  { key: "bullets", label: "Bullet points" },
  { key: "chapters", label: "Chapters" },
  { key: "eli5", label: "ELI5" },
] as const;

type JobView = {
  status: string;
  phase: string | null;
  error: string | null;
  summaries: Record<string, string>;
  complete_notes: boolean;
  summary_types: string[];
};

function labelFor(key: string): string {
  if (key === "notes") return "Complete notes";
  return TYPES.find((t) => t.key === key)?.label ?? key;
}

export default function SummarizePage() {
  const router = useRouter();
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [transcript, setTranscript] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set(TYPES.map((t) => t.key)));
  const [notes, setNotes] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobView | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/auth/me");
        if (!active) return;
        setAuthed(res.ok);
        if (!res.ok) router.push("/login");
      } catch {
        if (active) setAuthed(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function poll(jobId: string) {
    for (let i = 0; i < 60; i++) {
      const res = await api(`/api/jobs/${jobId}`);
      if (res.status === 401) {
        router.push("/login");
        return;
      }
      if (!res.ok) throw new Error("Lost track of the job.");
      const data = (await res.json()) as JobView;
      setJob(data);
      if (data.status === "done") return;
      if (data.status === "error") throw new Error(data.error || "The job failed.");
      await new Promise((r) => setTimeout(r, 1500));
    }
    throw new Error("Timed out waiting for the summary.");
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setJob(null);
    const types = TYPES.map((t) => t.key).filter((k) => selected.has(k));
    if (types.length === 0) {
      setError("Pick at least one summary type.");
      return;
    }
    setBusy(true);
    try {
      const res = await api("/api/summarize", {
        method: "POST",
        body: JSON.stringify({ transcript_text: transcript, summary_types: types, complete_notes: notes }),
      });
      if (res.status === 401) {
        router.push("/login");
        return;
      }
      if (!res.ok) throw new Error(await errorDetail(res, "Summarize failed"));
      const { job_id } = (await res.json()) as { job_id: string };
      await poll(job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (authed === null) {
    return <div className="flex flex-1 items-center justify-center text-sm text-zinc-500">Loading…</div>;
  }

  const done = job?.status === "done";
  const orderedTypes = [
    ...(job?.summary_types ?? []),
    ...(job?.complete_notes ? ["notes"] : []),
  ];

  return (
    <div className="w-full flex-1 bg-zinc-50 px-6 py-12 font-sans dark:bg-black">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-8">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold tracking-tight">Summarize a transcript</h1>
          <Link href="/" className="text-sm text-zinc-500 underline">
            Home
          </Link>
        </header>

        <form onSubmit={onSubmit} className="flex flex-col gap-5 rounded-2xl border border-black/[.06] bg-white p-6 shadow-sm dark:border-white/[.08] dark:bg-zinc-950">
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={10}
            required
            placeholder="Paste a transcript here…"
            className="w-full resize-y rounded-lg border border-black/[.1] bg-white p-3 text-sm outline-none focus:border-zinc-400 dark:border-white/[.15] dark:bg-black"
          />

          <div className="flex flex-wrap gap-3">
            {TYPES.map((t) => (
              <label key={t.key} className="flex cursor-pointer items-center gap-2 rounded-full border border-black/[.1] px-3 py-1.5 text-sm dark:border-white/[.15]">
                <input type="checkbox" checked={selected.has(t.key)} onChange={() => toggle(t.key)} />
                {t.label}
              </label>
            ))}
            <label className="flex cursor-pointer items-center gap-2 rounded-full border border-black/[.1] px-3 py-1.5 text-sm dark:border-white/[.15]">
              <input type="checkbox" checked={notes} onChange={(e) => setNotes(e.target.checked)} />
              Complete notes
            </label>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}

          <button
            type="submit"
            disabled={busy}
            className="h-11 rounded-full bg-foreground font-medium text-background transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "Summarizing…" : "Summarize"}
          </button>
        </form>

        {job && !done && (
          <p className="text-sm text-zinc-500">
            Working… <span className="font-medium">{job.phase ?? job.status}</span>
          </p>
        )}

        {done && (
          <div className="flex flex-col gap-6">
            {orderedTypes.map((t) =>
              job?.summaries[t] ? (
                <section key={t} className="rounded-2xl border border-black/[.06] bg-white p-6 shadow-sm dark:border-white/[.08] dark:bg-zinc-950">
                  <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-zinc-400">
                    {labelFor(t)}
                  </h2>
                  <Markdown>{job.summaries[t]}</Markdown>
                </section>
              ) : null
            )}
          </div>
        )}
      </div>
    </div>
  );
}
