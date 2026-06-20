"use client";

import { useEffect, useRef, useState } from "react";

import { Button, Card, Icons, Spinner } from "@/components/ui";
import { Markdown } from "@/components/markdown";
import {
  fetchAdaptiveSummary,
  fetchProfile,
  hasStylePreferences,
  setStyle,
  summaryContent,
} from "@/lib/comprehension";

type State =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ready"; summary: string }
  | { phase: "error"; message: string };

// Direct style controls — each nudges a style on the user's profile (backend
// decays the rest so styles blend/shift), then the summary regenerates.
const STYLE_CHIPS: { value: string; label: string }[] = [
  { value: "story", label: "📖 Story" },
  { value: "bullets", label: "• Bullets" },
  { value: "simple", label: "🧒 Simpler" },
  { value: "technical", label: "🔬 Technical" },
  { value: "concise", label: "✂️ Shorter" },
  { value: "detailed", label: "📝 More detail" },
];

/**
 * Auto-generated, story-style summary tailored to the viewer's comprehension
 * profile — produced by the Hermes sidecar (which follows the `adaptive-video-summary`
 * skill + the per-user profile). Renders NOTHING unless the user has saved style
 * preferences, so it never duplicates the normal summary cards. The chips let the
 * user steer the style directly (no quiz needed) and the card re-adapts.
 */
export function PersonalizedSummary({ summaries }: { summaries?: Record<string, string> }) {
  const content = summaryContent(summaries);
  const [state, setState] = useState<State>({ phase: "idle" });
  const [styling, setStyling] = useState(false);
  const [note, setNote] = useState("");
  // The job page polls every 1.5s, so the parent re-renders constantly. Dedupe to
  // exactly ONE Hermes call per distinct summaries payload by claiming this ref
  // synchronously BEFORE awaiting (also makes React StrictMode's double-invoke safe).
  const fetchedFor = useRef<string | null>(null);

  async function run(force = false) {
    if (content.trim().length < 50) return; // summaries not ready yet
    if (!force && fetchedFor.current === content) return;
    fetchedFor.current = content;
    setState({ phase: "loading" });
    try {
      const profile = await fetchProfile();
      if (!hasStylePreferences(profile)) {
        setState({ phase: "idle" }); // nothing to personalize -> render null
        return;
      }
      const { summary } = await fetchAdaptiveSummary(content, "detailed", force);
      setState({ phase: "ready", summary });
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Something went wrong.";
      if (msg === "UNAUTHORIZED") {
        setState({ phase: "idle" }); // page-level auth handles the redirect
        return;
      }
      setState({ phase: "error", message: msg });
    }
  }

  // Apply a direct style change, then regenerate the summary with it.
  async function applyStyle(value?: string, freeNote?: string) {
    if (styling || state.phase === "loading") return;
    setStyling(true);
    try {
      await setStyle(value, freeNote);
    } catch (e) {
      setState({ phase: "error", message: e instanceof Error ? e.message : "Could not update style." });
      setStyling(false);
      return;
    }
    setStyling(false);
    await run(true);
  }

  useEffect(() => {
    void (async () => {
      await run();
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content]);

  if (state.phase === "idle") return null;

  const busy = styling || state.phase === "loading";

  return (
    <Card className="overflow-hidden p-5 animate-slide-up">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-accent-text">
          <Icons.sparkles className="h-3.5 w-3.5" /> Personalized for you
        </h2>
        {state.phase === "ready" && (
          <Button variant="ghost" size="sm" onClick={() => run(true)} disabled={busy}>
            <Icons.refresh className="h-4 w-4" /> Regenerate
          </Button>
        )}
      </div>

      {state.phase === "loading" && (
        <div className="flex items-center gap-2 text-sm text-muted">
          <Spinner className="h-4 w-4" /> Writing your story-style version…
        </div>
      )}

      {state.phase === "ready" && <Markdown>{state.summary}</Markdown>}

      {state.phase === "error" && (
        <div className="text-sm">
          <p className="mb-2 flex items-start gap-2 text-muted">
            <Icons.alert className="mt-0.5 h-4 w-4 shrink-0 text-warn" />
            {state.message}
          </p>
          <Button variant="outline" size="sm" onClick={() => run(true)} disabled={busy}>
            <Icons.refresh className="h-4 w-4" /> Try again
          </Button>
        </div>
      )}

      {/* Direct style controls — change the style without taking a quiz. */}
      {(state.phase === "ready" || state.phase === "error") && (
        <div className="mt-4 border-t border-border pt-3">
          <div className="mb-2 text-xs text-muted">Make it:</div>
          <div className="flex flex-wrap gap-2">
            {STYLE_CHIPS.map((c) => (
              <button
                key={c.value}
                type="button"
                disabled={busy}
                onClick={() => applyStyle(c.value)}
                className="rounded-full border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-accent hover:text-fg disabled:opacity-50"
              >
                {c.label}
              </button>
            ))}
          </div>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const n = note.trim();
              if (!n) return;
              setNote("");
              void applyStyle(undefined, n);
            }}
          >
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              disabled={busy}
              placeholder="Or tell it how you like it…"
              className="flex-1 rounded-lg border border-border bg-bg px-3 py-2 text-sm outline-none placeholder:text-muted focus:border-accent disabled:opacity-50"
            />
            <Button type="submit" variant="outline" size="sm" disabled={busy || !note.trim()}>
              Apply
            </Button>
          </form>
        </div>
      )}
    </Card>
  );
}
