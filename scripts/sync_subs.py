"""Sync the Supabase `subs` catalog from local sub analytics + canonical names.

Source data:
- weekly-prompt.md canonical company list (hardcoded here for now)
- data/sub-phase-rollups.json — density / reliability per (sub, phase)

Run: python scripts/sync_subs.py
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from process import _supabase_client


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60]


# Canonical sub catalog. Pulled from weekly-prompt.md "Canonical vendor / sub
# names" section plus subs that appear in sub-phase-rollups.json. `aliases`
# are the short-name / first-name forms that show up in transcripts, used
# for regex-extraction against todo title text.
CATALOG: list[dict] = [
    # From weekly-prompt.md
    {"name": "Volcano Stone, LLC",            "trade": "Stone/Masonry",   "aliases": ["Volcano Stone", "Oleg"]},
    {"name": "Tom Sanger Pool and Spa",       "trade": "Pool/Spa",        "aliases": ["Tom Sanger", "Sanger"]},
    {"name": "Rangel Custom Tile",            "trade": "Tile/Floor",      "aliases": ["Rangel"]},
    {"name": "Nemesio Mason",                 "trade": "Mason",           "aliases": ["Nemesio"]},
    {"name": "Rosa's Cast Stone",             "trade": "Stone/Masonry",   "aliases": ["Rosa"]},
    {"name": "Jeff Watts Plastering and Stucco", "trade": "Plaster/Stucco", "aliases": ["Jeff Watts", "Watts Stucco", "Watts"]},
    {"name": "Myers Painting",                "trade": "Paint",           "aliases": ["Myers Paint", "Myers"]},
    {"name": "Faust Renovations",             "trade": "Trim/Finish",     "aliases": ["Faust"]},
    {"name": "TNT Custom Painting",           "trade": "Paint",           "aliases": ["TNT", "Terry"]},
    {"name": "Michael A. Gilkey, Inc.",       "trade": "Landscape",       "aliases": ["Gilkey", "Laura at Gilkey"]},
    {"name": "Parrish Well Drilling",         "trade": "Site/Excavation", "aliases": ["Parrish Well", "Parrish"]},
    {"name": "Elizabeth Key Rosser",          "trade": "Tile/Floor",      "aliases": ["Key Rosser", "Rosser"]},
    {"name": "HBS Drywall",                   "trade": "Drywall",         "aliases": ["HBS"]},
    {"name": "Integrity Floors",              "trade": "Tile/Floor",      "aliases": ["Integrity"]},
    {"name": "Sight to See Construction",     "trade": "Trim/Finish",     "aliases": ["Sight to See", "SMS Construction", "SMS"]},
    {"name": "Campbell Cabinetry",            "trade": "Cabinetry",       "aliases": ["Campbell"]},
    {"name": "Banko Overhead Doors",          "trade": "Doors",           "aliases": ["Banko", "D&D"]},
    {"name": "Cucine Ricci",                  "trade": "Cabinetry",       "aliases": ["Cucine Ricci", "Kuchin Ricci"]},
    {"name": "First Choice Custom Cabinets",  "trade": "Cabinetry",       "aliases": ["First Choice"]},
    {"name": "Fuse Specialty Appliances",     "trade": "Appliances",      "aliases": ["Fuse", "Fuse Appliance", "Josh at Fuse"]},
    {"name": "DB Welding Inc.",               "trade": "Metal/Welding",   "aliases": ["DB Welding", "DB Fabrication", "Dave at DB"]},
    {"name": "DB Improvement Services",       "trade": "Trim/Finish",     "aliases": ["DB Improvements", "DB Improvement"]},
    {"name": "Real Woods",                    "trade": "Doors",           "aliases": ["Real Woods"]},
    {"name": "Metro Electric",                "trade": "Electrical",     "aliases": ["Metro Electric"]},
    {"name": "Lonestar Electric",             "trade": "Electrical",     "aliases": ["Lonestar Electric", "Lonestar"]},
    {"name": "Precision Stairs",              "trade": "Carpentry/Stairs","aliases": ["Precision Stairs"]},
    # From sub-phase-rollups.json that aren't in the weekly-prompt list
    {"name": "ALL Valencia Construction",     "trade": "Site/Excavation", "aliases": ["Valencia Construction", "Valencia"]},
    {"name": "Avery Roof Services, LLC",      "trade": "Roof",            "aliases": ["Avery Roof", "Avery"]},
    {"name": "Blue Vision Roofing Inc.",      "trade": "Roof",            "aliases": ["Blue Vision Roofing", "Blue Vision"]},
    {"name": "Captain Cool LLC",              "trade": "HVAC",            "aliases": ["Captain Cool"]},
    {"name": "Climatic Conditioning Company Inc", "trade": "HVAC",        "aliases": ["Climatic Conditioning", "Climatic"]},
    {"name": "CoatRite LLC",                  "trade": "Paint",           "aliases": ["CoatRite"]},
    {"name": "Doug Naeher Drywall Inc.",      "trade": "Drywall",         "aliases": ["Doug Naeher", "Naeher Drywall"]},
    {"name": "EcoSouth",                      "trade": "Insulation",      "aliases": ["EcoSouth"]},
    {"name": "Florida Sunshine Carpentry LLC","trade": "Carpentry/Stairs","aliases": ["Florida Sunshine", "Sunshine Carpentry"]},
    {"name": "Gator Plumbing",                "trade": "Plumbing",        "aliases": ["Gator"]},
    {"name": "Gonzalez Construction Services FL LLC", "trade": "Windows/Doors", "aliases": ["Gonzalez Construction", "Gonzalez"]},
    {"name": "Kimal Lumber Company",          "trade": "Lumber",          "aliases": ["Kimal Lumber", "Kimal"]},
    {"name": "M&J Florida Enterprise LLC",    "trade": "Siding",          "aliases": ["M&J Florida", "M&J"]},
    {"name": "ML Concrete, LLC",              "trade": "Concrete",        "aliases": ["ML Concrete"]},
    {"name": "Ross Built Crew",               "trade": "Internal",        "aliases": ["Ross Built Crew", "Internal Crew", "Ross Built internal"]},
    {"name": "WG Quality",                    "trade": "Drywall",         "aliases": ["WG Quality"]},
    {"name": "SmartShield Homes LLC",         "trade": "Audio/Video",     "aliases": ["SmartShield", "Smart Home", "Mark"]},
    {"name": "Triple H Painting",             "trade": "Paint",           "aliases": ["Triple H Painting", "Jerry"]},
    {"name": "Universal Windows",             "trade": "Windows/Doors",   "aliases": ["Universal Windows"]},
    {"name": "Detweilers Propane Gas",        "trade": "Plumbing",        "aliases": ["Detweilers", "Detweiler"]},
    # Additions from backfill audit on existing 249 todos
    {"name": "Creative Electric Services",    "trade": "Electrical",     "aliases": ["Creative Electric Services", "Creative Electric"]},
    {"name": "Cottrell Construction",         "trade": "Concrete",        "aliases": ["Cottrell"]},
    {"name": "Scranton Elevator",             "trade": "Elevator",        "aliases": ["Scranton"]},
    {"name": "Ebro Low Voltage",              "trade": "Audio/Video",     "aliases": ["Ebro"]},
    {"name": "Forbes & Lomax",                "trade": "Lighting/Fixtures","aliases": ["Forbes & Lomax", "Forbes and Lomax"]},
    {"name": "Sidral Docks",                  "trade": "Dock/Marine",     "aliases": ["Sidral"]},
    {"name": "Smarthouse Integration",        "trade": "Audio/Video",     "aliases": ["Smarthouse Integration", "Smarthouse"]},
    {"name": "Walter Drywall",                "trade": "Drywall",         "aliases": ["Walter backup", "Walter drywall"]},
]


def _compute_rating(rollups: list[dict]) -> tuple[float | None, list[str]]:
    """Compute a 1.0–5.0 star rating + human-readable basis from a sub's
    sub-phase rollup entries.

    Approach: start at 5.0 (clean record), subtract for problem patterns:
      • flagged for PM binder           -1.5
      • avg return-burst rate > 50%     -1.0  (callbacks / redos)
      • avg return-burst rate > 30%     -0.5
      • avg punch-burst rate > 30%      -0.5  (punch-list rework)
      • any phase labeled 'dragging'    -0.5 each (cap -1.5)
      • performed on ≥3 jobs (bonus)    +0.0  (no bonus, just baseline)

    Returns (rating, list_of_basis_strings). When no rollups, returns
    (None, ["No Buildertrend data yet · rating fills in on next sync"])."""
    if not rollups:
        return None, ["No Buildertrend data yet · rating fills in on next sync"]

    rating = 5.0
    basis: list[str] = []

    flagged_phases = [r for r in rollups if r.get("flag_for_pm_binder")]
    if flagged_phases:
        rating -= 1.5
        phase_names = ", ".join(p.get("phase_name", "?") for p in flagged_phases[:3])
        basis.append(
            f"−1.5 · Flagged in PM binder on {len(flagged_phases)} phase(s) "
            f"({phase_names}{'…' if len(flagged_phases) > 3 else ''})"
        )

    if rollups:
        avg_return = sum(r.get("return_burst_rate") or 0 for r in rollups) / len(rollups)
        if avg_return > 0.5:
            rating -= 1.0
            basis.append(f"−1.0 · High return-burst rate {avg_return:.0%} (frequent callbacks)")
        elif avg_return > 0.3:
            rating -= 0.5
            basis.append(f"−0.5 · Moderate return-burst rate {avg_return:.0%}")

        avg_punch = sum(r.get("punch_burst_rate") or 0 for r in rollups) / len(rollups)
        if avg_punch > 0.3:
            rating -= 0.5
            basis.append(f"−0.5 · Punch-burst rate {avg_punch:.0%} (punch-list rework)")

    dragging = [r for r in rollups if r.get("primary_density_label") == "dragging"]
    if dragging:
        deduction = min(0.5 * len(dragging), 1.5)
        rating -= deduction
        basis.append(
            f"−{deduction:.1f} · {len(dragging)} phase(s) below benchmark pace "
            f"(longer than typical to complete)"
        )

    if not basis:
        rating = 5.0
        continuous = [r for r in rollups if r.get("primary_density_label") == "continuous"]
        if continuous:
            basis.append(
                f"5.0★ baseline · {len(continuous)} phase(s) at steady pace · no flags"
            )
        else:
            basis.append("5.0★ baseline · no flags found in BT analytics")

    rating = max(1.0, min(5.0, round(rating, 2)))
    return rating, basis


def main():
    client = _supabase_client()
    if client is None:
        print("FAIL: no supabase client (check .env)")
        sys.exit(1)

    # Load BT analytics
    rollups_path = ROOT / "data" / "sub-phase-rollups.json"
    rollups_by_sub: dict[str, list[dict]] = {}
    if rollups_path.exists():
        data = json.loads(rollups_path.read_text(encoding="utf-8"))
        for r in data.get("rollups", []):
            rollups_by_sub.setdefault(r["sub"], []).append(r)
        print(f"Loaded rollups for {len(rollups_by_sub)} subs from {rollups_path.name}")
    else:
        print(f"WARN: {rollups_path} missing — rating will be NULL for all subs")

    rows = []
    for entry in CATALOG:
        slug = _slug(entry["name"])
        rollup_entries = rollups_by_sub.get(entry["name"], [])
        rating, basis = _compute_rating(rollup_entries)
        if rollup_entries:
            densities = [r["primary_density"] for r in rollup_entries if r.get("primary_density") is not None]
            avg_density = sum(densities) / len(densities) if densities else None
            jobs = max((r.get("jobs_performed", 0) or 0) for r in rollup_entries)
            flagged = any(r.get("flag_for_pm_binder") for r in rollup_entries)
            flag_reasons: list[str] = []
            for r in rollup_entries:
                if r.get("flag_for_pm_binder") and r.get("flag_reasons"):
                    flag_reasons.extend(r["flag_reasons"])
            reliability = int(round(avg_density * 100)) if avg_density is not None else None
            # Avg active days per (sub, phase, job) — pulled directly from the
            # BT rollup data so we can show "this sub typically takes N days
            # for this phase" without the density vocabulary.
            day_medians = [r.get("primary_active_days_median") for r in rollup_entries if r.get("primary_active_days_median")]
            avg_days = round(sum(day_medians) / len(day_medians), 1) if day_medians else None
        else:
            reliability = None
            jobs = None
            flagged = False
            flag_reasons = []
            avg_days = None
        rows.append({
            "id": slug,
            "name": entry["name"],
            "trade": entry["trade"],
            "aliases": entry["aliases"],
            "rating": rating,
            "reliability_pct": reliability,
            "avg_days_per_job": avg_days,
            "jobs_performed": jobs,
            "flagged_for_pm_binder": flagged,
            "flag_reasons": flag_reasons[:5] or None,
            "rating_basis": basis,
        })

    client.table("subs").upsert(rows, on_conflict="id").execute()
    print(f"Upserted {len(rows)} subs.")

    rated = sum(1 for r in rows if r["rating"] is not None)
    print(f"  Of which {rated} have BT-derived rating; {len(rows) - rated} pending data.")


if __name__ == "__main__":
    main()
