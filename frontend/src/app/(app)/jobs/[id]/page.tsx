"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";

import { api } from "@/lib/api";
import { SummaryCard } from "@/components/summary";
import { Card, Spinner } from "@/components/ui";

type JobView = {
  status: string;
  phase: string | null;
  error: string | null;
  summaries: Record<string, string>;
  complete_notes: boolean;
  summary_types: string[];
};

export default function JobPage() {
  const params = useParams();
  const router = useRouter();
  const id = String(params.id);
  const [job, setJob] = useState<JobView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      for (let i = 0; i < 200 && active; i++) {
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
    })();
    return () => {
      active = false;
    };
  }, [id, router]);

  const ordered = [...(job?.summary_types ?? []), ...(job?.complete_notes ? ["notes"] : [])];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-5 py-8">
      <Link href="/history" className="text-sm text-muted transition-colors hover:text-fg">
        ← History
      </Link>
      {error && <Card className="border-red-500/40 bg-red-500/5 p-4 text-sm text-red-500">{error}</Card>}
      {!job && !error && (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-5 w-5" />
        </div>
      )}
      {job && job.status !== "done" && !error && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner className="h-4 w-4" /> Working… <span className="font-medium text-fg">{job.phase ?? job.status}</span>
        </Card>
      )}
      {job?.status === "done" &&
        ordered.map((t) => (job.summaries[t] ? <SummaryCard key={t} type={t} content={job.summaries[t]} /> : null))}
    </div>
  );
}
