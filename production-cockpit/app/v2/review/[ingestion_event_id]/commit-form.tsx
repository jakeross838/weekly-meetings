"use client";

// Client component — handles the commit POST to the review API.

import { useState } from "react";
import { useRouter } from "next/navigation";

export function CommitForm({
  ingestionEventId,
  proposedChangeIds,
}: {
  ingestionEventId: string;
  proposedChangeIds: string[];
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function commit(action: "accept" | "reject") {
    setBusy(true);
    setErr(null);
    try {
      const decisions = proposedChangeIds.map((id) => ({
        proposed_change_id: id,
        action,
      }));
      const resp = await fetch(`/v2/api/review/${ingestionEventId}/commit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decisions }),
      });
      if (!resp.ok) {
        const body = await resp.text();
        throw new Error(`commit failed (${resp.status}): ${body.slice(0, 200)}`);
      }
      router.refresh();
      router.push("/v2/review");
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 pt-6 border-t border-rule">
      <div className="flex gap-3 flex-wrap">
        <button
          onClick={() => commit("accept")}
          disabled={busy || proposedChangeIds.length === 0}
          className="px-5 py-3 min-h-[44px] bg-ink text-paper font-medium text-sm uppercase tracking-[0.06em] hover:bg-ink-2 disabled:opacity-50 transition-colors"
        >
          {busy ? "Committing…" : `Accept all (${proposedChangeIds.length})`}
        </button>
        <button
          onClick={() => commit("reject")}
          disabled={busy || proposedChangeIds.length === 0}
          className="px-5 py-3 min-h-[44px] border border-rule text-ink-2 font-medium text-sm uppercase tracking-[0.06em] hover:border-urgent hover:text-urgent disabled:opacity-50 transition-colors"
        >
          Reject all
        </button>
      </div>
      {err && (
        <p className="mt-3 text-urgent text-xs">
          {err}
        </p>
      )}
      <p className="mt-3 text-ink-3 text-xs">
        Per-row accept/edit/reject is coming. v1: bulk action only.
      </p>
    </div>
  );
}
