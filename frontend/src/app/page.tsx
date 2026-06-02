"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { api } from "@/lib/api";
import { Card, Icons, Spinner } from "@/components/ui";
import { ThemeToggle } from "@/components/theme";

const FEATURES = [
  { icon: Icons.layers, title: "Five summary styles", body: "Brief, detailed, bullet points, timestamped chapters, and ELI5 — generate any mix in one pass." },
  { icon: Icons.fileText, title: "Complete study notes", body: "Turn a lecture or talk into structured, comprehensive notes with headings, key points, and takeaways." },
  { icon: Icons.bolt, title: "Any length, handled", body: "Long transcripts are split, digested, and recombined automatically — paste hours of video and it just works." },
  { icon: Icons.copy, title: "Copy & export", body: "One-click copy or download any summary as clean Markdown, ready to drop into your notes." },
  { icon: Icons.history, title: "Saved history", body: "Every summary is kept in your history — search, revisit, export, or delete it anytime." },
  { icon: Icons.shield, title: "Private & secure", body: "Your account is protected with hashed passwords, rotating sessions, and per-account isolation." },
];

const CHIPS = ["Brief", "Detailed", "Bullets", "Chapters", "ELI5", "Notes"];

export default function Landing() {
  const router = useRouter();
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/auth/me");
        if (!active) return;
        if (res.ok) {
          router.replace("/summarize");
          return;
        }
        setChecking(false);
      } catch {
        if (active) setChecking(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  if (checking) {
    return (
      <div className="grid min-h-screen place-items-center bg-bg text-muted">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col bg-bg text-fg">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-bg/80 backdrop-blur-md">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-[image:var(--gradient-logo)] text-white shadow-[var(--shadow-sm)]">
              <Icons.logo className="h-[18px] w-[18px]" />
            </span>
            <span className="font-semibold tracking-tight">Video Synopsis</span>
          </div>
          <div className="flex items-center gap-1.5">
            <ThemeToggle />
            <Link href="/login" className="rounded-lg px-3.5 py-2 text-sm text-muted transition-colors hover:text-fg">
              Log in
            </Link>
            <Link
              href="/signup"
              className="rounded-[var(--radius-button)] bg-[image:var(--gradient-accent)] px-4 py-2 text-sm font-medium text-accent-contrast shadow-[var(--shadow-sm)] transition-[transform,box-shadow] duration-150 hover:-translate-y-px hover:shadow-glow"
            >
              Sign up
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="hero-aurora">
          <div className="mx-auto flex max-w-3xl flex-col items-center px-5 pb-16 pt-20 text-center sm:pt-28">
            <span className="mb-5 inline-flex items-center gap-1.5 rounded-full border border-border bg-surface/70 px-3 py-1 text-xs text-muted backdrop-blur-sm">
              <Icons.sparkles className="h-3.5 w-3.5 text-accent-text" />
              AI-powered video summaries
            </span>
            <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-6xl">
              Summarize any video <span className="text-gradient">in seconds</span>
            </h1>
            <p className="mt-5 max-w-xl text-pretty text-base leading-relaxed text-muted sm:text-lg">
              Paste a YouTube link and get brief, detailed, bullet, chapter, and ELI5 summaries — plus complete study
              notes. We fetch the transcript for you; long videos handled automatically.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link
                href="/signup"
                className="inline-flex h-11 items-center justify-center rounded-[var(--radius-button)] bg-[image:var(--gradient-accent)] px-6 text-sm font-medium text-accent-contrast shadow-[var(--shadow-sm)] transition-[transform,box-shadow] duration-150 hover:-translate-y-px hover:shadow-glow"
              >
                {"Get started — it's free"}
              </Link>
              <Link
                href="/login"
                className="inline-flex h-11 items-center justify-center rounded-[var(--radius-button)] border border-border bg-surface px-6 text-sm font-medium transition-colors hover:bg-surface-2"
              >
                Log in
              </Link>
            </div>

            {/* Decorative product preview */}
            <Card className="mt-14 w-full max-w-2xl p-5 text-left" aria-hidden>
              <div className="flex flex-wrap gap-2">
                {CHIPS.map((c, i) => (
                  <span
                    key={c}
                    className={`rounded-full border px-3 py-1 text-xs ${
                      i < 3 ? "border-accent/40 bg-accent-soft text-accent-text" : "border-border bg-surface-2 text-muted"
                    }`}
                  >
                    {c}
                  </span>
                ))}
              </div>
              <div className="mt-4 space-y-2.5">
                <div className="h-2.5 w-1/3 rounded-full bg-accent-soft" />
                <div className="h-2 w-full rounded-full bg-surface-2" />
                <div className="h-2 w-11/12 rounded-full bg-surface-2" />
                <div className="h-2 w-4/5 rounded-full bg-surface-2" />
                <div className="mt-4 h-2.5 w-1/4 rounded-full bg-accent-soft" />
                <div className="h-2 w-full rounded-full bg-surface-2" />
                <div className="h-2 w-3/4 rounded-full bg-surface-2" />
              </div>
            </Card>
          </div>
        </section>

        {/* Features */}
        <section className="mx-auto max-w-6xl px-5 py-16 sm:py-20">
          <div className="mx-auto mb-10 max-w-2xl text-center">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Everything you need to read less</h2>
            <p className="mt-3 text-muted">Built for students, researchers, and anyone drowning in long videos.</p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => {
              const I = f.icon;
              return (
                <Card key={f.title} interactive className="p-5">
                  <span className="mb-3 grid h-10 w-10 place-items-center rounded-xl bg-accent-soft text-accent-text">
                    <I className="h-5 w-5" />
                  </span>
                  <h3 className="text-sm font-semibold">{f.title}</h3>
                  <p className="mt-1.5 text-sm leading-relaxed text-muted">{f.body}</p>
                </Card>
              );
            })}
          </div>
        </section>

        {/* CTA band */}
        <section className="mx-auto max-w-6xl px-5 pb-20">
          <div className="hero-aurora overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface px-6 py-12 text-center shadow-card">
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">Ready to summarize?</h2>
            <p className="mx-auto mt-3 max-w-md text-muted">Create a free account and turn your first transcript into summaries right now.</p>
            <Link
              href="/signup"
              className="mt-7 inline-flex h-11 items-center justify-center rounded-[var(--radius-button)] bg-[image:var(--gradient-accent)] px-6 text-sm font-medium text-accent-contrast shadow-[var(--shadow-sm)] transition-[transform,box-shadow] duration-150 hover:-translate-y-px hover:shadow-glow"
            >
              Get started
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-3 px-5 py-6 text-sm text-muted sm:flex-row">
          <div className="flex items-center gap-2">
            <Icons.logo className="h-4 w-4" />
            <span>Video Synopsis</span>
          </div>
          <div className="flex items-center gap-4">
            <Link href="/login" className="hover:text-fg">Log in</Link>
            <Link href="/signup" className="hover:text-fg">Sign up</Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
