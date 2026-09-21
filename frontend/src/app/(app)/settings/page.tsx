"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { Button, Card, Chip, Icons, Skeleton } from "@/components/ui";
import { useToast } from "@/components/toast";

type Usage = { jobs_used: number; jobs_limit: number; jobs_remaining: number; resets_at: string };

function SectionTitle({ icon: Icon, children }: { icon: (p: { className?: string }) => React.ReactNode; children: React.ReactNode }) {
  return (
    <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-muted">
      <Icon className="h-4 w-4" />
      {children}
    </h2>
  );
}

function UsageCard() {
  const [usage, setUsage] = useState<Usage | null>(null);
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/api/usage");
        if (active && res.ok) setUsage((await res.json()) as Usage);
      } catch {
        /* ignore */
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  return (
    <Card className="p-5">
      <SectionTitle icon={Icons.bolt}>Daily usage</SectionTitle>
      {!usage ? (
        <Skeleton className="h-10" />
      ) : (
        <>
          <div className="mb-1.5 flex items-baseline justify-between">
            <span className="text-sm">
              <span className="font-semibold text-fg">{usage.jobs_used}</span>
              <span className="text-muted"> / {usage.jobs_limit} summaries today</span>
            </span>
            <span className={`text-xs ${usage.jobs_remaining <= 0 ? "font-medium text-warn" : "text-muted"}`}>
              {usage.jobs_remaining} left
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-2">
            <div
              className={`h-full rounded-full transition-[width] duration-500 ${usage.jobs_remaining <= 0 ? "bg-warn" : "bg-[image:var(--gradient-accent)]"}`}
              style={{ width: `${usage.jobs_limit > 0 ? Math.min(100, (usage.jobs_used / usage.jobs_limit) * 100) : 0}%` }}
            />
          </div>
          <p className="mt-2 text-xs text-muted">
            Resets {new Date(usage.resets_at).toLocaleString()}.
          </p>
        </>
      )}
    </Card>
  );
}

function AppearanceCard() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    let active = true;
    (async () => {
      await Promise.resolve();
      if (active) setTheme(document.documentElement.dataset.theme === "light" ? "light" : "dark");
    })();
    return () => {
      active = false;
    };
  }, []);
  function set(t: "dark" | "light") {
    setTheme(t);
    document.documentElement.dataset.theme = t;
    try {
      localStorage.setItem("theme", t);
    } catch {
      /* ignore */
    }
  }
  return (
    <Card className="p-5">
      <SectionTitle icon={Icons.settings}>Appearance</SectionTitle>
      <div className="flex items-center gap-2">
        <Chip selected={theme === "light"} onClick={() => set("light")}>
          Light
        </Chip>
        <Chip selected={theme === "dark"} onClick={() => set("dark")}>
          Dark
        </Chip>
      </div>
    </Card>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const toast = useToast();
  const [email, setEmail] = useState("");

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/auth/me");
        if (active && res.ok) {
          const me = (await res.json()) as { email: string };
          setEmail(me.email);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    router.push("/signin");
  }

  async function logoutAll() {
    // Sign out by invalidating the session server-side, then redirect.
    await api("/auth/logout", { method: "POST" });
    toast.success("Signed out");
    router.push("/signin");
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-6 sm:px-5 sm:py-8">
      <Card className="p-5">
        <SectionTitle icon={Icons.user}>Account</SectionTitle>
        <p className="text-sm">
          Signed in as <span className="font-medium">{email || "…"}</span>
        </p>
        <p className="mt-1 text-xs text-muted">
          To switch accounts, sign out and enter a different email address.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" onClick={logout}>
            <Icons.logout className="h-4 w-4" /> Sign out
          </Button>
          <Button variant="ghost" onClick={logoutAll}>
            Sign out all devices
          </Button>
        </div>
      </Card>

      <UsageCard />
      <AppearanceCard />
    </div>
  );
}
