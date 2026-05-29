"use client";

// Sub-level "watch this one" flag. Replaced the auto-derived density / burst-rate
// math that lived here previously — PMs were bouncing off opaque strings like
// "primary density 0.56 below 0.65 threshold". Now it's a manual on/off with a
// single sticky-note sentence ("crew shows up late") that the PM types and owns.

import { useRouter } from "next/navigation";
import { useState } from "react";
import { EditableText } from "./editable-text";

export function FlagBanner({
  subId,
  flagged,
  note,
}: {
  subId: string;
  flagged: boolean;
  note: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    await fetch(`/api/subs/${subId}/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        flagged_for_pm_binder: !flagged,
        // Clearing the note on unflag keeps the data clean — if you re-flag
        // later, you'd want to write a fresh note anyway.
        ...(flagged ? { flag_note: null } : {}),
      }),
    });
    setBusy(false);
    router.refresh();
  }

  if (!flagged) {
    return (
      <button
        type="button"
        disabled={busy}
        onClick={toggle}
        className="inline-flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 hover:text-gold transition-colors disabled:opacity-50"
      >
        <span aria-hidden>⚑</span> Flag this sub for your binder
      </button>
    );
  }

  return (
    <div className="border border-gold p-3">
      <div className="flex items-center justify-between gap-3">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-gold">
          ⚑ Flagged for PM binder
        </p>
        <button
          type="button"
          disabled={busy}
          onClick={toggle}
          className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3 hover:text-ink transition-colors disabled:opacity-50"
        >
          unflag
        </button>
      </div>
      <div className="mt-2 text-sm leading-snug">
        <EditableText
          value={note}
          field="flag_note"
          type="textarea"
          endpoint={`/api/subs/${subId}/edit`}
          placeholder="add a note — what to watch with this sub"
          className="text-foreground"
        />
      </div>
    </div>
  );
}
