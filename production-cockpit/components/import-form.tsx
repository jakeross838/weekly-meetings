"use client";

import { useState, useTransition, useRef } from "react";
import { useRouter } from "next/navigation";
import { CATEGORIES, styleFor } from "@/lib/categories";

interface PMOpt {
  id: string;
  full_name: string;
}

interface JobOpt {
  id: string;
  name: string;
}

interface SubOpt {
  id: string;
  name: string;
}

interface Assignment {
  job_id: string;
  pm_id: string;
}

interface ImportFormProps {
  pms: PMOpt[];
  jobs?: JobOpt[];
  assignments?: Assignment[];
  subs?: SubOpt[];
}

// Parse Plaud filenames like:
//   "04-15 Fish Site Production Meeting-transcript (1).txt"
//   "04-09 Lee W Office Production Meeting-transcript.txt"
// Returns the date (MM-DD assumed current year), meeting type, and the middle
// token(s) (job name or PM first-name).
function parsePlaudFilename(name: string): {
  date: string | null;
  meetingType: "SITE" | "OFFICE" | null;
  candidate: string | null;
} {
  const base = name.replace(/\.txt$/i, "");
  const dateMatch = base.match(/^(\d{2})-(\d{2})\s+(.+)$/);
  if (!dateMatch) return { date: null, meetingType: null, candidate: null };
  const yyyy = new Date().getFullYear();
  const date = `${yyyy}-${dateMatch[1]}-${dateMatch[2]}`;
  const rest = dateMatch[3];
  const lower = rest.toLowerCase();
  let meetingType: "SITE" | "OFFICE" | null = null;
  let candidate: string | null = null;
  const m = lower.match(/^(.+?)\s+(site|office)\s+production meeting/);
  if (m) {
    candidate = m[1].trim();
    meetingType = m[2] === "site" ? "SITE" : "OFFICE";
  }
  return { date, meetingType, candidate };
}

function matchJob(candidate: string, jobs: JobOpt[]): JobOpt | null {
  const c = candidate.toLowerCase().trim();
  // Exact id or name match first, then startsWith
  let hit = jobs.find(
    (j) => j.id.toLowerCase() === c || j.name.toLowerCase() === c
  );
  if (hit) return hit;
  hit = jobs.find(
    (j) =>
      j.name.toLowerCase().startsWith(c) || j.id.toLowerCase().startsWith(c)
  );
  return hit ?? null;
}

function matchPm(candidate: string, pms: PMOpt[]): PMOpt | null {
  const c = candidate.toLowerCase().trim();
  // First-name match, then startsWith on full name
  let hit = pms.find(
    (p) => p.full_name.split(" ")[0].toLowerCase() === c
  );
  if (hit) return hit;
  hit = pms.find((p) => p.full_name.toLowerCase().startsWith(c));
  return hit ?? null;
}

interface ExtractedItem {
  title: string;
  sub_name: string | null;
  job: string;
  priority: "URGENT" | "HIGH" | "NORMAL";
  due_date: string | null;
  suggested_due_date?: string | null;
  suggested_due_date_reason?: string | null;
  category: string;
  type: string;
  source_excerpt?: string | null;
}

interface SubGroup {
  sub_id: string | null;
  sub_name: string | null;
  items: ExtractedItem[];
}

interface ExtractResp {
  summary: string;
  grouped: SubGroup[];
  totalItems: number;
  jobs_mentioned?: string[];
}

const todayIso = () => new Date().toISOString().slice(0, 10);

interface RowState {
  enabled: boolean;
  title: string;
  due_date: string | null;
  suggested_due_date: string | null;
  suggested_due_date_reason: string | null;
  sub_id: string | null;
  sub_name: string | null;
  category: string;
  priority: "URGENT" | "HIGH" | "NORMAL";
  type: string;
  job: string;
  source_excerpt: string | null;
}

export function ImportForm({
  pms,
  jobs = [],
  assignments = [],
  subs = [],
}: ImportFormProps) {
  const router = useRouter();
  const [pmId, setPmId] = useState(pms[0]?.id ?? "");
  const [jobId, setJobId] = useState<string>("");
  const [meetingDate, setMeetingDate] = useState(todayIso());
  const [meetingType, setMeetingType] = useState<"SITE" | "OFFICE">("SITE");
  const [transcript, setTranscript] = useState("");
  const [filename, setFilename] = useState("");
  const [autoDetected, setAutoDetected] = useState<string | null>(null);
  const [isDragging, setDragging] = useState(false);
  const [step, setStep] = useState<"upload" | "review">("upload");
  const [extract, setExtract] = useState<ExtractResp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, start] = useTransition();
  const [processing, setProcessing] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Per-row state keyed by `${gi}:${ii}` — holds editable overrides on the
  // extractor's output plus an enabled flag.
  const [rows, setRows] = useState<Record<string, RowState>>({});
  const itemKey = (gi: number, ii: number) => `${gi}:${ii}`;

  function onFile(file: File) {
    if (!file.name.endsWith(".txt") && file.type !== "text/plain") {
      setError("Only .txt transcripts are supported");
      return;
    }
    setFilename(file.name);
    const reader = new FileReader();
    reader.onload = () => setTranscript(String(reader.result || ""));
    reader.onerror = () => setError("Could not read file");
    reader.readAsText(file);

    // Auto-detect from filename
    const parsed = parsePlaudFilename(file.name);
    const hits: string[] = [];
    if (parsed.date) {
      setMeetingDate(parsed.date);
      hits.push(`date: ${parsed.date}`);
    }
    if (parsed.meetingType) {
      setMeetingType(parsed.meetingType);
      hits.push(`type: ${parsed.meetingType}`);
    }
    if (parsed.candidate) {
      const job = matchJob(parsed.candidate, jobs);
      if (job) {
        setJobId(job.id);
        hits.push(`job: ${job.name}`);
        const a = assignments.find((x) => x.job_id === job.id);
        if (a) {
          setPmId(a.pm_id);
          const pm = pms.find((p) => p.id === a.pm_id);
          if (pm) hits.push(`pm: ${pm.full_name}`);
        }
      } else {
        const pm = matchPm(parsed.candidate, pms);
        if (pm) {
          setPmId(pm.id);
          hits.push(`pm: ${pm.full_name}`);
        }
      }
    }
    setAutoDetected(hits.length > 0 ? hits.join(" · ") : null);
  }

  async function process() {
    setError(null);
    if (transcript.trim().length < 100) {
      setError("Transcript missing or too short");
      return;
    }
    if (!pmId) {
      setError("Pick a PM first");
      return;
    }
    const pmName = pms.find((p) => p.id === pmId)?.full_name ?? pmId;
    setProcessing(true);
    try {
      const res = await fetch("/api/import-transcript", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          transcript,
          pm_id: pmId,
          pm_name: pmName,
          meeting_date: meetingDate,
          meeting_type: meetingType,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setError(data.error || `HTTP ${res.status}`);
        setProcessing(false);
        return;
      }
      setExtract(data);
      // Default per-row state: everything enabled, original values from extractor
      const init: Record<string, RowState> = {};
      data.grouped.forEach((g: SubGroup, gi: number) => {
        g.items.forEach((item: ExtractedItem, ii: number) => {
          init[itemKey(gi, ii)] = {
            enabled: true,
            title: item.title,
            due_date: item.due_date,
            suggested_due_date: item.suggested_due_date ?? null,
            suggested_due_date_reason: item.suggested_due_date_reason ?? null,
            sub_id: g.sub_id,
            sub_name: g.sub_name,
            category: item.category,
            priority: item.priority,
            type: item.type,
            job: item.job,
            source_excerpt: item.source_excerpt ?? null,
          };
        });
      });
      setRows(init);
      setStep("review");
      setProcessing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setProcessing(false);
    }
  }

  async function save() {
    if (!extract) return;
    setSaving(true);
    setError(null);
    const items: (ExtractedItem & { sub_id: string | null })[] = [];
    Object.values(rows).forEach((r) => {
      if (!r.enabled) return;
      items.push({
        title: r.title,
        sub_name: r.sub_name,
        job: r.job,
        priority: r.priority,
        due_date: r.due_date,
        category: r.category,
        type: r.type,
        sub_id: r.sub_id,
      });
    });
    try {
      const res = await fetch("/api/save-extracted-todos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pm_id: pmId,
          meeting_date: meetingDate,
          source_label: filename || "cockpit-import",
          items,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        setError(data.error || `HTTP ${res.status}`);
        setSaving(false);
        return;
      }
      start(() => router.push(`/?pm=${pmId}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  }

  if (step === "review" && extract) {
    const rowEntries = Object.entries(rows);
    const totalEnabled = rowEntries.filter(([, r]) => r.enabled).length;

    // Regroup the flat rowEntries by Job → Category → row[]
    const byJob = new Map<
      string,
      Map<string, { key: string; row: RowState }[]>
    >();
    for (const [key, row] of rowEntries) {
      const job = row.job || "(no job)";
      const cat = row.category || "(uncategorized)";
      if (!byJob.has(job)) byJob.set(job, new Map());
      const catMap = byJob.get(job)!;
      if (!catMap.has(cat)) catMap.set(cat, []);
      catMap.get(cat)!.push({ key, row });
    }
    const sortedJobs = Array.from(byJob.keys()).sort();
    const CAT_ORDER = [
      "SCHEDULE",
      "QUALITY",
      "PROCUREMENT",
      "SELECTION",
      "BUDGET",
      "CLIENT",
      "ADMIN",
      "SUB-TRADE",
    ];

    const updateRow = (key: string, patch: Partial<RowState>) => {
      setRows((s) => ({ ...s, [key]: { ...s[key], ...patch } }));
    };

    return (
      <div className="px-5 pb-32">
        <div className="py-6">
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
            Step 2 of 2 · Edit, then push to the to-do list
          </p>
          <h2 className="mt-2 font-head text-2xl font-semibold text-ink">
            {extract.totalItems} to-do{extract.totalItems === 1 ? "" : "s"}{" "}
            generated by Claude
          </h2>
          {extract.summary && (
            <p className="mt-3 text-sm text-ink-2 leading-relaxed">
              {extract.summary}
            </p>
          )}
          <p className="mt-3 text-xs text-ink-3">
            Fix anything Claude got wrong — title, due date, sub. Uncheck rows
            to drop them. Every row cites the exact transcript line it came
            from. When it looks right, hit the green button.
          </p>
        </div>

        {/* Other jobs mentioned — flag so the operator knows to check those job pages too */}
        {extract.jobs_mentioned && extract.jobs_mentioned.length > 0 && (() => {
          const here = new Set(sortedJobs.map((j) => j.toLowerCase()));
          const elsewhere = extract.jobs_mentioned.filter(
            (j) => !here.has(j.toLowerCase())
          );
          if (elsewhere.length === 0) return null;
          return (
            <div className="mb-6 border-l-2 border-accent bg-accent/5 px-4 py-3">
              <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent mb-1">
                Also mentioned · check those job pages
              </p>
              <p className="text-sm text-ink-2 leading-snug">
                {elsewhere.join(" · ")}
              </p>
            </div>
          );
        })()}

        {sortedJobs.map((job) => {
          const catMap = byJob.get(job)!;
          const jobTotal = Array.from(catMap.values()).reduce(
            (n, arr) => n + arr.length,
            0
          );
          const orderedCats = [
            ...CAT_ORDER.filter((c) => catMap.has(c)),
            ...Array.from(catMap.keys()).filter((c) => !CAT_ORDER.includes(c)),
          ];
          return (
            <section
              key={job}
              className="mb-6 border border-rule bg-paper"
            >
              <header className="px-4 py-3 bg-sand-2/40 border-b border-rule flex items-baseline justify-between">
                <h3 className="font-head text-base font-semibold text-ink">
                  {job}
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
                      {arr.map(({ key, row }) => (
                        <li
                          key={key}
                          className="border-b border-rule-soft last:border-b-0 px-4 py-3"
                        >
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              checked={row.enabled}
                              onChange={(e) =>
                                updateRow(key, {
                                  enabled: e.target.checked,
                                })
                              }
                              className="mt-1 h-4 w-4 accent-accent shrink-0"
                              aria-label="Include in commit"
                            />
                            <div
                              className={`flex-1 min-w-0 space-y-2 ${
                                row.enabled ? "" : "opacity-40"
                              }`}
                            >
                              <textarea
                                value={row.title}
                                onChange={(e) =>
                                  updateRow(key, { title: e.target.value })
                                }
                                rows={2}
                                className="w-full bg-transparent border-b border-rule-soft focus:border-ink text-sm text-ink resize-none focus:outline-none"
                              />
                              <div className="flex flex-wrap gap-2 items-center">
                                <input
                                  type="date"
                                  value={row.due_date ?? ""}
                                  onChange={(e) =>
                                    updateRow(key, {
                                      due_date: e.target.value || null,
                                    })
                                  }
                                  className="bg-paper border border-rule px-2 py-1 text-xs text-ink focus:outline-none focus:border-ink"
                                  aria-label="Due date"
                                />
                                {!row.due_date && row.suggested_due_date && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      updateRow(key, {
                                        due_date: row.suggested_due_date,
                                      })
                                    }
                                    title={
                                      row.suggested_due_date_reason ??
                                      "AI suggestion"
                                    }
                                    className="text-xs px-2 py-1 border border-accent/40 bg-accent/5 text-accent hover:bg-accent hover:text-paper transition-colors"
                                  >
                                    ✨ use {row.suggested_due_date}
                                  </button>
                                )}
                                <select
                                  value={row.sub_id ?? ""}
                                  onChange={(e) => {
                                    const sid = e.target.value || null;
                                    const sname = sid
                                      ? subs.find((s) => s.id === sid)
                                          ?.name ?? null
                                      : null;
                                    updateRow(key, {
                                      sub_id: sid,
                                      sub_name: sname,
                                    });
                                  }}
                                  className="bg-paper border border-rule px-2 py-1 text-xs text-ink focus:outline-none focus:border-ink flex-1 min-w-[120px]"
                                  aria-label="Sub"
                                >
                                  <option value="">— no sub —</option>
                                  {subs.map((s) => (
                                    <option key={s.id} value={s.id}>
                                      {s.name}
                                    </option>
                                  ))}
                                </select>
                                {!row.sub_id && row.sub_name && (
                                  <span className="font-mono text-[10px] text-ink-3">
                                    extractor said: {row.sub_name}
                                  </span>
                                )}
                                <select
                                  value={row.category ?? ""}
                                  onChange={(e) =>
                                    updateRow(key, {
                                      category: e.target.value || "",
                                    })
                                  }
                                  className={`border border-rule px-2 py-1 text-xs focus:outline-none focus:border-ink font-mono tracking-[0.12em] ${styleFor(row.category)}`}
                                  aria-label="Category"
                                  title={
                                    row.category
                                      ? `AI picked ${row.category} — change if needed`
                                      : "Pick a category"
                                  }
                                >
                                  <option value="">— category —</option>
                                  {CATEGORIES.map((c) => (
                                    <option key={c} value={c}>
                                      {c}
                                    </option>
                                  ))}
                                </select>
                              </div>
                              {row.source_excerpt && (
                                <p className="pt-1 font-mono text-[10px] text-ink-3 italic leading-snug">
                                  “{row.source_excerpt}”
                                </p>
                              )}
                            </div>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </section>
          );
        })}

        {/* Raw API output — collapsible */}
        <details className="mb-6 border border-rule bg-paper">
          <summary className="cursor-pointer px-4 py-2 font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink">
            View raw extractor output (JSON)
          </summary>
          <pre className="px-4 py-3 text-[11px] leading-snug text-ink-2 overflow-x-auto bg-sand-2/30 font-mono whitespace-pre-wrap break-words max-h-96 overflow-y-auto">
            {JSON.stringify(extract, null, 2)}
          </pre>
        </details>

        {error && (
          <p className="mb-4 text-sm text-urgent">{error}</p>
        )}

        <div className="flex items-center justify-between gap-4 sticky bottom-0 bg-background border-t border-rule -mx-5 px-5 py-4">
          <button
            type="button"
            onClick={() => setStep("upload")}
            className="text-xs tracking-[0.18em] uppercase text-ink-2 hover:text-ink"
            disabled={saving}
          >
            Back
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving || totalEnabled === 0}
            className="bg-success text-paper px-5 py-2.5 text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity shadow-sm"
          >
            {saving
              ? "Pushing…"
              : `Push ${totalEnabled} to to-do list →`}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-5 lg:px-10 py-8 space-y-5">
      {/* Meta */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            PM
          </label>
          <select
            value={pmId}
            onChange={(e) => setPmId(e.target.value)}
            className="w-full bg-paper border border-rule px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-ink"
          >
            {pms.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Job
          </label>
          <select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="w-full bg-paper border border-rule px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-ink"
          >
            <option value="">— (let extractor decide) —</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Meeting date
          </label>
          <input
            type="date"
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
            className="w-full bg-paper border border-rule px-3 py-2.5 text-sm text-ink focus:outline-none focus:border-ink"
          />
        </div>
        <div>
          <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
            Type
          </label>
          <div className="flex gap-2">
            {(["SITE", "OFFICE"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setMeetingType(t)}
                className={
                  "flex-1 px-3 py-2.5 text-sm font-medium border transition-colors " +
                  (meetingType === t
                    ? "bg-ink text-paper border-ink"
                    : "bg-paper text-ink border-rule hover:border-ink")
                }
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {autoDetected && (
        <p className="font-mono text-[10px] tracking-[0.18em] uppercase text-success/80">
          Auto-filled · {autoDetected}
        </p>
      )}

      {/* Drop zone */}
      <div>
        <label className="block font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3 mb-1.5">
          Transcript File
        </label>
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) onFile(file);
          }}
          onClick={() => fileRef.current?.click()}
          className={
            "border-2 border-dashed cursor-pointer px-6 py-10 text-center transition-colors " +
            (isDragging
              ? "border-accent bg-accent/5"
              : "border-rule hover:border-ink bg-paper")
          }
        >
          {filename ? (
            <>
              <p className="font-mono text-[13px] text-ink">{filename}</p>
              <p className="mt-1 font-mono text-[11px] text-ink-3 tabular-nums">
                {(transcript.length / 1024).toFixed(1)} KB · click to replace
              </p>
            </>
          ) : (
            <>
              <p className="text-[15px] text-ink-2">
                Drag a Plaud .txt here, or click to pick a file
              </p>
              <p className="mt-1 font-mono text-[11px] text-ink-3">
                .txt only · max ~1 MB
              </p>
            </>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".txt,text/plain"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onFile(file);
            }}
          />
        </div>
      </div>

      {error && <p className="text-[13px] text-urgent">{error}</p>}

      <div className="flex items-center justify-end gap-4">
        <button
          type="button"
          onClick={process}
          disabled={!transcript || !pmId || processing}
          className="bg-ink text-paper px-6 py-3 text-[13px] tracking-[0.15em] uppercase font-medium hover:bg-accent disabled:opacity-50 transition-colors"
        >
          {processing ? "Extracting..." : "Extract Action Items"}
        </button>
      </div>
      {processing && (
        <p className="text-[13px] text-ink-2 text-center">
          Calling Claude · this can take 20–40 seconds for a long meeting...
        </p>
      )}
    </div>
  );
}
