"use client";

import { useState } from "react";

import { Card, IconButton, Icons, Spinner } from "./ui";
import { Markdown } from "./markdown";
import { MindMap } from "./mindmap";
import { downloadText, labelFor, slugify, summaryToMarkdown } from "@/lib/summaries";

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
    <IconButton size="sm" onClick={copy} aria-label="Copy to clipboard" title="Copy">
      {done ? <Icons.check className="h-4 w-4 text-success" /> : <Icons.copy className="h-4 w-4" />}
    </IconButton>
  );
}

export function SummaryCard({
  type,
  content,
  onRegenerate,
  regenerating = false,
}: {
  type: string;
  content: string;
  onRegenerate?: (type: string) => void;
  regenerating?: boolean;
}) {
  return (
    <Card className="overflow-hidden p-5 animate-slide-up">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted">{labelFor(type)}</h2>
        <div className="flex items-center gap-0.5">
          {onRegenerate && (
            <IconButton
              size="sm"
              tone="accent"
              onClick={() => onRegenerate(type)}
              disabled={regenerating}
              aria-label={`Regenerate ${labelFor(type)}`}
              title="Regenerate this summary"
            >
              {regenerating ? <Spinner className="h-4 w-4" /> : <Icons.refresh className="h-4 w-4" />}
            </IconButton>
          )}
          <IconButton
            size="sm"
            onClick={() => downloadText(`${slugify(labelFor(type))}.md`, summaryToMarkdown(type, content))}
            aria-label={`Download ${labelFor(type)} as markdown`}
            title="Download .md"
          >
            <Icons.download className="h-4 w-4" />
          </IconButton>
          <CopyButton text={content} />
        </div>
      </div>
      {type === "mindmap" ? <MindMap markdown={content} /> : <Markdown>{content}</Markdown>}
    </Card>
  );
}
