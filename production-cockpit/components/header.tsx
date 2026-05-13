import Link from "next/link";
import { RossBuiltLogo } from "./logo";

export function Header() {
  const today = new Date();
  const weekday = today.toLocaleDateString("en-US", { weekday: "long" });
  const stamp = today.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  return (
    <header className="bg-ink text-paper rise">
      {/* Top stripe — Ross Built lockup against slate ink */}
      <div className="px-5 py-3 flex items-center justify-between gap-3 border-b border-ink">
        <Link href="/" className="shrink-0">
          <RossBuiltLogo size={22} className="text-paper" />
        </Link>
        <nav className="flex items-center gap-3 font-mono text-[10px] tracking-[0.22em] uppercase">
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
      {/* Main bar — page label + date stamp on sand */}
      <div className="px-5 pt-5 pb-4 bg-background border-b border-rule">
        <div className="flex items-baseline justify-between gap-3">
          <div>
            <p className="font-mono text-[10px] tracking-[0.22em] uppercase text-ink-3">
              Sheet · PROD-01
            </p>
            <h1 className="mt-1 font-head text-3xl font-semibold tracking-tight leading-none text-ink">
              Production
            </h1>
          </div>
          <div className="text-right font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 leading-tight">
            <div>{weekday}</div>
            <div className="text-ink">{stamp}</div>
          </div>
        </div>
      </div>
    </header>
  );
}
