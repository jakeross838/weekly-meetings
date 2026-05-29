// /forgot — public page to request a password-reset email.

import Link from "next/link";
import { RossBuiltLogo } from "@/components/logo";
import { ForgotForm } from "./forgot-form";

export const metadata = { title: "Forgot password · Ross Built" };
export const dynamic = "force-dynamic";

export default function ForgotPage() {
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
            Forgot password
          </h1>
          <p className="mt-2.5 text-sm text-ink-2">
            Enter your email and we&apos;ll send a reset link.
          </p>
        </div>

        <ForgotForm />

        <p className="mt-6 text-center text-xs text-ink-3">
          Remembered it?{" "}
          <Link href="/login" className="text-accent hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
