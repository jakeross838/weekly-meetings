"use client";

// Interactive run-of-show. The server hands us a fully-computed, ordered
// agenda; this component only owns the "covered" walk-through state so a PM
// can step through jobs in the meeting and watch progress. Ephemeral by
// design (resets on reload) — covering a job is a meeting gesture, not data.

import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { DeleteButton } from "@/components/delete-button";
import { EditableText } from "@/components/editable-text";
import { CATEGORIES, styleFor } from "@/lib/categories";

export interface MeetingItem {
  id: string;
  source: "item" | "todo"; // which table — drives the edit/delete endpoint
  title: string;
  due_date: string | null; // raw yyyy-mm-dd, so the date is inline-editable
  daysOver: number | null; // set when past due
  daysTo: number | null; // set when due in the future
  subName: string | null;
  category: string | null;
}

// Stable display order for category sub-groups inside a bucket. Anything not
// in CATEGORIES (or null) lands in "Uncategorized" at the bottom.
const CATEGORY_ORDER: readonly string[] = [...CATEGORIES, "__uncategorized__"];
function categoryKey(c: string | null): string {
  return c && (CATEGORIES as readonly string[]).includes(c) ? c : "__uncategorized__";
}
function categoryLabel(key: string): string {
  return key === "__uncategorized__" ? "Other" : key;
}

function groupByCategory(items: MeetingItem[]): { key: string; label: string; items: MeetingItem[] }[] {
  const buckets = new Map<string, MeetingItem[]>();
  for (const it of items) {
    const k = categoryKey(it.category);
    const arr = buckets.get(k) ?? [];
    arr.push(it);
    buckets.set(k, arr);
  }
  return CATEGORY_ORDER.filter((k) => buckets.has(k)).map((k) => ({
    key: k,
    label: categoryLabel(k),
    items: buckets.get(k)!,
  }));
}
export interface AttentionSub {
  id: string;
  name: string;
  status: "red" | "yellow" | "green";
  dotClass: string;
  reason: string | null;
  trade: string | null;
  flagged: boolean;
}
export interface MeetingJob {
  id: string;
  name: string;
  pmName: string | null;
  contractPct: number | null;
  pending: number;
  pastDue: MeetingItem[];
  dueSoon: MeetingItem[];
  laterCount: number;
  attentionSubs: AttentionSub[];
}

// Full sub roster (id + name), passed once and reused by every job's
// "assign a sub" picker.
export interface SubOption {
  id: string;
  name: string;
}

export function MeetingAgenda({ jobs, subs }: { jobs: MeetingJob[]; subs: SubOption[] }) {
  const [covered, setCovered] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setCovered((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const done = covered.size;
  const pct = jobs.length ? Math.round((done / jobs.length) * 100) : 0;

  return (
    <>
      {/* Sticky progress — stays visible while walking the agenda. */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur px-5 pt-3 pb-3 border-b border-rule">
        <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          <span>
            {done} of {jobs.length} covered
          </span>
          {done > 0 && (
            <button
              onClick={() => setCovered(new Set())}
              className="hover:text-ink transition-colors"
            >
              reset
            </button>
          )}
        </div>
        <div className="mt-2 h-1 w-full bg-sand-2 overflow-hidden">
          <div
            className="h-full bg-ink transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {jobs.length === 0 ? (
        <p className="px-5 pt-10 text-ink-3 text-sm">No jobs in scope.</p>
      ) : (
        <ol className="px-5 pt-6 pb-16 space-y-7 stagger-children">
          {jobs.map((j, i) => (
            <JobCard
              key={j.id}
              job={j}
              subs={subs}
              index={i + 1}
              covered={covered.has(j.id)}
              onToggle={() => toggle(j.id)}
            />
          ))}
        </ol>
      )}
    </>
  );
}

function JobCard({
  job,
  subs,
  index,
  covered,
  onToggle,
}: {
  job: MeetingJob;
  subs: SubOption[];
  index: number;
  covered: boolean;
  onToggle: () => void;
}) {
  const nothing =
    job.pastDue.length === 0 &&
    job.dueSoon.length === 0 &&
    job.attentionSubs.length === 0 &&
    job.pending === 0;

  // Side accent bar tone: urgent if past-due exists, accent if anything else
  // needs attention, neutral when nothing's open.
  const accent =
    job.pastDue.length > 0
      ? "before:bg-urgent"
      : !nothing
        ? "before:bg-accent"
        : "before:bg-rule";

  return (
    <li
      className={
        "relative border border-rule bg-paper transition-all duration-300 overflow-hidden " +
        // left accent stripe via ::before pseudo
        "before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 " +
        accent +
        " " +
        (covered
          ? "opacity-60 bg-background"
          : "shadow-[0_1px_0_rgba(0,0,0,0.02)] hover:shadow-md")
      }
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 px-6 pt-5 pb-4">
        <Link href={`/v2/job/${job.id}`} className="flex items-start gap-3 flex-1 min-w-0 group">
          <span
            aria-hidden
            className={
              "shrink-0 mt-0.5 grid h-7 w-7 place-items-center rounded-full font-mono text-[11px] tabular-nums transition-colors " +
              (covered
                ? "bg-ink/10 text-ink-3"
                : "bg-oceanside/40 text-ink group-hover:bg-accent group-hover:text-paper")
            }
          >
            {String(index).padStart(2, "0")}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="font-head text-[19px] leading-tight tracking-tight text-foreground group-hover:text-accent transition-colors truncate">
              {job.name}
            </h2>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-ink-3">
              {job.pmName && <span className="font-mono uppercase tracking-[0.1em]">{job.pmName}</span>}
              {job.contractPct != null && (
                <>
                  <Dot />
                  <span className="font-mono tabular-nums">{job.contractPct}% billed</span>
                </>
              )}
              {job.pending > 0 && (
                <>
                  <Dot />
                  <span className="font-mono text-accent uppercase tracking-[0.1em]">
                    {job.pending} to approve
                  </span>
                </>
              )}
            </div>
          </div>
        </Link>
        <button
          onClick={onToggle}
          className={
            "shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] border px-2.5 py-1.5 transition-colors " +
            (covered
              ? "bg-ink text-paper border-ink"
              : "bg-transparent text-ink-2 border-rule hover:border-ink hover:text-ink hover:bg-oceanside/30")
          }
        >
          {covered ? "✓ covered" : "cover"}
        </button>
      </div>

      {!covered && (
        <div className="px-6 pb-6">
          {nothing ? (
            <div className="border-t border-rule pt-5 text-ink-3 text-sm italic">
              Nothing open — quick confirm and move on.
            </div>
          ) : (
            <div className="border-t border-rule pt-5 grid gap-5">
              {job.pastDue.length > 0 && (
                <Bucket tone="urgent" title="Past due" count={job.pastDue.length}>
                  <CategoryGroups items={job.pastDue} pastDue tone="urgent" />
                </Bucket>
              )}
              {job.dueSoon.length > 0 && (
                <Bucket tone="accent" title="This week" count={job.dueSoon.length}>
                  <CategoryGroups items={job.dueSoon} tone="accent" />
                </Bucket>
              )}
              {job.attentionSubs.length > 0 && (
                <Bucket tone="neutral" title="Subs to watch" count={job.attentionSubs.length}>
                  <ul className="flex flex-wrap gap-1.5 pt-1">
                    {job.attentionSubs.map((s) => (
                      <SubChip key={s.id} sub={s} />
                    ))}
                  </ul>
                </Bucket>
              )}
              {job.laterCount > 0 && (
                <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-3 pt-1">
                  + {job.laterCount} more open (no near date)
                </p>
              )}
            </div>
          )}
          {/* Always available while the card is open — assigning a sub creates
              a to-do on this job, which is what actually links a sub to it. */}
          <AssignSub jobId={job.id} subs={subs} />
        </div>
      )}
    </li>
  );
}

function Dot() {
  return <span aria-hidden className="text-ink-3/60">·</span>;
}

function Bucket({
  title,
  count,
  tone,
  children,
}: {
  title: string;
  count: number;
  tone: "urgent" | "accent" | "neutral";
  children: ReactNode;
}) {
  // Each bucket gets a soft tinted background + header to chunk the content
  // visually, so the page reads as discrete blocks instead of one wall.
  const bg =
    tone === "urgent"
      ? "bg-urgent/[0.04] border-urgent/20"
      : tone === "accent"
        ? "bg-oceanside/30 border-rule"
        : "bg-sand/40 border-rule";
  const titleColor =
    tone === "urgent" ? "text-urgent" : tone === "accent" ? "text-ink" : "text-ink-2";
  return (
    <section className={`border ${bg}`}>
      <header
        className={`flex items-baseline justify-between px-4 py-2.5 font-mono text-[10px] uppercase tracking-[0.18em] ${titleColor}`}
      >
        <span>{title}</span>
        <span className="tabular-nums">{count}</span>
      </header>
      <div className="bg-paper">{children}</div>
    </section>
  );
}

// Within a bucket, group items by category (Schedule / Quality / Procurement
// / Selection / Budget / Client / Admin / Sub-trade / Other) so a 12-item
// past-due list reads as 4 short sections instead of one long wall.
function CategoryGroups({
  items,
  pastDue,
  tone,
}: {
  items: MeetingItem[];
  pastDue?: boolean;
  tone: "urgent" | "accent";
}) {
  const groups = groupByCategory(items);
  // Single category? Skip the inner labels — just render the flat list so we
  // don't add visual noise when grouping wouldn't help.
  if (groups.length <= 1) {
    return (
      <ul className={pastDue ? "divide-y divide-urgent/15" : "divide-y divide-rule"}>
        {items.map((it) => (
          <ItemRow key={`${it.source}:${it.id}`} it={it} pastDue={pastDue} />
        ))}
      </ul>
    );
  }
  const divider =
    tone === "urgent" ? "divide-y divide-urgent/15" : "divide-y divide-rule";
  return (
    <div className="divide-y divide-rule">
      {groups.map((g) => (
        <div key={g.key} className="px-2 py-2">
          <div className="flex items-baseline justify-between px-2 pt-1 pb-1">
            <span
              className={
                "inline-block px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] " +
                styleFor(g.key === "__uncategorized__" ? null : g.key)
              }
            >
              {g.label}
            </span>
            <span className="font-mono text-[10px] tabular-nums text-ink-3">
              {g.items.length}
            </span>
          </div>
          <ul className={divider}>
            {g.items.map((it) => (
              <ItemRow key={`${it.source}:${it.id}`} it={it} pastDue={pastDue} />
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

function ItemRow({ it, pastDue }: { it: MeetingItem; pastDue?: boolean }) {
  // Inline edits route to the id-in-URL edit endpoints so the shared
  // <EditableText> (which POSTs only { [field]: value }) works unchanged.
  // todos store the date as `due_date`; v2 items as `target_date`.
  const editEndpoint =
    it.source === "item" ? `/v2/api/items/${it.id}/edit` : `/api/todos/${it.id}/edit`;
  const dateField = it.source === "item" ? "target_date" : "due_date";
  const dateLabel = pastDue
    ? `${it.daysOver}d over`
    : it.daysTo === 0
      ? "today"
      : `${it.daysTo}d`;

  return (
    <li className="flex gap-4 items-baseline px-4 py-4">
      <span className="flex-1 min-w-0 text-foreground text-sm leading-relaxed">
        <EditableText
          value={it.title}
          endpoint={editEndpoint}
          field="title"
          type="text"
          label="Click to edit task"
          className="text-foreground text-sm leading-relaxed"
        />
        {it.subName && (
          <span className="ml-2 inline-block font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            · {it.subName}
          </span>
        )}
      </span>
      <EditableText
        value={it.due_date}
        endpoint={editEndpoint}
        field={dateField}
        type="date"
        display={dateLabel}
        label="Click to edit due date"
        className={
          "shrink-0 font-mono text-xs tabular-nums whitespace-nowrap " +
          (pastDue ? "text-urgent" : "text-ink-3")
        }
      />
      <DeleteButton
        endpoint={
          it.source === "item"
            ? `/v2/api/items/${it.id}/delete`
            : `/api/todos/${it.id}/delete`
        }
        label={it.source === "item" ? "item" : "to-do"}
        className="self-center text-sm"
      />
    </li>
  );
}

// The "Subs to watch" chips are no longer plain links — clicking one opens a
// small popover so a PM can edit/flag/remove the sub in the moment without
// leaving the run-of-show. Edits route to the existing /api/subs/[id]/edit and
// /delete endpoints; router.refresh() (via the shared components) repaints the
// agenda. There's deliberately no "add a sub here": a sub only appears under a
// job because it has an open commitment on it, so "add" lives on /subs, not on
// a per-job watch list that's derived, not stored.
function SubChip({ sub }: { sub: AttentionSub }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const endpoint = `/api/subs/${sub.id}/edit`;

  return (
    <li ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title={sub.reason ?? "Edit sub"}
        className={
          "inline-flex items-center gap-1.5 border bg-paper px-2 py-1 text-xs transition-colors " +
          (open
            ? "border-ink-2 bg-oceanside/30"
            : "border-rule hover:border-ink-2 hover:bg-oceanside/30")
        }
      >
        <span className={`shrink-0 h-2 w-2 rounded-full ${sub.dotClass}`} />
        <span className="text-foreground">{sub.name}</span>
        {sub.flagged && <span className="shrink-0 text-gold">⚑</span>}
        {sub.reason && (
          <span className="text-ink-3 font-mono text-[10px] uppercase tracking-[0.1em] hidden sm:inline">
            · {sub.reason}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1 w-64 cursor-default space-y-2.5 border border-ink-2 bg-paper p-3 text-left shadow-lg">
          <div>
            <FieldLabel>Name</FieldLabel>
            <EditableText
              value={sub.name}
              endpoint={endpoint}
              field="name"
              type="text"
              className="text-foreground text-sm"
            />
          </div>
          <div>
            <FieldLabel>Trade</FieldLabel>
            <EditableText
              value={sub.trade}
              endpoint={endpoint}
              field="trade"
              type="text"
              placeholder="add a trade…"
              className="text-foreground text-sm"
            />
          </div>
          <div>
            <FieldLabel>Watch</FieldLabel>
            <FlagToggle id={sub.id} flagged={sub.flagged} />
            <div className="mt-1.5">
              <EditableText
                value={sub.reason}
                endpoint={endpoint}
                field="flag_note"
                type="text"
                placeholder="why we're watching…"
                className="text-ink-2 text-xs"
              />
            </div>
          </div>
          <div className="flex items-center justify-between border-t border-rule pt-2">
            <Link
              href={`/sub/${sub.id}`}
              className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-2 hover:text-accent transition-colors"
            >
              View profile →
            </Link>
            <DeleteButton
              endpoint={`/api/subs/${sub.id}/delete`}
              label={sub.name}
              className="text-sm"
            />
          </div>
        </div>
      )}
    </li>
  );
}

function FieldLabel({ children }: { children: ReactNode }) {
  return (
    <div className="font-mono text-[9px] uppercase tracking-[0.16em] text-ink-3 mb-0.5">
      {children}
    </div>
  );
}

// Toggles flagged_for_pm_binder — the single "watch this sub" signal that
// drives sub health and why the chip is here. Posts to the same edit route.
function FlagToggle({ id, flagged }: { id: string; flagged: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function toggle() {
    setBusy(true);
    try {
      await fetch(`/api/subs/${id}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flagged_for_pm_binder: !flagged }),
      });
    } catch {
      /* leave the toggle as-is on a network error */
    }
    setBusy(false);
    router.refresh();
  }
  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      className={
        "inline-flex items-center gap-1 border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors disabled:opacity-50 " +
        (flagged
          ? "border-gold text-gold"
          : "border-rule text-ink-3 hover:border-ink hover:text-ink")
      }
    >
      <span>{flagged ? "⚑" : "☆"}</span>
      <span>{flagged ? "flagged" : "flag for binder"}</span>
    </button>
  );
}

// Assign a sub to this job by creating a to-do on it (the only thing that
// actually links a sub to a job — subs surface on the agenda via their open
// commitments). Posts to the shared /api/todos/create route, tagged SUB-TRADE.
function AssignSub({ jobId, subs }: { jobId: string; subs: SubOption[] }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [subId, setSubId] = useState("");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function reset() {
    setSubId("");
    setTitle("");
    setDue("");
    setErr(null);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!subId) {
      setErr("pick a sub");
      return;
    }
    if (!title.trim()) {
      setErr("add a task");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch("/api/todos/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          job_id: jobId,
          sub_id: subId,
          title: title.trim(),
          due_date: due || undefined,
          category: "SUB-TRADE",
        }),
      });
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        setErr(b.error || `HTTP ${r.status}`);
        setBusy(false);
        return;
      }
      setBusy(false);
      reset();
      setOpen(false);
      router.refresh();
    } catch (e2) {
      setErr((e2 as Error).message);
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="mt-4 inline-flex items-center gap-1.5 border border-rule px-2.5 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-2 hover:border-ink hover:bg-oceanside/30 hover:text-ink transition-colors"
      >
        ＋ assign a sub
      </button>
    );
  }

  const inputCls =
    "w-full bg-paper border border-rule px-2 py-1.5 text-sm text-ink focus:outline-none focus:border-ink";

  return (
    <form onSubmit={submit} className="mt-4 space-y-2 border border-rule bg-sand/40 p-3">
      <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-2">
        Assign a sub
      </div>
      <select
        value={subId}
        onChange={(e) => setSubId(e.target.value)}
        className={inputCls}
      >
        <option value="">Select a sub…</option>
        {subs.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
      <input
        type="text"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="what do they need to do?"
        className={inputCls}
      />
      <div className="flex items-center gap-2">
        <input
          type="date"
          value={due}
          onChange={(e) => setDue(e.target.value)}
          className="bg-paper border border-rule px-2 py-1.5 text-sm text-ink focus:outline-none focus:border-ink"
        />
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
          due (optional)
        </span>
      </div>
      {err && <div className="text-urgent text-xs">{err}</div>}
      <div className="flex items-center gap-2 pt-1">
        <button
          type="submit"
          disabled={busy}
          className="bg-ink px-3 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-paper hover:bg-ink/90 disabled:opacity-50 transition-colors"
        >
          {busy ? "adding…" : "add"}
        </button>
        <button
          type="button"
          onClick={() => {
            reset();
            setOpen(false);
          }}
          className="px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3 hover:text-ink transition-colors"
        >
          cancel
        </button>
      </div>
    </form>
  );
}
