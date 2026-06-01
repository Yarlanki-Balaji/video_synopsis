"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { Spinner } from "@/components/ui";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [email, setEmail] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const res = await api("/auth/me");
        if (!active) return;
        if (!res.ok) {
          router.replace("/login");
          return;
        }
        const me = (await res.json()) as { email: string };
        setEmail(me.email);
        setReady(true);
      } catch {
        if (active) router.replace("/login");
      }
    })();
    return () => {
      active = false;
    };
  }, [router]);

  if (!ready) {
    return (
      <div className="grid h-screen place-items-center bg-bg text-muted">
        <Spinner className="h-5 w-5" />
      </div>
    );
  }
  return <AppShell email={email ?? ""}>{children}</AppShell>;
}
