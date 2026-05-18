// Horizontal pill row for filtering a list by category via ?cat= search
// param. Used on /v2/job/[id] and /sub/[id]. Pure server component —
// links re-render the page server-side with the new param.

import Link from "next/link";
import { CATEGORIES } from "@/lib/categories";

interface Props {
  basePath: string;
  activeCategory: string | null;
  availableCategories?: string[] | null;
}

export function CategoryFilterPills({
  basePath,
  activeCategory,
  availableCategories,
}: Props) {
  const known = new Set(CATEGORIES as readonly string[]);
  const data = (availableCategories ?? []).filter((c) => !known.has(c));
  const list = [...CATEGORIES, ...data];
  if (list.length === 0) return null;

  return (
    <div className="px-5 pt-4 pb-2">
      <div className="flex gap-1.5 overflow-x-auto no-scrollbar -mx-5 px-5">
        <Pill
          href={basePath}
          active={!activeCategory}
          label="All"
        />
        {list.map((c) => (
          <Pill
            key={c}
            href={`${basePath}?cat=${encodeURIComponent(c)}`}
            active={activeCategory === c}
            label={c}
          />
        ))}
      </div>
    </div>
  );
}

function Pill({
  href,
  active,
  label,
}: {
  href: string;
  active: boolean;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={
        "shrink-0 px-3 py-1.5 text-[10px] tracking-[0.12em] font-mono uppercase border transition-colors " +
        (active
          ? "bg-ink text-paper border-ink"
          : "bg-transparent text-ink-2 border-rule hover:border-ink hover:text-ink")
      }
    >
      {label}
    </Link>
  );
}
