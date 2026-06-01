"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { api, errorDetail } from "@/lib/api";
import { Button, Card, Spinner } from "@/components/ui";
import { SummaryCard } from "@/components/summary";

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

export default function SummarizePage() {
  const router = useRouter();
  const [transcript, setTranscript] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set(TYPES.map((t) => t.key)));
  const [notes, setNotes] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobView | null>(null);

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function poll(jobId: string) {
    for (let i = 0; i < 200; i++) {
      const res = await api(`/api/jobs/${jobId}`);
      if (res.status === 401) return router.push("/login");
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
    if (types.length === 0) return setError("Pick at least one summary type.");
    if (!transcript.trim()) return setError("Paste a transcript first.");
    setBusy(true);
    try {
      const res = await api("/api/summarize", {
        method: "POST",
        body: JSON.stringify({ transcript_text: transcript, summary_types: types, complete_notes: notes }),
      });
      if (res.status === 401) return router.push("/login");
      if (!res.ok) throw new Error(await errorDetail(res, "Summarize failed"));
      const { job_id } = (await res.json()) as { job_id: string };
      await poll(job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const done = job?.status === "done";
  const ordered = [...(job?.summary_types ?? []), ...(job?.complete_notes ? ["notes"] : [])];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-5 py-8">
      <form onSubmit={onSubmit}>
        <Card className="flex flex-col gap-4 p-5">
          <textarea
            value={transcript}
            onChange={(e) => setTranscript(e.target.value)}
            rows={9}
            placeholder="Paste a transcript…"
            className="w-full resize-y rounded-lg border border-border bg-bg p-3 text-sm leading-relaxed outline-none placeholder:text-muted focus:border-accent"
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              {TYPES.map((t) => {
                const on = selected.has(t.key);
                return (
                  <button
                    key={t.key}
                    type="button"
                    onClick={() => toggle(t.key)}
                    className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                      on ? "border-accent bg-surface-2 text-fg" : "border-border text-muted hover:text-fg"
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
              <button
                type="button"
                onClick={() => setNotes((v) => !v)}
                className={`rounded-full border px-3 py-1.5 text-sm transition-colors ${
                  notes ? "border-accent bg-surface-2 text-fg" : "border-border text-muted hover:text-fg"
                }`}
              >
                + Complete notes
              </button>
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? (
                <>
                  <Spinner className="h-4 w-4" /> Summarizing…
                </>
              ) : (
                "Summarize"
              )}
            </Button>
          </div>
        </Card>
      </form>

      {error && (
        <Card className="border-red-500/40 bg-red-500/5 p-4 text-sm text-red-500">{error}</Card>
      )}

      {job && !done && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner className="h-4 w-4" />
          Working… <span className="font-medium text-fg">{job.phase ?? job.status}</span>
        </Card>
      )}

      {done &&
        ordered.map((t) =>
          job?.summaries[t] ? <SummaryCard key={t} type={t} content={job.summaries[t]} /> : null
        )}
    </div>
  );
}
