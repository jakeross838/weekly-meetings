// Org-configurable knobs live in the `app_config` (key/value) table, never as
// code literals. getConfig reads one key; getConfigMany batches several. Values
// fall back to the provided default when the row is absent, so the app boots
// even before an operator sets anything. Reads go through supabaseServer()
// (service role, no-store) so a config change takes effect on the next request.

import { supabaseServer } from "@/lib/supabase";

export async function getConfig(key: string, fallback: string): Promise<string> {
  try {
    const { data } = await supabaseServer()
      .from("app_config")
      .select("value")
      .eq("key", key)
      .maybeSingle();
    const v = (data as { value?: string } | null)?.value;
    return v != null && v !== "" ? v : fallback;
  } catch {
    return fallback;
  }
}

export async function getConfigMany(
  defaults: Record<string, string>
): Promise<Record<string, string>> {
  const out = { ...defaults };
  try {
    const keys = Object.keys(defaults);
    const { data } = await supabaseServer()
      .from("app_config")
      .select("key, value")
      .in("key", keys);
    for (const row of (data ?? []) as Array<{ key: string; value: string }>) {
      if (row.value != null && row.value !== "") out[row.key] = row.value;
    }
  } catch {
    /* fall back to defaults */
  }
  return out;
}
