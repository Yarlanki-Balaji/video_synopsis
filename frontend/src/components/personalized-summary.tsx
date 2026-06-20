"use client";

import { useEffect, useRef, useState } from "react";

import { Button, Card, Icons, Spinner } from "@/components/ui";
import { Markdown } from "@/components/markdown";
import {
  fetchAdaptiveSummary,
  fetchProfile,
  hasStylePreferences,
  summaryContent,
} from "@/lib/comprehension";

type State =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "ready"; summary: string }
  | { phase: "error"; message: string };

/**
 * Auto-generated, story-style summary tailored to the viewer's comprehension
 * profile — produced by the Hermes sidecar (which follows the `adaptive-video-summary`
 * skill + the per-user profile). Renders NOTHING unless the user has saved style
 * preferences, so it never duplicates the normal summary cards.
 */
export function PersonalizedSummary({ summaries }: { summaries?: Record<string, string> }) {
  const content = summaryContent(summaries);
  const [state, setState] = useState<State>({ phase: "idle" });
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

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content]);

  if (state.phase === "idle") return null;

  return (
    <Card className="overflow-hidden p-5 animate-slide-up">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-accent-text">
          <Icons.sparkles className="h-3.5 w-3.5" /> Personalized for you
        </h2>
        {state.phase === "ready" && (
          <Button variant="ghost" size="sm" onClick={() => run(true)}>
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
          <Button variant="outline" size="sm" onClick={() => run(true)}>
            <Icons.refresh className="h-4 w-4" /> Try again
          </Button>
        </div>
      )}
    </Card>
  );
}
