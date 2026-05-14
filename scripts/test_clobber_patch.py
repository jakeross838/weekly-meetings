"""Test the SELECT-then-merge clobber-prevention patch in sink_to_supabase.

Inserts a fake todo flagged as cockpit-complete, then asks sink_to_supabase
to upsert that same id with an LLM-style IN_PROGRESS row. Post-condition:
the row in Supabase is still COMPLETE with the original cockpit timestamp.

Run: python scripts/test_clobber_patch.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from process import sink_to_supabase, _supabase_client


class _ConsoleLogger:
    def info(self, msg): print(f"[info]  {msg}")
    def error(self, msg): print(f"[error] {msg}", file=sys.stderr)


TEST_ID = "TEST-CLOBBER-001"
COCKPIT_TIMESTAMP = "2026-05-13T17:00:00+00:00"


def main():
    logger = _ConsoleLogger()
    client = _supabase_client()
    if client is None:
        print("FAIL: no supabase client (check .env)")
        sys.exit(1)

    # Use a real pm_id ('bob') because todos.pm_id has a FK to pms.id. The
    # test row is filtered out of the cockpit by category=ADMIN being one of
    # many categories, but more importantly by the try/finally cleanup below
    # that runs even on assertion failure.
    fake_row = {
        "id": TEST_ID,
        "pm_id": "bob",
        "job": "TestJob",
        "title": "Test row for clobber-prevention patch (delete me if this leaks)",
        "status": "COMPLETE",
        "completed_at": COCKPIT_TIMESTAMP,
        "previous_status": "IN_PROGRESS",
        "category": "ADMIN",
        "priority": "NORMAL",
    }

    failures: list[str] = []
    try:
        client.table("todos").upsert(fake_row, on_conflict="id").execute()
        print(f"[setup] Inserted fake todo {TEST_ID} as COMPLETE @ {COCKPIT_TIMESTAMP}")

        # Build a fake binder where the LLM says IN_PROGRESS for the same id
        # (the clobber pattern — same shape as the 4 armed completes had).
        fake_binder = {
            "items": [
                {
                    "id": TEST_ID,
                    "job": "TestJob",
                    "type": "FOLLOWUP",
                    "action": "Test row for clobber-prevention patch",
                    "owner": "Test",
                    "opened": "2026-05-01",
                    "due": "2026-05-13",
                    "status": "IN_PROGRESS",
                    "priority": "NORMAL",
                    "category": "ADMIN",
                    "source": "transcript",
                    "update": (
                        "still working on it (this should be overridden by cockpit state)"
                    ),
                }
            ]
        }

        # Action: sink. Patch should preserve COMPLETE.
        sink_to_supabase("Bob Mozine", fake_binder, "test-clobber.txt", logger)

        # Verify.
        resp = (
            client.table("todos")
            .select("id, status, completed_at, previous_status")
            .eq("id", TEST_ID)
            .single()
            .execute()
        )
        row = resp.data
        print(
            f"[verify] After sink: status={row['status']} "
            f"completed_at={row['completed_at']} "
            f"previous_status={row['previous_status']}"
        )

        if row["status"] != "COMPLETE":
            failures.append(f"status: expected COMPLETE, got {row['status']!r}")
        if not row["completed_at"] or not row["completed_at"].startswith("2026-05-13"):
            failures.append(
                f"completed_at: expected to start with 2026-05-13, "
                f"got {row['completed_at']!r}"
            )
        if row["previous_status"] != "IN_PROGRESS":
            failures.append(
                f"previous_status: expected 'IN_PROGRESS', "
                f"got {row['previous_status']!r}"
            )
    finally:
        # Cleanup always runs, even on assertion failure.
        try:
            client.table("todos").delete().eq("id", TEST_ID).execute()
            print(f"[cleanup] Deleted test row {TEST_ID}")
        except Exception as e:
            print(f"[cleanup] WARNING: could not delete {TEST_ID}: {e}", file=sys.stderr)

    if failures:
        print("\nFAIL:")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("\nPASS: clobber-prevention patch is working.")
    sys.exit(0)


if __name__ == "__main__":
    main()
