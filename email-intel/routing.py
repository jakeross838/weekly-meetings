#!/usr/bin/env python3
"""Ross Built - Email Intel: JOB ROUTING (pure functions, no network).

Every captured email must be attached to a REAL job so its durable intel lands
on the right job timeline. This module resolves an email to a `jobs.id` slug.

Two-stage resolver -- resolve_job_id(msg, extracted, jobs):

  1. PRIMARY (address-based, reliable). Compare the email's PEOPLE
     (sender + to + cc) against each job's addresses (client_emails[] + pm_email),
     case-insensitive, exact-address match.
       - client_emails are unique per job, so a client address pins exactly one job.
       - pm_email is SHARED across all of a PM's jobs, so on its own it over-matches.
     We therefore resolve in two tiers so the unique client signal wins:
       (a) combined overlap over (client_emails + pm_email) -- if EXACTLY ONE job
           matches, use it (the clean single-job / fully-populated case);
       (b) otherwise client_emails-only overlap -- if EXACTLY ONE job matches, use
           it (the common case: the shared pm_email matched several of the PM's
           jobs in (a), but only one job actually has this client on it).

  2. FALLBACK (name-based, only if PRIMARY is none/ambiguous). Match Claude's
     inferred `project` name string to a job by NAME using the app's
     word-boundary prefix rule -- ported verbatim from
     production-cockpit/lib/job-key.ts (jobKeyMatchesName). The `project` string
     plays the role of the free-text jobKey; the job's `name` plays jobName.
     The job with the LONGEST matching name wins.

  3. UNRESOLVED -> job_id = None. The row is still stored (with `project` set) so
     it shows up in an "unrouted" bucket a human can re-route. A warning is logged.

resolve_job_id returns (job_id_or_None, reason) where reason is one of
"address", "address:client", "name", or "unresolved".

Run `python routing.py` for an offline self-test of the matcher and resolver.
"""

import re

# Matches the JavaScript character class /[a-z0-9]/ used by lib/job-key.ts. The
# inputs are lowercased first, so this is exactly ASCII a-z and 0-9.
_ALNUM = re.compile(r"[a-z0-9]")


# ---------------------------------------------------------------------------
# Word-boundary name matcher -- ported verbatim from lib/job-key.ts:
#   jobKeyMatchesName(jobKey, jobName)
# Here `project` is the free-text key (e.g. "Clark-853 Front St", "Markgraf
# closeout") and `job_name` is the canonical short job name (e.g. "Clark").
# A job name matches iff:
#   * project == name, OR
#   * project startsWith(name) AND the next char is NOT [a-z0-9]
# so "Clark" matches "Clark-853..." and "Clark closeout" but NEVER "Clarkson-...".
# ---------------------------------------------------------------------------
def name_matches_project(project, job_name):
    if not project or not job_name:
        return False
    key = str(project).strip().lower()
    name = str(job_name).strip().lower()
    if not name:
        return False
    if key == name:
        return True
    if not key.startswith(name):
        return False
    # The char right after the matched name must NOT be alphanumeric, so we don't
    # treat "Clarkson" as a match for "Clark".
    nxt = key[len(name)] if len(key) > len(name) else ""
    return nxt != "" and _ALNUM.match(nxt) is None


# ---------------------------------------------------------------------------
# Address helpers
# ---------------------------------------------------------------------------
def _addr(obj):
    """Pull a lowercased email address out of a Graph recipient object:
    {"emailAddress": {"address": "a@b.com", "name": "..."}} -> "a@b.com"."""
    return (((obj or {}).get("emailAddress") or {}).get("address") or "").strip().lower()


def message_addresses(msg):
    """All people on the email: sender + to + cc (lowercased, deduped)."""
    people = set()
    for field in ("toRecipients", "ccRecipients"):
        for r in msg.get(field) or []:
            a = _addr(r)
            if a:
                people.add(a)
    # Sender: Graph exposes both `from` and `sender`; take whichever is present.
    for key in ("from", "sender"):
        a = _addr(msg.get(key))
        if a:
            people.add(a)
    return people


def _job_client_addresses(job):
    out = set()
    for c in job.get("client_emails") or []:
        c = (c or "").strip().lower()
        if c:
            out.add(c)
    return out


def _job_all_addresses(job):
    out = _job_client_addresses(job)
    pm = (job.get("pm_email") or "").strip().lower()
    if pm:
        out.add(pm)
    return out


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------
def resolve_job_id(msg, extracted, jobs, log=None):
    """Resolve (job_id, reason). See module docstring for the algorithm.

    msg       -- Graph message dict (from/sender, toRecipients, ccRecipients)
    extracted -- Claude's extraction record (uses its "project" field)
    jobs      -- list of dicts: {id, name, pm_email, client_emails:[...]}
    log       -- optional callable(str) for the unrouted warning
    """
    people = message_addresses(msg)

    # PRIMARY (a): combined overlap over client_emails + pm_email.
    if people:
        combined = [j for j in jobs if _job_all_addresses(j) & people]
        if len(combined) == 1:
            return combined[0].get("id"), "address"

        # PRIMARY (b): the shared pm_email matched several jobs above; the unique
        # client address disambiguates. Match on client_emails ONLY.
        client_only = [j for j in jobs if _job_client_addresses(j) & people]
        if len(client_only) == 1:
            return client_only[0].get("id"), "address:client"

    # FALLBACK: Claude's inferred project name -> job name (word-boundary prefix).
    project = (extracted or {}).get("project")
    if project:
        candidates = [j for j in jobs if name_matches_project(project, j.get("name"))]
        if candidates:
            # Longest matching name wins (e.g. "North Shore" beats "North").
            best = max(candidates, key=lambda j: len((j.get("name") or "")))
            return best.get("id"), "name"

    # UNRESOLVED -- still stored, human re-routes from the unrouted bucket.
    if log:
        log(
            "UNROUTED: no job matched  people=%s  project=%r"
            % (sorted(people), project)
        )
    return None, "unresolved"


# ---------------------------------------------------------------------------
# Offline self-test (no network). Run: python routing.py
# ---------------------------------------------------------------------------
def _selftest():
    failures = []

    def check(label, got, want):
        ok = got == want
        print(("  PASS " if ok else "  FAIL ") + label + f"  -> {got!r}")
        if not ok:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    print("name_matches_project (ported lib/job-key.ts rule):")
    # "Clark" vs "Clarkson"
    check('"Clark-853 Front St" ~ "Clark"',
          name_matches_project("Clark-853 Front St", "Clark"), True)
    check('"Clarkson-99 Bay Rd" !~ "Clark"',
          name_matches_project("Clarkson-99 Bay Rd", "Clark"), False)
    check('"Clarkson-99 Bay Rd" ~ "Clarkson"',
          name_matches_project("Clarkson-99 Bay Rd", "Clarkson"), True)
    # space boundary
    check('"Markgraf closeout" ~ "Markgraf"',
          name_matches_project("Markgraf closeout", "Markgraf"), True)
    check('"Gavin - Fitness Room Remodel" ~ "Gavin"',
          name_matches_project("Gavin - Fitness Room Remodel", "Gavin"), True)
    # exact match
    check('"Fish" == "Fish"', name_matches_project("Fish", "Fish"), True)
    # alnum boundary blocks partial
    check('"Fisher-1 Elm" !~ "Fish"',
          name_matches_project("Fisher-1 Elm", "Fish"), False)
    # no match
    check('"Krauss-427 South Blvd" !~ "Fish"',
          name_matches_project("Krauss-427 South Blvd", "Fish"), False)
    # empties
    check('empty project', name_matches_project("", "Fish"), False)
    check('empty name', name_matches_project("Fish", ""), False)

    print("\nresolve_job_id:")
    jobs = [
        {"id": "krauss", "name": "Krauss", "pm_email": "jake@rossbuilt.com",
         "client_emails": ["krauss@example.com"]},
        {"id": "fish", "name": "Fish", "pm_email": "jake@rossbuilt.com",
         "client_emails": ["fish.family@example.com"]},
        {"id": "clark", "name": "Clark", "pm_email": "jake@rossbuilt.com",
         "client_emails": ["clark@example.com"]},
        {"id": "clarkson", "name": "Clarkson", "pm_email": "dana@rossbuilt.com",
         "client_emails": ["clarkson@example.com"]},
        # longest-match demonstrator (two name-prefix candidates, space boundary)
        {"id": "north", "name": "North", "pm_email": "dana@rossbuilt.com",
         "client_emails": []},
        {"id": "north-shore", "name": "North Shore", "pm_email": "dana@rossbuilt.com",
         "client_emails": []},
    ]

    def to(*addrs):
        return [{"emailAddress": {"address": a}} for a in addrs]

    # PRIMARY (b): sender=PM (matches all of Jake's jobs via pm_email) but the
    # client recipient pins exactly one -> routes by client.
    m1 = {"from": {"emailAddress": {"address": "jake@rossbuilt.com"}},
          "toRecipients": to("krauss@example.com")}
    check("PM -> client(krauss)", resolve_job_id(m1, {}, jobs), ("krauss", "address:client"))

    # FALLBACK: unknown recipient, but Claude inferred the project name.
    m2 = {"from": {"emailAddress": {"address": "jake@rossbuilt.com"}},
          "toRecipients": to("unknown@vendor.com")}
    check("name fallback -> Fish",
          resolve_job_id(m2, {"project": "Fish"}, jobs), ("fish", "name"))

    # FALLBACK longest-match: "North Shore Reno" beats "North".
    m3 = {"toRecipients": to("someone@vendor.com")}
    check("name fallback longest -> North Shore",
          resolve_job_id(m3, {"project": "North Shore Reno"}, jobs),
          ("north-shore", "name"))

    # FALLBACK word boundary: "Clarkson-..." must NOT route to "Clark".
    m4 = {"toRecipients": to("someone@vendor.com")}
    check("name fallback -> Clarkson (not Clark)",
          resolve_job_id(m4, {"project": "Clarkson-99 Bay Rd"}, jobs),
          ("clarkson", "name"))

    # PRIMARY single clean match (client + pm both only on one job).
    solo = [{"id": "solo", "name": "Solo", "pm_email": "pm2@x.com",
             "client_emails": ["c@x.com"]}]
    m5 = {"from": {"emailAddress": {"address": "pm2@x.com"}},
          "toRecipients": to("c@x.com")}
    check("single-job PM -> address", resolve_job_id(m5, {}, solo), ("solo", "address"))

    # UNRESOLVED: no address match, no project.
    m6 = {"from": {"emailAddress": {"address": "ext@nope.com"}},
          "toRecipients": to("other@nope.com")}
    check("unresolved -> (None,'unresolved')",
          resolve_job_id(m6, {"project": None}, jobs), (None, "unresolved"))

    # UNRESOLVED: project set but matches no job name -> None (still stored upstream).
    m7 = {"toRecipients": to("other@nope.com")}
    check("unknown project -> unresolved",
          resolve_job_id(m7, {"project": "Nonexistent Job"}, jobs),
          (None, "unresolved"))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S):")
        for f in failures:
            print("  - " + f)
        raise SystemExit(1)
    print("All routing self-tests passed.")


if __name__ == "__main__":
    _selftest()
