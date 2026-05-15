"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function UploadForm({
  jobs,
  pms,
  assignments,
}: {
  jobs: { id: string; name: string }[];
  pms: { id: string; full_name: string }[];
  assignments: { job_id: string; pm_id: string }[];
}) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [jobId, setJobId] = useState(jobs[0]?.id ?? "");
  const [meetingType, setMeetingType] = useState<"site" | "office" | "spontaneous">("site");
  const [meetingDate, setMeetingDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [pmId, setPmId] = useState(() => {
    const a = assignments.find((x) => x.job_id === jobs[0]?.id);
    return a?.pm_id ?? pms[0]?.id ?? "";
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function onJobChange(newJobId: string) {
    setJobId(newJobId);
    const a = assignments.find((x) => x.job_id === newJobId);
    if (a) setPmId(a.pm_id);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) {
      setError("Please pick a file.");
      return;
    }
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const text = await file.text();
      const resp = await fetch("/v2/api/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          text,
          job_id: jobId,
          meeting_type: meetingType,
          meeting_date: meetingDate,
          pm_id: pmId,
        }),
      });
      const body = (await resp.json()) as {
        ok?: boolean;
        meeting_id?: string;
        ingestion_event_id?: string | null;
        duplicate_of?: string;
        error?: string;
      };
      if (!resp.ok) throw new Error(body.error ?? `HTTP ${resp.status}`);
      if (body.duplicate_of) {
        setSuccess(`Already ingested. Existing meeting id: ${body.duplicate_of}.`);
      } else if (body.ingestion_event_id) {
        router.push(`/v2/review/${body.ingestion_event_id}`);
      } else {
        setSuccess(
          `Upload received. Meeting id: ${body.meeting_id}. Pipeline processing is offline for v1 — run scripts/run_gate_1e_reconcile.py to produce proposals.`,
        );
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-5">
      <label className="block">
        <span className="text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">File</span>
        <input
          type="file"
          accept=".txt,.md,.json"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          className="mt-1 block w-full text-sm border border-rule px-3 py-3 min-h-[44px] bg-paper"
        />
      </label>

      <label className="block">
        <span className="text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">Job</span>
        <select
          value={jobId}
          onChange={(e) => onJobChange(e.target.value)}
          className="mt-1 block w-full text-sm border border-rule px-3 py-3 min-h-[44px] bg-paper"
        >
          {jobs.map((j) => (
            <option key={j.id} value={j.id}>
              {j.name}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="block">
        <legend className="text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">Meeting type</legend>
        <div className="mt-1 flex gap-4 flex-wrap">
          {(["site", "office", "spontaneous"] as const).map((t) => (
            <label key={t} className="flex items-center gap-2 min-h-[44px]">
              <input
                type="radio"
                name="meeting_type"
                value={t}
                checked={meetingType === t}
                onChange={() => setMeetingType(t)}
              />
              <span className="text-foreground text-sm">{t}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <label className="block">
        <span className="text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">Meeting date</span>
        <input
          type="date"
          value={meetingDate}
          onChange={(e) => setMeetingDate(e.target.value)}
          className="mt-1 block w-full text-sm border border-rule px-3 py-3 min-h-[44px] bg-paper font-mono"
        />
      </label>

      <label className="block">
        <span className="text-ink-3 text-xs font-mono uppercase tracking-[0.06em]">PM</span>
        <select
          value={pmId}
          onChange={(e) => setPmId(e.target.value)}
          className="mt-1 block w-full text-sm border border-rule px-3 py-3 min-h-[44px] bg-paper"
        >
          {pms.map((p) => (
            <option key={p.id} value={p.id}>
              {p.full_name}
            </option>
          ))}
        </select>
      </label>

      <button
        type="submit"
        disabled={busy || !file}
        className="px-5 py-3 min-h-[44px] bg-ink text-paper font-medium text-sm uppercase tracking-[0.06em] hover:bg-ink-2 disabled:opacity-50 transition-colors"
      >
        {busy ? "Uploading…" : "Process and route to review"}
      </button>

      {error && <p className="mt-3 text-urgent text-xs">{error}</p>}
      {success && <p className="mt-3 text-success text-xs">{success}</p>}
    </form>
  );
}
