"use client";

import { useRouter, useSearchParams } from "next/navigation";

interface TradeSelectProps {
  trades: string[];
  selected: string;
}

/**
 * Native <select> so the OS dropdown handles overflow — every trade is
 * always accessible regardless of how many there are. Way better mobile
 * UX than wrapped pills when the count gets above ~10.
 */
export function TradeSelect({ trades, selected }: TradeSelectProps) {
  const router = useRouter();
  const params = useSearchParams();

  function onChange(value: string) {
    const p = new URLSearchParams(params.toString());
    if (!value || value === "all") p.delete("trade");
    else p.set("trade", value);
    const qs = p.toString();
    router.push(qs ? `/subs?${qs}` : "/subs");
  }

  return (
    <select
      value={selected || "all"}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-paper border border-rule px-3 py-2.5 text-[14px] font-medium text-ink focus:outline-none focus:border-ink"
    >
      <option value="all">All trades ({trades.length})</option>
      {trades.map((t) => (
        <option key={t} value={t}>
          {t}
        </option>
      ))}
    </select>
  );
}
