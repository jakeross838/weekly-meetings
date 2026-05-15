import Link from "next/link";
import { RossBuiltLogo } from "./logo";

export function Header() {
  const today = new Date();
  const stamp = today.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });

  return (
    <header className="bg-ink text-paper">
      {/* Brand stripe — slate ink with logo + nav */}
      <div className="px-5 py-3.5 flex items-center justify-between gap-3 border-b border-ink">
        <Link href="/" className="shrink-0">
          <RossBuiltLogo size={24} className="text-paper" />
        </Link>
        <nav className="flex items-center gap-4 font-mono text-[11px] tracking-[0.18em] uppercase">
          <Link href="/" className="text-paper hover:text-paper/80">
            Todos
          </Link>
          <Link href="/selections" className="text-paper/70 hover:text-paper">
            Selections
          </Link>
          <Link href="/subs" className="text-paper/70 hover:text-paper">
            Subs
          </Link>
          <Link href="/pace" className="text-paper/70 hover:text-paper">
            Pace
          </Link>
        </nav>
      </div>
      {/* Date — quiet, on sand. No "Sheet · PROD-01" decoration. */}
      <div className="px-5 py-3 bg-background border-b border-rule text-center">
        <span className="font-mono text-[11px] tracking-[0.2em] uppercase text-ink-3">
          {stamp}
        </span>
      </div>
    </header>
  );
}
