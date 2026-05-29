"use client";

// Generic confirm-action modal. Replaces window.confirm / window.prompt for
// admin destructive actions so we get:
//   · A real on-page popup that can't be blocked or auto-dismissed
//   · Clear "are you sure?" wording with the user's name spelled out
//   · An optional input (for password reset) inside the same flow
//   · Color-coded action button (urgent for destructive, accent for safe)

import { useEffect, useRef, useState, type ReactNode } from "react";

export interface ConfirmModalProps {
  open: boolean;
  title: string;
  subject: string; // who/what is being acted on (shown prominently)
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string;
  tone?: "urgent" | "accent";
  /** If set, show a text input above the buttons and pass its value to onConfirm. */
  input?: {
    label: string;
    placeholder?: string;
    type?: "text" | "password";
    initial?: string;
    minLength?: number;
  };
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (inputValue?: string) => void | Promise<void>;
}

export function ConfirmModal({
  open,
  title,
  subject,
  body,
  confirmLabel,
  cancelLabel = "Cancel",
  tone = "urgent",
  input,
  busy,
  onCancel,
  onConfirm,
}: ConfirmModalProps) {
  const [value, setValue] = useState(input?.initial ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setValue(input?.initial ?? "");
      // Autofocus after the dialog mounts.
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open, input?.initial]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!open) return;
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel]);

  if (!open) return null;

  const canConfirm =
    !busy &&
    (!input || (value.length >= (input.minLength ?? 0) && value.length > 0));

  const confirmBg =
    tone === "urgent"
      ? "bg-urgent hover:bg-urgent/90 text-paper"
      : "bg-ink hover:bg-accent text-paper";

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 bg-ink/60 backdrop-blur-sm flex items-end sm:items-center justify-center px-4 py-4"
      onClick={(e) => {
        if (e.target === e.currentTarget && !busy) onCancel();
      }}
      style={{ animation: "fadeUp 180ms ease-out both" }}
    >
      <div className="w-full max-w-md bg-paper border border-rule shadow-2xl">
        <header className="px-5 pt-5 pb-3 border-b border-rule">
          <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-ink-3">
            {title}
          </p>
          <h2 className="mt-1 font-head text-[19px] text-foreground leading-tight">
            {subject}
          </h2>
        </header>
        <div className="px-5 py-4 text-sm text-ink-2 leading-relaxed">
          {body}
          {input && (
            <label className="block mt-4">
              <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
                {input.label}
              </span>
              <input
                ref={inputRef}
                type={input.type ?? "text"}
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={input.placeholder}
                minLength={input.minLength}
                className="mt-1 w-full border border-rule bg-paper px-3 py-2.5 text-sm text-foreground placeholder:text-ink-3 focus:outline-none focus:border-accent"
              />
            </label>
          )}
        </div>
        <footer className="px-5 py-4 border-t border-rule flex items-center justify-end gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={onCancel}
            className="text-sm font-head text-ink-3 hover:text-ink px-3 py-2 transition-colors disabled:opacity-50"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            disabled={!canConfirm}
            onClick={() => onConfirm(input ? value : undefined)}
            className={`font-head text-sm px-5 py-2.5 transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${confirmBg}`}
          >
            {busy ? "Working…" : confirmLabel}
          </button>
        </footer>
      </div>
    </div>
  );
}
