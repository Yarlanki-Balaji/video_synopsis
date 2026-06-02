"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import { Badge, Button, Card, Chip, IconButton, Icons, Input, Skeleton } from "@/components/ui";
import { ConfirmDialog } from "@/components/modal";
import { useToast } from "@/components/toast";
import { SUMMARY_TYPES, NOTES_DEF, downloadText, jobToMarkdown, orderedKeys } from "@/lib/summaries";

type JobItem = {
  job_id: string;
  status: string;
  created_at: string;
  summary_types: string[];
  complete_notes: boolean;
  preview: string;
};

const STATUS_FILTERS = ["all", "done", "running", "queued", "error"] as const;
type StatusFilter = (typeof STATUS_FILTERS)[number];

const STATUS_TONE: Record<string, "success" | "danger" | "warn" | "neutral"> = {
  done: "success",
  error: "danger",
  running: "warn",
  queued: "neutral",
};

export default function HistoryPage() {
  const toast = useToast();
  const [items, setItems] = useState<JobItem[] | null>(null);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [type, setType] = useState("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [confirm, setConfirm] = useState<{ ids: string[] } | null>(null);
  const [working, setWorking] = useState(false);

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

  const filtered = useMemo(() => {
    if (!items) return [];
    const needle = q.trim().toLowerCase();
    return items.filter((j) => {
      if (status !== "all" && j.status !== status) return false;
      if (type !== "all") {
        const has = type === "notes" ? j.complete_notes : j.summary_types.includes(type);
        if (!has) return false;
      }
      if (needle && !j.preview.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [items, q, status, type]);

  // Keep selection within the currently-visible set.
  const visibleIds = filtered.map((j) => j.job_id);
  const selectedVisible = visibleIds.filter((id) => selected.has(id));
  const allSelected = visibleIds.length > 0 && selectedVisible.length === visibleIds.length;

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }
  function toggleAll() {
    setSelected(allSelected ? new Set() : new Set(visibleIds));
  }

  async function doDelete(ids: string[]) {
    setWorking(true);
    try {
      const results = await Promise.all(ids.map((id) => api(`/api/jobs/${id}`, { method: "DELETE" })));
      // Only drop the ones the server actually deleted (treat 404 as already-gone).
      const okIds = ids.filter((_, i) => results[i].ok || results[i].status === 404);
      setItems((prev) => (prev ? prev.filter((j) => !okIds.includes(j.job_id)) : prev));
      setSelected(new Set());
      const failed = ids.length - okIds.length;
      if (failed > 0) {
        toast.error(`Couldn't delete ${failed} ${failed === 1 ? "summary" : "summaries"}`, "Please try again.");
      } else {
        toast.success(ids.length > 1 ? `Deleted ${ids.length} summaries` : "Summary deleted");
      }
    } catch {
      toast.error("Couldn't delete", "Please try again.");
    } finally {
      setWorking(false);
      setConfirm(null);
    }
  }

  async function exportSelected() {
    const chosen = filtered.filter((j) => selected.has(j.job_id) && j.status === "done");
    if (chosen.length === 0) {
      toast.toast({ title: "Nothing to export", description: "Select finished summaries first.", variant: "warn" });
      return;
    }
    setWorking(true);
    try {
      const parts: string[] = [];
      for (const j of chosen) {
        const res = await api(`/api/jobs/${j.job_id}`);
        if (!res.ok) continue;
        const d = (await res.json()) as { summaries: Record<string, string>; summary_types: string[]; complete_notes: boolean };
        const keys = orderedKeys(d.summary_types, d.complete_notes);
        parts.push(jobToMarkdown(d.summaries, keys, { title: j.preview || "Summary", date: new Date(j.created_at + "Z").toLocaleString() }));
      }
      if (parts.length) downloadText(`summaries-${parts.length}.md`, parts.join("\n\n---\n\n"));
      toast.success(`Exported ${parts.length} ${parts.length === 1 ? "summary" : "summaries"}`);
    } catch {
      toast.error("Export failed");
    } finally {
      setWorking(false);
    }
  }

  const empty = items !== null && items.length === 0;

  return (
    <div className="mx-auto max-w-3xl px-4 py-6 sm:px-5 sm:py-8">
      {/* Controls */}
      {!empty && (
        <div className="mb-4 flex flex-col gap-3">
          <div className="relative">
            <Icons.search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search summaries…"
              className="pl-9"
              aria-label="Search history"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5">
              {STATUS_FILTERS.map((s) => (
                <Chip key={s} selected={status === s} onClick={() => setStatus(s)} className="capitalize">
                  {s}
                </Chip>
              ))}
            </div>
            <select
              value={type}
              onChange={(e) => setType(e.target.value)}
              aria-label="Filter by type"
              className="rounded-[var(--radius-field)] border border-border bg-surface px-2.5 py-1.5 text-sm text-fg outline-none focus:border-accent"
            >
              <option value="all">All types</option>
              {SUMMARY_TYPES.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
              <option value={NOTES_DEF.key}>{NOTES_DEF.label}</option>
            </select>
          </div>
        </div>
      )}

      {/* Selection action bar */}
      {selectedVisible.length > 0 && (
        <div className="mb-3 flex items-center justify-between gap-2 rounded-xl border border-border bg-surface-2/60 px-3 py-2 text-sm animate-fade-in">
          <span className="font-medium">{selectedVisible.length} selected</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={exportSelected} disabled={working}>
              <Icons.download className="h-4 w-4" /> Export
            </Button>
            <Button variant="danger" size="sm" onClick={() => setConfirm({ ids: selectedVisible })} disabled={working}>
              <Icons.trash className="h-4 w-4" /> Delete
            </Button>
          </div>
        </div>
      )}

      {/* List */}
      {items === null ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[68px]" />
          ))}
        </div>
      ) : empty ? (
        <Card className="flex flex-col items-center gap-3 p-12 text-center">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-accent-soft text-accent-text">
            <Icons.history className="h-6 w-6" />
          </span>
          <p className="text-sm text-muted">No summaries yet.</p>
          <Link
            href="/summarize"
            className="inline-flex h-9 items-center gap-2 rounded-[var(--radius-button)] bg-[image:var(--gradient-accent)] px-4 text-sm font-medium text-accent-contrast shadow-[var(--shadow-sm)] transition-[transform,box-shadow] hover:-translate-y-px hover:shadow-glow"
          >
            <Icons.sparkles className="h-4 w-4" /> Create your first summary
          </Link>
        </Card>
      ) : filtered.length === 0 ? (
        <Card className="p-10 text-center text-sm text-muted">No summaries match your filters.</Card>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-2 px-1">
            <button
              type="button"
              role="checkbox"
              aria-checked={allSelected ? true : selectedVisible.length === 0 ? false : "mixed"}
              onClick={toggleAll}
              className="flex items-center gap-2 text-xs text-muted transition-colors hover:text-fg"
            >
              <span
                className={`grid h-4 w-4 place-items-center rounded border ${allSelected || selectedVisible.length > 0 ? "border-accent bg-accent-strong text-accent-contrast" : "border-border-strong"}`}
              >
                {allSelected ? (
                  <Icons.check className="h-3 w-3" />
                ) : selectedVisible.length > 0 ? (
                  <span className="h-0.5 w-2 rounded-full bg-current" />
                ) : null}
              </span>
              Select all
            </button>
          </div>
          <div className="flex flex-col gap-2">
            {filtered.map((j) => {
              const isSel = selected.has(j.job_id);
              const count = j.summary_types.length + (j.complete_notes ? 1 : 0);
              return (
                <Card key={j.job_id} className="flex items-center gap-3 p-3 sm:p-4">
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={isSel}
                    onClick={() => toggle(j.job_id)}
                    aria-label={isSel ? "Deselect summary" : "Select summary"}
                    className={`grid h-5 w-5 shrink-0 place-items-center rounded border transition-colors ${isSel ? "border-accent bg-accent-strong text-accent-contrast" : "border-border-strong hover:border-accent"}`}
                  >
                    {isSel && <Icons.check className="h-3.5 w-3.5" />}
                  </button>
                  <Link href={`/jobs/${j.job_id}`} className="min-w-0 flex-1">
                    <p className="truncate text-sm text-fg">{j.preview || "(no preview)"}</p>
                    <p className="mt-1 text-xs text-muted">
                      {new Date(j.created_at + "Z").toLocaleString()} · {count} {count === 1 ? "summary" : "summaries"}
                    </p>
                  </Link>
                  <Badge tone={STATUS_TONE[j.status] ?? "neutral"} dot={j.status === "running"}>
                    {j.status}
                  </Badge>
                  <IconButton
                    size="sm"
                    tone="danger"
                    onClick={() => setConfirm({ ids: [j.job_id] })}
                    aria-label="Delete summary"
                    title="Delete"
                  >
                    <Icons.trash className="h-4 w-4" />
                  </IconButton>
                </Card>
              );
            })}
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirm !== null}
        onClose={() => setConfirm(null)}
        onConfirm={() => confirm && doDelete(confirm.ids)}
        title={confirm && confirm.ids.length > 1 ? `Delete ${confirm.ids.length} summaries?` : "Delete this summary?"}
        message="This removes it from your history. This can't be undone."
        confirmLabel="Delete"
        danger
        busy={working}
      />
    </div>
  );
}
