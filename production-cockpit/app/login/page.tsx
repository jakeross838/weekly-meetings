// /login — sign-in WIREFRAME. No auth yet (the user asked for UI only for now;
// real sign-in wiring comes later). Each profile card just enters the app, so
// nothing here gates routing. Brand-aligned: real logo, whiteSand surface with
// a soft stone-blue wash, staggered card entrance + hover lift.

import Link from "next/link";
import { RossBuiltLogo } from "@/components/logo";

export const metadata = { title: "Sign in · Ross Built" };

interface Profile {
  initials: string;
  name: string;
  role: string;
  blurb: string;
}

const PROFILES: Profile[] = [
  {
    initials: "JR",
    name: "Jake Ross",
    role: "Director of Construction",
    blurb: "Portfolio budgets, schedule + every job at a glance.",
  },
  {
    initials: "PM",
    name: "Project Manager",
    role: "Field + subcontractors",
    blurb: "Your jobs, daily logs, and weekly meeting items.",
  },
  {
    initials: "OA",
    name: "Office / Admin",
    role: "Accounting + selections",
    blurb: "POs, change orders, and client-facing summaries.",
  },
];

export default function LoginPage() {
  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center px-5 py-14"
      style={{
        background:
          "radial-gradient(125% 85% at 50% -15%, color-mix(in oklab, var(--accent) 14%, transparent), transparent 60%), var(--background)",
      }}
    >
      <div className="w-full max-w-[400px]">
        {/* Brand */}
        <div className="flex flex-col items-center text-center">
          <RossBuiltLogo size={42} />
          <h1 className="mt-7 font-head text-[26px] leading-none tracking-tight text-foreground">
            Production Cockpit
          </h1>
          <p className="mt-2.5 text-sm text-ink-2">
            Choose your profile to continue.
          </p>
        </div>

        {/* Profile picker */}
        <div className="mt-9 space-y-3">
          {PROFILES.map((p, i) => (
            <Link
              key={p.initials}
              href="/"
              className="group flex items-center gap-4 border border-rule bg-paper p-4 transition hover:-translate-y-0.5 hover:border-accent hover:bg-oceanside/30 hover:shadow-md focus:outline-none focus-visible:border-accent"
              style={{
                animation: "fadeUp 460ms ease-out both",
                animationDelay: `${120 + i * 90}ms`,
              }}
            >
              <span
                aria-hidden
                className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-accent/10 font-head text-sm font-semibold text-accent transition group-hover:bg-accent group-hover:text-paper"
              >
                {p.initials}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block font-head text-[15px] leading-tight text-foreground">
                  {p.name}
                </span>
                <span className="block font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
                  {p.role}
                </span>
                <span className="mt-1 block text-xs leading-snug text-ink-2">
                  {p.blurb}
                </span>
              </span>
              <span
                aria-hidden
                className="shrink-0 text-ink-3 transition group-hover:translate-x-0.5 group-hover:text-accent"
              >
                →
              </span>
            </Link>
          ))}
        </div>

        {/* Wireframe note */}
        <p className="mt-8 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Wireframe · sign-in wiring comes later
        </p>
      </div>
    </main>
  );
}
