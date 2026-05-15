"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

interface FiltersProps {
  pms: { id: string; full_name: string }[];
  jobs: string[];
  selectedPm: string;
  selectedJob: string;
  view: "open" | "done";
}

export function Filters({
  pms,
  jobs,
  selectedPm,
  selectedJob,
  view,
}: FiltersProps) {
  const router = useRouter();
  const params = useSearchParams();
  const [, startTransition] = useTransition();

  function update(patch: Record<string, string | null>) {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      if (!v) p.delete(k);
      else p.set(k, v);
    }
    startTransition(() => router.push(`/?${p.toString()}`));
  }

  return (
    <div className="border-b border-rule">
      {/* Open / Done segmented toggle — full-width, big touch targets */}
      <div className="grid grid-cols-2 border-b border-rule">
        <ToggleBtn
          active={view === "open"}
          onClick={() => update({ view: null })}
          label="Open"
        />
        <ToggleBtn
          active={view === "done"}
          onClick={() => update({ view: "done" })}
          label="Done This Week"
          divider
        />
      </div>

      {/* PM pill row */}
      <div className="px-5 py-3.5">
        <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-5 px-5">
          <Pill
            active={!selectedPm}
            onClick={() => update({ pm: null, job: null })}
            label="All PMs"
          />
          {pms.map((p) => (
            <Pill
              key={p.id}
              active={selectedPm === p.id}
              onClick={() => update({ pm: p.id, job: null })}
              label={p.full_name.split(" ")[0]}
            />
          ))}
        </div>
      </div>

      {/* Job pill row — only when a PM is selected (avoids the 11-job blast) */}
      {selectedPm && jobs.length > 0 && (
        <div className="px-5 py-3 border-t border-rule">
          <div className="flex gap-2 overflow-x-auto no-scrollbar -mx-5 px-5">
            <Pill
              active={!selectedJob}
              onClick={() => update({ job: null })}
              label="All jobs"
            />
            {jobs.map((j) => (
              <Pill
                key={j}
                active={selectedJob === j}
                onClick={() => update({ job: j })}
                label={j}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ToggleBtn({
  active,
  onClick,
  label,
  divider,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  divider?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        "py-4 font-mono text-[12px] tracking-[0.18em] uppercase transition-colors " +
        (divider ? "border-l border-rule " : "") +
        (active
          ? "bg-ink text-paper"
          : "bg-transparent text-ink-2 hover:text-ink")
      }
    >
      {label}
    </button>
  );
}

function Pill({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={
        "shrink-0 px-3.5 py-2 text-[14px] font-medium border transition-colors " +
        (active
          ? "bg-ink text-paper border-ink"
          : "bg-transparent text-ink border-rule hover:border-ink")
      }
    >
      {label}
    </button>
  );
}
