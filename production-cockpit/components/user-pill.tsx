"use client";

import { useState, useRef, useEffect } from "react";

export function UserPill({ name, role }: { name: string; role: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  async function onLogout() {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  }

  const initials = name
    .split(/\s+/)
    .map((s) => s[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 border border-rule px-2 py-1 font-mono text-[10px] tracking-[0.12em] uppercase text-ink-2 hover:border-accent hover:text-ink transition-colors"
        aria-label={`Signed in as ${name}`}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span
          aria-hidden
          className="grid h-4 w-4 place-items-center rounded-full bg-accent/15 text-[8px] font-semibold text-accent"
        >
          {initials}
        </span>
        <span className="hidden sm:inline">{name.split(" ")[0]}</span>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-1 z-30 min-w-[180px] border border-rule bg-paper shadow-md"
        >
          <div className="px-3 py-2 border-b border-rule">
            <p className="text-xs text-foreground">{name}</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 mt-0.5">
              {role}
            </p>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="block w-full text-left px-3 py-2 text-xs text-ink-2 hover:bg-oceanside/30 hover:text-ink transition-colors"
            role="menuitem"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
