import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, TextareaHTMLAttributes } from "react";

/* --------------------------------- Button -------------------------------- */

type Variant = "primary" | "outline" | "ghost" | "danger" | "subtle";
type Size = "sm" | "md";

const BTN_BASE =
  "relative inline-flex select-none items-center justify-center gap-2 rounded-[var(--radius-button)] font-medium " +
  "transition-[transform,box-shadow,background-color,border-color,color,opacity] duration-150 " +
  "ease-[var(--ease-standard)] disabled:pointer-events-none disabled:opacity-50";

const BTN_VARIANTS: Record<Variant, string> = {
  primary:
    "text-accent-contrast bg-[image:var(--gradient-accent)] shadow-[var(--shadow-sm)] hover:-translate-y-px hover:shadow-glow active:translate-y-0",
  outline: "border border-border bg-surface text-fg hover:bg-surface-2 hover:border-border-strong",
  ghost: "text-muted hover:bg-surface-2 hover:text-fg",
  danger: "bg-danger-soft text-danger border border-danger/25 hover:border-danger/45",
  subtle: "bg-accent-soft text-accent-text hover:brightness-105 dark:hover:brightness-110",
};

const BTN_SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-9 px-4 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size }) {
  return <button className={`${BTN_BASE} ${BTN_SIZES[size]} ${BTN_VARIANTS[variant]} ${className}`} {...props} />;
}

export function IconButton({
  className = "",
  size = "md",
  tone = "muted",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { size?: Size; tone?: "muted" | "danger" | "accent" }) {
  const dims = size === "sm" ? "h-7 w-7" : "h-9 w-9";
  const tones = {
    muted: "text-muted hover:bg-surface-2 hover:text-fg",
    danger: "text-muted hover:bg-danger-soft hover:text-danger",
    accent: "text-muted hover:bg-accent-soft hover:text-accent-text",
  }[tone];
  return (
    <button
      className={`grid shrink-0 place-items-center rounded-lg transition-colors duration-150 disabled:pointer-events-none disabled:opacity-50 ${dims} ${tones} ${className}`}
      {...props}
    />
  );
}

/* ---------------------------------- Card --------------------------------- */

export function Card({
  interactive = false,
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement> & { interactive?: boolean }) {
  const hover = interactive
    ? "transition-[transform,box-shadow,border-color] duration-200 ease-[var(--ease-standard)] hover:-translate-y-0.5 hover:shadow-pop hover:border-border-strong"
    : "";
  return (
    <div
      className={`rounded-[var(--radius-card)] border border-border bg-surface shadow-card ${hover} ${className}`}
      {...props}
    />
  );
}

/* --------------------------------- Badge --------------------------------- */

type Tone = "neutral" | "accent" | "success" | "warn" | "danger";

const BADGE_TONES: Record<Tone, string> = {
  neutral: "border-border bg-surface-2 text-muted",
  accent: "border-transparent bg-accent-soft text-accent-text",
  success: "border-transparent bg-success-soft text-success",
  warn: "border-transparent bg-warn-soft text-warn",
  danger: "border-transparent bg-danger-soft text-danger",
};

export function Badge({
  tone = "neutral",
  dot = false,
  className = "",
  children,
}: {
  tone?: Tone;
  dot?: boolean;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${BADGE_TONES[tone]} ${className}`}
    >
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current shadow-[0_0_6px_currentColor]" />}
      {children}
    </span>
  );
}

/* ---------------------------- Selectable chip ---------------------------- */

export function Chip({
  selected = false,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { selected?: boolean }) {
  const state = selected
    ? "border-accent/40 bg-accent-soft text-accent-text"
    : "border-border bg-surface-2/60 text-muted hover:text-fg hover:border-border-strong";
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={`rounded-full border px-3 py-1.5 text-sm transition-[color,background-color,border-color] duration-150 ${state} ${className}`}
      {...props}
    />
  );
}

/* ----------------------------- Inputs / fields --------------------------- */

const FIELD =
  "w-full rounded-[var(--radius-field)] border border-border bg-surface text-fg outline-none " +
  "placeholder:text-muted transition-[border-color] duration-150 focus:border-accent";

export function Input({ className = "", ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`${FIELD} px-3 py-2 text-sm ${className}`} {...props} />;
}

export function Textarea({ className = "", ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={`${FIELD} resize-y p-3 text-sm leading-relaxed ${className}`} {...props} />;
}

/* ------------------------------- Skeleton -------------------------------- */

export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden className={`skeleton ${className}`} />;
}

/* -------------------------------- Spinner -------------------------------- */

export function Spinner({ className = "" }: { className?: string }) {
  return (
    <svg className={`animate-spin ${className}`} width="16" height="16" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.2" />
      <path d="M22 12a10 10 0 0 0-10-10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

/* --------------------------------- Icons --------------------------------- */

type IconProps = { className?: string };
function makeIcon(name: string, children: React.ReactNode) {
  const C = ({ className = "" }: IconProps) => (
    <svg
      className={className}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {children}
    </svg>
  );
  C.displayName = `Icon(${name})`;
  return C;
}

export const Icons = {
  logo: makeIcon("logo", <><path d="m10 8 6 4-6 4V8z" /><rect x="3" y="4" width="18" height="16" rx="3" /></>),
  summarize: makeIcon("summarize", <path d="M4 6h16M4 12h10M4 18h7" />),
  history: makeIcon("history", <><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 4v4h4" /><path d="M12 8v4l3 2" /></>),
  settings: makeIcon("settings", <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></>),
  copy: makeIcon("copy", <><rect x="9" y="9" width="13" height="13" rx="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></>),
  check: makeIcon("check", <path d="M20 6 9 17l-5-5" />),
  checkCircle: makeIcon("checkCircle", <><path d="M22 11.1V12a10 10 0 1 1-5.9-9.1" /><path d="M22 4 12 14.01l-3-3" /></>),
  logout: makeIcon("logout", <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="m16 17 5-5-5-5" /><path d="M21 12H9" /></>),
  menu: makeIcon("menu", <path d="M4 6h16M4 12h16M4 18h16" />),
  close: makeIcon("close", <path d="M18 6 6 18M6 6l12 12" />),
  search: makeIcon("search", <><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>),
  trash: makeIcon("trash", <><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M10 11v6M14 11v6" /></>),
  download: makeIcon("download", <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M7 10l5 5 5-5" /><path d="M12 15V3" /></>),
  upload: makeIcon("upload", <><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="M7 9l5-5 5 5" /><path d="M12 4v12" /></>),
  refresh: makeIcon("refresh", <><path d="M3 12a9 9 0 0 1 15-6.7L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-15 6.7L3 16" /><path d="M3 21v-5h5" /></>),
  clipboard: makeIcon("clipboard", <><rect x="8" y="2" width="8" height="4" rx="1" /><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" /></>),
  chevronLeft: makeIcon("chevronLeft", <path d="m15 18-6-6 6-6" />),
  chevronRight: makeIcon("chevronRight", <path d="m9 18 6-6-6-6" />),
  chevronDown: makeIcon("chevronDown", <path d="m6 9 6 6 6-6" />),
  mail: makeIcon("mail", <><rect x="2" y="4" width="20" height="16" rx="2" /><path d="m2 7 10 6 10-6" /></>),
  lock: makeIcon("lock", <><rect x="3" y="11" width="18" height="11" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></>),
  alert: makeIcon("alert", <><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /><path d="M12 9v4M12 17h.01" /></>),
  info: makeIcon("info", <><circle cx="12" cy="12" r="10" /><path d="M12 16v-4M12 8h.01" /></>),
  sparkles: makeIcon("sparkles", <><path d="M12 3v4M12 17v4M3 12h4M17 12h4" /><path d="m6.3 6.3 2.1 2.1M15.6 15.6l2.1 2.1M17.7 6.3l-2.1 2.1M8.4 15.6l-2.1 2.1" /></>),
  bolt: makeIcon("bolt", <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8z" />),
  fileText: makeIcon("fileText", <><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /><path d="M8 13h8M8 17h8M8 9h2" /></>),
  shield: makeIcon("shield", <><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></>),
  user: makeIcon("user", <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>),
  layers: makeIcon("layers", <><path d="m12 2 9 5-9 5-9-5 9-5z" /><path d="m3 12 9 5 9-5" /><path d="m3 17 9 5 9-5" /></>),
  globe: makeIcon("globe", <><circle cx="12" cy="12" r="10" /><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z" /></>),
};
