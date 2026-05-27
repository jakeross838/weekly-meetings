// User-overlay store. The seed users in lib/auth-users.ts (USERS) are the
// baseline; this file lets the admin panel layer additions / job-access edits
// on top WITHOUT a code change + redeploy. Overlay rows match by email
// (case-insensitive) and win over the seed.
//
// Persistence: Supabase `public.user_overlay` table. Works on Vercel's
// read-only filesystem (the previous JSON-file version did not).

import { supabaseServer } from "./supabase";
import { USERS, type User, type Role } from "./auth-users";

interface OverlayRow {
  email: string;
  name: string;
  role: string; // 'admin' | 'pm'
  pm_id: string | null;
  allowed_jobs: string[] | null;
  password: string | null;
}

function rowToUser(r: OverlayRow): User {
  return {
    email: r.email,
    password: r.password ?? "password",
    name: r.name,
    role: (r.role === "admin" ? "admin" : "pm") as Role,
    pmId: r.pm_id,
    allowedJobs: r.allowed_jobs ?? [],
  };
}

async function readOverlay(): Promise<OverlayRow[]> {
  const sb = supabaseServer();
  const { data, error } = await sb
    .from("user_overlay")
    .select("email, name, role, pm_id, allowed_jobs, password");
  if (error) {
    console.warn("[user-store] could not read user_overlay:", error.message);
    return [];
  }
  return (data ?? []) as OverlayRow[];
}

// Merged users: seed + overlay. Overlay rows win by case-insensitive email.
export async function getAllUsers(): Promise<User[]> {
  const overlay = await readOverlay();
  const overlayByEmail = new Map<string, OverlayRow>();
  for (const r of overlay) overlayByEmail.set(r.email.toLowerCase(), r);
  const merged: User[] = USERS.map((seed) => {
    const r = overlayByEmail.get(seed.email.toLowerCase());
    if (!r) return seed;
    overlayByEmail.delete(seed.email.toLowerCase()); // consumed
    return rowToUser({ ...r, email: seed.email }); // preserve casing
  });
  // Overlay-only users (not in seed) come after. Array.from() rather than
  // direct `for…of overlayByEmail.values()` because Vercel's TS build target
  // doesn't enable downlevelIteration for Map iterators.
  Array.from(overlayByEmail.values()).forEach((r) => merged.push(rowToUser(r)));
  return merged;
}

export async function upsertUserAccess(
  email: string,
  allowedJobs: string[]
): Promise<User> {
  const norm = email.trim().toLowerCase();
  const seed = USERS.find((u) => u.email.toLowerCase() === norm);
  const sb = supabaseServer();
  // If an overlay row already exists, just update the allowed_jobs (preserve
  // any prior name/role/pm_id edits). Otherwise seed the row from USERS.
  const { data: existing } = await sb
    .from("user_overlay")
    .select("email")
    .ilike("email", email.trim())
    .maybeSingle();
  if (existing) {
    const { error } = await sb
      .from("user_overlay")
      .update({ allowed_jobs: allowedJobs, updated_at: new Date().toISOString() })
      .eq("email", (existing as { email: string }).email);
    if (error) throw new Error(error.message);
  } else if (seed) {
    const { error } = await sb.from("user_overlay").insert({
      email: seed.email,
      name: seed.name,
      role: seed.role,
      pm_id: seed.pmId,
      allowed_jobs: allowedJobs,
    });
    if (error) throw new Error(error.message);
  } else {
    throw new Error(`No such user: ${email}`);
  }
  return (await getAllUsers()).find((u) => u.email.toLowerCase() === norm)!;
}

export async function createUser(input: {
  email: string;
  name: string;
  pmId: string | null;
  allowedJobs: string[];
}): Promise<User> {
  const norm = input.email.trim().toLowerCase();
  if (!norm.includes("@")) throw new Error("Invalid email");
  const all = await getAllUsers();
  if (all.some((u) => u.email.toLowerCase() === norm)) {
    throw new Error("A user with that email already exists");
  }
  const sb = supabaseServer();
  const { error } = await sb.from("user_overlay").insert({
    email: input.email.trim(),
    name: input.name.trim() || norm,
    role: "pm",
    pm_id: input.pmId?.trim() || null,
    allowed_jobs: input.allowedJobs,
  });
  if (error) throw new Error(error.message);
  return (await getAllUsers()).find((u) => u.email.toLowerCase() === norm)!;
}

export async function deleteUser(email: string): Promise<void> {
  // Seed users can't be hard-deleted — only their overlay row.
  const sb = supabaseServer();
  const { error } = await sb
    .from("user_overlay")
    .delete()
    .ilike("email", email.trim());
  if (error) throw new Error(error.message);
}
