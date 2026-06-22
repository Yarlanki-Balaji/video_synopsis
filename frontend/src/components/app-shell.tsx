"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { IconButton, Icons } from "./ui";
import { ThemeToggle } from "./theme";

const NAV = [
  { href: "/history", label: "History", icon: Icons.history },
  { href: "/agent", label: "Learning agent", icon: Icons.sparkles },
  { href: "/settings", label: "Settings", icon: Icons.settings },
];

const SUMMARIZE_SUBS = [
  { href: "/summarize/url", label: "YouTube URL", icon: Icons.logo },
  { href: "/summarize/upload", label: "Upload video", icon: Icons.upload },
  { href: "/summarize/paste", label: "Paste transcript", icon: Icons.fileText },
];

type Usage = { jobs_used: number; jobs_limit: number; jobs_remaining: number };

function UsageMeter() {
  const [usage, setUsage] = useState<Usage | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const res = await api("/api/usage");
        if (active && res.ok) setUsage((await res.json()) as Usage);
      } catch {
        /* ignore */
      }
    }
    load();
    // Refetch when a summary is created elsewhere in the app.
    window.addEventListener("usage:changed", load);
    return () => {
      active = false;
      window.removeEventListener("usage:changed", load);
    };
  }, []);

  if (!usage) return <div className="mx-1 h-[58px] rounded-xl skeleton" />;

  const pct = usage.jobs_limit > 0 ? Math.min(100, (usage.jobs_used / usage.jobs_limit) * 100) : 0;
  const depleted = usage.jobs_remaining <= 0;

  return (
    <div className="mx-1 rounded-xl border border-border bg-surface-2/60 p-3">
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-medium text-muted">Daily usage</span>
        <span className={depleted ? "font-semibold text-warn" : "text-muted"}>
          {usage.jobs_used}/{usage.jobs_limit}
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div
          className={`h-full rounded-full transition-[width] duration-500 ${depleted ? "bg-warn" : "bg-[image:var(--gradient-accent)]"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 text-[11px] leading-tight text-muted">
        {depleted ? "Limit reached — resets at midnight UTC." : `${usage.jobs_remaining} summaries left today.`}
      </p>
    </div>
  );
}

function SummarizeNav({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  const active = pathname.startsWith("/summarize");
  const [open, setOpen] = useState(false);
  // Expanded when toggled open OR while you're inside the Summarize section.
  const expanded = open || active;

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={expanded}
        className={`relative flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150 ${
          active ? "bg-accent-soft font-medium text-accent-text" : "text-muted hover:bg-surface-2 hover:text-fg"
        }`}
      >
        {active && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-accent" />}
        <Icons.summarize className="h-[18px] w-[18px] shrink-0" />
        <span className="flex-1 text-left">Summarize</span>
        <Icons.chevronDown className={`h-4 w-4 shrink-0 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`} />
      </button>

      {/* Slide-down sub-options (grid-rows trick animates height: auto). */}
      <div className={`grid transition-all duration-200 ease-out ${expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"}`}>
        <div className="overflow-hidden">
          <div className="mt-0.5 flex flex-col gap-0.5 pl-3">
            {SUMMARIZE_SUBS.map((s) => {
              const I = s.icon;
              const subActive = pathname === s.href;
              return (
                <Link
                  key={s.href}
                  href={s.href}
                  onClick={onNavigate}
                  aria-current={subActive ? "page" : undefined}
                  className={`flex items-center gap-2.5 rounded-lg px-3 py-1.5 text-[13px] transition-colors ${
                    subActive ? "bg-surface-2 font-medium text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
                  }`}
                >
                  <I className="h-4 w-4 shrink-0" />
                  {s.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="flex flex-col gap-1">
      <SummarizeNav pathname={pathname} onNavigate={onNavigate} />
      {NAV.map((n) => {
        const active = pathname.startsWith(n.href);
        const I = n.icon;
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={`relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors duration-150 ${
              active
                ? "bg-accent-soft font-medium text-accent-text"
                : "text-muted hover:bg-surface-2 hover:text-fg"
            }`}
          >
            {active && <span className="absolute left-0 top-1/2 h-5 w-[3px] -translate-y-1/2 rounded-full bg-accent" />}
            <I className="h-[18px] w-[18px] shrink-0" />
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <Link href="/summarize" onClick={onNavigate} className="flex items-center gap-2.5 px-2">
      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[image:var(--gradient-logo)] text-white shadow-[var(--shadow-sm)]">
        <Icons.logo className="h-[18px] w-[18px]" />
      </span>
      <span className="text-sm font-semibold tracking-tight">Video Synopsis</span>
    </Link>
  );
}

function SidebarBody({
  email,
  pathname,
  onNavigate,
  onLogout,
}: {
  email: string;
  pathname: string;
  onNavigate?: () => void;
  onLogout: () => void;
}) {
  return (
    <div className="relative flex h-full flex-col gap-4 px-3 py-4">
      {/* Warm aurora bleed at the top of the rail. */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-32 opacity-70"
        style={{ background: "var(--grad-glow-radial)" }}
      />
      <div className="relative">
        <Brand onNavigate={onNavigate} />
      </div>
      <div className="relative mt-1 flex-1">
        <NavLinks pathname={pathname} onNavigate={onNavigate} />
      </div>
      <div className="relative flex flex-col gap-3">
        <UsageMeter />
        <div className="flex items-center gap-2 rounded-xl border border-border bg-surface-2/40 px-2.5 py-2">
          <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-accent-soft text-accent-text">
            <Icons.user className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1 truncate text-xs text-muted" title={email}>
            {email}
          </span>
          <IconButton size="sm" tone="danger" onClick={onLogout} aria-label="Log out" title="Log out">
            <Icons.logout className="h-4 w-4" />
          </IconButton>
        </div>
      </div>
    </div>
  );
}

export function AppShell({ children, email }: { children: React.ReactNode; email: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [drawer, setDrawer] = useState(false);
  const title = pathname.startsWith("/summarize")
    ? "Summarize"
    : NAV.find((n) => pathname.startsWith(n.href))?.label ?? "Video Synopsis";

  async function logout() {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      router.push("/login");
    }
  }

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-fg">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r border-border bg-bg md:block">
        <SidebarBody email={email} pathname={pathname} onLogout={logout} />
      </aside>

      {/* Mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-scrim backdrop-blur-[2px] animate-fade-in" onClick={() => setDrawer(false)} aria-hidden />
          <aside className="absolute inset-y-0 left-0 w-[78%] max-w-xs border-r border-border bg-bg shadow-[var(--shadow-lg)] animate-slide-up">
            <SidebarBody email={email} pathname={pathname} onNavigate={() => setDrawer(false)} onLogout={logout} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border bg-bg/80 px-4 backdrop-blur-sm sm:px-5">
          <div className="flex items-center gap-2">
            <IconButton className="md:hidden" onClick={() => setDrawer(true)} aria-label="Open menu">
              <Icons.menu className="h-5 w-5" />
            </IconButton>
            <h1 className="text-sm font-medium">{title}</h1>
          </div>
          <ThemeToggle />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
