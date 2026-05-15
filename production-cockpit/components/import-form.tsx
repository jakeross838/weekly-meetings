"use client";

import { useState, useTransition, useRef } from "react";
import { useRouter } from "next/navigation";

interface PMOpt {
  id: string;
  full_name: string;
}

interface ImportFormProps {
  pms: PMOpt[];
}

interface ExtractedItem {
  title: string;
  sub_name: string | null;
  job: string;
  priority: "URGENT" | "HIGH" | "NORMAL";
  due_date: string | null;
  category: string;
  type: string;
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
}

const todayIso = () => new Date().toISOString().slice(0, 10);

export function ImportForm({ pms }: ImportFormProps) {
  const router = useRouter();
  const [pmId, setPmId] = useState(pms[0]?.id ?? "");
  const [meetingDate, setMeetingDate] = useState(todayIso());
  const [meetingType, setMeetingType] = useState<"SITE" | "OFFICE">("SITE");
  const [transcript, setTranscript] = useState("");
  const [filename, setFilename] = useState("");
  const [isDragging, setDragging] = useState(false);
  const [step, setStep] = useState<"upload" | "review">("upload");
  const [extract, setExtract] = useState<ExtractResp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, start] = useTransition();
  const [processing, setProcessing] = useState(false);
  const [saving, setSaving] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Per-item checked state — drives what gets saved
  const [enabled, setEnabled] = useState<Record<string, boolean>>({});
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
      // Default: everything enabled
      const init: Record<string, boolean> = {};
      data.grouped.forEach((g: SubGroup, gi: number) => {
        g.items.forEach((_, ii) => {
          init[itemKey(gi, ii)] = true;
        });
      });
      setEnabled(init);
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
    extract.grouped.forEach((g, gi) => {
      g.items.forEach((item, ii) => {
        if (!enabled[itemKey(gi, ii)]) return;
        items.push({ ...item, sub_id: g.sub_id });
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
    const totalEnabled = Object.values(enabled).filter(Boolean).length;
    return (
      <div className="px-6 lg:px-10 pb-12">
        <div className="py-6">
          <p className="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3">
            Step 2 of 2 · Review &amp; save
          </p>
          <h2 className="mt-2 font-head text-2xl font-semibold text-ink">
            {extract.totalItems} item{extract.totalItems === 1 ? "" : "s"}{" "}
            extracted
          </h2>
          {extract.summary && (
            <p className="mt-3 text-[15px] text-ink-2 leading-relaxed">
              {extract.summary}
            </p>
          )}
        </div>

        {extract.grouped.map((g, gi) => (
          <section
            key={gi}
            className="mb-6 border border-rule bg-paper"
          >
            <header className="px-5 py-3 bg-sand-2/50 border-b border-rule flex items-center justify-between">
              <h3 className="font-head text-base font-semibold text-ink">
                {g.sub_name || "No sub linked"}
                {!g.sub_id && g.sub_name && (
                  <span className="ml-2 font-mono text-[11px] text-ink-3">
                    (not in catalog — will save without link)
                  </span>
                )}
              </h3>
              <span className="font-mono text-[12px] text-ink-3 tabular-nums">
                {g.items.length}
              </span>
            </header>
            <ul>
              {g.items.map((item, ii) => {
                const k = itemKey(gi, ii);
                const on = enabled[k];
                return (
                  <li
                    key={ii}
                    className="border-b border-rule-soft last:border-b-0"
                  >
                    <label className="flex items-start gap-3 px-5 py-3 cursor-pointer hover:bg-sand-2/30">
                      <input
                        type="checkbox"
                        checked={on}
                        onChange={(e) =>
                          setEnabled((s) => ({
                            ...s,
                            [k]: e.target.checked,
                          }))
                        }
                        className="mt-1 h-4 w-4 accent-accent"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-[15px] leading-snug text-ink">
                          {item.title}
                        </p>
                        <p className="mt-1 font-mono text-[11px] text-ink-3 tabular-nums">
                          {item.job} · {item.category} · {item.priority}
                          {item.due_date && ` · due ${item.due_date}`}
                        </p>
                      </div>
                    </label>
                  </li>
                );
              })}
            </ul>
          </section>
        ))}

        {error && (
          <p className="mb-4 text-[13px] text-urgent">{error}</p>
        )}

        <div className="flex items-center justify-between gap-4 sticky bottom-0 bg-background border-t border-rule -mx-6 lg:-mx-10 px-6 lg:px-10 py-4">
          <button
            type="button"
            onClick={() => setStep("upload")}
            className="text-[13px] tracking-[0.15em] uppercase text-ink-2 hover:text-ink"
            disabled={saving}
          >
            Back
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving || totalEnabled === 0}
            className="bg-ink text-paper px-5 py-2.5 text-[13px] tracking-[0.15em] uppercase font-medium hover:bg-accent disabled:opacity-50 transition-colors"
          >
            {saving
              ? "Saving..."
              : `Save ${totalEnabled} item${totalEnabled === 1 ? "" : "s"}`}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-6 lg:px-10 py-8 space-y-6">
      <p className="font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3">
        Step 1 of 2 · Upload &amp; meta
      </p>

      {/* Meta */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div>
          <label className="block font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3 mb-1.5">
            PM
          </label>
          <select
            value={pmId}
            onChange={(e) => setPmId(e.target.value)}
            className="w-full bg-paper border border-rule px-3 py-2.5 text-[15px] text-ink focus:outline-none focus:border-ink"
          >
            {pms.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3 mb-1.5">
            Meeting Date
          </label>
          <input
            type="date"
            value={meetingDate}
            onChange={(e) => setMeetingDate(e.target.value)}
            className="w-full bg-paper border border-rule px-3 py-2.5 text-[15px] text-ink focus:outline-none focus:border-ink"
          />
        </div>
        <div>
          <label className="block font-mono text-[11px] tracking-[0.18em] uppercase text-ink-3 mb-1.5">
            Type
          </label>
          <div className="flex gap-2">
            {(["SITE", "OFFICE"] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setMeetingType(t)}
                className={
                  "flex-1 px-3 py-2.5 text-[14px] font-medium border transition-colors " +
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
