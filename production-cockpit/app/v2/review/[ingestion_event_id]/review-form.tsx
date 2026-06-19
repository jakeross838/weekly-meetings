"use client";

// Per-row review form. Replaces the old bulk-only CommitForm.
//
// For each proposed_change, the user can:
//   • include it (default) or skip
//   • edit its fields (add_item / add_signal types only — others stay as
//     accept-or-reject only because they have no editable surface)
//
// Submit posts one decision per change to /v2/api/review/[id]/commit:
//   action="accept" if included and unedited
//   action="edit"   if included and any field changed (sends edited_data)
//   action="reject" if not included

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";

type ChangeType =
  | "add_item"
  | "update_item"
  | "resolve_item"
  | "merge_items"
  | "add_decision"
  | "add_open_question"
  | "add_signal"
  | "add_sub_event";

export interface ProposedChange {
  id: string;
  change_type: ChangeType;
  proposed_item_data: Record<string, unknown> | null;
  target_item_id: string | null;
  field_changes: Record<string, { before: unknown; after: unknown }> | null;
  proposed_decision_data: Record<string, unknown> | null;
  proposed_question_data: Record<string, unknown> | null;
  source_claim_ids: string[] | null;
  confidence: "high" | "medium" | "low" | null;
  job_id: string | null;
  sub_id: string | null;
  notes: string | null;
}

export interface ClaimLite {
  speaker: string | null;
  statement: string;
  raw_quote: string | null;
}

export interface SubOpt {
  id: string;
  name: string;
  trade?: string | null;
}

export interface JobOpt {
  id: string;
  name: string;
}

interface RowState {
  enabled: boolean;
  edited: {
    title?: string;
    target_date?: string | null;
    sub_id?: string | null;
    category?: string | null;
    priority?: string;
  };
}

const CATEGORIES = [
  "SCHEDULE",
  "QUALITY",
  "PROCUREMENT",
  "SELECTION",
  "BUDGET",
  "CLIENT",
  "ADMIN",
  "SUB-TRADE",
];

function jobLabel(jobId: string | null | undefined): string {
  if (!jobId) return "—";
  return jobId.charAt(0).toUpperCase() + jobId.slice(1);
}

export function ReviewForm({
  ingestionEventId,
  changes,
  claimById,
  subs,
  alreadyClosed,
}: {
  ingestionEventId: string;
  changes: ProposedChange[];
  claimById: Record<string, ClaimLite>;
  subs: SubOpt[];
  jobs: JobOpt[];
  alreadyClosed: boolean;
}) {
  const router = useRouter();

  // Per-row state, keyed by proposed_change.id. Defaults: enabled=true, no edits.
  const [rows, setRows] = useState<Record<string, RowState>>(() => {
    const out: Record<string, RowState> = {};
    for (const c of changes) out[c.id] = { enabled: true, edited: {} };
    return out;
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const totalEnabled = useMemo(
    () => Object.values(rows).filter((r) => r.enabled).length,
    [rows]
  );

  // Pre-commit impact: which jobs will this commit touch, with counts?
  // Uses the edited override when present, else the proposed_item_data,
  // else the change's job_id, else the meeting's primary job.
  const enabledJobsBreakdown = useMemo(() => {
    const m = new Map<string, number>();
    for (const c of changes) {
      const state = rows[c.id];
      if (!state?.enabled) continue;
      const d = (c.proposed_item_data ?? {}) as Record<string, unknown>;
      const job =
        (state.edited as { job?: string }).job ??
        ((d.job_id as string) || c.job_id || "(no job)");
      m.set(job, (m.get(job) ?? 0) + 1);
    }
    return Array.from(m.entries()).sort((a, b) => b[1] - a[1]);
  }, [changes, rows]);

  // All jobs referenced anywhere in the proposed changes, regardless of
  // whether they're enabled. Used for the "also touched" header banner so
  // the operator knows this batch reaches beyond the meeting's primary job.
  const allReferencedJobs = useMemo(() => {
    const s = new Set<string>();
    for (const c of changes) {
      const d = (c.proposed_item_data ?? {}) as Record<string, unknown>;
      const job = (d.job_id as string) || c.job_id;
      if (job) s.add(job);
    }
    return Array.from(s).sort();
  }, [changes]);

  function updateRow(id: string, patch: Partial<RowState>) {
    setRows((s) => ({ ...s, [id]: { ...s[id], ...patch } }));
  }
  function updateEdit(id: string, patch: Partial<RowState["edited"]>) {
    setRows((s) => ({
      ...s,
      [id]: { ...s[id], edited: { ...s[id].edited, ...patch } },
    }));
  }

  async function commit() {
    setBusy(true);
    setErr(null);
    try {
      const decisions = changes.map((c) => {
        const state = rows[c.id];
        if (!state.enabled) {
          return { proposed_change_id: c.id, action: "reject" as const };
        }
        const hasEdits = Object.keys(state.edited).length > 0;
        if (!hasEdits) {
          return { proposed_change_id: c.id, action: "accept" as const };
        }
        return {
          proposed_change_id: c.id,
          action: "edit" as const,
          edited_data: state.edited,
        };
      });
      const resp = await fetch(
        `/v2/api/review/${ingestionEventId}/commit`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decisions }),
        }
      );
      if (!resp.ok) {
        const body = await resp.text();
        setErr(`commit failed (${resp.status}): ${body.slice(0, 200)}`);
        setBusy(false);
        return;
      }
      router.refresh();
      router.push("/v2/review");
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  // Group add_item + add_signal rows by Job → Category (matching /import).
  // Other types render in their own sections.
  type EditableGroup = Map<string, Map<string, ProposedChange[]>>;
  const editableByJob: EditableGroup = useMemo(() => {
    const m: EditableGroup = new Map();
    for (const c of changes) {
      if (c.change_type !== "add_item" && c.change_type !== "add_signal")
        continue;
      const d = (c.proposed_item_data ?? {}) as Record<string, unknown>;
      const job = (d.job_id as string) ?? c.job_id ?? "(no job)";
      const cat = (d.category as string) ?? "(uncategorized)";
      const jobLabelKey = job;
      if (!m.has(jobLabelKey)) m.set(jobLabelKey, new Map());
      const catMap = m.get(jobLabelKey)!;
      if (!catMap.has(cat)) catMap.set(cat, []);
      catMap.get(cat)!.push(c);
    }
    return m;
  }, [changes]);

  const otherChanges = changes.filter(
    (c) => c.change_type !== "add_item" && c.change_type !== "add_signal"
  );

  const sortedJobs = Array.from(editableByJob.keys()).sort();

  if (alreadyClosed) {
    return (
      <p className="text-ink-3 text-sm py-4">
        This event is already committed/rejected. No further action.
      </p>
    );
  }

  if (changes.length === 0) {
    return (
      <p className="text-ink-3 text-sm py-4">No proposed changes.</p>
    );
  }

  return (
    <div className="pb-32">
      <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
        Edit, uncheck, then push to the to-do list
      </p>
      <h2 className="mt-2 font-head text-xl text-ink">
        {changes.length} proposed change{changes.length === 1 ? "" : "s"}
      </h2>
      <p className="mt-2 text-xs text-ink-3">
        Fix anything the brain got wrong — title, date, sub, category.
        Uncheck a row to skip it. Every row cites the transcript line it came
        from. Green button at the bottom commits everything checked.
      </p>

      {/* "Also touched" banner — show all jobs referenced by this batch.
          Surfaces multi-job impact before the operator commits. */}
      {allReferencedJobs.length > 1 && (
        <div className="mt-4 border-l-2 border-accent bg-accent/5 px-4 py-3">
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent mb-1">
            Touches {allReferencedJobs.length} jobs · check each one
          </p>
          <p className="text-sm text-ink-2 leading-snug">
            {allReferencedJobs
              .map((j) => j.charAt(0).toUpperCase() + j.slice(1))
              .join(" · ")}
          </p>
        </div>
      )}

      {/* EDITABLE: add_item + add_signal grouped by Job → Category */}
      {sortedJobs.map((job) => {
        const catMap = editableByJob.get(job)!;
        const jobTotal = Array.from(catMap.values()).reduce(
          (n, arr) => n + arr.length,
          0
        );
        const orderedCats = [
          ...CATEGORIES.filter((c) => catMap.has(c)),
          ...Array.from(catMap.keys()).filter(
            (c) => !CATEGORIES.includes(c)
          ),
        ];
        return (
          <section
            key={job}
            className="mt-6 border border-rule bg-paper"
          >
            <header className="px-4 py-3 bg-sand-2/40 border-b border-rule flex items-baseline justify-between">
              <h3 className="font-head text-base text-ink">
                {jobLabel(job)}
              </h3>
              <span className="font-mono text-[11px] text-ink-3 tabular-nums">
                {jobTotal}
              </span>
            </header>
            {orderedCats.map((cat) => {
              const arr = catMap.get(cat)!;
              return (
                <div
                  key={cat}
                  className="border-b border-rule-soft last:border-b-0"
                >
                  <div className="px-4 py-2 bg-sand-2/20">
                    <span className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
                      {cat} · {arr.length}
                    </span>
                  </div>
                  <ul>
                    {arr.map((c) => {
                      const d = (c.proposed_item_data ?? {}) as Record<
                        string,
                        unknown
                      >;
                      const state = rows[c.id];
                      const isSignal = c.change_type === "add_signal";
                      const claim = c.source_claim_ids?.[0]
                        ? claimById[c.source_claim_ids[0]]
                        : undefined;
                      return (
                        <li
                          key={c.id}
                          className="border-b border-rule-soft last:border-b-0 px-4 py-3"
                        >
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={state.enabled}
                              onChange={(e) =>
                                updateRow(c.id, {
                                  enabled: e.target.checked,
                                })
                              }
                              className="mt-1 h-4 w-4 accent-accent shrink-0"
                              aria-label="Include"
                            />
                            <div
                              className={`flex-1 min-w-0 space-y-2 ${
                                state.enabled ? "" : "opacity-40"
                              }`}
                            >
                              {isSignal && (
                                <span className="inline-block font-mono text-[9px] tracking-[0.12em] uppercase px-1.5 py-0.5 bg-sand-2 text-ink-3">
                                  signal (awareness only)
                                </span>
                              )}
                              <textarea
                                value={
                                  state.edited.title ?? ((d.title as string) ?? "")
                                }
                                onChange={(e) =>
                                  updateEdit(c.id, { title: e.target.value })
                                }
                                rows={2}
                                className="w-full bg-transparent border-b border-rule-soft focus:border-ink text-sm text-ink resize-none focus:outline-none"
                              />
                              <div className="flex flex-wrap gap-2 items-center">
                                <input
                                  type="date"
                                  value={
                                    state.edited.target_date ??
                                    ((d.target_date as string) ?? "")
                                  }
                                  onChange={(e) =>
                                    updateEdit(c.id, {
                                      target_date: e.target.value || null,
                                    })
                                  }
                                  className="bg-paper border border-rule px-2 py-1 text-xs text-ink focus:outline-none focus:border-ink"
                                  aria-label="Target date"
                                />
                                <select
                                  value={
                                    state.edited.sub_id ??
                                    ((d.sub_id as string) ?? "")
                                  }
                                  onChange={(e) =>
                                    updateEdit(c.id, {
                                      sub_id: e.target.value || null,
                                    })
                                  }
                                  className="bg-paper border border-rule px-2 py-1 text-xs text-ink focus:outline-none focus:border-ink flex-1 min-w-[120px]"
                                  aria-label="Sub"
                                >
                                  <option value="">— no sub —</option>
                                  {subs.map((s) => (
                                    <option key={s.id} value={s.id}>
                                      {s.trade ? `${s.name} — ${s.trade}` : s.name}
                                    </option>
                                  ))}
                                </select>
                                <select
                                  value={
                                    state.edited.category ??
                                    ((d.category as string) ?? "")
                                  }
                                  onChange={(e) =>
                                    updateEdit(c.id, {
                                      category: e.target.value || null,
                                    })
                                  }
                                  className="bg-paper border border-rule px-2 py-1 text-xs text-ink focus:outline-none focus:border-ink"
                                  aria-label="Category"
                                >
                                  <option value="">— category —</option>
                                  {CATEGORIES.map((c2) => (
                                    <option key={c2} value={c2}>
                                      {c2}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              {claim?.raw_quote && (
                                <p className="font-mono text-[10px] text-ink-3 italic leading-snug pt-1">
                                  “{claim.raw_quote.slice(0, 180)}
                                  {claim.raw_quote.length > 180 ? "…" : ""}”
                                  {claim.speaker && (
                                    <span className="ml-2 not-italic">
                                      — {claim.speaker}
                                    </span>
                                  )}
                                </p>
                              )}
                            </div>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              );
            })}
          </section>
        );
      })}

      {/* NON-EDITABLE: decisions, questions, update_items — accept/reject only */}
      {otherChanges.length > 0 && (
        <section className="mt-8">
          <h3 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-3">
            Other proposed changes · {otherChanges.length}
          </h3>
          <ul className="space-y-2">
            {otherChanges.map((c) => (
              <NonEditableRow
                key={c.id}
                change={c}
                enabled={rows[c.id].enabled}
                onToggle={(v) => updateRow(c.id, { enabled: v })}
                claim={
                  c.source_claim_ids?.[0]
                    ? claimById[c.source_claim_ids[0]]
                    : undefined
                }
              />
            ))}
          </ul>
        </section>
      )}

      {err && <p className="mt-4 text-sm text-urgent">{err}</p>}

      {/* Pre-commit impact summary — which jobs the green button will touch
          right now (based on currently-checked rows). Updates as the user
          toggles rows. */}
      {enabledJobsBreakdown.length > 0 && (
        <div className="mt-8 px-4 py-3 border border-rule-soft bg-sand-2/30">
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1">
            This push will affect
          </p>
          <p className="text-sm text-ink-2 leading-snug">
            {enabledJobsBreakdown
              .map(
                ([job, n]) =>
                  `${job.charAt(0).toUpperCase() + job.slice(1)} (${n})`
              )
              .join(" · ")}
          </p>
        </div>
      )}

      <div className="flex items-center justify-between gap-4 sticky bottom-0 bg-background border-t border-rule -mx-5 px-5 py-4 mt-4">
        <p className="font-mono text-[10px] text-ink-3 tabular-nums">
          {totalEnabled} of {changes.length} included
        </p>
        <button
          type="button"
          onClick={commit}
          disabled={busy}
          className="bg-ink text-paper px-5 py-2.5 text-sm font-medium hover:bg-accent disabled:opacity-50 transition-colors shadow-sm"
        >
          {busy
            ? "Pushing…"
            : `Push ${totalEnabled} to to-do list →`}
        </button>
      </div>
    </div>
  );
}

function NonEditableRow({
  change,
  enabled,
  onToggle,
  claim,
}: {
  change: ProposedChange;
  enabled: boolean;
  onToggle: (v: boolean) => void;
  claim: ClaimLite | undefined;
}) {
  let label = change.change_type as string;
  let body: React.ReactNode = null;
  if (change.change_type === "add_decision") {
    const d = (change.proposed_decision_data ?? {}) as Record<string, string>;
    label = "decision";
    body = (
      <>
        <p className="text-sm text-ink">{d.description}</p>
        <p className="mt-1 text-xs text-ink-3 font-mono">
          {d.decided_by ? `by ${d.decided_by}` : ""}
          {d.decision_date ? ` · ${d.decision_date}` : ""}
        </p>
      </>
    );
  } else if (change.change_type === "add_open_question") {
    const q = (change.proposed_question_data ?? {}) as Record<string, string>;
    label = "question";
    body = (
      <>
        <p className="text-sm text-ink">{q.question}</p>
        {q.asked_by && (
          <p className="mt-1 text-xs text-ink-3 font-mono">
            asked by {q.asked_by}
          </p>
        )}
      </>
    );
  } else if (change.change_type === "update_item") {
    const fc = change.field_changes ?? {};
    label = `update ${change.target_item_id?.slice(0, 8) ?? ""}`;
    body = (
      <dl className="text-xs space-y-1">
        {Object.entries(fc).map(([field, pair]) => (
          <div key={field} className="flex gap-2">
            <dt className="text-ink-3 font-mono w-24 shrink-0">{field}</dt>
            <dd>
              <span className="text-ink-3 line-through">
                {String((pair as { before: unknown }).before ?? "—")}
              </span>
              <span className="text-ink-3 mx-1">→</span>
              <span className="text-foreground">
                {String((pair as { after: unknown }).after ?? "—")}
              </span>
            </dd>
          </div>
        ))}
      </dl>
    );
  } else {
    body = (
      <p className="text-xs text-ink-3 font-mono">
        {JSON.stringify(change.proposed_item_data ?? {}).slice(0, 140)}…
      </p>
    );
  }

  return (
    <li className="border border-rule bg-paper px-4 py-3">
      <div className="flex items-start gap-3">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => onToggle(e.target.checked)}
          className="mt-1 h-4 w-4 accent-accent shrink-0"
          aria-label="Include"
        />
        <div className={`flex-1 min-w-0 ${enabled ? "" : "opacity-40"}`}>
          <span className="inline-block font-mono text-[9px] tracking-[0.12em] uppercase px-1.5 py-0.5 bg-sand-2 text-ink-3 mb-2">
            {label}
          </span>
          {body}
          {claim?.raw_quote && (
            <p className="mt-2 font-mono text-[10px] text-ink-3 italic leading-snug">
              “{claim.raw_quote.slice(0, 180)}
              {claim.raw_quote.length > 180 ? "…" : ""}”
            </p>
          )}
        </div>
      </div>
    </li>
  );
}
