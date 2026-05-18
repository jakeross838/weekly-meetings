"use client";

// Client wrapper for a single row on /v2/job. Owns the edit-modal state
// and lays out the visual row identical to the previous server-rendered
// version.

import { useState } from "react";
import { CheckOffButton } from "./check-off-button";
import { EditRowModal, SubOpt, RowEditValues } from "./edit-row";
import { CategoryPillEdit } from "./category-pill-edit";

function dayLabel(iso: string, today: string): string {
  if (iso < today) {
    const days = Math.floor(
      (new Date(today).getTime() - new Date(iso).getTime()) / 86_400_000
    );
    return `-${days}d`;
  }
  if (iso === today) return "today";
  const days = Math.floor(
    (new Date(iso).getTime() - new Date(today).getTime()) / 86_400_000
  );
  if (days <= 7) {
    return new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", {
      weekday: "short",
      timeZone: "UTC",
    });
  }
  return `${days}d`;
}

export interface RowClientProps {
  id: string;
  source: "item" | "todo";
  title: string;
  sub_id: string | null;
  sub_name: string | null;
  owner: string | null;
  target_date: string | null;
  category: string | null;
  today: string;
  highlight?: boolean;
  hideRightSlot?: boolean;
  subs: SubOpt[];
}

export function RowClient({
  id,
  source,
  title,
  sub_id,
  sub_name,
  owner,
  target_date,
  category,
  today,
  highlight,
  hideRightSlot,
  subs,
}: RowClientProps) {
  const [editing, setEditing] = useState(false);

  const subLabel = sub_name ?? owner ?? null;
  const initial: RowEditValues = {
    title,
    target_date,
    sub_id,
    category,
  };

  return (
    <>
      <li
        className={`py-1.5 min-h-[40px] ${
          highlight ? "border-l-2 border-urgent pl-2 -ml-2" : ""
        }`}
      >
        <div className="flex gap-3 items-baseline">
          <CheckOffButton itemId={id} source={source} />
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="flex-1 min-w-0 text-left group"
            aria-label="Edit"
          >
            <p className="text-foreground text-sm leading-snug group-hover:text-accent transition-colors">
              {title}
              {subLabel && (
                <span className="text-ink-3"> · {subLabel}</span>
              )}
            </p>
          </button>
          <CategoryPillEdit id={id} source={source} category={category} />
          {!hideRightSlot && target_date && (
            <span
              className={`shrink-0 text-xs font-mono ${
                highlight ? "text-urgent" : "text-ink-3"
              }`}
            >
              {dayLabel(target_date, today)}
            </span>
          )}
        </div>
      </li>
      <EditRowModal
        open={editing}
        onClose={() => setEditing(false)}
        source={source}
        id={id}
        initial={initial}
        subs={subs}
      />
    </>
  );
}
