// /reset/[token] — set a new password after clicking the email link.

import Link from "next/link";
import { RossBuiltLogo } from "@/components/logo";
import { ResetForm } from "./reset-form";
import { lookupResetToken } from "@/lib/tokens";

export const metadata = { title: "Reset password · Ross Built" };
export const dynamic = "force-dynamic";

export default async function ResetPage({
  params,
}: {
  params: { token: string };
}) {
  const info = await lookupResetToken(params.token);
  const valid = info?.valid === true;
  const reason = info?.reason;

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
            Set new password
          </h1>
          {valid ? (
            <p className="mt-2.5 text-sm text-ink-2">
              For <span className="font-mono">{info!.email}</span>
            </p>
          ) : (
            <p className="mt-2.5 text-sm text-urgent">
              {reason === "expired"
                ? "This link expired."
                : reason === "used"
                  ? "This link was already used."
                  : "This link isn't valid."}
            </p>
          )}
        </div>

        {valid ? (
          <ResetForm token={params.token} />
        ) : (
          <div className="mt-8 text-center">
            <Link
              href="/forgot"
              className="inline-block bg-ink px-4 py-2.5 font-head text-sm text-paper transition hover:bg-accent"
            >
              Request a new link
            </Link>
          </div>
        )}

        <p className="mt-6 text-center text-xs text-ink-3">
          <Link href="/login" className="text-accent hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </main>
  );
}
