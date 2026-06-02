"use client";

import { useState } from "react";
import Link from "next/link";

import { Icons, Spinner } from "./ui";

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    <div className="hero-aurora flex min-h-screen flex-col items-center justify-center bg-bg px-6 py-12 text-fg">
      <Link href="/" className="mb-7 flex items-center gap-2.5">
        <span className="grid h-9 w-9 place-items-center rounded-xl bg-[image:var(--gradient-logo)] text-white shadow-[var(--shadow-sm)]">
          <Icons.logo className="h-5 w-5" />
        </span>
        <span className="text-base font-semibold tracking-tight">Video Synopsis</span>
      </Link>
      <main className="relative w-full max-w-sm overflow-hidden rounded-[var(--radius-card)] border border-border bg-surface p-7 shadow-[var(--shadow-lg)]">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px"
          style={{ background: "var(--grad-divider)" }}
        />
        <div className="mb-5 flex flex-col gap-1.5">
          <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
          {subtitle && <p className="text-sm leading-relaxed text-muted">{subtitle}</p>}
        </div>
        {children}
      </main>
      {footer && <p className="mt-6 text-sm text-muted">{footer}</p>}
    </div>
  );
}

const inputClass =
  "w-full rounded-[var(--radius-field)] border border-border bg-surface px-3 py-2.5 text-sm text-fg outline-none placeholder:text-muted transition-[border-color] duration-150 focus:border-accent";

export function AuthError({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2.5 text-sm text-danger">
      <Icons.alert className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function AuthSuccess({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-success/30 bg-success-soft px-3 py-2.5 text-sm text-success">
      <Icons.checkCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

export function Field({
  label,
  value,
  onChange,
  type = "text",
  placeholder,
  autoComplete,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  autoComplete?: string;
  hint?: string;
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-fg">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete={autoComplete}
        required
        className={inputClass}
      />
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function PasswordField({
  label,
  value,
  onChange,
  autoComplete,
  hint,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  autoComplete?: string;
  hint?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="font-medium text-fg">{label}</span>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          autoComplete={autoComplete}
          required
          className={`${inputClass} pr-10`}
        />
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          aria-label={show ? "Hide password" : "Show password"}
          title={show ? "Hide password" : "Show password"}
          className="absolute right-1.5 top-1/2 grid h-7 w-7 -translate-y-1/2 place-items-center rounded text-muted transition-colors hover:text-fg"
        >
          {show ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M9.9 4.2A11 11 0 0 1 12 4c6.5 0 10 8 10 8a18 18 0 0 1-2.2 3.2M6.6 6.6A18 18 0 0 0 2 12s3.5 8 10 8a11 11 0 0 0 3.4-.6" />
              <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2M2 2l20 20" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <path d="M2 12s3.5-8 10-8 10 8 10 8-3.5 8-10 8-10-8-10-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </button>
      </div>
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

export function SubmitButton({ busy, children }: { busy: boolean; children: React.ReactNode }) {
  return (
    <button
      type="submit"
      disabled={busy}
      className="mt-1 inline-flex h-11 items-center justify-center gap-2 rounded-[var(--radius-button)] bg-[image:var(--gradient-accent)] font-medium text-accent-contrast shadow-[var(--shadow-sm)] transition-[transform,box-shadow,opacity] duration-150 hover:-translate-y-px hover:shadow-glow active:translate-y-0 disabled:opacity-60 disabled:hover:translate-y-0 disabled:hover:shadow-[var(--shadow-sm)]"
    >
      {busy ? (
        <>
          <Spinner className="h-4 w-4" /> Working…
        </>
      ) : (
        children
      )}
    </button>
  );
}
