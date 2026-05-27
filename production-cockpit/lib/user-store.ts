// User-overlay store. The four hardcoded users in lib/auth.ts (USERS) are the
// seed; this file lets the admin panel layer additions / job-access edits on
// top WITHOUT a code change + redeploy. Overlay rows match by email and win
// over the seed.
//
// Persistence: a JSON file under production-cockpit/data/. NOT gitignored on
// purpose — it's the source of truth for "who has access to what" once any
// edit has been made, so it needs to ship with the repo.

import fs from "node:fs";
import path from "node:path";
import { USERS, type User, type Role } from "./auth-users";

const OVERLAY_PATH = path.join(process.cwd(), "data", "user-overlay.json");

interface OverlayUser {
  email: string;
  name: string;
  role: Role;
  pmId: string | null;
  allowedJobs: string[];
  // Password defaults to "password" when omitted (matches the seed behavior;
  // change-password isn't part of this MVP).
  password?: string;
}

interface OverlayFile {
  users: OverlayUser[];
}

function readOverlay(): OverlayFile {
  try {
    if (!fs.existsSync(OVERLAY_PATH)) return { users: [] };
    const raw = fs.readFileSync(OVERLAY_PATH, "utf-8");
    const parsed = JSON.parse(raw) as OverlayFile;
    if (!Array.isArray(parsed?.users)) return { users: [] };
    return parsed;
  } catch (err) {
    console.warn("[user-store] could not read overlay:", err);
    return { users: [] };
  }
}

function writeOverlay(data: OverlayFile): void {
  fs.mkdirSync(path.dirname(OVERLAY_PATH), { recursive: true });
  fs.writeFileSync(OVERLAY_PATH, JSON.stringify(data, null, 2), "utf-8");
}

function overlayToUser(o: OverlayUser): User {
  return {
    email: o.email,
    password: o.password ?? "password",
    name: o.name,
    role: o.role,
    pmId: o.pmId,
    allowedJobs: o.allowedJobs,
  };
}

// Merged users: seed + overlay. Overlay rows win by email match.
export function getAllUsers(): User[] {
  const overlay = readOverlay();
  const overlayByEmail = new Map<string, OverlayUser>();
  for (const u of overlay.users) overlayByEmail.set(u.email.toLowerCase(), u);
  const merged: User[] = USERS.map((seed) => {
    const o = overlayByEmail.get(seed.email.toLowerCase());
    if (!o) return seed;
    overlayByEmail.delete(seed.email.toLowerCase()); // consumed
    return overlayToUser({ ...o, email: seed.email }); // preserve casing
  });
  // Overlay-only users (not in seed) come after.
  for (const o of overlayByEmail.values()) {
    merged.push(overlayToUser(o));
  }
  return merged;
}

export function upsertUserAccess(email: string, allowedJobs: string[]): User {
  const norm = email.trim().toLowerCase();
  const seed = USERS.find((u) => u.email.toLowerCase() === norm);
  const overlay = readOverlay();
  const idx = overlay.users.findIndex((u) => u.email.toLowerCase() === norm);
  if (idx >= 0) {
    overlay.users[idx].allowedJobs = allowedJobs;
  } else if (seed) {
    overlay.users.push({
      email: seed.email,
      name: seed.name,
      role: seed.role,
      pmId: seed.pmId,
      allowedJobs,
    });
  } else {
    throw new Error(`No such user: ${email}`);
  }
  writeOverlay(overlay);
  // Return the merged row that callers will see.
  return getAllUsers().find((u) => u.email.toLowerCase() === norm)!;
}

export function createUser(input: {
  email: string;
  name: string;
  pmId: string | null;
  allowedJobs: string[];
}): User {
  const norm = input.email.trim().toLowerCase();
  if (!norm.includes("@")) throw new Error("Invalid email");
  if (getAllUsers().some((u) => u.email.toLowerCase() === norm)) {
    throw new Error("A user with that email already exists");
  }
  const overlay = readOverlay();
  overlay.users.push({
    email: input.email.trim(),
    name: input.name.trim() || norm,
    role: "pm",
    pmId: input.pmId?.trim() || null,
    allowedJobs: input.allowedJobs,
  });
  writeOverlay(overlay);
  return getAllUsers().find((u) => u.email.toLowerCase() === norm)!;
}

export function deleteUser(email: string): void {
  const norm = email.trim().toLowerCase();
  // Seed users can't be deleted — only their overlay row.
  const overlay = readOverlay();
  const before = overlay.users.length;
  overlay.users = overlay.users.filter((u) => u.email.toLowerCase() !== norm);
  if (overlay.users.length === before) return; // nothing to do
  writeOverlay(overlay);
}
