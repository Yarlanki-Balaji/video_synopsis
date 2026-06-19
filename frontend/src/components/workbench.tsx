"use client";

import { useCallback, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { api, errorDetail, API_URL } from "@/lib/api";
import { Button, Card, Chip, IconButton, Icons, Input, Spinner, Textarea } from "@/components/ui";
import { SummaryCard } from "@/components/summary";
import { useToast } from "@/components/toast";
import { SUMMARY_TYPES, NOTES_DEF, downloadText, jobToMarkdown, labelFor, orderedKeys } from "@/lib/summaries";
import { TestUnderstandingButton } from "@/components/test-understanding-button";

const MIN_CHARS = 50;
const MAX_CHARS = 200_000;
const MAX_UPLOAD_MB = 200;

export type Mode = "url" | "upload" | "paste";

const MODE_META: Record<Mode, { icon: keyof typeof Icons; title: string; sub: string }> = {
  url: { icon: "logo", title: "Summarize from YouTube", sub: "Paste a video link — we fetch the captions, or transcribe the audio when there are none." },
  upload: { icon: "upload", title: "Summarize an upload", sub: "Upload a video or audio file — the audio is extracted right in your browser." },
  paste: { icon: "fileText", title: "Summarize a transcript", sub: "Already have the text? Paste it and summarize." },
};

type JobView = {
  status: string;
  phase: string | null;
  error: string | null;
  summaries: Record<string, string>;
  complete_notes: boolean;
  summary_types: string[];
  transcript?: string;
};

type TranscriptOut = {
  video_id: string;
  title: string | null;
  duration: number | null;
  transcript: string;
  truncated: boolean;
  needs_audio?: boolean;
};

function formatDuration(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h > 0
    ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
    : `${m}:${String(sec).padStart(2, "0")}`;
}

const PHASE_LABEL: Record<string, string> = {
  queued: "Queued",
  claimed: "Starting up",
  transcribing: "Transcribing audio",
  summarizing: "Summarizing",
  notes: "Writing study notes",
  cached: "Retrieving",
  requeued: "Retrying",
  recovered: "Recovering",
  done: "Done",
};

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function Workbench({ mode }: { mode: Mode }) {
  const router = useRouter();
  const toast = useToast();
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [transcript, setTranscript] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [videoTitle, setVideoTitle] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set(SUMMARY_TYPES.map((t) => t.key)));
  const [notes, setNotes] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<"fetching" | "extracting" | "summarizing" | null>(null);
  const [extractPct, setExtractPct] = useState(0);
  const [regen, setRegen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<JobView | null>(null);

  const len = transcript.trim().length;
  const tooShort = len > 0 && len < MIN_CHARS;
  const tooLong = len > MAX_CHARS;
  const hasType = selected.size > 0 || notes;
  const canSubmit =
    !busy &&
    hasType &&
    (mode === "url" ? url.trim().length > 0 : mode === "upload" ? !!file : len >= MIN_CHARS && !tooLong);

  function toggle(key: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function paste() {
    try {
      const text = await navigator.clipboard.readText();
      if (text) setTranscript(text);
      else toast.toast({ title: "Clipboard is empty", variant: "warn" });
    } catch {
      toast.error("Clipboard unavailable", "Allow clipboard access or paste manually with Ctrl/⌘+V.");
    }
  }

  const pollJob = useCallback(
    async (jobId: string, onUpdate?: (j: JobView) => void): Promise<JobView> => {
      for (let i = 0; i < 400; i++) {
        const res = await api(`/api/jobs/${jobId}`);
        if (res.status === 401) {
          router.push("/login");
          throw new Error("Your session expired.");
        }
        if (!res.ok) throw new Error("Lost track of the job.");
        const data = (await res.json()) as JobView;
        onUpdate?.(data);
        if (data.status === "done") return data;
        if (data.status === "error") throw new Error(data.error || "The job failed.");
        await sleep(1500);
      }
      throw new Error("Timed out waiting for the summary.");
    },
    [router]
  );

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setJob(null);
    setVideoTitle(null);
    setVideoDuration(null);
    if (!hasType) return setError("Pick at least one summary type.");

    const types = SUMMARY_TYPES.map((t) => t.key).filter((k) => selected.has(k));
    setBusy(true);
    try {
      // Upload mode: extract the audio IN THE BROWSER (so only a few MB upload,
      // regardless of video length), then send that. Falls back to the raw file
      // if browser extraction fails and the file is within the direct cap.
      if (mode === "upload") {
        if (!file) return setError("Choose a video or audio file.");
        let blob: Blob = file;
        let name = file.name;
        if (!file.type.startsWith("audio/")) {
          setStage("extracting");
          setExtractPct(0);
          try {
            const { extractAudio } = await import("@/lib/extract-audio");
            blob = await extractAudio(file, setExtractPct);
            name = file.name.replace(/\.[^.]+$/, "") + ".mp3";
          } catch {
            if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
              throw new Error(
                `Couldn't process this file in the browser, and it's over the ${MAX_UPLOAD_MB} MB direct-upload limit. Try a lower-resolution file or upload the audio.`
              );
            }
            blob = file;
            name = file.name; // fall back: let the server extract the audio
          }
        }
        setStage("summarizing");
        const fd = new FormData();
        fd.append("file", blob, name);
        fd.append("summary_types", types.join(","));
        fd.append("complete_notes", String(notes));
        const res = await fetch(`${API_URL}/api/upload`, { method: "POST", credentials: "include", body: fd });
        if (res.status === 401) return router.push("/login");
        if (!res.ok) throw new Error(await errorDetail(res, "Upload failed"));
        const { job_id } = (await res.json()) as { job_id: string };
        window.dispatchEvent(new Event("usage:changed"));
        const final = await pollJob(job_id, setJob);
        setJob(final);
        if (final.transcript) setSubmitted(final.transcript);
        toast.success("Summary ready", "Scroll down to read, copy, or download it.");
        return;
      }

      // Resolve the transcript text + optional video id.
      let text = transcript;
      let videoId: string | undefined;
      let source = "paste";

      if (mode === "url") {
        if (!url.trim()) return setError("Paste a YouTube video URL.");
        setStage("fetching");
        const res = await api("/api/transcript", { method: "POST", body: JSON.stringify({ url }) });
        if (res.status === 401) return router.push("/login");
        if (!res.ok) throw new Error(await errorDetail(res, "Couldn't fetch the transcript"));
        const data = (await res.json()) as TranscriptOut;
        videoId = data.video_id;
        setVideoTitle(data.title);
        setVideoDuration(data.duration);
        if (data.needs_audio) {
          source = "audio";
          text = "";
          toast.toast({ title: "No captions found", description: "Transcribing the audio — this can take a little longer.", variant: "accent" });
        } else {
          text = data.transcript;
          source = "api";
          if (data.truncated) {
            toast.toast({ title: "Long video", description: "The transcript was truncated to fit the limit.", variant: "warn" });
          }
        }
      } else {
        if (len < MIN_CHARS) return setError(`Paste at least ${MIN_CHARS} characters of transcript.`);
        if (tooLong) return setError(`Transcript exceeds the ${MAX_CHARS.toLocaleString()} character limit.`);
      }

      setSubmitted(text);
      setStage("summarizing");
      const res = await api("/api/summarize", {
        method: "POST",
        body: JSON.stringify({ transcript_text: text, summary_types: types, complete_notes: notes, video_id: videoId, source }),
      });
      if (res.status === 401) return router.push("/login");
      if (!res.ok) throw new Error(await errorDetail(res, "Summarize failed"));
      const { job_id } = (await res.json()) as { job_id: string };
      window.dispatchEvent(new Event("usage:changed"));
      const final = await pollJob(job_id, setJob);
      setJob(final);
      if (final.transcript) setSubmitted(final.transcript);
      toast.success("Summary ready", "Scroll down to read, copy, or download it.");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setError(msg);
      toast.error("Couldn't summarize", msg);
    } finally {
      setBusy(false);
      setStage(null);
    }
  }

  const regenerate = useCallback(
    async (type: string) => {
      if (!submitted) return;
      setRegen(type);
      try {
        const isNotes = type === "notes";
        const res = await api("/api/summarize", {
          method: "POST",
          body: JSON.stringify({
            transcript_text: submitted,
            summary_types: isNotes ? [] : [type],
            complete_notes: isNotes,
            force: true,
            source: mode === "url" ? "api" : "paste",
          }),
        });
        if (res.status === 401) return router.push("/login");
        if (!res.ok) throw new Error(await errorDetail(res, "Regenerate failed"));
        const { job_id } = (await res.json()) as { job_id: string };
        window.dispatchEvent(new Event("usage:changed"));
        const final = await pollJob(job_id);
        const fresh = final.summaries[type];
        if (fresh) {
          setJob((prev) => (prev ? { ...prev, summaries: { ...prev.summaries, [type]: fresh } } : prev));
          toast.success(`${labelFor(type)} regenerated`);
        } else {
          toast.error("Couldn't regenerate", "No new content was returned.");
        }
      } catch (err) {
        toast.error("Couldn't regenerate", err instanceof Error ? err.message : undefined);
      } finally {
        setRegen(null);
      }
    },
    [submitted, mode, pollJob, toast, router]
  );

  const done = job?.status === "done";
  const keys = useMemo(() => (job ? orderedKeys(job.summary_types, job.complete_notes) : []), [job]);

  function jobMarkdown() {
    if (!job) return "";
    return jobToMarkdown(job.summaries, keys, { title: videoTitle ?? "Video summary", date: new Date().toLocaleString() });
  }

  async function copyAll() {
    try {
      await navigator.clipboard.writeText(jobMarkdown());
      toast.success("Copied all summaries");
    } catch {
      toast.error("Clipboard unavailable");
    }
  }

  const progressLabel =
    stage === "fetching"
      ? "Fetching transcript"
      : stage === "extracting"
        ? `Extracting audio${extractPct ? ` ${Math.round(extractPct * 100)}%` : ""}`
        : PHASE_LABEL[job?.phase ?? ""] ?? "Summarizing";

  const meta = MODE_META[mode];
  const HeaderIcon = Icons[meta.icon];

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-6 sm:px-5 sm:py-8">
      <div className="flex items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent-text">
          <HeaderIcon className="h-[18px] w-[18px]" />
        </span>
        <div>
          <h1 className="text-base font-semibold tracking-tight text-fg">{meta.title}</h1>
          <p className="text-xs text-muted">{meta.sub}</p>
        </div>
      </div>

      <form onSubmit={onSubmit}>
        <Card className="flex flex-col gap-4 p-4 sm:p-5">
          {mode === "url" ? (
            <div className="flex flex-col gap-2">
              <div className="relative">
                <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted">
                  <Icons.logo className="h-4 w-4" />
                </span>
                <Input
                  type="url"
                  inputMode="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://www.youtube.com/watch?v=…"
                  aria-label="YouTube video URL"
                  className="pl-9"
                />
              </div>
              <p className="text-xs text-muted">Paste a YouTube link — we&apos;ll fetch the transcript and summarize it.</p>
            </div>
          ) : mode === "upload" ? (
            <div className="flex flex-col gap-2">
              <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-[var(--radius-field)] border border-dashed border-border-strong bg-surface-2/40 px-4 py-8 text-center transition-colors hover:border-accent hover:bg-surface-2/70">
                <Icons.upload className="h-6 w-6 text-muted" />
                {file ? (
                  <span className="text-sm font-medium text-fg">
                    {file.name} <span className="font-normal text-muted">({(file.size / 1024 / 1024).toFixed(1)} MB)</span>
                  </span>
                ) : (
                  <>
                    <span className="text-sm font-medium text-fg">Choose a video or audio file</span>
                    <span className="text-xs text-muted">The audio is extracted in your browser, so only a few MB upload — long videos work too. Very large files may need a lower resolution.</span>
                  </>
                )}
                <input type="file" accept="video/*,audio/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              </label>
              {file && (
                <button type="button" onClick={() => setFile(null)} className="self-start text-xs text-muted transition-colors hover:text-fg">
                  Remove file
                </button>
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              <Textarea
                value={transcript}
                onChange={(e) => setTranscript(e.target.value)}
                rows={9}
                placeholder="Paste a video transcript here…"
                aria-label="Transcript"
                className={tooLong ? "border-danger focus:border-danger" : ""}
              />
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-1">
                  <IconButton size="sm" type="button" onClick={paste} aria-label="Paste from clipboard" title="Paste from clipboard">
                    <Icons.clipboard className="h-4 w-4" />
                  </IconButton>
                  {transcript && (
                    <IconButton size="sm" type="button" onClick={() => setTranscript("")} aria-label="Clear transcript" title="Clear">
                      <Icons.close className="h-4 w-4" />
                    </IconButton>
                  )}
                </div>
                <span className={tooLong ? "font-medium text-danger" : tooShort ? "text-warn" : "text-muted"}>
                  {tooShort ? `${MIN_CHARS - len} more characters needed` : `${len.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`}
                </span>
              </div>
            </div>
          )}

          {/* Type selection */}
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-widest text-muted">Summary types</span>
              <div className="flex items-center gap-2 text-xs">
                <button type="button" onClick={() => setSelected(new Set(SUMMARY_TYPES.map((t) => t.key)))} className="text-muted transition-colors hover:text-accent-text">
                  Select all
                </button>
                <span className="text-border-strong">·</span>
                <button type="button" onClick={() => setSelected(new Set())} className="text-muted transition-colors hover:text-accent-text">
                  Clear
                </button>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              {SUMMARY_TYPES.map((t) => (
                <Chip key={t.key} selected={selected.has(t.key)} onClick={() => toggle(t.key)} title={t.desc}>
                  {t.label}
                </Chip>
              ))}
              <Chip selected={notes} onClick={() => setNotes((v) => !v)} title={NOTES_DEF.desc}>
                <Icons.sparkles className="mr-1 inline h-3.5 w-3.5 align-[-2px]" />
                {NOTES_DEF.label}
              </Chip>
            </div>
          </div>

          <div className="flex items-center justify-end">
            <Button type="submit" disabled={!canSubmit}>
              {busy ? (
                <>
                  <Spinner className="h-4 w-4" /> {stage === "fetching" ? "Fetching…" : stage === "extracting" ? "Extracting…" : "Summarizing…"}
                </>
              ) : (
                <>
                  <Icons.sparkles className="h-4 w-4" /> Summarize
                </>
              )}
            </Button>
          </div>
        </Card>
      </form>

      {error && (
        <Card className="flex items-start gap-2 border-danger/40 bg-danger-soft p-4 text-sm text-danger">
          <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />
          {error}
        </Card>
      )}

      {busy && !done && (
        <Card className="flex items-center gap-3 p-4 text-sm text-muted">
          <Spinner className="h-4 w-4 text-accent-text" />
          <span>
            Working… <span className="font-medium text-fg">{progressLabel}</span>
          </span>
        </Card>
      )}

      {done && keys.length > 0 && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              {videoTitle && (
                <p className="truncate text-sm font-medium text-fg" title={videoTitle}>
                  {videoTitle}
                  {videoDuration ? <span className="font-normal text-muted"> · {formatDuration(videoDuration)}</span> : null}
                </p>
              )}
              <h2 className="text-sm text-muted">
                {keys.length} {keys.length === 1 ? "summary" : "summaries"}
              </h2>
            </div>
            <div className="flex items-center gap-2">
              <TestUnderstandingButton transcript={job?.transcript ?? submitted} />
              <Button variant="outline" size="sm" onClick={copyAll}>
                <Icons.copy className="h-4 w-4" /> Copy all
              </Button>
              <Button variant="outline" size="sm" onClick={() => downloadText("video-summary.md", jobMarkdown())}>
                <Icons.download className="h-4 w-4" /> Download
              </Button>
            </div>
          </div>
          {keys.map((t) =>
            job?.summaries[t] ? (
              <SummaryCard key={t} type={t} content={job.summaries[t]} onRegenerate={regenerate} regenerating={regen === t} />
            ) : null
          )}
        </>
      )}
    </div>
  );
}
