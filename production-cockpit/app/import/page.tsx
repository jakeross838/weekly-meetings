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
import { DailyLogUploadForm } from "../v2/daily-logs/upload/upload-form";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const supabase = supabaseServer();
  const [pmsRes, jobsRes, assignRes, subsRes, txRes, dlRes, poRes, coRes] = await Promise.all([
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
    supabase.from("subs").select("id, name").eq("hidden", false).order("name"),
    // Transcript import history (derived from todos.source_transcript).
    supabase
      .from("todos")
      .select("source_transcript, created_at")
      .not("source_transcript", "is", null)
      .order("created_at", { ascending: false })
      .limit(1000),
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
  ]);
  const pms = (pmsRes.data ?? []) as PM[];
  const jobs = (jobsRes.data ?? []) as { id: string; name: string }[];
  const assignments = (assignRes.data ?? []) as {
    job_id: string;
    pm_id: string;
  }[];
  const subs = (subsRes.data ?? []) as { id: string; name: string }[];

  // Group todos by source file into a transcript-import history; the same set
  // (name + date) is handed to the form so it can flag a re-upload.
  const txTodos = (txRes.data ?? []) as {
    source_transcript: string | null;
    created_at: string;
  }[];
  const importMap = new Map<string, { name: string; date: string; count: number }>();
  for (const t of txTodos) {
    const name = t.source_transcript;
    if (!name || name === "cockpit-import") continue;
    const date = (t.created_at ?? "").slice(0, 10);
    const ex = importMap.get(name);
    if (ex) ex.count += 1;
    else importMap.set(name, { name, date, count: 1 });
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
          <HistoryRow label="Purchase orders" when={lastPoPull} count={poCount} unit="POs" />
          <HistoryRow label="Change orders" when={lastCoPull} count={coCount} unit="COs" />
          <HistoryRow label="Daily logs" when={lastDailyImport} count={dailyCount} unit="logs" />
          <HistoryRow
            label="Transcripts"
            when={transcriptImports[0]?.date ?? null}
            count={transcriptImports.length || null}
            unit="files"
          />
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
              {transcriptImports.slice(0, 20).map((imp) => (
                <li
                  key={imp.name}
                  className="flex items-baseline justify-between gap-3 px-4 py-2.5"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-ink-2 text-sm">
                      {prettyImport(imp.name)}
                    </span>
                    <span className="block truncate font-mono text-[10px] text-ink-3 mt-0.5">
                      {imp.name}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink-3">
                    {prettyDate(imp.date)} · {imp.count} item{imp.count === 1 ? "" : "s"}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}
      </Section>

      {/* SECTION 3 — Daily logs */}
      <Section
        eyebrow="Buildertrend daily logs"
        title="Pull this week&rsquo;s field activity"
        description={
          <>
            One click logs into Buildertrend, downloads every daily log + on-site
            photos from the past two weeks, and writes it all to the cockpit.
            Claude then looks at the photos and writes a short summary of what
            was happening on site. After it&apos;s done you&apos;ll see fresh
            crew counts, weather, photo summaries, and a refreshed timeline on
            every job page.
          </>
        }
        howItWorks={
          <>
            <p className="mb-2">
              The button spawns a Python + Playwright scraper on your laptop
              that hits BT&apos;s JSON API directly. Credentials are passed via
              env vars and never persisted in the browser. The scraper output
              upserts into <code className="font-mono text-[11px]">daily_logs</code>;
              manually-edited fields are preserved on re-pull.
            </p>
            <p>
              First-time login? Tick &ldquo;show browser&rdquo; in the modal
              so you can complete the MFA prompt. The session sticks for ~2
              weeks after that.
            </p>
          </>
        }
      >
        <BtSyncButton />
        <details className="mt-5">
          <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 hover:text-ink py-2">
            Already have a scraper JSON? Upload it manually
          </summary>
          <div className="mt-3 text-sm text-ink-3 leading-relaxed">
            <p className="mb-4">
              If you ran the BT scraper outside the cockpit, drop the resulting{" "}
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
      </Section>

      {/* SECTION 4 — POs + COs */}
      <Section
        eyebrow="Buildertrend financials"
        title="Pull purchase orders &amp; change orders"
        description={
          <>
            Refresh the accounting view: every PO (committed cost, what&apos;s
            been paid, what&apos;s still open) and every change order. After
            it lands you&apos;ll see updated cost-breakdown bars on each pay
            app and a fresh portfolio rollup at the top of the home page.
          </>
        }
        howItWorks={
          <>
            <p className="mb-2">
              The grid pull is fast (~30s for ~1,200 POs across the whole
              portfolio). Tick &ldquo;include line items&rdquo; for the
              detailed breakdown per PO, but pair it with a job filter — it
              hits one request per PO and can take 10–30 minutes across the
              whole portfolio.
            </p>
            <p>
              Edits you make in the PO ledger survive future pulls — every
              column you touch is added to{" "}
              <code className="font-mono text-[11px]">manually_edited_fields</code>{" "}
              and the upserter skips it on the next sync.
            </p>
          </>
        }
        bottomGap
      >
        <div className="flex flex-wrap gap-3">
          <BtPoSyncButton />
          <BtCoSyncButton />
        </div>
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
function prettyDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  if (Number.isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getMonth()]} ${d.getDate()}`;
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
