"use client";

import { useState } from "react";

import { Card, Icons } from "./ui";
import { Markdown } from "./markdown";

const LABELS: Record<string, string> = {
  brief: "Brief",
  detailed: "Detailed",
  bullets: "Bullet points",
  chapters: "Chapters",
  eli5: "ELI5",
  notes: "Complete notes",
};

export function labelFor(key: string): string {
  return LABELS[key] ?? key;
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setDone(true);
      setTimeout(() => setDone(false), 1400);
    } catch {
      /* clipboard unavailable */
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      title="Copy"
      className="grid h-7 w-7 place-items-center rounded-md text-muted transition-colors hover:bg-surface-2 hover:text-fg"
    >
      {done ? <Icons.check className="h-4 w-4 text-accent" /> : <Icons.copy className="h-4 w-4" />}
    </button>
  );
}

export function SummaryCard({ type, content }: { type: string; content: string }) {
  return (
    <Card className="p-5">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">{labelFor(type)}</h2>
        <CopyButton text={content} />
      </div>
      <Markdown>{content}</Markdown>
    </Card>
  );
}
