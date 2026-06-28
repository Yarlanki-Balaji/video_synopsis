"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { api } from "@/lib/api";
import { SummaryCard } from "@/components/summary";
import { Button, Card, Icons, Skeleton, Spinner } from "@/components/ui";
import { ConfirmDialog } from "@/components/modal";
import { useToast } from "@/components/toast";
import { downloadText, jobToMarkdown, orderedKeys } from "@/lib/summaries";

type JobView = {
  status: string;
  phase: string | null;
  error: string | null;
  summaries: Record<string, string>;
  complete_notes: boolean;
  summary_types: string[];
  transcript?: string;
};

const PHASE_LABEL: Record<string, string> = {
  queued: "Queued",
  claimed: "Starting up",
  summarizing: "Summarizing",
  notes: "Writing study notes",
  cached: "Retrieving",
  requeued: "Retrying",
  recovered: "Recovering",
};

export default function JobPage() {
  const params = useParams();
  const router = useRouter();
  const toast = useToast();
  const id = String(params.id);
  const [job, setJob] = useState<JobView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        for (let i = 0; i < 400 && active; i++) {
          const res = await api(`/api/jobs/${id}`);
          if (res.status === 401) return router.push("/login");
          if (res.status === 404) return setError("Summary not found.");
          if (!res.ok) return setError("Failed to load.");
          const data = (await res.json()) as JobView;
          if (!active) return;
          setJob(data);
          if (data.status === "done") return;
          if (data.status === "error") return setError(data.error || "Job failed.");
          await new Promise((r) => setTimeout(r, 1500));
        }
      } catch {
        // Transient network/parse failure during polling — surface it instead
        // of leaving the page stuck on the loading skeleton forever.
        if (active) setError("Failed to load. Check your connection and refresh.");
      }
    })();
    return () => {
      active = false;
    };
  }, [id, router]);

  const keys = useMemo(() => (job ? orderedKeys(job.summary_types, job.complete_notes) : []), [job]);

  function markdown() {
    if (!job) return "";
    return jobToMarkdown(job.summaries, keys, { title: "Video summary", date: new Date().toLocaleString() });
  }

  async function doDelete() {
    setDeleting(true);
    try {
      const res = await api(`/api/jobs/${id}`, { method: "DELETE" });
      if (!res.ok && res.status !== 404) throw new Error();
      toast.success("Summary deleted");
      router.push("/history");
    } catch {
      toast.error("Couldn't delete", "Please try again.");
      setDeleting(false);
      setConfirm(false);
    }
  }

  const done = job?.status === "done";

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-5 px-4 py-6 sm:px-5 sm:py-8">
      <div className="flex items-center justify-between gap-2">
        <Link
          href="/history"
          className="inline-flex items-center gap-1.5 text-sm text-muted transition-colors hover:text-fg"
        >
          <Icons.chevronLeft className="h-4 w-4" /> History
        </Link>
        {done && keys.length > 0 && (
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => downloadText("video-summary.md", markdown())}>
              <Icons.download className="h-4 w-4" /> Download
            </Button>
            <Button variant="danger" size="sm" onClick={() => setConfirm(true)}>
              <Icons.trash className="h-4 w-4" /> Delete
            </Button>
          </div>
        )}
      </div>

      {error && (
        <Card className="flex items-start gap-2 border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </Card>
      )}

      {!job && !error && (
        <div className="flex flex-col gap-4">
          <Skeleton className="h-40" />
          <Skeleton className="h-40" />
        </div>
      )}

      {job && job.status !== "done" && !error && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner className="h-4 w-4 text-accent-text" />
          <span>
            Working… <span className="font-medium text-fg">{PHASE_LABEL[job.phase ?? ""] ?? "Processing"}</span>
          </span>
        </Card>
      )}

      {done && keys.map((t) => (job.summaries[t] ? <SummaryCard key={t} type={t} content={job.summaries[t]} /> : null))}

      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        onConfirm={doDelete}
        title="Delete this summary?"
        message="This removes it from your history. This can't be undone."
        confirmLabel="Delete"
        danger
        busy={deleting}
      />
    </div>
  );
}
