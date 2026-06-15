import { APP_VERSION_HISTORY, CURRENT_VERSION } from "@/lib/version-history";

// App-wide version footer. Sits at the very bottom of every page (rendered in
// the root layout, after the page <main>). Collapsed to a single "Version N ·
// date" line; expands to the full history. Data lives in lib/version-history.
export function VersionFooter() {
  return (
    <footer className="max-w-[560px] mx-auto px-5 pb-10 pt-8">
      <div className="border-t border-rule-soft pt-4">
        <details className="group">
          <summary className="inline-flex cursor-pointer items-center gap-1.5 font-mono text-[10px] tracking-[0.18em] uppercase text-ink-3 hover:text-ink-2">
            <span className="disc-mark text-accent">›</span>
            Version {CURRENT_VERSION.version} · {CURRENT_VERSION.date}
          </summary>
          <ul className="mt-3 space-y-2.5">
            {APP_VERSION_HISTORY.map((v) => (
              <li key={v.version} className="flex gap-3">
                <span className="w-9 shrink-0 font-mono text-[12px] tabular-nums text-ink">
                  v{v.version}
                </span>
                <div className="min-w-0">
                  <p className="font-mono text-[10px] tabular-nums text-ink-3">
                    {v.date}
                  </p>
                  <p className="mt-0.5 text-[12px] leading-snug text-ink-2">
                    {v.summary}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </details>
      </div>
    </footer>
  );
}
