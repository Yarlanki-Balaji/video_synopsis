"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Icons } from "./ui";
import { ThemeToggle } from "./theme";

const NAV = [
  { href: "/summarize", label: "Summarize", icon: Icons.summarize },
  { href: "/history", label: "History", icon: Icons.history },
  { href: "/settings", label: "Settings", icon: Icons.settings },
];

export function AppShell({ children, email }: { children: React.ReactNode; email: string }) {
  const pathname = usePathname();
  const title = NAV.find((n) => pathname.startsWith(n.href))?.label ?? "Video Synopsis";

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-fg">
      <aside className="flex w-14 shrink-0 flex-col gap-1 border-r border-border bg-surface py-3 md:w-56 md:px-3">
        <Link href="/summarize" className="mb-4 flex items-center gap-2 px-1.5 md:px-2">
          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent text-accent-contrast">
            <Icons.logo className="h-[18px] w-[18px]" />
          </span>
          <span className="hidden text-sm font-semibold tracking-tight md:block">Video Synopsis</span>
        </Link>

        {NAV.map((n) => {
          const active = pathname.startsWith(n.href);
          const I = n.icon;
          return (
            <Link
              key={n.href}
              href={n.href}
              title={n.label}
              className={`flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors ${
                active ? "bg-surface-2 text-fg" : "text-muted hover:bg-surface-2 hover:text-fg"
              }`}
            >
              <I className="h-[18px] w-[18px] shrink-0" />
              <span className="hidden md:block">{n.label}</span>
            </Link>
          );
        })}

        <div className="mt-auto hidden truncate px-2.5 text-xs text-muted md:block" title={email}>
          {email}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-5">
          <h1 className="text-sm font-medium">{title}</h1>
          <ThemeToggle />
        </header>
        <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
