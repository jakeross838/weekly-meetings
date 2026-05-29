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
  disabled: boolean | null;
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
    .select("email, name, role, pm_id, allowed_jobs, password, disabled");
  if (error) {
    console.warn("[user-store] could not read user_overlay:", error.message);
    return [];
  }
  return (data ?? []) as OverlayRow[];
}

// Merged users for ACTIVE sign-in + visibility: disabled overlay rows are
// excluded entirely. If a seed user has a disabled overlay, the seed user is
// also excluded (the overlay disable wins). Used by login + page guards.
export async function getAllUsers(): Promise<User[]> {
  return (await getAllUsersIncludingDisabled()).filter((u) => !u._disabled).map(stripFlag);
}

// Same shape but includes the `_disabled` flag, so the admin panel can render
// disabled users in the list (greyed out) while still letting an admin
// re-enable them.
export interface AdminUser extends User {
  _disabled: boolean;
  _seedOnly: boolean;
}
export async function getAllUsersIncludingDisabled(): Promise<AdminUser[]> {
  const overlay = await readOverlay();
  const overlayByEmail = new Map<string, OverlayRow>();
  for (const r of overlay) overlayByEmail.set(r.email.toLowerCase(), r);
  const merged: AdminUser[] = USERS.map((seed) => {
    const r = overlayByEmail.get(seed.email.toLowerCase());
    if (!r) return { ...seed, _disabled: false, _seedOnly: true };
    overlayByEmail.delete(seed.email.toLowerCase()); // consumed
    return {
      ...rowToUser({ ...r, email: seed.email }),
      _disabled: r.disabled === true,
      _seedOnly: false,
    };
  });
  Array.from(overlayByEmail.values()).forEach((r) =>
    merged.push({
      ...rowToUser(r),
      _disabled: r.disabled === true,
      _seedOnly: false,
    })
  );
  return merged;
}

function stripFlag(u: AdminUser): User {
  const { _disabled, _seedOnly, ...rest } = u;
  return rest as User;
}

// Helper: load (or insert seed-mirror of) the overlay row for an email so any
// admin update has a row to write to. Returns the canonical email (preserved
// casing) to use as the .eq() key in the subsequent UPDATE.
async function ensureOverlayRow(email: string): Promise<string> {
  const norm = email.trim().toLowerCase();
  const seed = USERS.find((u) => u.email.toLowerCase() === norm);
  const sb = supabaseServer();
  const { data: existing } = await sb
    .from("user_overlay")
    .select("email")
    .ilike("email", email.trim())
    .maybeSingle();
  if (existing) return (existing as { email: string }).email;
  if (!seed) throw new Error(`No such user: ${email}`);
  const { error } = await sb.from("user_overlay").insert({
    email: seed.email,
    name: seed.name,
    role: seed.role,
    pm_id: seed.pmId,
    allowed_jobs: [],
  });
  if (error) throw new Error(error.message);
  return seed.email;
}

export async function upsertUserAccess(
  email: string,
  allowedJobs: string[]
): Promise<User> {
  const norm = email.trim().toLowerCase();
  const key = await ensureOverlayRow(email);
  const sb = supabaseServer();
  const { error } = await sb
    .from("user_overlay")
    .update({ allowed_jobs: allowedJobs, updated_at: new Date().toISOString() })
    .eq("email", key);
  if (error) throw new Error(error.message);
  return (await getAllUsers()).find((u) => u.email.toLowerCase() === norm)!;
}

export async function setUserPassword(email: string, password: string): Promise<void> {
  if (!password) throw new Error("password required");
  const key = await ensureOverlayRow(email);
  const sb = supabaseServer();
  const { error } = await sb
    .from("user_overlay")
    .update({ password, updated_at: new Date().toISOString() })
    .eq("email", key);
  if (error) throw new Error(error.message);
}

export async function setUserDisabled(email: string, disabled: boolean): Promise<void> {
  const key = await ensureOverlayRow(email);
  const sb = supabaseServer();
  const { error } = await sb
    .from("user_overlay")
    .update({ disabled, updated_at: new Date().toISOString() })
    .eq("email", key);
  if (error) throw new Error(error.message);
}

export async function setUserRole(email: string, role: Role): Promise<void> {
  if (role !== "admin" && role !== "pm") throw new Error("role must be admin or pm");
  const key = await ensureOverlayRow(email);
  const sb = supabaseServer();
  const { error } = await sb
    .from("user_overlay")
    .update({ role, updated_at: new Date().toISOString() })
    .eq("email", key);
  if (error) throw new Error(error.message);
}

export async function createUser(input: {
  email: string;
  name: string;
  pmId: string | null;
  allowedJobs: string[];
  password?: string;
}): Promise<User> {
  const norm = input.email.trim().toLowerCase();
  if (!norm.includes("@")) throw new Error("Invalid email");
  const all = await getAllUsersIncludingDisabled();
  if (all.some((u) => u.email.toLowerCase() === norm)) {
    throw new Error("A user with that email already exists");
  }
  const sb = supabaseServer();
  const cleanName = input.name.trim() || norm;
  const pmId = input.pmId?.trim() || null;
  const { error } = await sb.from("user_overlay").insert({
    email: input.email.trim(),
    name: cleanName,
    role: "pm",
    pm_id: pmId,
    allowed_jobs: input.allowedJobs,
    password: input.password?.trim() || null,
  });
  if (error) throw new Error(error.message);

  // Two-way sync: if the new user has a brand-new pmId that's not already in
  // the `pms` table, insert it so the new PM shows up in dropdowns (e.g. on
  // /admin/jobs) and on per-PM views. Idempotent via upsert on `id`.
  if (pmId) {
    const { error: pmErr } = await sb
      .from("pms")
      .upsert(
        { id: pmId, full_name: cleanName, active: true },
        { onConflict: "id", ignoreDuplicates: false }
      );
    if (pmErr) {
      console.warn("[user-store] pms upsert failed (non-fatal):", pmErr.message);
    }
  }

  return (await getAllUsers()).find((u) => u.email.toLowerCase() === norm)!;
}

export async function deleteUser(email: string): Promise<void> {
  // Seed users can't be hard-deleted — only their overlay row. To revoke a
  // seed user use setUserDisabled instead.
  const sb = supabaseServer();
  const { error } = await sb
    .from("user_overlay")
    .delete()
    .ilike("email", email.trim());
  if (error) throw new Error(error.message);
}
