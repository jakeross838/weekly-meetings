"use client";

// Interactive Weekly Review surface for one job.
//
// Flow (all human-gated — nothing is auto-sent):
//   generate -> DRAFT -> edit -> APPROVE -> copy/export or mark sent.
// Editing an approved report reverts it to draft (server enforces re-approval).
// Also: propose to-dos (accepted one-by-one into the live list) and leave
// feedback that tunes the next generation.

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ReportBody, WeeklyReport } from "@/lib/weekly";
import { reportToText } from "@/lib/weekly";

type Feedback = { id: string; feedback: string; created_by: string | null; created_at: string };
type Proposal = {
  title: string;
  due_date?: string | null;
  category: string;
  priority: string;
  rationale: string;
  billing_ref?: string | null;
};

function bodyOf(r: WeeklyReport | null): ReportBody | null {
  if (!r) return null;
  return r.edited_body ?? r.body;
}

const H3 = "font-mono text-[9px] tracking-[0.2em] uppercase text-ink-3 mb-1";
const TA =
  "w-full bg-paper border border-rule px-3 py-2 text-sm text-ink focus:outline-none focus:border-ink resize-y";

export function WeeklyReviewClient({
  jobId,
  jobName,
  weekStart,
  initialReport,
  initialFeedback,
}: {
  jobId: string;
  jobName: string;
  weekStart: string;
  initialReport: WeeklyReport | null;
  initialFeedback: Feedback[];
}) {
  const router = useRouter();
  const [report, setReport] = useState<WeeklyReport | null>(initialReport);
  const [draft, setDraft] = useState<ReportBody | null>(bodyOf(initialReport));
  const [dirty, setDirty] = useState(false);
  const [period, setPeriod] = useState<"weekly" | "monthly">("weekly");
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [proposals, setProposals] = useState<Proposal[] | null>(null);
  const [added, setAdded] = useState<Set<number>>(new Set());
  const [feedback, setFeedback] = useState<Feedback[]>(initialFeedback);
  const [fbText, setFbText] = useState("");

  const status = report?.status ?? "none";

  async function post(url: string, payload: unknown): Promise<Record<string, unknown>> {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const j = (await r.json().catch(() => ({}))) as Record<string, unknown>;
    if (!r.ok || j.ok === false) throw new Error((j.error as string) || `HTTP ${r.status}`);
    return j;
  }

  async function generate(p: "weekly" | "monthly") {
    setBusy("gen");
    setErr(null);
    setPeriod(p);
    try {
      const j = await post(`/v2/api/weekly/${jobId}/generate`, { period: p });
      const rep = j.report as WeeklyReport;
      setReport(rep);
      setDraft(bodyOf(rep));
      setDirty(false);
      setProposals(null);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function setField<K extends keyof ReportBody>(k: K, v: ReportBody[K]) {
    setDraft((d) => (d ? { ...d, [k]: v } : d));
    setDirty(true);
    setCopied(false);
  }

  async function save() {
    if (!draft) return;
    setBusy("save");
    setErr(null);
    try {
      const j = await post(`/v2/api/weekly/${jobId}/save`, { week_start: weekStart, body: draft });
      setReport(j.report as WeeklyReport);
      setDirty(false);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function approve(approveIt: boolean) {
    setBusy("approve");
    setErr(null);
    try {
      const j = await post(`/v2/api/weekly/${jobId}/approve`, { week_start: weekStart, approve: approveIt });
      setReport(j.report as WeeklyReport);
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function markSent() {
    setBusy("sent");
    setErr(null);
    try {
      const j = await post(`/v2/api/weekly/${jobId}/mark-sent`, { week_start: weekStart });
      setReport(j.report as WeeklyReport);
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  function copy() {
    if (!draft || typeof navigator === "undefined" || !navigator.clipboard) return;
    navigator.clipboard.writeText(reportToText(draft)).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  async function genTodos() {
    setBusy("todos");
    setErr(null);
    try {
      const j = await post(`/v2/api/weekly/${jobId}/generate-todos`, {});
      setProposals((j.proposals as Proposal[]) ?? []);
      setAdded(new Set());
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function addTodo(i: number, p: Proposal) {
    setBusy(`todo-${i}`);
    setErr(null);
    try {
      await post(`/api/todos/create`, {
        job_id: jobId,
        title: p.title,
        due_date: p.due_date ?? null,
        category: p.category,
        priority: p.priority,
      });
      setAdded((s) => new Set(s).add(i));
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function addFeedback() {
    const text = fbText.trim();
    if (!text) return;
    setBusy("fb");
    setErr(null);
    try {
      const j = await post(`/v2/api/weekly/${jobId}/feedback`, { feedback: text });
      setFeedback((f) => [j.feedback as Feedback, ...f]);
      setFbText("");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const tab = (active: boolean) =>
    "px-3 py-1.5 text-xs font-medium border transition-colors disabled:opacity-50 " +
    (active ? "bg-ink text-paper border-ink" : "bg-paper text-ink border-rule hover:border-ink");

  const statusBadge: Record<string, string> = {
    draft: "text-amber-700 border-amber-300 bg-amber-50",
    approved: "text-emerald-700 border-emerald-300 bg-emerald-50",
    sent: "text-sky-700 border-sky-300 bg-sky-50",
  };

  return (
    <>
      {/* ---- Homeowner report (draft → approve → send) ---- */}
      <section className="px-5 pt-6">
        <div className="border border-rule bg-paper p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
                Homeowner report
              </h2>
              {status !== "none" && (
                <span
                  className={
                    "px-1.5 py-0.5 text-[9px] font-mono uppercase tracking-[0.14em] border " +
                    (statusBadge[status] ?? "")
                  }
                >
                  {status}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={() => generate("weekly")} disabled={busy !== null} className={tab(period === "weekly")}>
                {busy === "gen" && period === "weekly" ? "…" : report ? "Regenerate" : "Weekly"}
              </button>
              <button type="button" onClick={() => generate("monthly")} disabled={busy !== null} className={tab(period === "monthly")}>
                {busy === "gen" && period === "monthly" ? "…" : "Monthly"}
              </button>
            </div>
          </div>

          {err && <p className="mt-3 text-sm text-urgent">{err}</p>}

          {!draft && busy !== "gen" && (
            <p className="mt-2 text-xs text-ink-3">
              Generate a draft {jobName} update for the homeowner — budget, schedule,
              and what&apos;s next. You edit and approve it before anything is sent.
            </p>
          )}
          {busy === "gen" && <p className="mt-3 font-mono text-[11px] text-accent">Writing the {period} draft…</p>}

          {draft && (
            <div className="mt-4 space-y-3">
              <div>
                <h3 className={H3}>Greeting</h3>
                <textarea rows={2} className={TA} value={draft.greeting} onChange={(e) => setField("greeting", e.target.value)} />
              </div>
              <div>
                <h3 className={H3}>Budget</h3>
                <textarea rows={3} className={TA} value={draft.budget} onChange={(e) => setField("budget", e.target.value)} />
              </div>
              <div>
                <h3 className={H3}>Schedule</h3>
                <textarea rows={3} className={TA} value={draft.schedule} onChange={(e) => setField("schedule", e.target.value)} />
              </div>
              <div>
                <h3 className={H3}>Upcoming selections (one per line)</h3>
                <textarea
                  rows={3}
                  className={TA}
                  value={draft.upcoming_selections.join("\n")}
                  onChange={(e) =>
                    setField("upcoming_selections", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))
                  }
                />
              </div>
              <div>
                <h3 className={H3}>What&apos;s next (one per line)</h3>
                <textarea
                  rows={3}
                  className={TA}
                  value={draft.whats_next.join("\n")}
                  onChange={(e) =>
                    setField("whats_next", e.target.value.split("\n").map((s) => s.trim()).filter(Boolean))
                  }
                />
              </div>
              <div>
                <h3 className={H3}>Closing</h3>
                <textarea rows={2} className={TA} value={draft.closing} onChange={(e) => setField("closing", e.target.value)} />
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                {dirty && (
                  <button
                    type="button"
                    onClick={save}
                    disabled={busy !== null}
                    className="bg-ink text-paper px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors disabled:opacity-50"
                  >
                    {busy === "save" ? "Saving…" : "Save edits"}
                  </button>
                )}
                {status === "draft" && !dirty && (
                  <button
                    type="button"
                    onClick={() => approve(true)}
                    disabled={busy !== null}
                    className="bg-emerald-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-emerald-700 transition-colors disabled:opacity-50"
                  >
                    {busy === "approve" ? "…" : "✓ Approve"}
                  </button>
                )}
                {status === "approved" && (
                  <>
                    <button
                      type="button"
                      onClick={copy}
                      className="border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-paper transition-colors"
                    >
                      {copied ? "✓ Copied" : "⧉ Copy for client"}
                    </button>
                    <button
                      type="button"
                      onClick={markSent}
                      disabled={busy !== null}
                      className="bg-sky-600 text-white px-3 py-1.5 text-xs font-medium hover:bg-sky-700 transition-colors disabled:opacity-50"
                    >
                      {busy === "sent" ? "…" : "Mark as sent"}
                    </button>
                    <button
                      type="button"
                      onClick={() => approve(false)}
                      disabled={busy !== null}
                      className="text-ink-3 px-2 py-1.5 text-xs hover:text-ink"
                    >
                      revert to draft
                    </button>
                  </>
                )}
                {status === "sent" && (
                  <>
                    <span className="text-xs text-sky-700 py-1.5">
                      Sent{report?.sent_at ? ` ${new Date(report.sent_at).toLocaleDateString()}` : ""}
                      {report?.sent_by ? ` by ${report.sent_by}` : ""}.
                    </span>
                    <button
                      type="button"
                      onClick={copy}
                      className="border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-paper transition-colors"
                    >
                      {copied ? "✓ Copied" : "⧉ Copy again"}
                    </button>
                  </>
                )}
              </div>
              {status === "approved" && (
                <p className="text-[11px] text-ink-3">
                  Approved{report?.approved_by ? ` by ${report.approved_by}` : ""}. Copy or send it
                  yourself — the app never sends to a client automatically.
                </p>
              )}
            </div>
          )}
        </div>
      </section>

      {/* ---- Proposed to-dos (accepted one-by-one) ---- */}
      <section className="px-5 pt-6">
        <div className="border border-rule bg-paper p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
              Suggested to-dos
            </h2>
            <button type="button" onClick={genTodos} disabled={busy !== null} className={tab(false)}>
              {busy === "todos" ? "Scanning…" : "Suggest from gaps"}
            </button>
          </div>
          {proposals && proposals.length === 0 && (
            <p className="mt-2 text-xs text-ink-3">No open commitments or gaps to convert right now.</p>
          )}
          {proposals && proposals.length > 0 && (
            <ul className="mt-3 space-y-2">
              {proposals.map((p, i) => (
                <li key={i} className="border border-rule p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-foreground leading-snug">{p.title}</p>
                      <p className="mt-1 text-[11px] text-ink-3">
                        {p.category} · {p.priority}
                        {p.due_date ? ` · due ${p.due_date}` : ""}
                      </p>
                      <p className="mt-1 text-[11px] text-ink-2 italic">{p.rationale}</p>
                      {p.billing_ref && (
                        <p className="mt-1 text-[11px] text-emerald-700">▸ billing: {p.billing_ref}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => addTodo(i, p)}
                      disabled={busy !== null || added.has(i)}
                      className="shrink-0 border border-ink text-ink px-2.5 py-1 text-[11px] font-medium hover:bg-ink hover:text-paper transition-colors disabled:opacity-50"
                    >
                      {added.has(i) ? "✓ Added" : busy === `todo-${i}` ? "…" : "+ Add"}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
          {!proposals && (
            <p className="mt-2 text-xs text-ink-3">
              Scan open commitments, past-due work, and outstanding POs for to-dos worth adding.
              You approve each one before it hits the list.
            </p>
          )}
        </div>
      </section>

      {/* ---- Feedback (tunes the next generation) ---- */}
      <section className="px-5 pt-6">
        <div className="border border-rule bg-paper p-4">
          <h2 className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Feedback for next time
          </h2>
          <p className="mt-1 text-[11px] text-ink-3">
            e.g. &ldquo;keep budget vaguer&rdquo;, &ldquo;the client cares most about the pool&rdquo;.
            Fed into the next draft.
          </p>
          <div className="mt-2 flex gap-2">
            <textarea
              rows={2}
              className={TA}
              value={fbText}
              onChange={(e) => setFbText(e.target.value)}
              placeholder="Add a note…"
            />
          </div>
          <div className="mt-2">
            <button
              type="button"
              onClick={addFeedback}
              disabled={busy !== null || !fbText.trim()}
              className="bg-ink text-paper px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors disabled:opacity-50"
            >
              {busy === "fb" ? "Saving…" : "Save feedback"}
            </button>
          </div>
          {feedback.length > 0 && (
            <ul className="mt-4 space-y-2">
              {feedback.map((f) => (
                <li key={f.id} className="text-xs text-ink-2 border-l-2 border-rule pl-2">
                  {f.feedback}
                  <span className="block text-[10px] text-ink-3 mt-0.5">
                    {f.created_by ?? "pm"} · {new Date(f.created_at).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>
    </>
  );
}
