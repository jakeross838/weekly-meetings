// Shared list of category values + their display styling. Single source
// of truth so adding a new category only requires editing one file.

export const CATEGORIES = [
  "SCHEDULE",
  "QUALITY",
  "PROCUREMENT",
  "SELECTION",
  "BUDGET",
  "CLIENT",
  "ADMIN",
  "SUB-TRADE",
] as const;

export type Category = (typeof CATEGORIES)[number];

export const CATEGORY_STYLE: Record<string, string> = {
  SCHEDULE: "text-sky-700 bg-sky-50",
  QUALITY: "text-amber-700 bg-amber-50",
  PROCUREMENT: "text-purple-700 bg-purple-50",
  SELECTION: "text-pink-700 bg-pink-50",
  BUDGET: "text-emerald-700 bg-emerald-50",
  CLIENT: "text-indigo-700 bg-indigo-50",
  ADMIN: "text-slate-700 bg-slate-100",
  "SUB-TRADE": "text-stone-700 bg-stone-100",
};

export function styleFor(category: string | null | undefined): string {
  if (!category) return "text-ink-3 bg-sand-2";
  return CATEGORY_STYLE[category] ?? "text-ink-3 bg-sand-2";
}
