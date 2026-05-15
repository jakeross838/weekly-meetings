"""Gate 1E runner: reconcile all 5 ingested meetings into items/decisions/questions.

Order: 4/30 site meetings first (cold start), then 5/07 office meeting (tests
cross-meeting dedup against the prior state).
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "brain"))

from reconciler import reconcile_meeting  # noqa: E402


def _supabase():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def main() -> int:
    client = _supabase()
    # Pull meetings ordered by meeting_date so 4/30 site meetings come before 5/07.
    r = client.table("meetings").select("id, meeting_date, job_id, meeting_type").order("meeting_date", desc=False).execute()
    meetings = r.data or []
    if not meetings:
        print("No meetings to reconcile.", file=sys.stderr)
        return 1

    print(f"Reconciling {len(meetings)} meeting(s) in date order:")
    for m in meetings:
        print(f"  {m['meeting_date']}  {m['job_id']}  {m['meeting_type']}  id={m['id'][:8]}")
    print()

    summaries = []
    total_cost = 0.0
    for m in meetings:
        print(f"--- {m['meeting_date']} {m['job_id']} {m['meeting_type']} ---")
        try:
            res = reconcile_meeting(m["id"], dry_run=False)
            total_cost += res.get("cost_usd", 0)
            print(
                f"  claims={res['claims_processed']}  "
                f"items_new={res['items_created']}  items_upd={res['items_updated']}  "
                f"decisions={res['decisions_created']}  questions={res['open_questions_created']}  "
                f"dropped={len(res['claims_dropped'])}  needs_review={len(res['needs_review'])}"
            )
            print(
                f"  sub_stages={res['sub_matches']['by_stage']}  "
                f"pay_app={res['pay_app_matches']}  "
                f"elapsed_ms={res['elapsed_ms']}  cost=${res['cost_usd']:.4f}"
            )
            summaries.append((m, res))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            summaries.append((m, {"error": str(e)}))
        print()

    print("=" * 130)
    print(f"{'Date':<11} {'Job':<10} {'Type':<7} {'Claims':>6} {'New':>5} {'Upd':>5} {'Dec':>5} {'Q':>3} {'Drop':>5} {'NR':>4} {'Cost':>8}")
    print("-" * 130)
    agg = {"claims": 0, "new": 0, "upd": 0, "dec": 0, "q": 0, "drop": 0, "nr": 0}
    for m, r in summaries:
        if "error" in r:
            print(f"{m['meeting_date']!s:<11} {m['job_id']:<10} {m['meeting_type']:<7} ERROR: {r['error']}")
            continue
        d = len(r["claims_dropped"])
        nr = len(r["needs_review"])
        print(
            f"{m['meeting_date']!s:<11} {m['job_id']:<10} {m['meeting_type']:<7} "
            f"{r['claims_processed']:>6} {r['items_created']:>5} {r['items_updated']:>5} "
            f"{r['decisions_created']:>5} {r['open_questions_created']:>3} {d:>5} {nr:>4} "
            f"${r['cost_usd']:>7.4f}"
        )
        agg["claims"] += r["claims_processed"]
        agg["new"] += r["items_created"]
        agg["upd"] += r["items_updated"]
        agg["dec"] += r["decisions_created"]
        agg["q"] += r["open_questions_created"]
        agg["drop"] += d
        agg["nr"] += nr
    print("-" * 130)
    print(
        f"{'TOTAL':<29} {agg['claims']:>6} {agg['new']:>5} {agg['upd']:>5} "
        f"{agg['dec']:>5} {agg['q']:>3} {agg['drop']:>5} {agg['nr']:>4} ${total_cost:>7.4f}"
    )
    print("=" * 130)
    return 0


if __name__ == "__main__":
    sys.exit(main())
