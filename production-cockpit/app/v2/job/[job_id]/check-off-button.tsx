"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function CheckOffButton({ itemId }: { itemId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function toggle() {
    setBusy(true);
    try {
      await fetch(`/v2/api/items/${itemId}/complete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ completion_basis: "manual" }),
      });
      router.refresh();
    } catch {
      // ignore for now
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      onClick={toggle}
      disabled={busy}
      aria-label="Mark complete"
      className="mt-0.5 inline-block w-4 h-4 border border-rule shrink-0 hover:border-ink hover:bg-success/20 disabled:opacity-50 transition-colors"
    />
  );
}
