import Link from "next/link";
import { supabaseServer } from "@/lib/supabase";
import { PM } from "@/lib/types";
import { Header } from "@/components/header";
import { ImportForm } from "@/components/import-form";

export const dynamic = "force-dynamic";

export default async function ImportPage() {
  const supabase = supabaseServer();
  const pmsRes = await supabase
    .from("pms")
    .select("id, full_name, active")
    .eq("active", true)
    .order("full_name");
  const pms = (pmsRes.data ?? []) as PM[];

  return (
    <main className="max-w-[480px] lg:max-w-[960px] mx-auto min-h-screen bg-background">
      <Header />
      <div className="px-6 lg:px-10 py-4 border-b border-rule flex items-center justify-between">
        <Link
          href="/"
          className="text-[12px] tracking-[0.16em] uppercase font-medium text-ink-2 hover:text-accent"
        >
          ← Back
        </Link>
      </div>
      <div className="px-6 lg:px-10 pt-8 pb-6 border-b border-rule">
        <h1 className="font-head text-4xl lg:text-5xl font-semibold leading-tight text-ink">
          Import Transcript
        </h1>
        <p className="mt-3 text-[15px] text-ink-2 max-w-prose leading-relaxed">
          Drop a Plaud transcript and Claude will extract action items, group
          them by sub, and queue them for review before writing to the cockpit.
          Existing binders/*.json pipeline is untouched.
        </p>
      </div>
      <ImportForm pms={pms} />
    </main>
  );
}
