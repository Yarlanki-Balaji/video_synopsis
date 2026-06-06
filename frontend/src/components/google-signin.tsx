"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { api, errorDetail } from "@/lib/api";

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID;

type GoogleAccounts = {
  id: {
    initialize: (cfg: { client_id: string; callback: (r: { credential: string }) => void }) => void;
    renderButton: (el: HTMLElement, opts: Record<string, unknown>) => void;
  };
};
declare global {
  interface Window {
    google?: { accounts: GoogleAccounts };
  }
}

/**
 * "Sign in with Google" via Google Identity Services. The button only renders
 * when NEXT_PUBLIC_GOOGLE_CLIENT_ID is set. The backend (/auth/google) signs the
 * user in ONLY if a verified account already exists for the Google email.
 */
export function GoogleSignInButton({ onError }: { onError?: (msg: string) => void }) {
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const clientId = CLIENT_ID;
    if (!clientId) return;
    let cancelled = false;

    async function onCredential(resp: { credential: string }) {
      try {
        const r = await api("/auth/google", {
          method: "POST",
          body: JSON.stringify({ credential: resp.credential }),
        });
        if (!r.ok) throw new Error(await errorDetail(r, "Google sign-in failed"));
        router.push("/summarize");
      } catch (e) {
        onError?.(e instanceof Error ? e.message : "Google sign-in failed");
      }
    }

    function render() {
      if (cancelled || !window.google || !ref.current) return;
      window.google.accounts.id.initialize({ client_id: clientId!, callback: onCredential });
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline",
        size: "large",
        text: "signin_with",
        shape: "pill",
        width: 320,
      });
    }

    if (window.google?.accounts?.id) {
      render();
      return () => {
        cancelled = true;
      };
    }
    let script = document.getElementById("gis-client") as HTMLScriptElement | null;
    if (!script) {
      script = document.createElement("script");
      script.id = "gis-client";
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.defer = true;
      document.body.appendChild(script);
    }
    script.addEventListener("load", render);
    return () => {
      cancelled = true;
      script?.removeEventListener("load", render);
    };
  }, [router, onError]);

  if (!CLIENT_ID) return null;
  return <div ref={ref} className="flex justify-center" />;
}
