"""Run all Phase 6 generators and write data/insights.json.

Pipeline:
  1. Re-run enrich_action_items (idempotent; writes binders/enriched/*.json)
  2. G1 Sequencing — uses ORIGINAL binders (PM lookup)
  3. G2 Sub drift  — uses ORIGINAL binders
  4. G3 Missed commitment — uses ENRICHED binders + daily logs
  5. Write data/insights.json

Prints stats: total insights, breakdown by type/severity/PM, G3 flag-rate.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from generators import enrich_action_items, g1_sequencing, g2_sub_drift, g3_missed_commitment
from generators._common import (
    DATA,
    insight_rank_score,
    load_binders,
    load_phase3,
)


def main() -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"=== Phase 6 generators · run started {generated_at} ===\n")

    # 1. Enrichment
    enrich_res = enrich_action_items.enrich_all()
    print("Enrichment:")
    for k, v in enrich_res["stats"].items():
        print(f"  {k}: {v}")
    print()

    # 2/3. Phase 3 + binders
    phase3 = load_phase3()
    originals = load_binders()
    enriched = g3_missed_commitment._load_enriched_binders()

    g1_out = g1_sequencing.generate(phase3, originals, generated_at)
    print(f"G1 sequencing : {len(g1_out)} insights")

    g2_out = g2_sub_drift.generate(phase3, originals, generated_at)
    print(f"G2 sub_drift  : {len(g2_out)} insights")

    g3_res = g3_missed_commitment.generate(phase3, enriched, generated_at)
    g3_out = g3_res["insights"]
    g3_stats = g3_res["stats"]
    print(f"G3 missed     : {len(g3_out)} insights")

    insights = g1_out + g2_out + g3_out
    print(f"\nTotal insights: {len(insights)}")

    # ----- breakdown -----
    by_type = Counter(ins["type"] for ins in insights)
    by_sev = Counter(ins["severity"] for ins in insights)
    by_pm = Counter(ins.get("related_pm") or "(unmapped)" for ins in insights)
    print("\nBy type:")
    for t, n in by_type.most_common():
        print(f"  {t:<25} {n}")
    print("\nBy severity:")
    for s, n in by_sev.most_common():
        print(f"  {s:<25} {n}")
    print("\nBy PM:")
    for pm, n in by_pm.most_common():
        print(f"  {pm:<25} {n}")
    print(f"\nG3 flag rate (target 2-20%): {g3_stats['flagged_pct']}% "
          f"({g3_stats['items_flagged']}/{g3_stats['items_complete_in_window']} in-window items)")

    # ----- write insights.json -----
    out_path = DATA / "insights.json"
    payload = {
        "generated_at": generated_at,
        "today": phase3["job_stages"].get("today"),
        "total_insights": len(insights),
        "by_type": dict(by_type),
        "by_severity": dict(by_sev),
        "by_pm": dict(by_pm),
        "g3_stats": g3_stats,
        "enrichment_stats": enrich_res["stats"],
        "insights": insights,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n-> wrote {out_path} ({out_path.stat().st_size:,} bytes)")

    # ----- top 10 preview -----
    print("\nTop-10 by rank score:")
    for i, ins in enumerate(sorted(insights, key=insight_rank_score, reverse=True)[:10], 1):
        pm = ins.get("related_pm") or "—"
        job = ins.get("related_job") or "—"
        print(f"  {i:>2}. [{ins['severity']:>8}] {ins['type']:<22} "
              f"{pm[:14]:<14} {job:<10} {ins['message'][:90]}")


if __name__ == "__main__":
    main()
