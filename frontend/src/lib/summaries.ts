// Shared summary-type metadata + markdown export helpers used across the
// summarize / history / job pages. Keeps labels and ordering in one place.

export type SummaryTypeDef = { key: string; label: string; desc: string };

// Light types mirror the backend's LIGHT_TYPES; "notes" is the heavier add-on.
export const SUMMARY_TYPES: SummaryTypeDef[] = [
  { key: "brief", label: "Brief", desc: "2–3 sentences" },
  { key: "detailed", label: "Detailed", desc: "Multi-paragraph" },
  { key: "bullets", label: "Bullet points", desc: "Key takeaways" },
  { key: "chapters", label: "Chapters", desc: "Timestamped sections" },
  { key: "eli5", label: "ELI5", desc: "Explained simply" },
  { key: "mindmap", label: "Mind map", desc: "Learning roadmap" },
];

export const NOTES_DEF: SummaryTypeDef = { key: "notes", label: "Complete notes", desc: "Full study notes" };

const LABELS: Record<string, string> = {
  ...Object.fromEntries([...SUMMARY_TYPES, NOTES_DEF].map((t) => [t.key, t.label])),
};

export function labelFor(key: string): string {
  return LABELS[key] ?? key;
}

/** Ordered list of result keys for a job (light types in canonical order, notes last). */
export function orderedKeys(summaryTypes: string[], completeNotes: boolean): string[] {
  const order = SUMMARY_TYPES.map((t) => t.key);
  const present = summaryTypes.filter((t) => order.includes(t)).sort((a, b) => order.indexOf(a) - order.indexOf(b));
  return [...present, ...(completeNotes ? ["notes"] : [])];
}

export function summaryToMarkdown(type: string, content: string): string {
  return `## ${labelFor(type)}\n\n${content.trim()}\n`;
}

export function jobToMarkdown(
  summaries: Record<string, string>,
  keys: string[],
  opts: { title?: string; date?: string } = {}
): string {
  const head = [`# ${opts.title ?? "Video summary"}`, opts.date ? `_${opts.date}_` : ""].filter(Boolean).join("\n");
  const body = keys
    .filter((k) => summaries[k])
    .map((k) => summaryToMarkdown(k, summaries[k]))
    .join("\n");
  return `${head}\n\n${body}`.trim() + "\n";
}

export function slugify(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 40) || "summary"
  );
}

/** Trigger a client-side download of a text/markdown file. */
export function downloadText(filename: string, text: string, mime = "text/markdown") {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
