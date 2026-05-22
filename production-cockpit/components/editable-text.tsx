"use client";

// Click-to-edit any field. Shows `display` (or the value); click → input/
// textarea → Enter or blur saves (POSTs { [field]: value } to `endpoint`) →
// router.refresh(); Esc cancels. `type="money"`/`"number"` send a parsed
// number (strips $ and commas). Modeled on the checklist-editor inline pattern.

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";

type EditType = "text" | "textarea" | "number" | "money" | "date";

export function EditableText({
  value,
  endpoint,
  field,
  type = "text",
  placeholder,
  display,
  className,
  inputClassName,
  label,
}: {
  value: string | number | null;
  endpoint: string;
  field: string;
  type?: EditType;
  placeholder?: string;
  display?: string;
  className?: string;
  inputClassName?: string;
  label?: string;
}) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const cancelRef = useRef(false);

  function start() {
    setErr(null);
    setDraft(value == null ? "" : String(value));
    cancelRef.current = false;
    setEditing(true);
  }

  async function save() {
    if (cancelRef.current) {
      cancelRef.current = false;
      setEditing(false);
      return;
    }
    const orig = value == null ? "" : String(value);
    if (draft === orig) {
      setEditing(false);
      return;
    }
    let payloadVal: string | number | null = draft.trim();
    if (type === "money" || type === "number") {
      if (payloadVal === "") {
        payloadVal = null;
      } else {
        const n = Number(String(payloadVal).replace(/[$,\s]/g, ""));
        if (Number.isNaN(n)) {
          setErr("not a number");
          return;
        }
        payloadVal = n;
      }
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: payloadVal }),
      });
      if (!r.ok) {
        const b = await r.json().catch(() => ({}));
        setErr(b.error || `HTTP ${r.status}`);
        setBusy(false);
        return;
      }
      setEditing(false);
      setBusy(false);
      router.refresh();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  const inputCls =
    inputClassName ??
    "bg-paper border border-ink px-1 py-0.5 text-sm text-ink focus:outline-none w-full min-w-0";

  if (editing) {
    return (
      <span className="inline-flex items-center gap-1 w-full">
        {type === "textarea" ? (
          <textarea
            autoFocus
            rows={2}
            disabled={busy}
            value={draft}
            placeholder={placeholder}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                cancelRef.current = true;
                (e.target as HTMLTextAreaElement).blur();
              }
            }}
            onBlur={save}
            className={inputCls}
          />
        ) : (
          <input
            autoFocus
            disabled={busy}
            value={draft}
            placeholder={placeholder}
            type={type === "date" ? "date" : "text"}
            inputMode={type === "money" || type === "number" ? "decimal" : undefined}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                (e.target as HTMLInputElement).blur();
              }
              if (e.key === "Escape") {
                cancelRef.current = true;
                (e.target as HTMLInputElement).blur();
              }
            }}
            onBlur={save}
            className={inputCls}
          />
        )}
        {err && <span className="text-urgent text-[10px] shrink-0">{err}</span>}
      </span>
    );
  }

  const isEmpty = value == null || value === "";
  const shown = display ?? (isEmpty ? placeholder ?? "—" : String(value));
  return (
    <button
      type="button"
      onClick={start}
      title={label ?? "Click to edit"}
      className={
        (className ?? "") +
        " text-left hover:underline decoration-dotted decoration-ink-3 underline-offset-2 " +
        (isEmpty ? "text-ink-3 italic" : "")
      }
    >
      {shown}
    </button>
  );
}
