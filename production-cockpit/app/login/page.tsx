// /login — real sign-in form (Ross Built branded).
// Posts to /api/auth/login. On success the API sets an HMAC-signed cookie
// and we navigate to the post-login redirect (?next=...) or "/".

import { RossBuiltLogo } from "@/components/logo";
import { LoginForm } from "./login-form";
import { currentUser } from "@/lib/auth";
import { redirect } from "next/navigation";

export const metadata = { title: "Sign in · Ross Built" };
export const dynamic = "force-dynamic";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: { next?: string };
}) {
  // If already signed in, hop straight to the cockpit.
  const u = await currentUser();
  if (u) {
    redirect(searchParams.next && searchParams.next.startsWith("/") ? searchParams.next : "/");
  }
  const next = searchParams.next && searchParams.next.startsWith("/") ? searchParams.next : "/";

  return (
    <main
      className="min-h-screen flex flex-col items-center justify-center px-5 py-14"
      style={{
        background:
          "radial-gradient(125% 85% at 50% -15%, color-mix(in oklab, var(--accent) 14%, transparent), transparent 60%), var(--background)",
      }}
    >
      <div className="w-full max-w-[400px]">
        <div className="flex flex-col items-center text-center">
          <RossBuiltLogo size={42} />
          <h1 className="mt-7 font-head text-[26px] leading-none tracking-tight text-foreground">
            Production Cockpit
          </h1>
          <p className="mt-2.5 text-sm text-ink-2">Sign in to continue.</p>
        </div>

        <LoginForm next={next} />

        <div className="mt-6 flex items-center justify-between text-xs">
          <a href="/forgot" className="text-accent hover:underline">
            Forgot password?
          </a>
          <a href="/signup" className="text-accent hover:underline">
            Request access →
          </a>
        </div>

        <p className="mt-8 text-center font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">
          Internal — Ross Built
        </p>
      </div>
    </main>
  );
}
