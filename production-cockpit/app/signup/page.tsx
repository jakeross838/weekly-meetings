// /signup — public account creation. Anyone can sign up with a password.
// They're signed in immediately but see no jobs until admin grants access.

import Link from "next/link";
import { RossBuiltLogo } from "@/components/logo";
import { SignupForm } from "./signup-form";

export const metadata = { title: "Create account · Ross Built" };
export const dynamic = "force-dynamic";

export default function SignupPage() {
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
            Create account
          </h1>
          <p className="mt-2.5 text-sm text-ink-2 leading-relaxed">
            You can sign in right away. You won&apos;t see any jobs until
            Jake grants you access — just click <strong>Request access</strong>
            {" "}from your home screen and Jake will approve it.
          </p>
        </div>

        <SignupForm />

        <p className="mt-6 text-center text-xs text-ink-3">
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
