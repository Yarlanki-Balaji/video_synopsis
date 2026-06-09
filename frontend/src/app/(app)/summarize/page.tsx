import Link from "next/link";

import { Icons } from "@/components/ui";

const OPTIONS = [
  {
    href: "/summarize/url",
    icon: Icons.logo,
    title: "YouTube URL",
    desc: "Paste a video link — we fetch the captions, or transcribe the audio when there are none.",
  },
  {
    href: "/summarize/upload",
    icon: Icons.upload,
    title: "Upload video",
    desc: "Upload a video or audio file — the audio is extracted in your browser, so long videos work too.",
  },
  {
    href: "/summarize/paste",
    icon: Icons.fileText,
    title: "Paste transcript",
    desc: "Already have the text? Paste it and get summaries, notes, and a mind map.",
  },
];

export default function SummarizeHome() {
  return (
    <div className="relative mx-auto flex min-h-full max-w-4xl flex-col items-center justify-center gap-10 px-4 py-16 text-center sm:py-24">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-64 opacity-70"
        style={{ background: "var(--grad-glow-radial)" }}
      />
      <div className="relative flex flex-col items-center gap-4">
        <span className="grid h-16 w-16 place-items-center rounded-2xl bg-[image:var(--gradient-logo)] text-white shadow-[var(--shadow-md)]">
          <Icons.logo className="h-8 w-8" />
        </span>
        <h1 className="bg-[image:var(--gradient-accent)] bg-clip-text text-5xl font-bold tracking-tight text-transparent sm:text-7xl">
          Video Synopsis
        </h1>
        <p className="max-w-md text-balance text-muted">
          Turn any video into summaries, study notes, and a mind map. Choose how you&apos;d like to start.
        </p>
      </div>

      <div className="relative grid w-full gap-4 sm:grid-cols-3">
        {OPTIONS.map((o) => {
          const I = o.icon;
          return (
            <Link
              key={o.href}
              href={o.href}
              className="group flex flex-col items-center gap-3 rounded-[var(--radius-card)] border border-border bg-surface p-6 text-center shadow-[var(--shadow-xs-light)] transition-all duration-200 hover:-translate-y-0.5 hover:border-accent hover:shadow-[var(--shadow-md)]"
            >
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-accent-soft text-accent-text transition-colors group-hover:bg-accent group-hover:text-white">
                <I className="h-5 w-5" />
              </span>
              <span className="font-semibold text-fg">{o.title}</span>
              <span className="text-xs leading-relaxed text-muted">{o.desc}</span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
