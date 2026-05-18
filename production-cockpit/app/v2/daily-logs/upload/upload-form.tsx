"use client";

import { useRef, useState } from "react";

type UploadResult = {
  ok: true;
  inserted: number;
  skipped: number;
  per_job: Record<string, { total: number; inserted: number; skipped: number }>;
};

type ExtractResult = {
  ok: true;
  considered: number;
  processed: number;
  failed: number;
  results: Array<{
    log_id: string;
    job_key: string;
    log_date: string | null;
    ok: boolean;
    photoCount: number;
    error?: string;
  }>;
};

export function DailyLogUploadForm() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [filename, setFilename] = useState("");
  const [bytes, setBytes] = useState(0);
  const [parsed, setParsed] = useState<unknown>(null);
  const [jobCount, setJobCount] = useState(0);
  const [recordCount, setRecordCount] = useState(0);
  const [isDragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [extract, setExtract] = useState<ExtractResult | null>(null);

  function onFile(file: File) {
    setError(null);
    setResult(null);
    setParsed(null);
    if (!file.name.toLowerCase().endsWith(".json")) {
      setError("Pick a .json file");
      return;
    }
    setFilename(file.name);
    setBytes(file.size);
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const text = String(reader.result || "");
        const json = JSON.parse(text) as {
          byJob?: Record<string, unknown[]>;
        };
        if (!json.byJob || typeof json.byJob !== "object") {
          setError("File missing top-level `byJob` object");
          return;
        }
        const jobs = Object.keys(json.byJob);
        const records = jobs.reduce(
          (n, k) =>
            n + (Array.isArray(json.byJob![k]) ? json.byJob![k]!.length : 0),
          0
        );
        setJobCount(jobs.length);
        setRecordCount(records);
        setParsed(json);
      } catch (e) {
        setError(`Could not parse JSON: ${(e as Error).message}`);
      }
    };
    reader.onerror = () => setError("Could not read file");
    reader.readAsText(file);
  }

  function PhotoExtractTrigger() {
    const [busy2, setBusy2] = useState(false);
    const [err2, setErr2] = useState<string | null>(null);
    async function extractPhotos() {
      setBusy2(true);
      setErr2(null);
      try {
        const resp = await fetch("/v2/api/daily-logs/extract-photos", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ limit: 10 }),
        });
        const data = (await resp.json()) as ExtractResult | { error: string };
        if (!resp.ok || !("ok" in data)) {
          setErr2(
            "error" in data ? data.error : `HTTP ${resp.status}`
          );
          setBusy2(false);
          return;
        }
        setExtract(data);
        setBusy2(false);
      } catch (e) {
        setErr2((e as Error).message);
        setBusy2(false);
      }
    }
    if (extract) {
      const failedRows = extract.results.filter((r) => !r.ok);
      return (
        <div className="mt-2 space-y-2">
          <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success/80">
            Photo extract · {extract.processed} processed
            {extract.failed > 0 && (
              <span className="text-urgent">
                {" "}
                · {extract.failed} failed
              </span>
            )}
          </p>
          {failedRows.length > 0 && (
            <details>
              <summary className="cursor-pointer font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
                show {failedRows.length} failure
                {failedRows.length === 1 ? "" : "s"}
              </summary>
              <ul className="mt-1 space-y-1">
                {failedRows.map((r) => (
                  <li
                    key={r.log_id}
                    className="font-mono text-[11px] text-urgent/90"
                  >
                    {r.job_key} {r.log_date ?? ""}: {r.error}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      );
    }
    return (
      <div className="mt-2">
        <button
          type="button"
          onClick={extractPhotos}
          disabled={busy2}
          className="text-xs px-3 py-1.5 border border-accent text-accent hover:bg-accent hover:text-paper transition-colors disabled:opacity-50"
        >
          {busy2
            ? "Extracting photo context…"
            : "✨ Extract photo context (10 most recent)"}
        </button>
        {err2 && <p className="mt-2 text-xs text-urgent">{err2}</p>}
      </div>
    );
  }

  async function submit() {
    if (!parsed) {
      setError("Drop a file first");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await fetch("/v2/api/daily-logs/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source: filename, payload: parsed }),
      });
      const data = (await resp.json()) as
        | UploadResult
        | { error: string };
      if (!resp.ok || !("ok" in data)) {
        setError(
          "error" in data ? data.error : `HTTP ${resp.status}`
        );
        setBusy(false);
        return;
      }
      setResult(data);
      setBusy(false);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="space-y-4">
        <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-success/80">
          Upload complete · {result.inserted} rows
        </p>
        <ul className="text-sm text-ink-2 space-y-1">
          {Object.entries(result.per_job).map(([job, c]) => (
            <li key={job} className="font-mono text-xs">
              {job}: {c.inserted}/{c.total} inserted
              {c.skipped > 0 && (
                <span className="text-ink-3">
                  {" "}
                  · {c.skipped} skipped (no logId)
                </span>
              )}
            </li>
          ))}
        </ul>

        {/* F8 — kick off photo vision pass for any newly-uploaded logs that
            have photos but no summary yet. Processes up to 10 per click to
            keep Claude usage bounded. */}
        <PhotoExtractTrigger />

        <button
          type="button"
          onClick={() => {
            setResult(null);
            setParsed(null);
            setFilename("");
            setBytes(0);
            setJobCount(0);
            setRecordCount(0);
            setExtract(null);
          }}
          className="mt-2 text-xs underline text-accent"
        >
          Upload another
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <label className="block font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3 mb-1.5">
          JSON file
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
              <p className="font-mono text-sm text-ink">{filename}</p>
              <p className="mt-1 font-mono text-[11px] text-ink-3 tabular-nums">
                {(bytes / 1024).toFixed(1)} KB · {jobCount} job
                {jobCount === 1 ? "" : "s"} · {recordCount} record
                {recordCount === 1 ? "" : "s"}
              </p>
            </>
          ) : (
            <>
              <p className="text-sm text-ink-2">
                Drag a daily-logs.json here, or click to pick
              </p>
              <p className="mt-1 font-mono text-[11px] text-ink-3">
                .json only
              </p>
            </>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".json,application/json"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
            }}
          />
        </div>
      </div>

      {error && <p className="text-xs text-urgent">{error}</p>}

      <button
        type="button"
        onClick={submit}
        disabled={!parsed || busy}
        className="bg-ink text-paper px-5 py-3 text-sm font-medium disabled:opacity-50 hover:bg-accent transition-colors"
      >
        {busy ? "Uploading…" : `Upload ${recordCount} records`}
      </button>
    </div>
  );
}
