import Link from "next/link";
import { RossBuiltLogo } from "./logo";
import { ViewToggle } from "./view-toggle";
import { UserPill } from "./user-pill";
import { currentUser } from "@/lib/auth";

// Minimal header: brand mark + 4 short links + signed-in pill.
// "Todos" was the v1 name for the portfolio home — renamed to "Jobs" to
// match the rebuilt /.

export async function Header() {
  const user = await currentUser();
  return (
    <header className="border-b border-rule">
      <div className="max-w-[560px] mx-auto px-5 py-4 flex items-center justify-between gap-4">
        <Link
          href="/"
          className="shrink-0 text-ink hover:text-accent transition-colors"
          aria-label="Home"
        >
          <RossBuiltLogo size={22} />
        </Link>
        <nav className="flex items-center gap-4 text-xs text-ink-2">
          <Link href="/meeting" className="hover:text-ink transition-colors">
            Meeting
          </Link>
          <Link href="/" className="hover:text-ink transition-colors">
            Jobs
          </Link>
          <Link href="/subs" className="hover:text-ink transition-colors">
            Subs
          </Link>
          <Link
            href="/import"
            className="text-accent hover:text-ink transition-colors"
          >
            Import
          </Link>
          {user?.role === "admin" && (
            <Link href="/admin" className="hover:text-ink transition-colors">
              Admin
            </Link>
          )}
          <ViewToggle />
          {user && <UserPill name={user.name} role={user.role} />}
        </nav>
      </div>
    </header>
  );
}
