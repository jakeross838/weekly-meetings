"use client";

// Portfolio purchase-order ledger. Dense, sortable, filterable, paginated table
// of every job's POs with committed / paid / outstanding totals, expandable
// line items, CSV export (POs + line items), and inline edit/delete per row.
//
// Pagination (100/page) keeps it fast: only the visible page's cells mount the
// EditableText/DeleteButton client components, so the full 1,200-row dataset
// stays snappy. Totals + filters + sort still operate on the whole set.

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { EditableText } from "@/components/editable-text";
import { DeleteButton } from "@/components/delete-button";

export interface AcctPO {
  id: string;
  po_number: string | null;
  vendor: string | null;
  paid_status: string | null;
  approval_status: string | null;
  work_status: string | null;
  cost: number | null;
  amount_paid: number | null;
  amount_remaining: number | null;
  pct_billed: number | null;
  date_added: string | null;
  job_key: string;
  jobId: string | null;
  jobName: string;
}
export interface AcctLine {
  id: string;
  po_id: string;
  cost_code: string | null;
  title: string | null;
  description: string | null;
  quantity: number | null;
  unit_cost: number | null;
  amount: number | null;
  amount_paid: number | null;
}

type SortKey = "po" | "job" | "vendor" | "status" | "cost" | "paid" | "outstanding" | "pct";
const PAGE_SIZE = 100;
const COLS = 10; // chevron, PO#, job, vendor, status, cost, paid, outstanding, %, delete

function money(n: number | null | undefined): string {
  return "$" + Math.round(Number(n) || 0).toLocaleString("en-US");
}

// CSV: quote any field containing a comma, quote, or newline; double inner quotes.
function csvCell(v: unknown): string {
  const s = v == null ? "" : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}
function downloadCsv(filename: string, rows: (string | number | null)[][]) {
  const csv = rows.map((r) => r.map(csvCell).join(",")).join("\r\n");
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function AccountingTable({ pos, lines }: { pos: AcctPO[]; lines: AcctLine[] }) {
  const [jobFilter, setJobFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [outstandingOnly, setOutstandingOnly] = useState(false);
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("cost");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);

  const jobNames = useMemo(
    () => Array.from(new Set(pos.map((p) => p.jobName))).sort((a, b) => a.localeCompare(b)),
    [pos]
  );
  const statuses = useMemo(
    () =>
      Array.from(new Set(pos.map((p) => p.paid_status).filter(Boolean) as string[])).sort((a, b) =>
        a.localeCompare(b)
      ),
    [pos]
  );
  const linesByPo = useMemo(() => {
    const m = new Map<string, AcctLine[]>();
    for (const l of lines) {
      const arr = m.get(l.po_id) ?? [];
      arr.push(l);
      m.set(l.po_id, arr);
    }
    return m;
  }, [lines]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return pos.filter((p) => {
      if (jobFilter && p.jobName !== jobFilter) return false;
      if (statusFilter && p.paid_status !== statusFilter) return false;
      if (outstandingOnly && (Number(p.amount_remaining) || 0) <= 0) return false;
      if (q) {
        const hay = `${p.po_number ?? ""} ${p.vendor ?? ""} ${p.jobName}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [pos, jobFilter, statusFilter, outstandingOnly, search]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    const dir = sortDir === "asc" ? 1 : -1;
    arr.sort((a, b) => {
      let r = 0;
      switch (sortKey) {
        case "po":
          r = (a.po_number ?? "").localeCompare(b.po_number ?? "", undefined, { numeric: true });
          break;
        case "job":
          r = a.jobName.localeCompare(b.jobName);
          break;
        case "vendor":
          r = (a.vendor ?? "").localeCompare(b.vendor ?? "");
          break;
        case "status":
          r = (a.paid_status ?? "").localeCompare(b.paid_status ?? "");
          break;
        case "cost":
          r = (Number(a.cost) || 0) - (Number(b.cost) || 0);
          break;
        case "paid":
          r = (Number(a.amount_paid) || 0) - (Number(b.amount_paid) || 0);
          break;
        case "outstanding":
          r = (Number(a.amount_remaining) || 0) - (Number(b.amount_remaining) || 0);
          break;
        case "pct":
          r = (Number(a.pct_billed) || 0) - (Number(b.pct_billed) || 0);
          break;
      }
      return r * dir;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const totals = useMemo(() => {
    let cost = 0,
      paid = 0,
      out = 0;
    for (const p of filtered) {
      cost += Number(p.cost) || 0;
      paid += Number(p.amount_paid) || 0;
      out += Number(p.amount_remaining) || 0;
    }
    return { cost, paid, out };
  }, [filtered]);

  // Reset to the first page whenever the result set changes.
  useEffect(() => {
    setPage(0);
  }, [jobFilter, statusFilter, outstandingOnly, search, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const pageRows = useMemo(
    () => sorted.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE),
    [sorted, safePage]
  );

  function setSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir(["cost", "paid", "outstanding", "pct"].includes(key) ? "desc" : "asc");
    }
  }
  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function exportPOs() {
    const header = [
      "Job", "PO #", "Vendor", "Approval", "Paid status", "Cost", "Paid", "Outstanding", "% Billed", "Date added",
    ];
    const rows: (string | number | null)[][] = [header];
    for (const p of sorted) {
      rows.push([
        p.jobName, p.po_number, p.vendor, p.approval_status, p.paid_status,
        Number(p.cost) || 0, Number(p.amount_paid) || 0, Number(p.amount_remaining) || 0,
        p.pct_billed, p.date_added,
      ]);
    }
    downloadCsv("purchase-orders.csv", rows);
  }
  function exportLines() {
    const ids = new Set(sorted.map((p) => p.id));
    const poById = new Map(sorted.map((p) => [p.id, p]));
    const header = [
      "Job", "PO #", "Vendor", "Cost code", "Line item", "Description", "Qty", "Unit cost", "Amount", "Amount paid",
    ];
    const rows: (string | number | null)[][] = [header];
    for (const l of lines) {
      if (!ids.has(l.po_id)) continue;
      const p = poById.get(l.po_id)!;
      rows.push([
        p.jobName, p.po_number, p.vendor, l.cost_code, l.title, l.description,
        l.quantity, l.unit_cost, Number(l.amount) || 0, Number(l.amount_paid) || 0,
      ]);
    }
    downloadCsv("po-line-items.csv", rows);
  }

  const arrow = (key: SortKey) => (sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "");
  const rangeStart = sorted.length === 0 ? 0 : safePage * PAGE_SIZE + 1;
  const rangeEnd = Math.min((safePage + 1) * PAGE_SIZE, sorted.length);

  return (
    <div className="mx-auto max-w-[1200px] px-5 pt-8">
      <header className="mb-5">
        <h1 className="font-head text-[28px] leading-none tracking-tight text-foreground">
          Accounting
        </h1>
        <p className="mt-2 text-ink-3 text-sm">
          {filtered.length} of {pos.length} purchase orders
        </p>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 font-mono text-sm tabular-nums">
          <span className="text-foreground">{money(totals.cost)} committed</span>
          <span className="text-ink-2">{money(totals.paid)} paid</span>
          <span className="text-urgent">{money(totals.out)} outstanding</span>
        </div>
      </header>

      {/* Filters + export */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <select
          value={jobFilter}
          onChange={(e) => setJobFilter(e.target.value)}
          className="bg-paper border border-rule px-2 py-1.5 text-sm text-ink focus:outline-none focus:border-ink"
        >
          <option value="">All jobs</option>
          {jobNames.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-paper border border-rule px-2 py-1.5 text-sm text-ink focus:outline-none focus:border-ink"
        >
          <option value="">All statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search PO# / vendor"
          className="bg-paper border border-rule px-2 py-1.5 text-sm text-ink focus:outline-none focus:border-ink"
        />
        <label className="flex items-center gap-2 text-sm text-ink-2 cursor-pointer">
          <input
            type="checkbox"
            checked={outstandingOnly}
            onChange={(e) => setOutstandingOnly(e.target.checked)}
            className="h-4 w-4 accent-accent"
          />
          Outstanding only
        </label>
        <div className="ml-auto flex gap-2">
          <button
            type="button"
            onClick={exportPOs}
            className="bg-ink text-paper px-3 py-1.5 text-xs font-medium hover:bg-accent transition-colors"
          >
            ⤓ POs CSV
          </button>
          <button
            type="button"
            onClick={exportLines}
            className="border border-ink text-ink px-3 py-1.5 text-xs font-medium hover:bg-ink hover:text-paper transition-colors"
          >
            ⤓ Line items CSV
          </button>
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto border border-rule">
        <table className="w-full min-w-[820px] text-sm">
          <thead>
            <tr className="border-b border-rule bg-sand-2/40 text-left font-mono text-[10px] uppercase tracking-[0.12em] text-ink-3">
              <th className="w-6 px-2 py-2" />
              <Th onClick={() => setSort("po")} label={`PO#${arrow("po")}`} />
              <Th onClick={() => setSort("job")} label={`Job${arrow("job")}`} />
              <Th onClick={() => setSort("vendor")} label={`Vendor${arrow("vendor")}`} />
              <Th onClick={() => setSort("status")} label={`Status${arrow("status")}`} />
              <Th onClick={() => setSort("cost")} label={`Cost${arrow("cost")}`} right />
              <Th onClick={() => setSort("paid")} label={`Paid${arrow("paid")}`} right />
              <Th onClick={() => setSort("outstanding")} label={`Outstanding${arrow("outstanding")}`} right />
              <Th onClick={() => setSort("pct")} label={`% Billed${arrow("pct")}`} right />
              <th className="w-6 px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {pageRows.length === 0 && (
              <tr>
                <td colSpan={COLS} className="px-3 py-10 text-center text-ink-3 text-sm">
                  No purchase orders match.
                </td>
              </tr>
            )}
            {pageRows.map((p) => (
              <PORow
                key={p.id}
                po={p}
                lines={linesByPo.get(p.id) ?? []}
                isOpen={expanded.has(p.id)}
                onToggle={() => toggleExpand(p.id)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="font-mono text-[11px] tabular-nums text-ink-3">
          {rangeStart}–{rangeEnd} of {sorted.length}
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={safePage <= 0}
            onClick={() => setPage(safePage - 1)}
            className="border border-rule px-2.5 py-1 text-xs text-ink-2 hover:border-ink hover:text-ink disabled:opacity-40 disabled:hover:border-rule"
          >
            ← Prev
          </button>
          <span className="font-mono text-[11px] tabular-nums text-ink-2">
            {safePage + 1}/{pageCount}
          </span>
          <button
            type="button"
            disabled={safePage >= pageCount - 1}
            onClick={() => setPage(safePage + 1)}
            className="border border-rule px-2.5 py-1 text-xs text-ink-2 hover:border-ink hover:text-ink disabled:opacity-40 disabled:hover:border-rule"
          >
            Next →
          </button>
        </div>
      </div>
      <p className="mt-3 text-[10px] font-mono tracking-[0.14em] uppercase text-ink-3">
        click a row ▸ for line items · click any cell to edit · ✕ deletes · PO# opens the job page
      </p>
    </div>
  );
}

function Th({ label, onClick, right }: { label: string; onClick: () => void; right?: boolean }) {
  return (
    <th
      onClick={onClick}
      className={
        "px-3 py-2 cursor-pointer select-none hover:text-ink whitespace-nowrap " +
        (right ? "text-right" : "")
      }
    >
      {label}
    </th>
  );
}

function PORow({
  po,
  lines,
  isOpen,
  onToggle,
}: {
  po: AcctPO;
  lines: AcctLine[];
  isOpen: boolean;
  onToggle: () => void;
}) {
  const out = Number(po.amount_remaining) || 0;
  const editEndpoint = `/v2/api/purchase-orders/${po.id}/edit`;
  const moneyInput =
    "bg-paper border border-ink px-1 py-0.5 text-xs text-ink focus:outline-none w-24 text-right";
  return (
    <>
      <tr className="border-b border-rule-soft hover:bg-sand-2/30">
        <td className="px-2 py-2 align-top">
          {lines.length > 0 ? (
            <button
              type="button"
              onClick={onToggle}
              aria-label={isOpen ? "Collapse line items" : "Expand line items"}
              className="text-ink-3 hover:text-ink font-mono"
            >
              {isOpen ? "▾" : "▸"}
            </button>
          ) : (
            <span className="text-ink-3/30 font-mono">·</span>
          )}
        </td>
        <td className="px-3 py-2 align-top whitespace-nowrap font-mono text-[11px]">
          {po.jobId ? (
            <Link href={`/v2/job/${po.jobId}`} className="text-accent hover:underline">
              {po.po_number ?? "PO"}
            </Link>
          ) : (
            <span className="text-ink-2">{po.po_number ?? "PO"}</span>
          )}
        </td>
        <td className="px-3 py-2 align-top whitespace-nowrap text-ink-2">{po.jobName}</td>
        <td className="px-3 py-2 align-top text-foreground">
          <EditableText
            value={po.vendor}
            field="vendor"
            endpoint={editEndpoint}
            placeholder="vendor"
            display={po.vendor ?? "—"}
          />
        </td>
        <td className="px-3 py-2 align-top whitespace-nowrap text-ink-2 text-xs">
          <EditableText
            value={po.paid_status}
            field="paid_status"
            endpoint={editEndpoint}
            placeholder="status"
            display={po.paid_status ?? "—"}
          />
        </td>
        <td className="px-3 py-2 align-top text-right font-mono tabular-nums text-foreground whitespace-nowrap">
          <EditableText
            value={po.cost}
            type="money"
            field="cost"
            endpoint={editEndpoint}
            display={money(po.cost)}
            inputClassName={moneyInput}
          />
        </td>
        <td className="px-3 py-2 align-top text-right font-mono tabular-nums text-ink-2 whitespace-nowrap">
          <EditableText
            value={po.amount_paid}
            type="money"
            field="amount_paid"
            endpoint={editEndpoint}
            display={money(po.amount_paid)}
            inputClassName={moneyInput}
          />
        </td>
        <td
          className={
            "px-3 py-2 align-top text-right font-mono tabular-nums whitespace-nowrap " +
            (out > 0 ? "text-urgent" : "text-ink-3")
          }
        >
          <EditableText
            value={po.amount_remaining}
            type="money"
            field="amount_remaining"
            endpoint={editEndpoint}
            display={money(po.amount_remaining)}
            inputClassName={moneyInput}
          />
        </td>
        <td className="px-3 py-2 align-top text-right font-mono tabular-nums text-ink-3 whitespace-nowrap">
          {po.pct_billed != null ? `${Math.round(Number(po.pct_billed))}%` : "—"}
        </td>
        <td className="px-2 py-2 align-top text-right">
          <DeleteButton
            endpoint={`/v2/api/purchase-orders/${po.id}/delete`}
            label={`PO ${po.po_number ?? ""}`.trim()}
            confirmLabel="Delete?"
          />
        </td>
      </tr>
      {isOpen && lines.length > 0 && (
        <tr className="bg-sand-2/20">
          <td />
          <td colSpan={COLS - 1} className="px-3 py-2">
            <ul className="space-y-1">
              {lines.map((l) => (
                <li
                  key={l.id}
                  className="flex items-baseline justify-between gap-3 text-xs border-b border-rule-soft/60 last:border-b-0 py-0.5"
                >
                  <span className="min-w-0 flex-1 text-ink-2">
                    {l.cost_code && <span className="text-ink-3">{l.cost_code} · </span>}
                    {l.title || l.description || "—"}
                    {l.quantity != null && l.unit_cost != null && (
                      <span className="text-ink-3">
                        {" "}({l.quantity} × {money(l.unit_cost)})
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 font-mono tabular-nums text-ink-2">{money(l.amount)}</span>
                </li>
              ))}
            </ul>
          </td>
        </tr>
      )}
    </>
  );
}
