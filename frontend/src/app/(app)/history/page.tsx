"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import { Card, Spinner } from "@/components/ui";

type JobItem = {
  job_id: string;
  status: string;
  created_at: string;
  summary_types: string[];
  complete_notes: boolean;
  preview: string;
};

const BADGE: Record<string, string> = {
  done: "border-emerald-500/30 bg-emerald-500/10 text-emerald-500",
  error: "border-red-500/30 bg-red-500/10 text-red-500",
  running: "border-amber-500/30 bg-amber-500/10 text-amber-500",
  queued: "border-border text-muted",
};

export default function HistoryPage() {
  const [items, setItems] = useState<JobItem[] | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/api/jobs");
        if (active) setItems(res.ok ? ((await res.json()) as JobItem[]) : []);
      } catch {
        if (active) setItems([]);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-5 py-8">
      {items === null ? (
        <div className="flex justify-center py-16 text-muted">
          <Spinner className="h-5 w-5" />
        </div>
      ) : items.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted">
          No summaries yet.{" "}
          <Link href="/summarize" className="text-fg underline">
            Create one →
          </Link>
        </Card>
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((j) => (
            <Link key={j.job_id} href={`/jobs/${j.job_id}`}>
              <Card className="flex items-center gap-4 p-4 transition-colors hover:bg-surface-2">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-fg">{j.preview || "(no preview)"}</p>
                  <p className="mt-1 text-xs text-muted">
                    {new Date(j.created_at + "Z").toLocaleString()} ·{" "}
                    {j.summary_types.length + (j.complete_notes ? 1 : 0)} summaries
                  </p>
                </div>
                <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${BADGE[j.status] ?? BADGE.queued}`}>
                  {j.status}
                </span>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
