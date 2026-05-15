"""Gate 1F runner: audit + retry each of the 5 reconciled meetings."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "brain"))

from retry_orchestrator import audit_and_retry  # noqa: E402


def _supabase():
    from supabase import create_client
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def main() -> int:
    client = _supabase()
    r = client.table("meetings").select("id, meeting_date, job_id, meeting_type").order("meeting_date", desc=False).execute()
    meetings = r.data or []
    if not meetings:
        print("No meetings to audit.", file=sys.stderr)
        return 1

    print(f"Auditing {len(meetings)} meeting(s):")
    for m in meetings:
        print(f"  {m['meeting_date']}  {m['job_id']}  {m['meeting_type']}  id={m['id'][:8]}")
    print()

    summaries = []
    total_cost = 0.0
    for m in meetings:
        print(f"--- {m['meeting_date']} {m['job_id']} {m['meeting_type']} ---")
        try:
            res = audit_and_retry(m["id"])
            total_cost += res.get("total_cost_usd", 0)
            n_mech_init = len(res["audit_initial"]["mechanical_issues"])
            n_llm_init = len(res["audit_initial"]["llm_issues"])
            print(
                f"  initial: mechanical={n_mech_init}  llm={n_llm_init}  severity={res['audit_initial']['severity']}"
            )
            if res["retried"]:
                n_mech_final = len(res["audit_final"]["mechanical_issues"])
                n_llm_final = len(res["audit_final"]["llm_issues"])
                print(
                    f"  retried! after retry: mechanical={n_mech_final}  llm={n_llm_final}  "
                    f"severity={res['audit_final']['severity']}  final={res['final_severity']}"
                )
            else:
                print(f"  no retry. final_severity={res['final_severity']}")
            print(f"  cost=${res['total_cost_usd']:.4f}  elapsed_ms={res['elapsed_ms']}")
            summaries.append((m, res))
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            summaries.append((m, {"error": str(e)}))
        print()

    print("=" * 120)
    print(f"{'Date':<11} {'Job':<10} {'Type':<7} {'Mech':>4} {'LLM':>4} {'Severity':<12} {'Retried':<8} {'Final':<14} {'Cost':>8}")
    print("-" * 120)
    for m, r in summaries:
        if "error" in r:
            print(f"{m['meeting_date']!s:<11} {m['job_id']:<10} {m['meeting_type']:<7} ERROR: {r['error']}")
            continue
        ai = r["audit_initial"]
        af = r.get("audit_final", ai)
        mech_initial = len(ai["mechanical_issues"])
        llm_initial = len(ai["llm_issues"])
        print(
            f"{m['meeting_date']!s:<11} {m['job_id']:<10} {m['meeting_type']:<7} "
            f"{mech_initial:>4} {llm_initial:>4} {ai['severity']:<12} {('yes' if r['retried'] else 'no'):<8} "
            f"{r['final_severity']:<14} ${r['total_cost_usd']:>7.4f}"
        )
    print("-" * 120)
    print(f"TOTAL COST: ${total_cost:.4f}")
    print("=" * 120)
    return 0


if __name__ == "__main__":
    sys.exit(main())
