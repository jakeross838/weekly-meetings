import Link from "next/link";
import { RossBuiltLogo } from "./logo";

/**
 * Header pulled toward rossbuilt.com's style: paper-white surface, stone-blue
 * brand mark, generous whitespace, sans-serif nav with tracked uppercase.
 * No more drafting-stock ink stripe — the brand color sits on white.
 */
export function Header() {
  const today = new Date();
  const stamp = today.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return (
    <header className="bg-paper border-b border-rule">
      <div className="px-6 lg:px-10 py-5 flex items-center justify-between gap-6">
        <Link
          href="/"
          className="shrink-0 text-ink hover:text-accent transition-colors"
        >
          <RossBuiltLogo size={28} />
        </Link>
        <nav className="flex items-center gap-4 sm:gap-6 text-[12px] font-medium tracking-[0.16em] uppercase">
          <Link
            href="/"
            className="text-ink hover:text-accent transition-colors"
          >
            Todos
          </Link>
          <Link
            href="/subs"
            className="text-ink-2 hover:text-accent transition-colors"
          >
            Subs
          </Link>
          <Link
            href="/schedule"
            className="text-ink-2 hover:text-accent transition-colors"
          >
            Schedule
          </Link>
          <Link
            href="/pace"
            className="text-ink-2 hover:text-accent transition-colors"
          >
            Pace
          </Link>
          <Link
            href="/import"
            className="text-accent hover:text-ink transition-colors"
          >
            + Import
          </Link>
        </nav>
      </div>
      <div className="px-6 lg:px-10 pb-4 text-[12px] tracking-[0.18em] uppercase text-ink-3 font-medium">
        {stamp}
      </div>
    </header>
  );
}
