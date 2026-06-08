"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import { Icons, IconButton } from "./ui";

type ToastVariant = "default" | "accent" | "success" | "warn" | "danger";

type Toast = {
  id: number;
  title: string;
  description?: string;
  variant: ToastVariant;
  duration: number;
};

type ToastInput = {
  title: string;
  description?: string;
  variant?: ToastVariant;
  duration?: number;
};

type ToastApi = {
  toast: (t: ToastInput) => number;
  dismiss: (id: number) => void;
  success: (title: string, description?: string) => number;
  error: (title: string, description?: string) => number;
};

const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within <ToastProvider>");
  return ctx;
}

const BAR: Record<ToastVariant, string> = {
  default: "bg-accent",
  accent: "bg-accent",
  success: "bg-success",
  warn: "bg-warn",
  danger: "bg-danger",
};

const ICON: Record<ToastVariant, React.ReactNode> = {
  default: <Icons.info className="h-4 w-4 text-muted" />,
  accent: <Icons.info className="h-4 w-4 text-accent-text" />,
  success: <Icons.checkCircle className="h-4 w-4 text-success" />,
  warn: <Icons.alert className="h-4 w-4 text-warn" />,
  danger: <Icons.alert className="h-4 w-4 text-danger" />,
};

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const counter = useRef(0);
  const timers = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const toast = useCallback(
    ({ title, description, variant = "default", duration = 4200 }: ToastInput) => {
      const id = ++counter.current;
      setToasts((prev) => [...prev, { id, title, description, variant, duration }]);
      if (duration > 0) {
        timers.current.set(
          id,
          setTimeout(() => dismiss(id), duration)
        );
      }
      return id;
    },
    [dismiss]
  );

  const success = useCallback((title: string, description?: string) => toast({ title, description, variant: "success" }), [toast]);
  const error = useCallback((title: string, description?: string) => toast({ title, description, variant: "danger", duration: 6000 }), [toast]);

  // Stable context value so consumers don't re-render when toasts change.
  const ctx = useMemo(() => ({ toast, dismiss, success, error }), [toast, dismiss, success, error]);

  return (
    <ToastContext.Provider value={ctx}>
      {children}
      <div
        className="pointer-events-none fixed inset-x-0 bottom-0 z-[100] flex flex-col items-center gap-2 p-4 sm:bottom-4 sm:right-4 sm:left-auto sm:items-end sm:p-0"
        aria-live="polite"
        role="region"
        aria-label="Notifications"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            className="glass pointer-events-auto relative w-full max-w-sm overflow-hidden rounded-[var(--radius-field)] pl-4 pr-2 py-3 animate-slide-up"
          >
            <span className={`absolute inset-y-0 left-0 w-[3px] ${BAR[t.variant]}`} />
            <div className="flex items-start gap-3">
              <span className="mt-0.5 shrink-0">{ICON[t.variant]}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-fg">{t.title}</p>
                {t.description && <p className="mt-0.5 text-xs leading-relaxed text-muted">{t.description}</p>}
              </div>
              <IconButton size="sm" aria-label="Dismiss" onClick={() => dismiss(t.id)}>
                <Icons.close className="h-4 w-4" />
              </IconButton>
            </div>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
