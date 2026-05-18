// POST /api/sub-specialties/seed-defaults
// Seeds sensible default specialties for every sub based on its trade.
// Idempotent (uses upsert on the (sub_id, specialty) unique key).
// Body: { dry_run?: boolean, trades?: string[] } — narrow to specific trades
// if you want; omit to seed every sub.

import { NextRequest, NextResponse } from "next/server";
import { revalidatePath } from "next/cache";
import { supabaseServer } from "@/lib/supabase";
import { getActor } from "@/lib/actor";

export const dynamic = "force-dynamic";

// Sensible work-bucket defaults per trade. Names match what BT's
// parent_group_activities tend to emit, so auto-detected and seeded
// specialties merge cleanly on /sub/[id].
const DEFAULTS: Record<string, string[]> = {
  "Tile/Floor": [
    "Stage materials",
    "Prep & level floors",
    "Prep & level walls",
    "Lay tile",
    "Grout",
    "Punch",
  ],
  Paint: [
    "Prep & mask",
    "Prime",
    "Exterior body",
    "Interior body",
    "Trim",
    "Touch-up & punch",
  ],
  Drywall: ["Hang", "Tape & finish", "Texture", "Patch"],
  "Plaster/Stucco": [
    "Wire & lath",
    "Scratch coat",
    "Brown coat",
    "Finish coat",
    "Patch",
  ],
  Plumbing: [
    "Under-slab rough",
    "Top-out rough",
    "Trim",
    "Punch",
  ],
  Electrical: [
    "Under-slab rough",
    "Wall rough",
    "Trim",
    "Punch",
  ],
  HVAC: ["Duct rough", "Equipment set", "Trim", "Punch"],
  "Carpentry/Stairs": [
    "Wall frame",
    "Roof frame",
    "Sheathing",
    "Stair install",
    "Punch",
  ],
  Roof: [
    "Underlayment",
    "Install",
    "Flashing",
    "Punch",
  ],
  Concrete: ["Form", "Pour", "Strip", "Patch"],
  Mason: ["Block lay", "Block fill", "Veneer", "Cap"],
  "Stone/Masonry": ["Stage", "Set", "Grout", "Seal"],
  Cabinetry: [
    "Deliver & stage",
    "Install",
    "Adjust",
    "Trim & touch-up",
  ],
  Siding: ["Prep", "Install", "Caulk", "Touch-up"],
  "Windows/Doors": [
    "Frame check",
    "Install",
    "Flash",
    "Trim",
  ],
  Doors: ["Install", "Hardware", "Adjust", "Trim"],
  Landscape: [
    "Site prep",
    "Tree set",
    "Sod",
    "Irrigation",
    "Punch",
  ],
  "Pool/Spa": [
    "Excavation",
    "Shell",
    "Plumbing & equipment",
    "Tile & coping",
    "Plaster",
    "Start-up",
  ],
  "Site/Excavation": [
    "Clearing",
    "Rough grade",
    "Utility trench",
    "Final grade",
  ],
  "Metal/Welding": ["Fab", "Install", "Touch-up"],
  Insulation: ["Walls", "Ceiling", "Attic", "Air seal"],
  Appliances: ["Deliver", "Install", "Trim & start-up"],
  "Audio/Video": [
    "Pre-wire",
    "Equipment install",
    "Programming",
    "Punch",
  ],
  "Lighting/Fixtures": ["Stage", "Install", "Trim & punch"],
  Elevator: ["Shaft prep", "Install", "Trim & inspection"],
  "Trim/Finish": ["Base", "Casing", "Crown", "Punch"],
  "Dock/Marine": ["Pilings", "Deck", "Hardware", "Punch"],
  Lumber: ["Deliver"],
  Internal: ["Site coordination", "Punch & callbacks"],
};

interface Body {
  dry_run?: boolean;
  trades?: string[];
}

export async function POST(req: NextRequest) {
  let body: Body = {};
  try {
    body = (await req.json()) as Body;
  } catch {
    /* empty body OK */
  }

  const supabase = supabaseServer();
  const actor = getActor(req);

  const subsRes = await supabase.from("subs").select("id, name, trade");
  if (subsRes.error) {
    return NextResponse.json(
      { error: `subs query failed: ${subsRes.error.message}` },
      { status: 500 }
    );
  }
  const subs = (subsRes.data ?? []) as {
    id: string;
    name: string;
    trade: string | null;
  }[];

  const tradeFilter = new Set(body.trades?.map((t) => t.toLowerCase()) ?? []);

  type Plan = {
    sub_id: string;
    sub_name: string;
    trade: string | null;
    specialties: string[];
    note?: string;
  };
  const plan: Plan[] = [];

  for (const s of subs) {
    if (
      tradeFilter.size > 0 &&
      (!s.trade || !tradeFilter.has(s.trade.toLowerCase()))
    ) {
      continue;
    }
    const specs = s.trade ? DEFAULTS[s.trade] ?? null : null;
    plan.push({
      sub_id: s.id,
      sub_name: s.name,
      trade: s.trade,
      specialties: specs ?? [],
      note: specs ? undefined : `no defaults for trade "${s.trade ?? "?"}"`,
    });
  }

  if (body.dry_run) {
    return NextResponse.json({
      ok: true,
      dry_run: true,
      to_seed: plan.filter((p) => p.specialties.length > 0).length,
      no_defaults: plan.filter((p) => p.specialties.length === 0).length,
      plan,
    });
  }

  // Upsert per (sub, specialty)
  const rows = plan.flatMap((p) =>
    p.specialties.map((sp) => ({
      sub_id: p.sub_id,
      specialty: sp,
      source: "manual" as const,
      created_by: actor,
    }))
  );

  if (rows.length === 0) {
    return NextResponse.json({
      ok: true,
      inserted: 0,
      note: "Nothing to seed — no defaults for any selected trade.",
    });
  }

  const { error, count } = await supabase
    .from("sub_specialties")
    .upsert(rows, { onConflict: "sub_id,specialty", count: "exact" });

  if (error) {
    const hint = /PGRST205|does not exist/i.test(error.message)
      ? " (apply migration 012_create_sub_specialties_table.sql first)"
      : "";
    return NextResponse.json(
      { error: `upsert failed: ${error.message}${hint}` },
      { status: 500 }
    );
  }

  revalidatePath("/subs");
  // Per-sub paths invalidated lazily on next visit.

  return NextResponse.json({
    ok: true,
    inserted_or_kept: count ?? rows.length,
    subs_touched: plan.filter((p) => p.specialties.length > 0).length,
    subs_without_defaults: plan.filter((p) => p.specialties.length === 0).length,
  });
}
