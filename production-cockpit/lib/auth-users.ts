// User types + seed list. Split out from lib/auth.ts so lib/user-store.ts
// can import the seed without pulling node:crypto into the wrong runtimes.
// Passwords are plaintext literals — same trade-off documented at the top of
// lib/auth.ts.

export type Role = "admin" | "pm";

export interface User {
  email: string;
  password: string;
  name: string;
  role: Role;
  pmId: string | null;
  // Job slugs (matches `jobs.id`) the user can see. Admin uses ["*"].
  allowedJobs: string[];
}

export const USERS: User[] = [
  {
    email: "jake@rossbuilt.com",
    password: "password",
    name: "Jake Ross",
    role: "admin",
    pmId: null,
    allowedJobs: ["*"],
  },
  {
    // Second admin login that uses Jake's actual Gmail address. On the Resend
    // free tier, only emails to the account-owner address (jakeross838@gmail.com)
    // are accepted — sending to jake@rossbuilt.com gets blocked with a
    // validation_error until the rossbuilt.com domain is verified in Resend.
    // Logging in as this user means forgot-password and other email flows
    // actually land in the inbox.
    email: "jakeross838@gmail.com",
    password: "password",
    name: "Jake Ross",
    role: "admin",
    pmId: null,
    allowedJobs: ["*"],
  },
  {
    email: "bob@rossbuilt.com",
    password: "password",
    name: "Bob Mozine",
    role: "pm",
    pmId: "bob",
    allowedJobs: ["molinari", "pou"],
  },
  {
    email: "nelson@rossbuilt.com",
    password: "password",
    name: "Nelson Belanger",
    role: "pm",
    pmId: "nelson",
    allowedJobs: ["dewberry", "clark"],
  },
  {
    email: "lee@rossbuilt.com",
    password: "password",
    name: "Lee Worthy",
    role: "pm",
    pmId: "lee",
    allowedJobs: ["ruthven", "krauss"],
  },
  {
    email: "martin@rossbuilt.com",
    password: "password",
    name: "Martin Mannix",
    role: "pm",
    pmId: "martin",
    allowedJobs: ["fish"],
  },
];
