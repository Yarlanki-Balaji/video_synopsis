"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { Button, Card } from "@/components/ui";

export default function SettingsPage() {
  const router = useRouter();
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
    router.push("/login");
  }

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-5 px-5 py-8">
      <Card className="p-5">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-muted">Account</h2>
        <p className="text-sm">
          Signed in as <span className="font-medium">{email || "…"}</span>
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant="outline" onClick={logout}>
            Log out
          </Button>
          <Button variant="ghost" onClick={logoutAll}>
            Log out all devices
          </Button>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="mb-1 text-xs font-semibold uppercase tracking-widest text-muted">Appearance</h2>
        <p className="text-sm text-muted">Switch light / dark with the toggle in the top bar.</p>
      </Card>
    </div>
  );
}
