// /signup — public-facing request-access form. Approval is manual by Jake.

import Link from "next/link";
import { RossBuiltLogo } from "@/components/logo";
import { SignupForm } from "./signup-form";

export const metadata = { title: "Request access · Ross Built" };
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
            Request access
          </h1>
          <p className="mt-2.5 text-sm text-ink-2 leading-relaxed">
            Send Jake a quick request — once he approves, you&apos;ll get an
            email with your account details.
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
