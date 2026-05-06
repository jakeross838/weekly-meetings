"""
Shared constants for the Ross Built weekly-meetings binder system.

Single source of truth for PM/job mappings, item status taxonomy, and the
canonical Buildertrend daily-logs path. Imported by process.py,
fetch_daily_logs.py, generate_monday_binder.py, server.py, email_sender.py
to eliminate the previously-duplicated definitions.
"""

from __future__ import annotations

from pathlib import Path


# PM -> list of job short names. Used everywhere a PM/job mapping is needed.
PM_JOBS: dict[str, list[str]] = {
    "Martin Mannix":   ["Fish"],
    "Jason Szykulski": ["Pou", "Dewberry", "Harllee"],
    "Lee Worthy":      ["Krauss", "Ruthven"],
    "Bob Mozine":      ["Drummond", "Molinari", "Biales"],
    "Nelson Belanger": ["Markgraf", "Clark", "Johnson"],
}

# Short job name -> full Buildertrend job key (the long "Short-StreetAddress"
# form used throughout the scraper output).
JOB_NAME_MAP: dict[str, str] = {
    "Fish":     "Fish-715 North Shore Dr",
    "Markgraf": "Markgraf-5939 River Forest Circle",
    "Dewberry": "Dewberry-681 Key Royale Dr",
    "Pou":      "Pou-109 Seagrape Ln",
    "Krauss":   "Krauss-427 South Blvd of the Presidents",
    "Harllee":  "Harllee-215 Sycamore",
    "Molinari": "Molinari-791 North Shore Dr",
    "Ruthven":  "Ruthven-673 Dream Island Rd",
    "Drummond": "Drummond-501 74th St",
    "Clark":    "Clark-853 North Shore Dr",
    "Biales":   "Biales-103 Seagrape Ln",
}

# Reverse lookup: short -> PM canonical name. Derived from PM_JOBS so the
# two cannot drift apart.
JOB_TO_PM: dict[str, str] = {
    short: pm for pm, jobs in PM_JOBS.items() for short in jobs
}

# Render order on the Monday binder page — alphabetical by last name.
PM_ORDER: list[str] = [
    "Nelson Belanger",
    "Martin Mannix",
    "Bob Mozine",
    "Jason Szykulski",
    "Lee Worthy",
]

# Migration map for legacy item statuses (pre-taxonomy binders).
OLD_TO_NEW_STATUS: dict[str, str] = {
    "OPEN":        "NOT_STARTED",
    "IN PROGRESS": "IN_PROGRESS",
    "IN_PROGRESS": "IN_PROGRESS",
    "DONE":        "COMPLETE",
    "KILLED":      "COMPLETE",
    "COMPLETE":    "COMPLETE",
    "BLOCKED":     "BLOCKED",
    "NOT_STARTED": "NOT_STARTED",
    "DISMISSED":   "DISMISSED",
}

# Statuses that count as "closed" (excluded from active dashboard counts and
# trigger setting closed_date on the item).
CLOSED_STATUSES: set[str] = {"COMPLETE", "DISMISSED"}

# Canonical path to the Buildertrend scraper's daily-logs output. The
# weekly-meetings system never writes to this file; it only reads.
DAILY_LOGS_PATH: Path = Path(r"C:\Users\Jake\buildertrend-scraper\data\daily-logs.json")
