// /import — unified import surface.
// Two sections: Transcripts (Plaud .txt) + Daily logs (BT scraper .json).
// Each daily-log JSON contains a full week (or more) of entries, indexed by
// job. One drop = whole week.

import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { PM } from "@/lib/types";
import { Header } from "@/components/header";
import { TranscriptImportModal } from "@/components/transcript-import-modal";
import { BtSyncButton } from "@/components/bt-sync-button";
import { BtPoSyncButton } from "@/components/bt-po-sync-button";
import { BtCoSyncButton } from "@/components/bt-co-sync-button";
import { BtImportAllButton } from "@/components/bt-import-all-button";
import { BtCloudSyncButton } from "@/components/bt-cloud-sync-button";
import { DailyLogUploadForm } from "../v2/daily-logs/upload/upload-form";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const supabase = supabaseServer();
  const [pmsRes, jobsRes, assignRes, subsRes, txRes, dlRes, poRes, coRes, syncRunRes] = await Promise.all([
    supabase
      .from("pms")
      .select("id, full_name, active")
      .eq("active", true)
      .order("full_name"),
    supabase.from("jobs").select("id, name").order("name"),
    supabase
      .from("job_pm_assignments")
      .select("job_id, pm_id")
      .is("ended_at", null),
    supabase.from("subs").select("id, name, trade").eq("hidden", false).order("name"),
    // Transcript import history — pull job too (it's a free-text job name on
    // the todo row, not a FK) so we can render a per-job breakdown for each
    // transcript (which jobs got todos out of it).
    supabase
      .from("todos")
      .select("source_transcript, created_at, job")
      .not("source_transcript", "is", null)
      .order("created_at", { ascending: false })
      .limit(2000),
    // Daily-log recency + total — enriched_at ≈ when last pulled/imported.
    supabase
      .from("daily_logs")
      .select("enriched_at", { count: "exact" })
      .order("enriched_at", { ascending: false, nullsFirst: false })
      .limit(1),
    // Purchase-order pull recency + total — scraped_at is set on every upload.
    supabase
      .from("purchase_orders")
      .select("scraped_at", { count: "exact" })
      .order("scraped_at", { ascending: false, nullsFirst: false })
      .limit(1),
    // Change-order pull recency + total — same shape as POs.
    supabase
      .from("change_orders")
      .select("scraped_at", { count: "exact" })
      .order("scraped_at", { ascending: false, nullsFirst: false })
      .limit(1),
    // Authoritative "last synced" — one row per full BT sync run (manual or the
    // every-12h scheduled job). Independent of whether any record's date moved.
    supabase
      .from("sync_runs")
      .select("kind, finished_at, ok, daily_logs, po_count, co_count")
      .not("finished_at", "is", null)
      .order("finished_at", { ascending: false })
      .limit(10),
  ]);
  const pms = (pmsRes.data ?? []) as PM[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const subs = (subsRes.data ?? []) as { id: string; name: string }[];

  // Group todos by source file into a transcript-import history; the same set
  // (name + date) is handed to the form so it can flag a re-upload. Also
  // tracks per-job breakdown (jobName -> count of todos created for it)
  // so we can show "what transcripts hit what jobs" in the expanded view.
  const txTodos = (txRes.data ?? []) as {
    source_transcript: string | null;
    created_at: string;
    job: string | null;
  }[];
  interface TxImport {
    name: string;
    date: string;
    count: number;
    byJob: Map<string, number>;
  }
  const importMap = new Map<string, TxImport>();
  for (const t of txTodos) {
    const name = t.source_transcript;
    if (!name || name === "cockpit-import") continue;
    const date = (t.created_at ?? "").slice(0, 10);
    let ex = importMap.get(name);
    if (!ex) {
      ex = { name, date, count: 0, byJob: new Map() };
      importMap.set(name, ex);
    }
    ex.count += 1;
    const jobLabel = t.job?.trim() || "(no job)";
    ex.byJob.set(jobLabel, (ex.byJob.get(jobLabel) ?? 0) + 1);
  }
  const transcriptImports = Array.from(importMap.values()).sort((a, b) =>
    b.date.localeCompare(a.date)
  );
  const priorImports = transcriptImports.map((i) => ({ name: i.name, date: i.date }));
  const dlRows = (dlRes.data ?? []) as { enriched_at: string | null }[];
  const dailyCount = dlRes.count ?? null;
  const lastDailyImport = dlRows[0]?.enriched_at
    ? dlRows[0].enriched_at.slice(0, 10)
    : null;
  const poRows = (poRes.data ?? []) as { scraped_at: string | null }[];
  const poCount = poRes.count ?? null;
  const lastPoPull = poRows[0]?.scraped_at ? poRows[0].scraped_at.slice(0, 10) : null;
  const coRows = (coRes.data ?? []) as { scraped_at: string | null }[];
  const coCount = coRes.count ?? null;
  const lastCoPull = coRows[0]?.scraped_at ? coRows[0].scraped_at.slice(0, 10) : null;
  const syncRuns = (syncRunRes?.data ?? []) as {
    kind: string;
    finished_at: string;
    ok: boolean | null;
    daily_logs: number | null;
    po_count: number | null;
    co_count: number | null;
  }[];
  const lastSync = syncRuns[0] ?? null;

  return (
    <main className="max-w-[560px] mx-auto min-h-screen bg-background pb-24">
      <Header />

      {/* Page hero — clear what this page is for */}
      <div className="px-5 pt-10 pb-2">
        <h1 className="font-head text-[32px] leading-none tracking-tight text-foreground">
          Import
        </h1>
        <p className="mt-3 text-ink-2 text-[15px] leading-relaxed">
          This is where new information comes into the cockpit — meeting
          notes from Plaud, daily logs and financials from Buildertrend.
          Everything you drop here ends up on the job pages, the meeting
          agenda, and the subs profiles.
        </p>
        {process.env.VERCEL === "1" && (
          <div className="mt-5 border border-accent/40 bg-accent/5 px-4 py-3 text-sm text-ink-2 leading-relaxed">
            <strong className="block font-mono text-[10px] tracking-[0.18em] uppercase text-accent mb-1">
              Heads up — you&apos;re on the deployed site
            </strong>
            The Buildertrend pull buttons below only work from your laptop
            (they need to run a Python script that can&apos;t live on
            Vercel). To actually pull, open the cockpit on your own
            machine: <code className="font-mono text-[12px]">npm run dev</code>
            {" "}in <code className="font-mono text-[12px]">production-cockpit/</code>
            {" "}then go to <code className="font-mono text-[12px]">localhost:3000/import</code>.
            Clicking the buttons here will pop a &ldquo;requires local
            environment&rdquo; error.
          </div>
        )}
      </div>

      {/* SECTION 1 — Status check at the top */}
      <Section
        eyebrow="At a glance"
        title="When did we last sync?"
        description={
          <>Quick health check. Each row shows when this source was last
          pulled and how many records are currently in the system. If a
          number looks stale, scroll down and pull again.</>
        }
      >
        <div className="border border-rule bg-paper p-5 space-y-2.5 text-sm">
          {lastSync ? (
            <div
              className={`-mx-5 -mt-5 mb-2 px-5 py-3 border-b border-rule ${
                lastSync.ok === false ? "bg-urgent/5" : "bg-accent/5"
              }`}
            >
              <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
                Last full Buildertrend sync
              </div>
              <div className="mt-1 text-foreground">
                <span className="font-medium">{agoLabel(lastSync.finished_at)}</span>
                <span className="text-ink-3">
                  {" · "}
                  {lastSync.kind === "auto" ? "auto · every 12h" : "manual"}
                  {lastSync.ok === false ? " · ⚠ had errors" : ""}
                </span>
              </div>
              <div className="mt-0.5 text-ink-3 text-xs">
                {prettyDate(lastSync.finished_at)} · {lastSync.daily_logs ?? 0} logs ·{" "}
                {lastSync.po_count ?? 0} POs · {lastSync.co_count ?? 0} COs
              </div>
            </div>
          ) : (
            <div className="-mx-5 -mt-5 mb-2 px-5 py-3 border-b border-rule bg-sand-2/40">
              <div className="font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3">
                Last full Buildertrend sync
              </div>
              <div className="mt-1 text-ink-3">
                No full sync recorded yet — runs automatically every 12h, or hit
                the button below.
              </div>
            </div>
          )}
          <HistoryRow label="Purchase orders" when={lastPoPull} count={poCount} unit="POs" />
          <HistoryRow label="Change orders" when={lastCoPull} count={coCount} unit="COs" />
          <HistoryRow label="Daily logs" when={lastDailyImport} count={dailyCount} unit="logs" />
          <HistoryRow
            label="Transcripts"
            when={transcriptImports[0]?.date ?? null}
            count={transcriptImports.length || null}
            unit="files"
          />
          {syncRuns.length > 0 && (
            <details className="!mt-3 border-t border-rule pt-2">
              <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-1">
                Sync history · {syncRuns.length}
              </summary>
              <ul className="mt-2 divide-y divide-rule">
                {syncRuns.map((s, i) => (
                  <li
                    key={i}
                    className="flex items-baseline justify-between gap-3 py-1.5"
                  >
                    <span className="flex items-center gap-2">
                      <span className={s.ok === false ? "text-urgent" : "text-success"}>
                        {s.ok === false ? "✗" : "✓"}
                      </span>
                      <span className="text-ink-2">{agoLabel(s.finished_at)}</span>
                      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                        {s.kind === "auto" ? "auto" : "manual"}
                      </span>
                    </span>
                    <span className="font-mono text-[10px] tabular-nums text-ink-3">
                      {s.daily_logs ?? 0} logs · {s.po_count ?? 0} POs ·{" "}
                      {s.co_count ?? 0} COs
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </Section>

      {/* SECTION 2 — Transcript */}
      <Section
        eyebrow="Meeting transcripts"
        title="Drop a Plaud recording"
        description={
          <>
            Upload the <code className="font-mono text-[12px]">.txt</code> file
            from your Plaud recorder. Claude reads through it and pulls out
            the action items — who said they&apos;d do what, by when. They land
            in the to-do list on the right job. The PM, job name, date, and
            meeting type are auto-detected from the filename.
          </>
        }
        howItWorks={
          <>
            <p className="mb-2">
              The text is sent to Claude with a strict schema (tool-use), so
              the output is always structured action items — no risk of
              malformed JSON. Filename pattern:{" "}
              <code className="font-mono text-[11px]">
                MM-DD &lt;Job&gt; &lt;Site|Office|Other&gt; Production Meeting-transcript.txt
              </code>
              .
            </p>
            <p>
              For the newer review-queue flow (proposed changes before they
              hit todos),{" "}
              <Link href="/v2/upload" className="text-accent hover:underline">
                use /v2/upload
              </Link>{" "}
              instead.
            </p>
          </>
        }
      >
        <TranscriptImportModal
          pms={pms}
          jobs={jobs}
          assignments={assignments}
          subs={subs}
          priorImports={priorImports}
        />
        {transcriptImports.length > 0 && (
          <details className="mt-5">
            <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-2">
              Transcript history · {transcriptImports.length}
            </summary>
            <ul className="mt-2 border border-rule bg-paper divide-y divide-rule">
              {transcriptImports.slice(0, 50).map((imp) => {
                const meetingDate = extractMeetingDate(imp.name);
                const jobsList = Array.from(imp.byJob.entries()).sort(
                  (a, b) => b[1] - a[1],
                );
                return (
                  <li key={imp.name} className="px-4 py-3 space-y-1.5">
                    <div className="flex items-baseline justify-between gap-3">
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-ink-2 text-sm font-medium">
                          {prettyImport(imp.name)}
                        </span>
                        <span className="block truncate font-mono text-[10px] text-ink-3 mt-0.5">
                          {imp.name}
                        </span>
                      </span>
                      <span className="shrink-0 text-right font-mono text-[10px] tabular-nums text-ink-3 leading-tight">
                        <span className="block">
                          imported {prettyDate(imp.date)}
                        </span>
                        {meetingDate && (
                          <span className="block text-accent">
                            meeting {meetingDate}
                          </span>
                        )}
                        <span className="block mt-0.5">
                          {imp.count} item{imp.count === 1 ? "" : "s"}
                        </span>
                      </span>
                    </div>
                    {/* Per-job breakdown — proves what jobs got todos out of
                        this transcript. */}
                    <ul className="flex flex-wrap gap-1.5 pt-1">
                      {jobsList.map(([jobLabel, count]) => (
                        <li
                          key={jobLabel}
                          className="inline-flex items-baseline gap-1 border border-rule bg-sand-2/30 px-2 py-0.5 text-[11px] text-ink-2"
                        >
                          <span>{jobLabel}</span>
                          <span className="font-mono text-[9px] tabular-nums text-ink-3">
                            {count}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </Section>

      {/* SECTION 3 — Unified Buildertrend pull (daily logs + POs + COs) */}
      <Section
        eyebrow="Buildertrend"
        title="Import everything from BT in one click"
        description={
          <>
            Logs into Buildertrend once and pulls daily logs (+ on-site photos),
            every PO with line items, and every change order — for{" "}
            <em>every active job</em>. New jobs (like a freshly-added{" "}
            <code className="font-mono text-[11px]">Clark</code>) are auto-detected
            from BT&apos;s job picker; nothing in the cockpit needs to be edited
            per job.
          </>
        }
        howItWorks={
          <>
            <p className="mb-2">
              Spawns a Python + Playwright scraper on your laptop that hits
              BT&apos;s JSON API directly. Credentials live in the child process
              env only (never persisted, never logged). The modal streams live
              per-step progress: daily logs → POs → COs. Manually-edited columns
              in any table are preserved on re-pull
              (<code className="font-mono text-[11px]">manually_edited_fields</code>).
            </p>
            <p className="mb-2">
              <strong>Note on the headed window:</strong> If you tick
              &ldquo;Show browser window&rdquo; you&apos;ll see the Playwright
              tab navigate to each BT page (DailyLogs → PurchaseOrders →
              ChangeOrders), but the page won&apos;t visibly scroll or copy
              text. That&apos;s by design — the data comes from JSON API
              calls running in the background, not from screen-scraping. The
              modal&apos;s 3-step progress UI is the real source of truth: a
              spinning circle while a step runs, a green ✓ when records
              upserted to Supabase, a red ✕ on failure.
            </p>
            <p>
              First-time login? Tick &ldquo;Show browser window&rdquo; so you
              can complete MFA. The session sticks for ~2 weeks after that.
              First full run takes ~10 min; subsequent runs are ~1–3 min
              thanks to incremental fetching (daily logs from
              <code className="font-mono text-[11px]"> max(date) − 2</code>,
              PO line items skipped for IDs already in the DB).
            </p>
          </>
        }
        bottomGap
      >
        <BtCloudSyncButton />

        {/* Advanced — local-only pulls that run the scraper on THIS computer
            (need the laptop + `npm run dev`). The cloud button above is what
            works from any device. */}
        <details className="mt-6">
          <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-2">
            Advanced — run a pull from this computer (local only)
          </summary>
          <div className="mt-3 space-y-4 border-l-2 border-rule pl-4">
            <p className="text-sm text-ink-3 leading-relaxed">
              These run the scraper on the machine you&apos;re on (they need the
              laptop with <code className="font-mono text-[11px]">npm run dev</code>).
              The one-click below pulls everything; the three after it retry a
              single source.
            </p>
            <BtImportAllButton />
            <div className="flex flex-wrap gap-3">
              <BtSyncButton />
              <BtPoSyncButton />
              <BtCoSyncButton />
            </div>
            <details className="mt-2">
              <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-2">
                Already have a scraper JSON? Upload it manually
              </summary>
              <div className="mt-3 text-sm text-ink-3 leading-relaxed">
                <p className="mb-4">
                  If you ran the BT scraper outside the cockpit, drop the
                  resulting{" "}
                  <code className="font-mono text-[11px]">daily-logs.json</code>{" "}
                  here. Same upsert logic as the one-click button. Powers the
                  no-show metric on{" "}
                  <Link href="/subs" className="text-accent hover:underline">
                    /subs
                  </Link>
                  .
                </p>
                <DailyLogUploadForm />
              </div>
            </details>
          </div>
        </details>
      </Section>
    </main>
  );
}

// Reusable section shell — eyebrow tag, big readable heading, plain-English
// description, optional "How it works" expander, then the section's content.
// Keeps every section on /import looking the same so the page reads as a
// short list of distinct tasks, not a wall.
function Section({
  eyebrow,
  title,
  description,
  howItWorks,
  bottomGap,
  children,
}: {
  eyebrow: string;
  title: React.ReactNode;
  description: React.ReactNode;
  howItWorks?: React.ReactNode;
  bottomGap?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className={`px-5 pt-12 ${bottomGap ? "pb-12" : ""}`}>
      <div className="border-t border-rule pt-8">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-accent">
          {eyebrow}
        </p>
        <h2 className="mt-2 font-head text-[22px] leading-tight tracking-tight text-foreground">
          {title}
        </h2>
        <p className="mt-3 text-ink-2 text-sm leading-relaxed">{description}</p>
        {howItWorks && (
          <details className="mt-3">
            <summary className="cursor-pointer inline-flex items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 hover:text-ink py-1.5">
              <span aria-hidden>ⓘ</span> How it works
            </summary>
            <div className="mt-2 text-ink-3 text-sm leading-relaxed border-l-2 border-rule pl-3">
              {howItWorks}
            </div>
          </details>
        )}
        <div className="mt-6">{children}</div>
      </div>
    </section>
  );
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

// One readable date format everywhere in the history: "2026-05-18" → "May 18".
// Relative "X ago" for an exact instant (sync finished_at). Timezone-agnostic
// (it's a duration), so it reads correctly regardless of server/viewer TZ.
function agoLabel(iso: string | null): string {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "unknown";
  if (ms < 0) return "just now";
  const mins = Math.round(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

function prettyDate(iso: string | null): string {
  if (!iso) return "—";
  // Accept both "YYYY-MM-DD" and full ISO timestamps: take the date part and
  // read it in UTC so the label is tz-stable and never "Invalid Date".
  const d = new Date(iso.slice(0, 10) + "T00:00:00Z");
  if (Number.isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}`;
}

// Pull a "Mon DD" meeting date out of the transcript filename, if it starts
// with MM-DD (or MM/DD). Returns null when nothing parses.
//   "05-18 Krauss Site Production Meeting-transcript.txt" -> "May 18"
function extractMeetingDate(name: string): string | null {
  const m = name.match(/^\s*(\d{1,2})[-_/](\d{1,2})\b/);
  if (!m) return null;
  const month = parseInt(m[1], 10);
  const day = parseInt(m[2], 10);
  if (!month || !day || month < 1 || month > 12 || day < 1 || day > 31) return null;
  return `${MONTHS[month - 1]} ${day}`;
}

// Normalize a transcript filename into one consistent, easy-to-read label so
// every history row looks the same regardless of how the file was named:
//   "05-18 Krauss Site Production Meeting-transcript.txt" → "Krauss · Site meeting"
function prettyImport(name: string): string {
  const base = name
    .replace(/\.(txt|md)$/i, "")
    .replace(/-?transcript$/i, "")
    .trim();
  const typeMatch = base.match(/\b(site|office|other)\b/i);
  const type = typeMatch ? typeMatch[1].toLowerCase() : "";
  const job = base
    .replace(/^\d{1,2}[-_/]\d{1,2}\s*/, "")
    .replace(/\b(site|office|other)\b/i, "")
    .replace(/production\s*meeting/i, "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  if (!job) return base || name;
  const typeLabel = type ? type.charAt(0).toUpperCase() + type.slice(1) : "";
  return typeLabel ? `${job} · ${typeLabel} meeting` : `${job} · Meeting`;
}

function HistoryRow({
  label,
  when,
  count,
  unit,
}: {
  label: string;
  when: string | null;
  count: number | null;
  unit: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-2">{label}</span>
      <span className="font-mono text-xs tabular-nums text-ink-3">
        {when ? `last ${prettyDate(when)}` : "never"}
        {count != null ? ` · ${count} ${unit}` : ""}
      </span>
    </div>
  );
}
