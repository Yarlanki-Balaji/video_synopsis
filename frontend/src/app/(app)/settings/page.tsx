"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api, errorDetail } from "@/lib/api";
import { Button, Card, Chip, Icons, Skeleton } from "@/components/ui";
import { PasswordField } from "@/components/auth";
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

function ChangePasswordCard() {
  const toast = useToast();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (next.length < 8) return toast.error("Password too short", "Use at least 8 characters.");
    if (next !== confirm) return toast.error("Passwords don't match");
    setBusy(true);
    try {
      const res = await api("/auth/change-password", {
        method: "POST",
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (!res.ok) throw new Error(await errorDetail(res, "Could not change password"));
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success("Password changed", "Other devices have been signed out.");
    } catch (err) {
      toast.error("Could not change password", err instanceof Error ? err.message : undefined);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-5">
      <SectionTitle icon={Icons.lock}>Change password</SectionTitle>
      <form onSubmit={onSubmit} className="flex flex-col gap-4">
        <PasswordField label="Current password" value={current} onChange={setCurrent} autoComplete="current-password" />
        <PasswordField label="New password" value={next} onChange={setNext} autoComplete="new-password" hint="At least 8 characters" />
        <PasswordField label="Confirm new password" value={confirm} onChange={setConfirm} autoComplete="new-password" />
        <div className="flex justify-end">
          <Button type="submit" disabled={busy || !current || !next || !confirm}>
            {busy ? "Updating…" : "Update password"}
          </Button>
        </div>
      </form>
    </Card>
  );
}

function AppearanceCard() {
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  useEffect(() => {
    let active = true;
    // Defer the read so it isn't a synchronous setState in the effect body.
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
    router.push("/login");
  }
  async function logoutAll() {
    await api("/auth/logout-all", { method: "POST" });
    toast.success("Signed out of all devices");
    router.push("/login");
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-6 sm:px-5 sm:py-8">
      <Card className="p-5">
        <SectionTitle icon={Icons.user}>Account</SectionTitle>
        <p className="text-sm">
          Signed in as <span className="font-medium">{email || "…"}</span>
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" onClick={logout}>
            <Icons.logout className="h-4 w-4" /> Log out
          </Button>
          <Button variant="ghost" onClick={logoutAll}>
            Log out all devices
          </Button>
        </div>
      </Card>

      <UsageCard />
      <ChangePasswordCard />
      <AppearanceCard />
    </div>
  );
}
