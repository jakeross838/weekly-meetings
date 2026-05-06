"""
Generate monday-binder.html — a purpose-built, meeting-flow-ordered view of
every PM's binder, produced from scratch (no longer wraps pm-binder.html).

Design aesthetic: Emil — restrained neutrals, Inter, tabular numerals,
soft shadows, paper-and-ink. Ross Built stone-blue (#5B8699) is the single
accent color.

Pipeline:
  1. Load all 5 binder JSONs from binders/
  2. Cross-reference api-responses/ + transcripts/processed/ to build a
     processing-history timeline per PM
  3. Emit a fully self-contained HTML file with embedded data + renderers

Hard constraints (see wm31.txt):
  - Don't touch server.py, process.py, weekly-prompt.md, fetch_daily_logs.py,
    pm-binder.html, buildertrend-scraper
  - Keep all existing functionality: Edit/Dismiss/status dropdown/refresh flow
  - Inter via CDN, no local fonts, no new JS deps
"""

from __future__ import annotations

import html as _html
import json
import re
import sys
import traceback
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import holidays as _holidays_pkg
from fetch_daily_logs import fetch_for_pm
from constants import (
    PM_ORDER,
    PM_JOBS,
    JOB_NAME_MAP,
    JOB_TO_PM,
    OLD_TO_NEW_STATUS,
    CLOSED_STATUSES,
    DAILY_LOGS_PATH,
)

SCRIPT_DIR   = Path(__file__).parent.resolve()
BINDERS_DIR  = SCRIPT_DIR / "binders"
API_DIR      = SCRIPT_DIR / "api-responses"
PROCESSED    = SCRIPT_DIR / "transcripts" / "processed"
OUTPUT       = SCRIPT_DIR / "monday-binder.html"

# Curated palette — cycles per job (see wm31 Step 5).
JOB_COLORS = {
    "Fish":      "#5B8699",  # Ross Built brand
    "Markgraf":  "#475569",
    "Clark":     "#047857",
    "Pou":       "#b45309",
    "Dewberry":  "#6d28d9",
    "Harllee":   "#be123c",
    "Krauss":    "#0e7490",
    "Ruthven":   "#0f766e",
    "Drummond":  "#c2410c",
    "Molinari":  "#a21caf",
    "Biales":    "#4d7c0f",
    "Johnson":   "#0369a1",
}

# ---------------------------------------------------------------------------
# Phase 5 — tooltip dictionary (single source of truth for jargon definitions)
#
# Lookup keys are uppercase. Both the Python render path (PM packets) and the
# JS render path (Jake's binder) read from this dict — JS gets it via the
# {TOOLTIPS_JSON} substitution into JS_TEMPLATE.
# ---------------------------------------------------------------------------

TOOLTIPS: dict[str, str] = {
    # Stat tile labels — cover + per-job pages
    "TOTAL LOG-DAYS":  "Number of distinct days a daily log was filed for this job.",
    "LOG-DAYS":        "Number of distinct days a daily log was filed for this job.",
    "PERSON-DAYS":     "Sum of crew sizes across all daily logs. 5 workers on site for 4 days = 20 person-days.",
    "AVG CREW":        "Average number of workers on site per logged day. \u2018pk\u2019 shows the single-day peak.",
    "AVG CREW \u00b7 PEAK": "Average workers per logged day. The 'peak NN' suffix is the single-day high.",
    "UNIQUE SUBS":     "Number of distinct subcontractor companies who appeared in daily logs on this job.",
    "DELIVERY DAYS":   "Number of distinct days a material delivery was logged.",
    "INSPECTION DAYS": "Number of distinct days an inspection occurred.",
    "LAST LOG":        "How long since the most recent daily log. \u26a0 flag means stale for an active job.",

    # Meeting-section labels (PM packet + Jake binder)
    "OPEN":            "Total open follow-up items for this PM.",
    "OPEN ITEMS":      "Total open follow-up items for this PM.",
    "URGENT":          "Items flagged URGENT priority \u2014 needs action this week.",
    "STALE":           "Open items where no progress has been logged in 14+ days. Pattern signal \u2014 worth escalating.",
    "STALE 14D+":      "Open items where no progress has been logged in 14+ days. Pattern signal \u2014 worth escalating.",
    "PPC":             "Percent Plan Complete. Of items committed last week, how many actually got done. Industry-standard schedule-reliability metric.",
    "14D+":            "This item has been open for 14+ days without progress.",

    # Subs table columns (Jake binder)
    "RECENT (30D)":    "Days this sub appeared in daily logs over the last 30 days.",
    "RECENT 30D":      "Days this sub appeared in daily logs over the last 30 days.",
    "RECENT JOBS":     "Number of distinct jobs this sub touched in the last 30 days.",
    "LIFETIME DAYS":   "Total days this sub has appeared in daily logs across all time.",
    "TOTAL JOBS":      "Number of distinct jobs this sub has ever touched.",
    "ABSENCES":        "Days this sub was scheduled but did not show. Number in parens = absences in last 30 days.",
    "RELIABILITY":     "Show-up rate: (scheduled days minus absences) divided by scheduled days.",
    "LAST SEEN":       "Calendar date of this sub's most recent daily-log appearance.",
    "DURATION VS PEERS":   "How long this sub typically takes per phase compared to other subs in the same trade. Tick = sub's median days; band = trade P25\u2013P75; strip = full range.",
    "RELIABILITY VS PEERS": "This sub's show-up rate vs the trade average. Delta is points above/below the average of subs in the same trade with \u226510 lifetime days.",
    "RECENT ACTIVITY": "Days on site over the last 30 days, with the 13-month sparkline behind it.",

    # Phase Durations table columns (Jake binder)
    "MED":             "Median duration in days for this phase across all completed instances.",
    "MEDIAN":          "Median duration in days for this phase across all completed instances.",
    "P25-P75":         "Interquartile range. 25% of jobs finished faster than P25; 75% finished faster than P75. The middle 50% lands in this range.",
    "P25\u2013P75":    "Interquartile range. 25% of jobs finished faster than P25; 75% finished faster than P75. The middle 50% lands in this range.",
    "RANGE":           "Fastest-to-slowest duration across all completed instances of this phase.",
    "SPAN":            "Calendar days from first activity to last activity on this phase, including gaps. Different from duration \u2014 a 4-day phase can have a 60-day span if work paused mid-phase.",
    "JOBS":            "Total number of jobs this phase has been performed on.",
    "ACTIVE":          "Number of jobs currently in this phase.",

    # Per-sub-on-phase status icons
    "\u2713 WITHIN RANGE":   "This sub's duration on this phase fell within the typical P25\u2013P75 range.",
    "WITHIN RANGE":          "This sub's duration on this phase fell within the typical P25\u2013P75 range.",
    "\u26a0 ABOVE MEDIAN":   "This sub took longer than the median. Worth understanding why.",
    "ABOVE MEDIAN":          "This sub took longer than the median. Worth understanding why.",
    "\u26a1 BELOW MEDIAN":   "Faster than median. Could be efficiency, could be incomplete scope \u2014 worth a quick check.",
    "BELOW MEDIAN":          "Faster than median. Could be efficiency, could be incomplete scope \u2014 worth a quick check.",
    "INSUFFICIENT SAMPLES":  "Not enough completed jobs yet to compute a typical range. Treat numbers as preliminary.",
    "(INSUFFICIENT SAMPLES)": "Not enough completed jobs yet to compute a typical range. Treat numbers as preliminary.",

    # Activity timeline status pills (per-job pages)
    "COMPLETE":      "Phase finished. Duration shown is the longest substantial work burst.",
    "ONGOING":       "Phase still active \u2014 sub still showing up in daily logs.",
    "MULTI-BURST":   "Phase had multiple separate work periods rather than one continuous burst.",
    "INTERMITTENT":  "Sub appeared on this phase but in scattered one-off visits, not a sustained burst. Active-day count is shown instead of inflated calendar span.",

    # Workforce histogram
    "PERSON-DAYS PER MONTH (LAST 13 MO)":
        "Total person-days logged each month. Each bar = one month. Trends up/down show whether the job is staffing up or winding down.",

    # Look-ahead table
    "WINDOW":      "How far out the item is. \u2018This week\u2019 / \u2018Next 2 weeks\u2019 / \u2018Within 30 days\u2019 / \u201830+ days\u2019.",
    "CONFIRM-BY":  "Phone call or written confirmation needed by this date before the work can start.",

    # Open items
    "HIGH":      "Priority level set when the item was opened.",
    "FOLLOWUP":  "Item type: a previously-opened action that's still open and being tracked week-to-week.",
    "PRIORITY":  "Priority level set when the item was opened (Urgent / High / Normal).",

    # Missed-logs banner
    "DAILY LOGS MISSED ON WORKDAYS":
        "Workdays = Mon\u2013Fri excluding US federal holidays. Closeout and pre-active jobs are excluded.",
    "MISSED DAILY LOGS":
        "Workdays = Mon\u2013Fri excluding US federal holidays. Closeout and pre-active jobs are excluded.",

    # Phase 5 — added beyond user's pre-listed terms (flagged in output for review)
    "AGING":     "Item has been open between 7 and 14 days \u2014 starting to need attention.",
    "FRESH":     "Item opened within the last 7 days.",
    "ABANDONED": "Item has been open 30+ days without progress \u2014 likely needs to be re-scoped or killed.",
    "WEEK":      "Week number of the year (1\u201352).",
    "GP":        "Gross Profit \u2014 projected dollars left on this job after subtracting all costs from contract value.",
    "TARGET CO": "Target Certificate of Occupancy date \u2014 when the homeowner is expected to be able to move in.",
}

# Inline SVG used by every hint(). Kept compact — same icon in JS and Python.
_TIP_ICON_SVG = (
    '<svg class="tip-icon" viewBox="0 0 16 16" aria-hidden="true">'
    '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.25"/>'
    '<circle cx="8" cy="5" r="0.9" fill="currentColor"/>'
    '<line x1="8" y1="7.5" x2="8" y2="12" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/>'
    '</svg>'
)


def hint(label: str) -> str:
    """Wrap a label in a hover-tooltip span if it's in the dictionary.

    Lookup is case-insensitive and trims trailing/leading whitespace. If the
    label isn't a known jargon term, returns it unchanged (HTML-escaped) so
    callers can apply this universally without worrying about over-wrapping.
    Emits class="tip" (not "hint" — that class is already taken by the
    pre-existing eyebrow style).
    """
    if label is None:
        return ""
    key = str(label).strip().upper()
    definition = TOOLTIPS.get(key)
    safe_label = _html.escape(str(label))
    if not definition:
        return safe_label
    safe_def = _html.escape(definition, quote=True)
    return f'<span class="tip" tabindex="0" data-hint="{safe_def}">{safe_label}{_TIP_ICON_SVG}</span>'


def _norm_status(s: str) -> str:
    return OLD_TO_NEW_STATUS.get(s or "", s or "")


def _aging_flag(item: dict, today: date) -> str:
    if item.get("aging_flag"):
        return item["aging_flag"]
    opened = item.get("opened")
    if not opened:
        return "fresh"
    try:
        od = datetime.strptime(opened, "%Y-%m-%d").date()
    except ValueError:
        return "fresh"
    days_open = (today - od).days
    if days_open < 7:
        return "fresh"
    if days_open < 14:
        return "aging"
    if days_open < 30:
        return "stale"
    return "abandoned"


def _load_binder(pm: str) -> tuple[dict | None, datetime | None]:
    fname = pm.replace(" ", "_") + ".json"
    path = BINDERS_DIR / fname
    if not path.exists():
        return None, None
    return json.loads(path.read_text(encoding="utf-8")), datetime.fromtimestamp(path.stat().st_mtime)


# ---------------------------------------------------------------------------
# Transcript history reconstruction (Phase 8 new feature)
# ---------------------------------------------------------------------------

def _parse_ts(name: str, pattern: str) -> datetime | None:
    m = re.search(pattern, name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def _extract_binder_from_raw(raw_text: str) -> dict | None:
    """Pull the JSON binder out of a raw Claude response file."""
    m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", raw_text)
    if not m:
        m = re.search(r"(\{[\s\S]*\})", raw_text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def build_transcript_history() -> dict[str, list[dict]]:
    """For every PM, walk api-responses/*.json (backups) + *_raw.txt (post-state)
    and pair them into a sequence of processing events.

    Returns { "Martin Mannix": [ { transcript, processed_at, pre_count,
        post_count, delta, reconciliation_entries }, ... ], ... }
    sorted newest first.
    """
    history: dict[str, list[dict]] = {pm: [] for pm in PM_ORDER}
    if not API_DIR.exists():
        return history

    processed_files: list[Path] = list(PROCESSED.iterdir()) if PROCESSED.exists() else []

    for pm in PM_ORDER:
        pm_safe = pm.replace(" ", "_")
        first_name = pm.split()[0]

        backups = [(p, _parse_ts(p.name, r"_backup_(\d{8}_\d{6})\.json$"))
                   for p in API_DIR.glob(f"{pm_safe}_backup_*.json")]
        backups = [(p, t) for (p, t) in backups if t is not None]
        raws = [(p, _parse_ts(p.name, r"_(\d{8}_\d{6})_raw\.txt$"))
                for p in API_DIR.glob(f"{pm_safe}_*_raw.txt")]
        raws = [(p, t) for (p, t) in raws if t is not None]

        raws.sort(key=lambda x: x[1])

        for raw_path, raw_ts in raws:
            # Nearest backup that precedes raw_ts
            pre_count = None
            best = None
            for bp, bt in backups:
                if bt > raw_ts:
                    continue
                diff = (raw_ts - bt).total_seconds()
                if best is None or diff < best[0]:
                    best = (diff, bp)
            if best:
                try:
                    pre_data = json.loads(best[1].read_text(encoding="utf-8"))
                    pre_count = len(pre_data.get("items", []))
                except Exception:
                    pre_count = None

            # Post-state from raw response
            post_count = None
            recon_count = 0
            try:
                binder = _extract_binder_from_raw(raw_path.read_text(encoding="utf-8"))
                if binder:
                    post_count = len(binder.get("items", []))
                    recon_count = len(binder.get("reconciliation", []))
            except Exception:
                pass

            # Transcript filename by mtime proximity, scoped to this PM's first name
            transcript = None
            best_diff = None
            for t in processed_files:
                if not t.name.endswith(".txt"):
                    continue
                if f"_{first_name}_" not in t.name:
                    continue
                try:
                    t_mtime = datetime.fromtimestamp(t.stat().st_mtime)
                except OSError:
                    continue
                diff = abs((t_mtime - raw_ts).total_seconds())
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    transcript = t.name
            if best_diff is not None and best_diff > 600:
                transcript = None  # >10 min apart = not confident

            history[pm].append({
                "transcript": transcript,
                "processed_at": raw_ts.isoformat(),
                "pre_count": pre_count,
                "post_count": post_count,
                "delta": (post_count - pre_count) if (pre_count is not None and post_count is not None) else None,
                "reconciliation_entries": recon_count,
            })

        history[pm].sort(key=lambda e: e["processed_at"], reverse=True)

    return history


# ---------------------------------------------------------------------------
# Dashboard counts
# ---------------------------------------------------------------------------

def dashboard_counts(binders: dict[str, dict], today: date) -> dict:
    total_active = urgent = stale_n = completed_today = dismissed_total = 0
    done_count = active_count = 0
    for b in binders.values():
        for item in b.get("items", []) or []:
            status = _norm_status(item.get("status", ""))
            if status in CLOSED_STATUSES:
                if status == "DISMISSED":
                    dismissed_total += 1
                if status == "COMPLETE":
                    done_count += 1
                    if item.get("closed_date") == today.isoformat():
                        completed_today += 1
                continue
            active_count += 1
            total_active += 1
            if item.get("priority") == "URGENT":
                urgent += 1
            if _aging_flag(item, today) in ("stale", "abandoned"):
                stale_n += 1
    total = active_count + done_count
    ppc = int(round(100 * done_count / total)) if total else 0
    return {
        "total_active": total_active,
        "urgent": urgent,
        "stale": stale_n,
        "completed_today": completed_today,
        "dismissed_total": dismissed_total,
        "ppc": ppc,
    }


# ---------------------------------------------------------------------------
# CSS / JS / HTML payload builders
# ---------------------------------------------------------------------------

CSS = r"""
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600&display=swap");

:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --d-fast: 150ms;
  --d-base: 220ms;
  --d-slow: 400ms;

  /* Slate palette (canonical — do not deviate) */
  --slate-tile:    #3B5864;
  --slate-deep:    #1A2830;
  --slate-deeper:  #132028;
  --stone-blue:    #5B8699;
  --gulf-blue:     #4E7A8C;
  --oceanside:     #CBD8DB;
  --white-sand:    #F7F5EC;
  --success:       #4A8A6F;
  --warn:          #C98A3B;
  --danger:        #B0554E;

  /* Semantic mapping for Slate Light — page flips to white-sand + white
     cards + slate-tile ink. The nav stays dark (see .app-header overrides
     below — it's the one anchor that doesn't flip). */
  --bg:          var(--white-sand);
  --bg-header:   var(--slate-deep);
  --surface:     #ffffff;
  --surface-2:   rgba(91, 134, 153, 0.03);
  --ink:         var(--slate-tile);
  --ink-2:       rgba(59, 88, 100, 0.70);
  --ink-3:       rgba(59, 88, 100, 0.55);
  --ink-muted:   rgba(59, 88, 100, 0.40);
  --line:        rgba(59, 88, 100, 0.15);
  --line-2:      rgba(59, 88, 100, 0.20);
  --line-strong: rgba(59, 88, 100, 0.25);

  /* Nav-island tokens (dark chrome on a light page) */
  --nav-ink:      var(--white-sand);
  --nav-ink-2:    rgba(247, 245, 236, 0.65);
  --nav-ink-3:    rgba(247, 245, 236, 0.40);
  --nav-line:     rgba(247, 245, 236, 0.08);
  --nav-line-2:   rgba(247, 245, 236, 0.15);
  --nav-line-strong: rgba(247, 245, 236, 0.20);

  /* Keep legacy token names resolved but square */
  --green:  var(--success);
  --red:    var(--danger);
  --amber:  var(--warn);
  --blue:   var(--stone-blue);
  --accent: var(--stone-blue);

  /* Square is the rule — keep legacy radius names but zero them */
  --r-sm: 0;
  --r: 0;
  --r-lg: 0;
  --r-full: 0;

  --shadow-sm: none;
  --shadow: none;

  /* Fonts */
  --font-display: "Space Grotesk", system-ui, sans-serif;
  --font-body:    "Inter", system-ui, -apple-system, sans-serif;
  --font-mono:    "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;

  /* Tracking */
  --tracking-eyebrow: 0.12em;
  --tracking-tight:  -0.02em;
}

* { box-sizing: border-box; }

/* The `hidden` HTML attribute must win over any `display: flex/block/...`
   rules below (needed for modal-backdrop + drop-overlay which default to
   display:flex). Without this, `<div hidden>` would still render. */
[hidden] { display: none !important; }

html, body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 14px;
  line-height: 1.5;
  font-variant-numeric: tabular-nums;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--stone-blue); text-decoration: none; }
a:hover { color: var(--gulf-blue); text-decoration: underline; }

h1, h2, h3, h4 {
  margin: 0; color: var(--ink);
  font-family: var(--font-display); font-weight: 500;
  letter-spacing: var(--tracking-tight); line-height: 1.15;
}
h1 { font-size: 30px; }
h2 { font-size: 22px; letter-spacing: -0.02em; }
h3 { font-size: 17px; letter-spacing: -0.01em; }
h4 { font-size: 14px; letter-spacing: -0.01em; }

p  { margin: 0; }

/* Eyebrow + hint — JetBrains Mono uppercase tracked labels */
.eyebrow, .hint, .section-subhead, .mono-label {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 500;
}
.hint { color: var(--ink-3); }
.section-subhead {
  color: var(--ink-2);
  text-transform: none;
  letter-spacing: 0;
  font-family: var(--font-body);
  font-size: 13px;
  margin-bottom: 14px;
}

.muted { color: var(--ink-3); }
.empty, .empty-state { color: var(--ink-3); font-style: italic; }

/* ─────────────  Hover tooltips (Phase 5)  ─────────────
   Pure-CSS tooltip on jargon/abbreviated labels. Underline + info icon
   signal "hoverable". Hidden in print (see @media print blocks below).
   Class name is .tip (not .hint — that class is already used elsewhere
   as an eyebrow-style label). */
.tip {
  position: relative;
  display: inline-block;
  border-bottom: 1px dotted currentColor;
  cursor: help;
  outline: none;
}
.tip:focus { outline: 1px dotted var(--stone-blue); outline-offset: 2px; }
.tip::after {
  content: attr(data-hint);
  position: absolute;
  bottom: calc(100% + 6px);
  left: 0;
  background: var(--slate-tile);
  color: var(--white-sand);
  padding: 6px 10px;
  font-family: var(--font-body);
  font-size: 12px;
  font-weight: 400;
  line-height: 1.4;
  letter-spacing: 0;
  text-transform: none;
  width: max-content;
  max-width: 280px;
  white-space: normal;
  opacity: 0;
  pointer-events: none;
  transition: opacity 120ms ease;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
}
.tip:hover::after,
.tip:focus::after,
.tip:focus-within::after { opacity: 1; }
.tip-icon {
  width: 11px;
  height: 11px;
  display: inline-block;
  margin-left: 3px;
  vertical-align: -1px;
  opacity: 0.5;
  color: currentColor;
}
.tip:hover .tip-icon,
.tip:focus .tip-icon { opacity: 0.85; }

/* ─────────────  App header (dark island on light page)  ───────────── */
.app-header {
  position: sticky; top: 0; z-index: 40;
  background: var(--bg-header);   /* slate-deep */
  border-bottom: 1px solid var(--nav-line);
}
.app-header-inner {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 24px;
  max-width: 1400px; margin: 0 auto;
}
.logo {
  font-family: var(--font-mono);
  font-weight: 600; font-size: 11px; letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--nav-ink);
}
.logo em { font-style: normal; color: var(--stone-blue); }

.tabs { display: flex; gap: 2px; flex: 1; margin-left: 24px; }
.tab {
  padding: 8px 14px;
  font-family: var(--font-body);
  font-size: 13px; font-weight: 500;
  color: var(--nav-ink-2); background: transparent;
  border: none; border-bottom: 2px solid transparent;
  cursor: pointer; position: relative;
  transition: color var(--d-fast) var(--ease-out),
              border-color var(--d-fast) var(--ease-out);
}
.tab:hover { color: var(--nav-ink); }
.tab[aria-selected="true"] {
  color: var(--nav-ink);
  border-bottom-color: var(--stone-blue);
}
.tab .tab-count {
  color: var(--nav-ink-3);
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  margin-left: 8px;
}
.tab[aria-selected="true"] .tab-count { color: var(--nav-ink-2); }

.refresh-status {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  padding: 4px 9px; background: transparent;
  border: 1px solid var(--nav-line-2); color: var(--nav-ink-2);
}
.refresh-status[data-phase="scraping"]     { border-color: var(--warn);        color: var(--warn); }
.refresh-status[data-phase="processing"]   { border-color: var(--stone-blue);  color: var(--stone-blue); }
.refresh-status[data-phase="regenerating"] { border-color: var(--oceanside);   color: var(--oceanside); }
.refresh-status[data-phase="done"]         { border-color: var(--success);     color: var(--success); }
.refresh-status[data-phase="error"]        { border-color: var(--danger);      color: var(--danger); }
.refresh-status[data-phase="captcha"]      { border-color: var(--warn);        color: var(--warn); }

.refresh-last {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--nav-ink-3);
}

/* Ghost buttons inside the dark nav island need a sand outline */
.app-header .ghost, .app-header button.ghost {
  border-color: var(--nav-line-strong);
  color: var(--nav-ink);
}
.app-header .ghost:hover, .app-header button.ghost:hover {
  border-color: var(--stone-blue); color: var(--stone-blue);
}

/* ─────────────  Main layout  ───────────── */
main { max-width: 1400px; margin: 0 auto; padding: 28px 24px 80px 24px; }
.pm-view > * { margin-bottom: 24px; }

.pm-view {
  opacity: 1; transform: translateY(0);
  transition: opacity 180ms var(--ease-out), transform 220ms var(--ease-out);
}
.pm-view.switching { opacity: 0; transform: translateY(4px); }
.pm-view .section { opacity: 1; transform: none; }

/* ─────────────  Meeting header  ───────────── */
.meeting-header { padding: 4px 0 0 0; }
.meeting-header .eyebrow { margin-bottom: 6px; display: block; }
.meeting-header h1 { margin-bottom: 4px; }
.meeting-header-row { display: flex; align-items: flex-start; gap: 14px; }
.meeting-header-row h1 { margin-bottom: 0; flex: 1; font-size: 32px; }
.meeting-header-actions { display: flex; gap: 8px; align-items: center; flex: 0 0 auto; }
.meeting-header-meta {
  color: var(--ink-2); font-size: 14px; margin-top: 6px;
  font-family: var(--font-body);
}
.meeting-header .hint { margin-top: 10px; display: block; }

/* ─────────────  Agenda roadmap (connected strip)  ───────────── */
.agenda-roadmap {
  display: flex; gap: 0;
  background: var(--surface);
  border: 1px solid var(--line);
}
.agenda-pill {
  display: inline-flex; align-items: center; gap: 8px;
  flex: 1; justify-content: center;
  font-family: var(--font-body);
  font-size: 13px; font-weight: 500; color: var(--ink-2);
  padding: 10px 14px;
  background: transparent;
  border: 1px solid transparent;
  border-left-color: var(--line);
  margin-left: -1px;
  cursor: pointer;
  transition: background var(--d-fast) var(--ease-out),
              color var(--d-fast) var(--ease-out),
              border-color var(--d-fast) var(--ease-out);
}
.agenda-pill:first-child { margin-left: 0; border-left-color: transparent; }
.agenda-pill:hover { background: var(--surface-2); color: var(--ink); }
.agenda-pill.active,
.agenda-pill[aria-current="true"] {
  background: var(--slate-tile);
  color: var(--white-sand);    /* active pill is a dark tile — white text */
  border-left-color: var(--slate-tile);
}
.agenda-pill .num {
  font-family: var(--font-display); font-weight: 500;
  color: var(--slate-tile); font-variant-numeric: tabular-nums;
  font-size: 12px;
}
.agenda-pill.active .num,
.agenda-pill[aria-current="true"] .num { color: var(--white-sand); }
.agenda-pill .time {
  font-family: var(--font-mono);
  color: var(--ink-3); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
}
.agenda-pill.active .time,
.agenda-pill[aria-current="true"] .time { color: rgba(247, 245, 236, 0.7); }

/* ─────────────  At-a-glance (dashboard bar)  ───────────── */
.ataglance {
  display: flex; gap: 0; align-items: stretch;
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 0;
}
.ataglance .stat {
  display: flex; flex-direction: column; gap: 4px;
  padding: 14px 22px;
  border-right: 1px solid var(--line);
  font-variant-numeric: tabular-nums;
}
.ataglance .stat:last-child { border-right: none; }
.ataglance .stat-num {
  font-family: var(--font-display); font-weight: 600;
  font-size: 22px; color: var(--ink); line-height: 1;
}
.ataglance .stat-label {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500;
}
.ataglance .stat.accent .stat-num { color: var(--danger); }
.ataglance .sep { display: none; }   /* separators now come from border-right */

/* ─────────────  Collapsible sections  ───────────── */
details.collapsible {
  background: var(--surface);
  border: 1px solid var(--line);
}
details.collapsible > summary {
  display: flex; align-items: center; gap: 10px;
  padding: 12px 18px; cursor: pointer; user-select: none;
  list-style: none;
  color: var(--ink); font-family: var(--font-display);
  font-weight: 500; font-size: 14px;
}
details.collapsible > summary::-webkit-details-marker { display: none; }
details.collapsible > summary .chev {
  display: inline-block; width: 12px; height: 12px; color: var(--ink-3);
  transition: transform var(--d-fast) var(--ease-out);
}
details.collapsible[open] > summary .chev {
  transform: rotate(90deg); color: var(--stone-blue);
}
details.collapsible > summary .summary-count {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-left: auto;
}
details.collapsible .section-body {
  padding: 14px 18px 18px 18px;
  border-top: 1px solid var(--line);
}

/* ─────────────  Quick tools  ───────────── */
.quick-tools .tools-row {
  display: flex; gap: 10px; flex-wrap: wrap; align-items: center;
}
.quick-tools .tools-row > * { flex: 0 0 auto; }
.quick-tools .search { flex: 1; min-width: 180px; max-width: 320px; }
.quick-tools .tool-sep { color: var(--ink-3); }

/* ─────────────  Form controls (inputs, selects)  ───────────── */
input[type="search"], input[type="text"], input[type="number"], input[type="date"],
select, textarea {
  background: #ffffff;
  color: var(--ink);
  border: 1px solid var(--line-2);
  padding: 7px 10px;
  font-family: var(--font-body); font-size: 13px;
  outline: none;
  transition: border-color var(--d-fast) var(--ease-out);
}
input:focus, select:focus, textarea:focus {
  border-color: var(--stone-blue);
}
input::placeholder { color: var(--ink-3); }
select option { background: #ffffff; color: var(--ink); }

/* ─────────────  Buttons  ───────────── */
.btn, button.btn {
  font-family: var(--font-mono);
  font-size: 11px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  padding: 10px 16px;
  background: var(--stone-blue); color: var(--white-sand);
  border: none; cursor: pointer;
  transition: background var(--d-fast) var(--ease-out);
}
.btn:hover:not(:disabled), button.btn:hover:not(:disabled) { background: var(--gulf-blue); }
.btn:disabled { opacity: 0.55; cursor: not-allowed; }

.btn.primary, button.primary {
  background: var(--stone-blue); color: var(--white-sand); border: none;
}
.btn.accent, button.accent { background: var(--stone-blue); color: var(--white-sand); }

.btn.ghost, button.ghost, .ghost {
  background: transparent;
  color: var(--ink);
  border: 1px solid var(--line-strong);
  font-family: var(--font-mono); font-size: 11px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  padding: 9px 14px; cursor: pointer;
}
.btn.ghost:hover, button.ghost:hover {
  border-color: var(--stone-blue); color: var(--stone-blue);
}
.btn.small, button.small, .small {
  padding: 7px 11px; font-size: 10px;
}

.danger-ghost {
  background: transparent;
  border: 1px solid rgba(176, 85, 78, 0.35);
  color: var(--danger);
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  padding: 5px 9px; cursor: pointer;
}
.danger-ghost:hover { border-color: var(--danger); background: rgba(176, 85, 78, 0.08); }

.email-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 10px 16px;
  font-family: var(--font-mono);
  font-size: 11px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  color: var(--white-sand);
  background: var(--stone-blue);
  border: none; cursor: pointer;
  transition: background var(--d-fast) var(--ease-out);
}
.email-btn:hover:not(:disabled) { background: var(--gulf-blue); }
.email-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.email-btn.success { background: var(--success); }

/* ─────────────  Transcript history  ───────────── */
.transcript-log { display: flex; flex-direction: column; gap: 10px; }
.transcript-entry {
  padding: 10px 12px;
  border-left: 2px solid var(--line-2);
  background: var(--surface-2);
}
.transcript-entry .filename {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink); letter-spacing: 0.03em;
}
.transcript-entry .line {
  font-family: var(--font-body); font-size: 12px;
  color: var(--ink-2); font-variant-numeric: tabular-nums;
}
.transcript-entry .delta-pos { color: var(--success); font-weight: 500; }
.transcript-entry .delta-neg { color: var(--danger);  font-weight: 500; }
.transcript-entry.empty {
  color: var(--ink-3); background: transparent;
  border-left: 2px dashed var(--line-2); font-style: italic;
}

/* ─────────────  Meeting sections  ───────────── */
.meeting-section {
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 20px 24px 22px 24px;
}
.meeting-section > header {
  display: flex; align-items: baseline; gap: 12px;
  padding-bottom: 10px;
  border-bottom: 2px solid var(--slate-tile);
  margin-bottom: 16px;
}
.meeting-section > header .eyebrow { flex: 0 0 auto; }
.meeting-section > header h2 { flex: 0 0 auto; }
.meeting-section > header .time-tag {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink-3);
  padding: 3px 9px;
  border: 1px solid var(--line-2);
  font-variant-numeric: tabular-nums;
}

/* Job sections — wraps items/issues/financial inside a per-job block so
   Krauss / Ruthven / etc. never intermingle in multi-job PMs */
.job-section {
  margin-bottom: 22px;
  padding-top: 4px;
}
.job-section + .job-section {
  margin-top: 10px;
  padding-top: 18px;
  border-top: 1px solid var(--line);
}
.job-section-head {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 12px; padding-bottom: 6px;
}
.job-section-head h3 {
  font-family: var(--font-display); font-size: 16px;
  font-weight: 500; color: var(--ink); letter-spacing: -0.01em;
  margin: 0; flex: 0 0 auto;
}
.job-section-head .dot { width: 10px; height: 10px; border-radius: 999px; flex: 0 0 auto; }
.job-section-head .job-section-count {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-left: 4px;
}
.job-section-head .job-section-total {
  margin-left: auto;
  font-family: var(--font-mono); font-variant-numeric: tabular-nums;
  font-size: 12px; font-weight: 500; color: var(--ink-2);
}

/* Priority groups in Open Items */
.priority-group { margin-bottom: 18px; }
.priority-group-head {
  display: flex; align-items: center; gap: 10px; margin-bottom: 10px;
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  color: var(--ink-2);
}
.priority-group-head .dot {
  width: 7px; height: 7px; border-radius: 999px;
}
.dot.urgent  { background: var(--danger); }
.dot.high    { background: var(--warn); }
.dot.normal  { background: var(--ink-3); }
.dot.accent  { background: var(--stone-blue); }

/* Item cards */
.item-card {
  padding: 12px 16px 12px 14px;
  margin-bottom: 8px;
  background: transparent;
  border: 1px solid var(--line);
  border-left: 3px solid var(--line-strong);
  transition: background var(--d-fast) var(--ease-out);
  position: relative;
}
.item-card:hover { background: var(--surface-2); }
.item-card .id,
.item-card .id-mono,
.id-mono {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500;
}
.item-card .action,
.item-card .action-text {
  font-family: var(--font-body);
  font-size: 14px; font-weight: 500; color: var(--ink);
  margin: 4px 0 6px 0; line-height: 1.45;
}
/* Collapsible action text: toggle between summary (default) and full.
   Print CSS overrides this to always show the full text. */
.item-card .action-text[data-collapsible] .action-full { display: none; }
.item-card .action-text[data-collapsible][data-expanded="1"] .action-summary { display: none; }
.item-card .action-text[data-collapsible][data-expanded="1"] .action-full { display: inline; }
.item-card .action-collapse-toggle {
  background: transparent;
  border: 1px solid var(--line-2);
  color: var(--ink-3);
  cursor: pointer;
  font-size: 11px;
  line-height: 1;
  padding: 1px 6px;
  margin-left: 6px;
  border-radius: 3px;
  vertical-align: baseline;
  transition: transform 0.15s, color 0.15s, border-color 0.15s;
}
.item-card .action-collapse-toggle:hover {
  color: var(--ink); border-color: var(--ink-3);
}
.item-card .action-text[data-expanded="1"] .action-collapse-toggle {
  transform: rotate(180deg);
}
.item-card .meta {
  display: flex; gap: 14px; flex-wrap: wrap;
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
.item-card .meta .label { color: var(--ink-muted); margin-right: 4px; }
.item-card .meta .value { color: var(--ink-2); font-family: var(--font-body); font-size: 12px; letter-spacing: 0; text-transform: none; }
.item-card .update,
.item-card .update-text {
  font-family: var(--font-body);
  font-size: 13px; color: var(--ink-2);
  margin-top: 8px; padding-left: 10px;
  border-left: 1px solid var(--line-2); font-style: italic;
  line-height: 1.5;
}

/* Priority pill (top-right on cards) */
.item-card .priority-pill,
.priority-pill {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  padding: 3px 8px;
  border: 1px solid var(--line-strong);
  color: var(--ink-2);
  display: inline-flex; align-items: center; gap: 6px;
}
.priority-pill .dot {
  width: 7px; height: 7px; border-radius: 999px;
}
.priority-pill.urgent,
.priority-pill:has(.dot.urgent) {
  border-color: var(--danger); color: var(--danger);
}
.priority-pill.high,
.priority-pill:has(.dot.high) {
  border-color: var(--warn); color: var(--warn);
}
.priority-pill.normal,
.priority-pill:has(.dot.normal) {
  border-color: var(--line-strong); color: var(--ink-2);
}

/* Aging badges */
.aging-badge, .aging {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  padding: 2px 7px;
  border: 1px solid var(--line-strong); color: var(--ink-3);
}
.aging.stale, .aging-badge.stale,
.aging-badge.aging-stale, .item-card.aging-stale .aging-badge {
  border-color: var(--warn); color: var(--warn);
}
.aging.abandoned, .aging-badge.abandoned,
.aging-badge.aging-abandoned, .item-card.aging-abandoned .aging-badge {
  border-color: var(--danger); color: var(--danger);
}

/* Status dropdown inside a card */
.item-card select,
.item-card .status-select {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  background: #ffffff; color: var(--ink-2);
  border: 1px solid var(--line-2); padding: 4px 8px;
}

/* Job chips above Open Items */
.chip, .job-chip {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  padding: 5px 10px;
  border: 1px solid var(--line-strong);
  color: var(--ink-2);
  background: transparent; cursor: pointer;
  transition: color var(--d-fast) var(--ease-out), border-color var(--d-fast) var(--ease-out);
}
.chip:hover, .job-chip:hover { border-color: var(--stone-blue); color: var(--stone-blue); }
.chip.active, .job-chip.active {
  border-color: var(--stone-blue); color: var(--stone-blue);
}
.chip .count, .job-chip .count { color: var(--ink-3); margin-left: 4px; }
.job-filter-row { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 14px; }

/* ─────────────  Look-behind cards (Section 2)  ───────────── */
.lb-grid {
  display: grid; gap: 16px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}
.lb-card {
  background: transparent;
  border: 1px solid var(--line);
  padding: 14px 16px;
}
.lb-head {
  display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
  margin-bottom: 10px; padding-bottom: 8px;
  border-bottom: 1px solid var(--line);
}
.lb-job {
  display: inline-flex; align-items: center; gap: 8px;
  font-family: var(--font-display); font-weight: 500;
  font-size: 15px; color: var(--ink);
}
.lb-job .dot { width: 8px; height: 8px; border-radius: 999px; }
.lb-week {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-3);
}
.ppc-block {
  display: flex; align-items: baseline; gap: 10px;
  margin-bottom: 10px;
}
.ppc-num {
  font-family: var(--font-display); font-weight: 600;
  font-size: 28px; color: var(--ink); letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
}
.ppc-label {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
}
.lb-row {
  font-family: var(--font-body); font-size: 13px;
  color: var(--ink-2); line-height: 1.5; margin-bottom: 6px;
}
.lb-row strong { color: var(--ink); font-weight: 600; }
.lb-row .variance-good { color: var(--success); }
.lb-pair-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 12px;
  margin: 10px 0;
}
.lb-pair-grid h4 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin-bottom: 4px;
}
.lb-pair-grid ul, .lb-notable ul {
  list-style: none; padding: 0; margin: 0;
  font-size: 12px; color: var(--ink-2);
}
.lb-pair-grid li, .lb-notable li {
  padding: 2px 0;
}
.lb-notable h4 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin-top: 10px; margin-bottom: 4px;
}
.lb-missed {
  font-family: var(--font-body); font-size: 12px;
  color: var(--ink-2); margin-top: 8px;
}
.lb-missed strong {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--warn); margin-right: 6px;
}
.lb-narrative {
  font-family: var(--font-body); font-size: 13px;
  color: var(--ink-2); line-height: 1.5; margin-top: 10px;
  padding-left: 10px; border-left: 1px solid var(--line-2);
  font-style: italic;
}

/* ─────────────  Chat assistant (FAB + side panel)  ───────────── */
.chat-fab {
  position: fixed;
  bottom: 24px; right: 24px;
  width: 54px; height: 54px;
  border-radius: 50%;
  background: var(--slate-deep);
  color: var(--white-sand);
  border: none; cursor: pointer;
  font-size: 22px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.18);
  z-index: 1000;
  transition: transform 80ms ease, background 100ms ease;
}
.chat-fab:hover { background: var(--accent); transform: scale(1.04); }

.chat-panel {
  position: fixed;
  bottom: 92px; right: 24px;
  width: 420px; height: 600px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 120px);
  background: var(--surface);
  border: 1px solid var(--line-strong);
  display: flex; flex-direction: column;
  box-shadow: 0 12px 40px rgba(0,0,0,0.18);
  z-index: 999;
}
.chat-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--bg-header);
  color: var(--nav-ink);
}
.chat-title {
  font-family: var(--font-display);
  font-weight: 600; font-size: 13px;
  letter-spacing: var(--tracking-tight);
}
.chat-head-actions { display: flex; gap: 6px; align-items: center; }
.chat-clear-btn {
  background: transparent; color: var(--nav-ink-2);
  border: 1px solid var(--nav-line-2);
  font-family: var(--font-mono); font-size: 10px;
  padding: 2px 8px; cursor: pointer;
  letter-spacing: 0.04em; text-transform: uppercase;
}
.chat-clear-btn:hover { color: var(--nav-ink); border-color: var(--nav-ink-2); }
.chat-close {
  background: transparent; color: var(--nav-ink-2);
  border: none; cursor: pointer; font-size: 22px;
  line-height: 1; padding: 0 6px;
}
.chat-close:hover { color: var(--nav-ink); }

.chat-messages {
  flex: 1; overflow-y: auto;
  padding: 12px 14px;
  background: var(--bg);
}
.chat-msg {
  margin-bottom: 10px;
  padding: 8px 12px;
  font-size: 13px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.chat-msg.system {
  background: var(--surface);
  color: var(--ink-2);
  border: 1px solid var(--line);
  font-size: 12px;
}
.chat-msg.system strong { color: var(--ink); }
.chat-msg.system ul { margin: 6px 0 6px 16px; padding: 0; }
.chat-msg.system li { margin: 2px 0; }
.chat-msg.system em { color: var(--accent); font-style: normal; }
.chat-msg.user {
  background: var(--accent);
  color: white;
  margin-left: 36px;
}
.chat-msg.assistant {
  background: var(--surface);
  color: var(--ink);
  border: 1px solid var(--line);
  margin-right: 36px;
}
.chat-msg.thinking {
  color: var(--ink-3); font-style: italic;
}
.chat-msg.error { color: var(--danger); border-color: var(--danger); }

.chat-form {
  display: flex; gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--line);
  background: var(--surface);
}
.chat-form textarea {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--line);
  font-family: var(--font-body);
  font-size: 13px;
  resize: none;
  background: var(--bg);
  color: var(--ink);
  outline: none;
}
.chat-form textarea:focus { border-color: var(--accent); }
.chat-form button {
  padding: 0 18px;
  font-family: var(--font-display);
  font-weight: 600; font-size: 13px;
  background: var(--accent); color: white;
  border: none; cursor: pointer;
}
.chat-form button:disabled { opacity: 0.5; cursor: not-allowed; }

@media print {
  .chat-fab, .chat-panel { display: none !important; }
}

/* ─────────────  Missed-logs banner (PM accountability)  ───────────── */
.missed-banner {
  margin: 12px 0;
  padding: 12px 16px;
  border: 1px solid var(--line);
  border-left: 4px solid var(--warn);
  background: rgba(255, 165, 0, 0.04);
}
.missed-banner.mid  { border-left-color: var(--warn); }
.missed-banner.high {
  border-left-color: var(--danger);
  background: rgba(176, 85, 78, 0.06);
}
.missed-banner-head {
  display: flex; align-items: baseline; gap: 8px;
  margin-bottom: 6px;
}
.missed-icon { font-size: 16px; }
.missed-banner.high .missed-icon { color: var(--danger); }
.missed-banner.mid  .missed-icon { color: var(--warn); }
.missed-title {
  font-family: var(--font-display);
  font-weight: 600; font-size: 14px;
  color: var(--ink);
}
.missed-banner.high .missed-title { color: var(--danger); }
.missed-sub {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-3);
}
.missed-banner-detail {
  display: flex; flex-wrap: wrap; gap: 6px;
  margin: 4px 0;
}
.missed-pill {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--line-2);
  border-left: 3px solid var(--job-color, var(--ink-3));
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.missed-pill b {
  color: var(--warn); font-weight: 700;
}
.missed-banner-note {
  margin: 6px 0 0;
  font-size: 10.5px;
  color: var(--ink-3);
  font-family: var(--font-mono);
  line-height: 1.5;
}
.missed-banner-dormant {
  color: var(--ink-3);
  font-size: 10px;
  margin: 4px 0 0;
  font-family: var(--font-mono);
  font-style: italic;
}

/* ─────────────  Jobs overview (top-of-doc briefing)  ───────────── */
.jobs-overview-grid {
  display: flex; flex-direction: column; gap: 8px;
  margin-bottom: 14px;
}
.job-overview-row {
  background: transparent;
  border: 1px solid var(--line);
  border-left: 3px solid var(--job-color, var(--line-strong));
  padding: 10px 14px;
}
.jor-head {
  display: flex; align-items: baseline; flex-wrap: wrap;
  gap: 10px; margin-bottom: 6px;
}
.status-badge {
  font-size: 12px; line-height: 1;
}
.status-badge.green { color: var(--success); }
.status-badge.amber { color: var(--warn); }
.status-badge.red   { color: var(--danger); }
.status-badge.muted { color: var(--ink-muted); }
.jor-name {
  font-family: var(--font-display); font-weight: 600;
  font-size: 14px; color: var(--ink);
}
.jor-addr {
  font-weight: 400; color: var(--ink-3);
  font-size: 12px; margin-left: 4px;
}
.jor-phase {
  font-family: var(--font-mono); font-size: 9px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-2);
  padding: 2px 7px;
  border: 1px solid var(--line-2);
  cursor: help;
}
.jor-co {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--ink-3); margin-left: auto;
  white-space: nowrap;
}
.jor-stats {
  display: flex; flex-wrap: wrap; gap: 14px;
  font-size: 12px; color: var(--ink-2);
  margin: 4px 0;
  font-variant-numeric: tabular-nums;
}
.jor-stat .lbl, .jor-crews .lbl {
  font-family: var(--font-mono); font-size: 9px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-3); margin-right: 4px;
  font-weight: 500;
}
.jor-stat.warn { color: var(--warn); }
.jor-crews {
  font-size: 12px; color: var(--ink-2);
  margin-top: 4px; line-height: 1.5;
}
.jor-progress {
  font-size: 12px; color: var(--ink-2);
  margin-top: 6px; padding-left: 10px;
  border-left: 1px solid var(--line-2);
  font-style: italic; line-height: 1.45;
}
.overview-rollup {
  display: flex; flex-wrap: wrap;
  border: 1px solid var(--line);
  padding: 8px 0;
  font-family: var(--font-mono); font-size: 11px;
  margin-top: 4px;
}
.rollup-stat {
  padding: 2px 16px;
  border-right: 1px solid var(--line);
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.rollup-stat:last-child { border-right: none; }
.rollup-stat.warn { color: var(--warn); }
.rollup-stat b {
  font-family: var(--font-display);
  font-weight: 600; font-size: 14px;
  color: var(--ink); margin-right: 4px;
}
.rollup-stat.warn b { color: var(--warn); }

/* ─────────────  Jobs analytics tab (own sheet)  ───────────── */
.tab-jobs {
  margin-left: 8px;
  border-left: 1px solid var(--nav-line-2);
  padding-left: 14px !important;
}
.tab-jobs[aria-selected="true"] { color: var(--accent); }

.jobs-view {
  padding: 4px 0 32px;
}
.jobs-view-head { margin-bottom: 16px; }
.jobs-view-head h1 {
  font-family: var(--font-display);
  font-size: 24px; font-weight: 600;
  color: var(--ink); margin: 4px 0 6px;
  letter-spacing: var(--tracking-tight);
}
.jobs-view-head .muted { font-size: 13px; }

.jobs-portfolio-rollup {
  display: flex; flex-wrap: wrap;
  border: 1px solid var(--line);
  padding: 10px 0; margin-bottom: 20px;
  font-family: var(--font-mono); font-size: 11px;
}
.jobs-portfolio-rollup .rollup-stat {
  padding: 4px 18px;
  border-right: 1px solid var(--line);
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}
.jobs-portfolio-rollup .rollup-stat:last-child { border-right: none; }
.jobs-portfolio-rollup .rollup-stat b {
  font-family: var(--font-display);
  font-weight: 600; font-size: 16px;
  color: var(--ink); margin-right: 5px;
}

.jobs-card-list {
  display: flex; flex-direction: column;
  gap: 18px;
}
.ja-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 4px solid var(--job-color, var(--line-strong));
  padding: 18px 22px;
}
.ja-head {
  display: flex; flex-wrap: wrap; gap: 10px 24px;
  justify-content: space-between; align-items: baseline;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.ja-title {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
}
.ja-title h2 {
  font-family: var(--font-display);
  font-size: 18px; font-weight: 600;
  color: var(--ink); margin: 0;
  letter-spacing: var(--tracking-tight);
}
.ja-addr {
  font-size: 12px; color: var(--ink-3);
  font-weight: 400;
}
.ja-meta {
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
}
.ja-pm {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-3);
}
.ja-phase {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-2);
  padding: 2px 8px;
  border: 1px solid var(--line-2);
  cursor: help;
}
.ja-co {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--ink-3); text-transform: uppercase;
  letter-spacing: var(--tracking-eyebrow);
}

.ja-stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 10px 18px;
  margin-bottom: 6px;
}
.ja-stat .lbl {
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-bottom: 2px;
}
.ja-stat .val {
  font-family: var(--font-display);
  font-weight: 600; font-size: 22px;
  color: var(--ink); line-height: 1.1;
  font-variant-numeric: tabular-nums;
}
.ja-stat .val .sub {
  font-size: 11px; font-weight: 400;
  color: var(--ink-3); margin-left: 4px;
  font-family: var(--font-mono);
}
.ja-stat.warn .val { color: var(--warn); }
.ja-range {
  font-size: 11px; color: var(--ink-3);
  font-family: var(--font-mono); margin: 6px 0 14px;
}

.ja-charts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 14px 22px;
  margin-bottom: 16px;
  padding: 12px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.ja-chart {
  margin: 0; padding: 0;
}
.ja-chart figcaption {
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-bottom: 4px;
}
.ja-spark {
  display: block; width: 100%; height: 36px;
}
.ja-chart-axis {
  display: flex; justify-content: space-between;
  font-family: var(--font-mono); font-size: 9px;
  color: var(--ink-3); margin-top: 2px;
}

.ja-cols {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 22px;
  margin-bottom: 14px;
}
.ja-col h3 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin: 0 0 6px;
}
.ja-rank {
  list-style: none; padding: 0; margin: 0;
  font-size: 12px;
}
.ja-rank li {
  display: flex; justify-content: space-between;
  padding: 3px 0;
  border-bottom: 1px solid var(--line);
  color: var(--ink-2);
}
.ja-rank li:last-child { border-bottom: none; }
.ja-crew-name {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-right: 8px;
}
.ja-crew-days {
  font-family: var(--font-mono);
  font-size: 11px; color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}

/* Workforce histogram (replaces the trio of sparklines) */
.ja-histogram {
  margin: 14px 0;
  padding: 12px 0;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.ja-histogram figcaption {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-bottom: 6px;
}
.ja-histogram svg {
  display: block; width: 100%; height: auto;
}

/* Two-column grid: subs list (compact) + phase table (wide) */
.ja-grid {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 22px;
  margin-bottom: 14px;
}
.ja-section h3 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin: 0 0 8px;
}

/* Phase activity table */
.phase-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.phase-table th {
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; text-align: left;
  padding: 4px 8px 6px;
  border-bottom: 1px solid var(--line-strong);
}
.phase-table td {
  padding: 5px 8px;
  border-bottom: 1px solid var(--line);
  color: var(--ink-2);
  vertical-align: baseline;
}
.phase-table tbody tr:last-child td { border-bottom: none; }
.phase-table tbody tr:hover { background: var(--surface-2); }
.pt-name {
  color: var(--ink); font-weight: 500;
  white-space: nowrap;
}
.pt-when {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-3); white-space: nowrap;
}
.pt-dur {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-2); white-space: nowrap;
}
.pt-days {
  color: var(--ink); font-weight: 600;
  margin-right: 6px;
}
.pt-active {
  color: var(--ink-3);
  font-size: 10.5px;
}
.pt-bursts {
  display: inline-block;
  font-size: 9px;
  color: var(--ink-3);
  padding: 0 4px;
  border: 1px solid var(--line-2);
  margin-left: 6px;
  cursor: help;
}
.pt-status {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.04em;
  padding: 2px 8px;
  border: 1px solid var(--line-2);
  white-space: nowrap;
}
.pt-status.complete    { color: var(--ink-3); border-color: var(--line); }
.pt-status.ongoing     { color: var(--accent); border-color: var(--accent); }
.pt-status.intermittent {
  color: var(--ink-3);
  background: rgba(91, 134, 153, 0.05);
}
.pt-status.intermittent.ongoing {
  color: var(--accent); border-color: var(--accent);
}
.pt-status.multi-burst {
  color: var(--warn);
  border-color: var(--warn);
  background: rgba(255, 165, 0, 0.04);
}
/* Sub-attribution row — sticks to the phase row above (no top border, no
   bottom border on the main row above it via :has). Subordinate visual weight. */
.phase-table tbody tr.phase-main-row:has(+ tr.phase-subs-row) > td {
  border-bottom: none;
}
.phase-subs-row > td {
  border-bottom: 1px solid var(--line) !important;
  padding: 0 8px 5px 16px;
  color: var(--ink-3);
}
.phase-table tbody tr.phase-subs-row:hover { background: transparent; }
.phase-table tbody tr.phase-subs-row:last-child > td { border-bottom: none !important; }
.pt-subs {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.01em;
}
.pt-subs-days {
  color: var(--ink-3);
  opacity: 0.75;
}
.pt-note {
  font-size: 10.5px;
  color: var(--ink-3);
  font-family: var(--font-mono);
  margin: 8px 0 0;
  line-height: 1.5;
}

/* Stack on narrow viewports */
@media (max-width: 980px) {
  .ja-grid { grid-template-columns: 1fr; }
}

.ja-phases {
  border-top: 1px solid var(--line);
  padding-top: 12px;
  margin-bottom: 14px;
}
.ja-phases h3 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin: 0 0 10px;
}
.ph-axis {
  position: relative;
  height: 16px;
  margin-left: 170px;   /* aligns under the bar wrap (160px name + 8px gap + 2px slack) */
  margin-right: 110px;  /* matches stat column width */
  margin-bottom: 4px;
  border-bottom: 1px solid var(--line);
}
.ph-tick {
  position: absolute;
  bottom: 1px;
  font-family: var(--font-mono);
  font-size: 9px;
  color: var(--ink-3);
  transform: translateX(-50%);
  white-space: nowrap;
}
.ph-gantt {
  display: grid;
  grid-template-columns: 1fr;
  gap: 4px;
}
.ph-row {
  display: grid;
  grid-template-columns: 160px 1fr 110px;
  gap: 8px;
  align-items: center;
  font-size: 12px;
}
.ph-name {
  color: var(--ink-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11.5px;
}
.ph-bar-wrap {
  position: relative;
  height: 14px;
  background: rgba(91, 134, 153, 0.05);
  border: 1px solid var(--line-2);
}
.ph-bar {
  position: absolute;
  top: 1px; height: 10px;
  background: rgba(59, 88, 100, 0.45);
  min-width: 2px;
}
.ph-bar.ongoing {
  background: var(--job-color, var(--accent));
  box-shadow: 0 0 0 1px rgba(255,255,255,0.6) inset;
}
.ph-bar-life {
  position: absolute;
  top: 5px; height: 2px;
  background: rgba(59, 88, 100, 0.20);
  min-width: 2px;
}
.ph-bursts {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--ink-3);
  padding: 0 4px;
  border: 1px solid var(--line-2);
  cursor: help;
}
.ph-stat {
  display: flex; gap: 6px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-2);
  text-align: left;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.ph-stat .ph-days {
  color: var(--ink); font-weight: 600;
}
.ph-stat .ph-active { color: var(--ink-3); }
.ph-stat .ph-ongoing { color: var(--accent); font-weight: 500; }
.ph-legend {
  margin: 8px 0 0;
  font-size: 10px; color: var(--ink-3);
  font-family: var(--font-mono);
}
.ph-legend-ongoing { color: var(--accent); }
.ph-legend-done    { color: var(--ink-3); }

.ja-events {
  border-top: 1px solid var(--line);
  padding-top: 10px;
}
.ja-events h3 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin: 0 0 6px;
}
.ja-event {
  font-size: 12px; color: var(--ink-2);
  margin: 4px 0; line-height: 1.45;
}
.ja-event-label {
  font-family: var(--font-mono); font-size: 9px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-3); margin-right: 4px;
}
.ja-event-date {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-3); margin-right: 4px;
}

.jobs-view-empty { padding: 40px 20px; text-align: center; }
.jobs-view-empty h2 { color: var(--ink); }

/* ─── Subs view ─── */
.tab-subs[aria-selected="true"] { color: var(--accent); }
.subs-view .overlap-panel {
  margin: 16px 0;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--warn);
}
.ov-list {
  display: flex; flex-direction: column;
  gap: 6px; margin-top: 6px;
}
.ov-row {
  display: grid;
  grid-template-columns: 220px 70px 1fr;
  gap: 10px;
  align-items: center;
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px solid var(--line);
}
.ov-row:last-child { border-bottom: none; }
.ov-name { color: var(--ink); font-weight: 500; }
.ov-count {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--warn); font-weight: 600;
}
.ov-jobtag {
  display: inline-block;
  font-family: var(--font-mono); font-size: 9px;
  color: white;
  letter-spacing: 0.04em;
  padding: 1px 6px; margin-right: 4px;
  text-transform: uppercase;
}

.subs-table-wrap { margin-top: 18px; }
.subs-table-head {
  display: flex; gap: 16px; align-items: center;
  margin-bottom: 8px;
}
.subs-filter {
  flex: 0 1 320px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  font-size: 13px;
  font-family: var(--font-body);
  background: var(--surface);
  color: var(--ink);
}
.subs-filter:focus { outline: 2px solid var(--accent); outline-offset: -1px; }
.subs-table-count {
  font-family: var(--font-mono); font-size: 11px;
}
.subs-stale-toggle {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--ink-3);
  cursor: pointer;
  font-size: 11px;
  font-family: var(--font-mono);
  padding: 4px 10px;
  border-radius: 12px;
  letter-spacing: 0.04em;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.subs-stale-toggle:hover {
  color: var(--ink); border-color: var(--ink-3);
}
.subs-stale-toggle.active {
  background: var(--ink-3);
  color: var(--bg, #fff);
  border-color: var(--ink-3);
}
.subs-stale-note {
  color: var(--ink-3); font-style: italic;
}

/* Expand all / collapse all toggle — sits in subs-table-head next to filter */
.subs-expand-all {
  background: transparent;
  border: 1px solid var(--line);
  color: var(--ink-3);
  cursor: pointer;
  font-size: 11px;
  font-family: var(--font-mono);
  padding: 4px 10px;
  border-radius: 12px;
  letter-spacing: 0.04em;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.subs-expand-all:hover { color: var(--ink); border-color: var(--ink-3); }
.subs-expand-all.active {
  background: var(--ink-3);
  color: var(--bg, #fff);
  border-color: var(--ink-3);
}

/* Build-stage section headers (Pre-Construction, MEP, Finishes, …) and
   trade-category sub-headers (Plumbing, Electrical, …) inside the Subs
   table. Section headers span the full table width and break the visual
   flow between alike trades. */
.subs-table tbody.subs-section-head td {
  background: var(--bg, #fff);
  padding: 16px 0 4px 0;
  border-bottom: 1px solid var(--line-2);
}
.subs-table tbody.subs-section-head .ssh-eyebrow {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink-3);
  margin-right: 8px;
}
.subs-table tbody.subs-section-head h3 {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 500;
  color: var(--ink);
  display: inline;
  margin: 0;
}
.subs-table tbody.subs-section-head .ssh-count {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
  margin-left: 10px;
}

.subs-table tbody.subs-cat-head td {
  background: var(--surface-2);
  padding: 8px 10px;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.subs-table tbody.subs-cat-head .sch-name {
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--ink);
  letter-spacing: 0.02em;
  margin-right: 10px;
}
.subs-table tbody.subs-cat-head .sch-count {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
  margin-right: 14px;
}

/* Schedule-estimates strip — compact pills showing portfolio-median
   duration per phase tag, grouped under the trade subsection. */
.schedule-estimates {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}
.schedule-estimates .se-label {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink-3);
  align-self: center;
  margin-right: 4px;
}
.schedule-estimates .se-pill {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--line-2);
  border-radius: 10px;
  background: var(--surface);
  font-family: var(--font-mono);
  font-size: 10.5px;
}
.schedule-estimates .se-pill .se-phase { color: var(--ink-2); }
.schedule-estimates .se-pill .se-days {
  color: var(--ink);
  font-weight: 600;
}
.schedule-estimates .se-pill.se-sparse {
  opacity: 0.6;
}
.schedule-estimates .se-pill.se-sparse .se-days {
  font-weight: 400;
  font-style: italic;
}

/* Phase 18 — denser subs table. Row-height target ~28px collapsed.
   Padding tightened, sub-name + category + stats fit on one line, the
   13-month sparkline moves inline with the name. Reliability cells get
   color-coded backgrounds for fast scanning, recent absences render
   as small inline ticks. Phase 17 disclosure tree intact on click. */
.subs-table {
  width: 100%; border-collapse: collapse;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.subs-table th {
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; text-align: left;
  padding: 4px 10px;
  border-bottom: 1px solid var(--line-strong);
  user-select: none;
}
.subs-table th[data-sort] { cursor: pointer; }
.subs-table th[data-sort]:hover { color: var(--ink); }
.subs-table th.right, .subs-table td.right { text-align: right; }
.subs-table td {
  padding: 3px 10px;
  border-bottom: 1px solid var(--line);
  color: var(--ink-2);
  vertical-align: middle;
  line-height: 1.25;
}
.subs-table tbody tr:hover { background: var(--surface-2); }
.subs-table td.warn { color: var(--warn); }
.subs-table .muted { color: var(--ink-muted); }
.subs-table .warn { color: var(--warn); }
.subs-table .sub-name {
  font-size: 12px;
  font-family: var(--font-body);
  color: var(--ink);
}
/* Phase 18 — sparkline moves inline next to the sub name, smaller. */
.subs-table .sub-row .sub-spark {
  display: inline-flex;
  margin-left: 8px;
  vertical-align: middle;
  height: 8px;
}
.subs-table .sub-spark-cell {
  width: 2px;
  margin-right: 1px;
}
/* Reliability color-coded badges. Saturation bumps reflect "you should
   look at this sub" risk. ≥95 % stays neutral-good, 80-94 % is meh,
   <80 % gets a stronger amber tint. */
.subs-table .rel-pct {
  padding: 0 6px;
  border-radius: 0;
}
.subs-table .rel-good { color: var(--success); border-color: var(--success); }
.subs-table .rel-mid  { color: var(--ink-3);   border-color: var(--line-2); }
.subs-table .rel-bad  { color: var(--warn);    border-color: var(--warn); }
/* Multi-category badges in the Category column — shown comma-separated. */
.cat-tag {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
  letter-spacing: 0.03em;
  padding: 0 4px;
  border: 1px solid var(--line-2);
  margin-right: 3px;
  white-space: nowrap;
}
.cat-tag + .cat-tag { margin-left: 1px; }

/* ─────────────  Phase 6 — comparison row (Subs view)  ───────────── */
.cmp-bar-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}
.cmp-bar {
  display: inline-block;
  vertical-align: middle;
  flex: 0 0 auto;
}
.cmp-strip {
  fill: rgba(91, 134, 153, 0.22);
}
.cmp-strip-empty {
  fill: rgba(59, 88, 100, 0.10);
}
.cmp-band {
  fill: rgba(91, 134, 153, 0.55);
}
.cmp-band-empty {
  fill: rgba(59, 88, 100, 0.18);
}
.cmp-tick {
  /* color set inline; no stroke — rect fill carries it */
}
.cmp-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-2);
  letter-spacing: 0.02em;
}
.cmp-label-empty {
  font-family: var(--font-mono);
  font-size: 10px;
  font-style: italic;
  color: var(--ink-3);
  letter-spacing: 0;
}
.cmp-delta {
  font-family: var(--font-mono);
  font-size: 10.5px;
  margin-left: 4px;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.cmp-delta-good { color: var(--success); }
.cmp-delta-mid  { color: var(--warn); }
.cmp-delta-bad  { color: var(--danger); }
.cmp-recent {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.cmp-recent-num {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-2);
  letter-spacing: 0.02em;
}

/* Filter chip — "Show only subs with comparison data" */
.subs-comparison-toggle {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  background: transparent;
  color: var(--ink-2);
  border: 1px solid var(--line-2);
  padding: 4px 9px;
  cursor: pointer;
  margin-left: 6px;
  transition: color var(--d-fast) var(--ease-out),
              border-color var(--d-fast) var(--ease-out),
              background var(--d-fast) var(--ease-out);
}
.subs-comparison-toggle:hover { border-color: var(--stone-blue); color: var(--stone-blue); }
.subs-comparison-toggle.active {
  background: rgba(91, 134, 153, 0.10);
  border-color: var(--stone-blue);
  color: var(--stone-blue);
}

/* ⓘ volume-disclosure popover */
.vol-disclosure {
  position: relative;
  display: inline-block;
}
.vol-disclosure-icon {
  background: transparent;
  border: none;
  padding: 0 2px;
  font-size: 14px;
  line-height: 1;
  color: var(--ink-3);
  cursor: help;
}
.vol-disclosure-icon:hover,
.vol-disclosure-icon:focus { color: var(--stone-blue); outline: none; }
.vol-popover {
  position: absolute;
  right: calc(100% + 6px);
  top: 50%;
  transform: translateY(-50%);
  background: var(--slate-tile);
  color: var(--white-sand);
  padding: 8px 10px 8px 10px;
  margin: 0;
  display: none;
  grid-template-columns: auto auto;
  column-gap: 12px;
  row-gap: 2px;
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.02em;
  white-space: nowrap;
  z-index: 100;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.18);
  pointer-events: none;
}
.vol-popover dt { color: rgba(247, 245, 236, 0.65); margin: 0; }
.vol-popover dd { margin: 0; color: var(--white-sand); }
.vol-disclosure:hover .vol-popover,
.vol-disclosure:focus-within .vol-popover { display: grid; }

/* Print-only italic summary that takes the popover's place when printed */
.vol-disclosure-print {
  display: none;
}

/* Phase-breakdown row — collapsible per-sub mix of parent_group_activities
   showing which phases the sub was tagged under, with day counts and the
   list of jobs where they did each. Default collapsed; click chevron to
   expand. Print mode forces all expanded (see @media print below). */
.sub-toggle {
  background: transparent;
  border: none;
  padding: 0 4px 0 0;
  font-size: 14px;
  line-height: 1;
  color: var(--ink-3);
  cursor: pointer;
  font-family: var(--font-mono);
}
.sub-toggle:hover { color: var(--ink); }
.sub-toggle:focus-visible { outline: 1px solid var(--ink-3); outline-offset: 1px; }
.sub-toggle-pad {
  display: inline-block;
  width: 18px;
}
.sub-row:hover { background: var(--surface-2); }
.sub-phases > td {
  /* Align with the sub-name: cell padding (10px) + chevron width (18px) = 28px */
  padding: 4px 10px 10px 28px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
}
.sub-phase-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
}
.sub-phase-list li {
  display: grid;
  grid-template-columns: 220px 90px 1fr;
  gap: 8px;
  align-items: baseline;
}
.sub-phase-name {
  color: var(--ink-2);
}
.sub-phase-days {
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.sub-phase-jobs {
  font-size: 10px;
  color: var(--ink-3);
  opacity: 0.85;
}

/* Phase 17 — 3-level progressive disclosure inside the phase breakdown.
   Level 1 row stays as the existing grid (phase / days / meta). Level 2
   (per-job) and Level 3 (per-date) are nested ULs that animate open on
   click. Print mode forces all levels expanded — see @media print at the
   bottom of the stylesheet. */
.sub-phase-list .phase-l1 {
  display: flex;
  flex-direction: column;
}
.sub-phase-list .phase-l1-row {
  display: grid;
  grid-template-columns: 14px 220px 90px 1fr;
  gap: 6px;
  align-items: baseline;
}
.phase-toggle {
  background: transparent;
  border: none;
  padding: 0;
  font-size: 10px;
  line-height: 1;
  color: var(--ink-3);
  cursor: pointer;
  font-family: var(--font-mono);
}
.phase-toggle:hover { color: var(--ink); }
.phase-toggle:focus-visible {
  outline: 1px solid var(--ink-3);
  outline-offset: 1px;
}
.phase-toggle-pad {
  display: inline-block;
  width: 14px;
}
.sub-phase-meta {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
  opacity: 0.85;
}
.sub-phase-meta .meta-bench {
  margin-left: 6px;
  opacity: 0.85;
}
.phase-jobs {
  list-style: none;
  margin: 4px 0 6px 22px;
  padding: 4px 0 4px 8px;
  border-left: 1px solid var(--line);
  display: none;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
}
.phase-l1.expanded > .phase-jobs { display: flex; }
.phase-l2 {
  display: flex;
  flex-direction: column;
}
.phase-l2-row {
  display: grid;
  grid-template-columns: 8px 180px 60px 110px 1fr;
  gap: 6px;
  align-items: baseline;
  font-size: 10.5px;
  color: var(--ink-3);
}
.phase-l2-bullet {
  color: var(--ink-3);
  opacity: 0.4;
  font-size: 8px;
}
.phase-l2 .job-name { color: var(--ink-2); }
.phase-l2 .job-days {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.phase-l2 .job-badge {
  font-family: var(--font-mono);
  font-size: 10px;
}
.phase-l2 .job-badge.fast { color: var(--accent); }
.phase-l2 .job-badge.norm { color: var(--ink-3); }
.phase-l2 .job-badge.slow { color: var(--warn); }
.phase-l2 .job-badge.nomark { color: var(--ink-3); opacity: 0.5; }
.phase-l2 .job-span {
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
}
.phase-l2 .job-status-ongoing { color: var(--accent); }

/* View toggle pill at the top of the Subs tab */
.subs-view-toggle {
  display: inline-flex;
  border: 1px solid var(--line-2);
  margin-right: 8px;
}
.subs-view-toggle button {
  background: transparent;
  border: none;
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
  cursor: pointer;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.subs-view-toggle button.active {
  background: var(--surface-2);
  color: var(--ink);
}
.subs-glossary-btn {
  background: transparent;
  border: 1px solid var(--line-2);
  padding: 4px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
  cursor: pointer;
  letter-spacing: 0.04em;
  margin-right: 8px;
}
.subs-glossary-btn:hover { color: var(--ink); }
.subs-view-controls {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0 12px;
}

/* Phase 18 — Phase Durations panel. Sits above the per-job cards on
   the Jobs tab. Dense, sortable table with one row per phase tag. */
.phase-dur-panel {
  margin: 12px 0 18px;
  border: 1px solid var(--line);
  background: var(--surface);
}
.phase-dur-head {
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap;
  padding: 8px 12px;
  border-bottom: 1px solid var(--line);
  gap: 12px;
}
.phase-dur-head h3 {
  font-family: var(--font-display);
  font-size: 13px; font-weight: 600;
  color: var(--ink); margin: 0;
}
.phase-dur-controls {
  display: flex; align-items: center; gap: 6px;
  flex-wrap: wrap;
}
.pd-filter {
  padding: 4px 8px;
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  color: var(--ink);
  width: 160px;
}
.pd-sort-btn {
  background: transparent;
  border: 1px solid var(--line-2);
  padding: 3px 8px;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-3);
  letter-spacing: 0.04em;
  text-transform: uppercase;
  cursor: pointer;
}
.pd-sort-btn.active {
  background: var(--surface-2);
  color: var(--ink);
  border-color: var(--accent);
}
.pd-sort-btn:hover { color: var(--ink); }
.phase-dur-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11.5px;
  font-family: var(--font-body);
}
.phase-dur-table th, .phase-dur-table td {
  padding: 4px 8px;
  border-bottom: 1px solid var(--line);
  text-align: left;
}
.phase-dur-table th {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 500;
  background: var(--surface-2);
}
.phase-dur-table th.right, .phase-dur-table td.right { text-align: right; font-variant-numeric: tabular-nums; }
.phase-dur-table .pd-num { font-family: var(--font-mono); }
.phase-dur-table .pd-row:hover { background: var(--surface-2); }
.phase-dur-table .pd-col-phase {
  width: 36%;
  font-family: var(--font-mono);
  color: var(--ink);
}
.phase-dur-table .pd-col-cat {
  width: 14%;
}
.phase-dur-table .pd-col-cat .cat-tag {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--ink-3);
  letter-spacing: 0.03em;
}
.phase-dur-table .pd-toggle {
  background: transparent;
  border: none;
  padding: 0 4px 0 0;
  font-size: 10px;
  color: var(--ink-3);
  cursor: pointer;
  font-family: var(--font-mono);
}
.phase-dur-table .pd-toggle:hover { color: var(--ink); }
.phase-dur-table .pd-active-cell { color: var(--accent); font-weight: 600; }
.phase-dur-table .pd-detail-row > td {
  padding: 0 8px 6px 36px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--line);
}
.pd-detail-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 10.5px;
  margin: 4px 0 4px;
}
.pd-detail-table td {
  padding: 3px 8px;
  border-bottom: 1px dashed var(--line);
  font-family: var(--font-mono);
  color: var(--ink-2);
}
.pd-detail-table td.right { text-align: right; font-variant-numeric: tabular-nums; }
.pd-detail-table .pd-job-name { color: var(--ink); width: 14%; }
.pd-detail-table .pd-job-days { width: 8%; }
.pd-detail-table .pd-job-span { width: 14%; color: var(--ink-3); }
.pd-detail-table .pd-job-subs { color: var(--ink-3); width: 30%; }
.pd-detail-table .pd-job-status { color: var(--ink-3); }
.pd-detail-table .pd-job-status .job-status-ongoing { color: var(--accent); }
@media print {
  .phase-dur-table .pd-detail-row { display: table-row !important; }
  .pd-detail-row[hidden] { display: table-row !important; }
}
.th-help {
  font-size: 9px;
  color: var(--ink-3);
  opacity: 0.6;
  margin-left: 3px;
  cursor: help;
  font-family: var(--font-mono);
}

/* Phase Sequence view — section-grouped subs (Foundation, Rough-In, etc.) */
.phase-seq-section { margin: 16px 0; }
.phase-seq-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 4px;
}
.phase-seq-head h4 {
  font-family: var(--font-display);
  font-weight: 600; font-size: 13px;
  color: var(--ink); margin: 0;
}
.phase-seq-count {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--ink-3); letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
}
/* Phase 18 — phase-sequence sections now use a dense table per section
   instead of card grids. Compact alignment with the Subs table look. */
.phase-seq-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  margin-top: 4px;
}
.phase-seq-table th {
  font-family: var(--font-mono);
  font-size: 9px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 500;
  padding: 4px 8px;
  text-align: left;
  border-bottom: 1px solid var(--line);
}
.phase-seq-table th.right, .phase-seq-table td.right {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.phase-seq-table td {
  padding: 3px 8px;
  border-bottom: 1px solid var(--line);
  color: var(--ink-2);
}
.phase-seq-table .pseq-name { color: var(--ink); }
.phase-seq-table .pseq-num { font-family: var(--font-mono); }
.phase-seq-table .pseq-recent { font-family: var(--font-mono); font-size: 10px; color: var(--ink-3); }
.phase-seq-row:hover { background: var(--surface-2); }

/* Glossary panel overlay */
.glossary-overlay {
  position: fixed; inset: 0;
  background: rgba(11, 13, 15, 0.55);
  display: none;
  align-items: flex-start;
  justify-content: center;
  z-index: 1000;
  padding: 40px 20px;
  overflow-y: auto;
}
.glossary-overlay.open { display: flex; }
.glossary-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  max-width: 920px;
  width: 100%;
  padding: 24px 32px 28px;
  font-family: var(--font-body);
}
.glossary-panel h2 {
  font-family: var(--font-display);
  font-size: 18px;
  margin: 0 0 4px;
  color: var(--ink);
}
.glossary-panel .glossary-sub {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  margin-bottom: 18px;
}
.glossary-panel .glossary-search {
  width: 100%;
  padding: 6px 8px;
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  color: var(--ink);
  margin-bottom: 14px;
}
.glossary-panel h3 {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--accent);
  margin: 16px 0 6px;
  padding-bottom: 2px;
  border-bottom: 1px solid var(--line);
}
.glossary-panel dl {
  display: grid;
  grid-template-columns: 220px 1fr;
  gap: 4px 16px;
  margin: 0 0 8px;
  font-size: 12px;
}
.glossary-panel dt {
  font-family: var(--font-mono);
  color: var(--ink);
  font-weight: 500;
}
.glossary-panel dd {
  color: var(--ink-2);
  margin: 0;
  line-height: 1.4;
}
.glossary-panel .gloss-note {
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
  font-size: 11px;
  color: var(--ink-3);
}
.glossary-panel .gloss-note h4 {
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  color: var(--ink);
  margin: 8px 0 2px;
}
.glossary-panel .gloss-close {
  position: absolute;
  top: 8px; right: 12px;
  background: transparent;
  border: none;
  font-size: 18px;
  color: var(--ink-3);
  cursor: pointer;
  padding: 4px 8px;
}
.glossary-panel .gloss-close:hover { color: var(--ink); }
.glossary-overlay .glossary-panel { position: relative; }
@media print {
  .glossary-overlay { display: none !important; }
  .phase-jobs {
    display: flex !important;
  }
  .phase-l1 {
    /* keep fully expanded for the printed PDF */
  }
}

.rel-pct {
  font-family: var(--font-mono);
  font-weight: 600;
  padding: 1px 6px;
  border: 1px solid var(--line-2);
}
.rel-good { color: var(--success); border-color: var(--success); }
.rel-mid  { color: var(--warn);    border-color: var(--warn); }
.rel-bad  { color: var(--danger);  border-color: var(--danger); }

/* Categories panel */
.cats-panel { margin: 16px 0; }
.cats-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 10px;
}
.cats-head h3 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; margin: 0;
}
.cat-clear {
  background: transparent;
  color: var(--ink-3);
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: 0.04em;
  padding: 2px 8px;
  border: 1px solid var(--line-2);
  cursor: pointer;
}
.cat-clear:hover { color: var(--ink); }

.cats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px;
}
.cat-card {
  border: 1px solid var(--line);
  padding: 10px 12px;
  cursor: pointer;
  transition: background 80ms ease;
  background: transparent;
}
.cat-card:hover { background: var(--surface-2); }
.cat-card.active {
  border-color: var(--accent);
  background: rgba(91, 134, 153, 0.06);
}
.cat-card-head {
  display: flex; justify-content: space-between; align-items: baseline;
  margin-bottom: 6px;
}
.cat-card-head h4 {
  font-family: var(--font-display);
  font-weight: 600; font-size: 13px;
  color: var(--ink); margin: 0;
}
.cat-count {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--ink-3); letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
}
.cat-stats {
  display: flex; flex-wrap: wrap; gap: 8px 14px;
  font-size: 11px; color: var(--ink-2);
  margin-bottom: 8px;
  font-variant-numeric: tabular-nums;
}
.cat-stats b {
  font-family: var(--font-display);
  font-weight: 600; color: var(--ink);
  font-size: 13px; margin-right: 3px;
}
.cat-top {
  list-style: none; padding: 0; margin: 0;
  font-size: 11px;
  color: var(--ink-3);
}
.cat-top li {
  display: flex; justify-content: space-between;
  padding: 1px 0;
}
.cat-sub-name {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  margin-right: 6px;
}
.cat-sub-days {
  font-family: var(--font-mono); font-size: 10px;
}

.cat-tag {
  display: inline-block;
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.04em;
  color: var(--ink-2);
  padding: 1px 6px;
  border: 1px solid var(--line-2);
  background: var(--surface-2);
}

/* Tiny 13-month spark for sub activity */
.sub-spark {
  display: flex; align-items: flex-end;
  gap: 1px; margin-top: 2px;
  height: 12px;
}
.sub-spark-cell {
  display: inline-block;
  width: 4px;
  background: var(--accent);
  min-height: 1px;
}

/* ─────────────  Site activity (Section 2.1)  ───────────── */
.sa-grid {
  display: grid; gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
}
.sa-card {
  background: transparent;
  border: 1px solid var(--line);
  border-left: 3px solid var(--job-color, var(--line-strong));
  padding: 12px 14px;
}
.sa-card.empty { opacity: 0.6; }
.sa-head {
  display: flex; align-items: baseline; justify-content: space-between;
  gap: 10px; margin-bottom: 8px; padding-bottom: 6px;
  border-bottom: 1px solid var(--line);
}
.sa-job {
  display: inline-flex; align-items: center; gap: 8px;
  font-family: var(--font-display); font-weight: 500;
  font-size: 14px; color: var(--ink);
}
.sa-job .dot { width: 8px; height: 8px; border-radius: 999px; }
.sa-last {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-3); white-space: nowrap;
}
.sa-stats {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 14px;
  margin: 0;
  font-size: 12px;
}
.sa-stats dt {
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  align-self: baseline;
  font-weight: 500;
}
.sa-stats dd {
  margin: 0; align-self: baseline;
  color: var(--ink-2); line-height: 1.45;
}
.sa-stats dd.sa-warn { color: var(--warn); }
.sa-mono {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-3);
}
.sa-empty {
  margin: 4px 0 0; font-style: italic; color: var(--ink-3);
  font-size: 12px;
}
.sa-stale {
  font-size: 12px; color: var(--warn);
  margin: 0 0 10px; font-family: var(--font-mono);
}

/* ─────────────  Heads Up (Section 2.5)  ───────────── */
.headsup-empty { color: var(--ink-3); font-style: italic; padding: 12px 0; }
.headsup-grid { display: grid; gap: 16px; }
.headsup-block { }
.headsup-block-head {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  color: var(--ink-2); margin-bottom: 8px;
  display: flex; align-items: center; gap: 8px;
}
.headsup-block-head .count {
  color: var(--ink-3); font-weight: 500;
}
.headsup-card {
  padding: 12px 16px;
  margin-bottom: 6px;
  background: transparent;
  border: 1px solid var(--line);
  border-left: 3px solid var(--line-strong);
  transition: background var(--d-fast) var(--ease-out);
}
.headsup-card:hover { background: var(--surface-2); }
.headsup-card.amber  { border-left-color: var(--warn); }
.headsup-card.red    { border-left-color: var(--danger); }
.headsup-card.orange { border-left-color: var(--warn); }
.headsup-card.blue   { border-left-color: var(--stone-blue); }
.headsup-card.gray   { border-left-color: var(--line-strong); }
.headsup-card .primary {
  font-family: var(--font-body); font-size: 14px; font-weight: 500;
  color: var(--ink); line-height: 1.5;
}
.headsup-card .meta {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-top: 4px; font-variant-numeric: tabular-nums;
}
.headsup-card .action {
  font-family: var(--font-body); font-size: 13px;
  color: var(--ink-2); margin-top: 6px;
  display: flex; align-items: flex-start; gap: 8px; line-height: 1.5;
}
.headsup-card .action::before {
  content: "→"; color: var(--stone-blue); font-weight: 500; flex: 0 0 auto;
}

/* ─────────────  Look-ahead cards (Sections 3/4/5)  ───────────── */
.lookahead-grid {
  display: grid; gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
}
.lookahead-card {
  background: transparent;
  border: 1px solid var(--line);
  padding: 12px 16px;
}
.lookahead-card h4 {
  display: flex; align-items: center; gap: 8px;
  font-family: var(--font-display); font-weight: 500;
  font-size: 14px; color: var(--ink);
  padding-bottom: 8px; margin-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.lookahead-card h4 .dot { width: 8px; height: 8px; border-radius: 999px; }
.lookahead-card ul {
  list-style: none; padding: 0; margin: 0;
  font-family: var(--font-body); font-size: 13px; color: var(--ink-2);
  line-height: 1.5;
}
.lookahead-card li {
  padding: 4px 0;
  border-top: 1px solid var(--line);
}
.lookahead-card li:first-child { border-top: none; padding-top: 0; }

/* ─────────────  Issues (Section 6)  ───────────── */
.issue-group { margin-bottom: 14px; }
.issue-group h4 {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  color: var(--ink-2); margin-bottom: 8px;
}
.issue-group h4 .muted { color: var(--ink-3); }
.issue-card, .issue-row {
  padding: 10px 14px;
  margin-bottom: 6px;
  background: transparent;
  border: 1px solid var(--line);
  font-family: var(--font-body); font-size: 13px;
  color: var(--ink); line-height: 1.5;
}
.issue-card.chronic {
  border-left: 3px solid var(--danger);
}
.issue-card .issue-text, .issue-row { color: var(--ink); }
.chronic-label {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 9px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  padding: 2px 6px;
  border: 1px solid var(--danger); color: var(--danger);
  margin-right: 8px;
  vertical-align: baseline;
}
.issue-row .kind {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  color: var(--ink-3); margin-right: 8px;
}

/* ─────────────  Financial (Section 7)  ───────────── */
.financial-row {
  padding: 10px 14px; margin-bottom: 6px;
  background: transparent;
  border: 1px solid var(--line);
  font-family: var(--font-body); font-size: 13px;
  color: var(--ink); line-height: 1.5;
}
.financial-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column;
}
.financial-list li {
  display: flex; gap: 14px; align-items: baseline;
  padding: 8px 0;
  border-top: 1px solid var(--line);
}
.financial-list li:first-child { border-top: none; }
.financial-list .amt {
  font-family: var(--font-mono); font-variant-numeric: tabular-nums;
  color: var(--ink); font-size: 13px; font-weight: 500;
  min-width: 92px; flex: 0 0 auto; text-align: right;
}
.financial-list li > span:last-child {
  flex: 1; color: var(--ink-2); font-size: 13px; line-height: 1.5;
}
.financial-total {
  display: flex; gap: 14px; align-items: baseline;
  padding: 10px 0 10px 0; margin-bottom: 10px;
  border-bottom: 1px solid var(--line);
}
.financial-total .total-label {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: 0.12em;
  text-transform: uppercase; color: var(--ink-3);
  font-weight: 500; min-width: 92px; text-align: right;
}
.financial-total .total-num {
  font-family: var(--font-mono); font-variant-numeric: tabular-nums;
  font-size: 15px; font-weight: 600; color: var(--ink);
}

/* ─────────────  General notes (Section 8)  ───────────── */
.general-notes {
  display: flex; flex-direction: column; gap: 8px;
}
.general-note-card {
  padding: 12px 14px;
  background: transparent;
  border: 1px solid var(--line);
  border-left: 3px solid var(--line-2);
  font-family: var(--font-body); font-size: 13px;
  color: var(--ink); line-height: 1.5;
}
.general-note-card.chronic { border-left-color: var(--danger); }
.general-note-card .note-context {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; color: var(--ink-3);
  margin-bottom: 4px; font-weight: 500;
}
.general-note-card .note-text { color: var(--ink); }

/* ─────────────  Appendix tables (Reconciliation / Completed / Dismissed)  ───────────── */
.appendix-table {
  width: 100%; border-collapse: collapse;
  font-family: var(--font-body); font-size: 13px; color: var(--ink-2);
}
.appendix-table thead th {
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase; font-weight: 500;
  color: var(--ink-3); text-align: left;
  padding: 8px 10px; border-bottom: 1px solid var(--line);
}
.appendix-table tbody td {
  padding: 9px 10px; border-bottom: 1px solid var(--line);
}
.appendix-table .appx-id {
  font-family: var(--font-mono);
  font-size: 11px; color: var(--ink-3);
  letter-spacing: 0.04em; text-transform: uppercase;
}
.appendix-table .appx-job { color: var(--ink-2); }
.appendix-table .appx-when {
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: var(--ink-3);
}

/* ─────────────  Modals  ───────────── */
.modal-backdrop {
  position: fixed; inset: 0;
  background: rgba(19, 32, 40, 0.75);
  display: flex; align-items: center; justify-content: center;
  z-index: 50;
}
.modal {
  background: #ffffff;
  border: 1px solid var(--line-2);
  padding: 20px 22px; max-width: 520px; width: calc(100% - 40px);
  color: var(--ink);
}
.modal .modal-title {
  font-family: var(--font-display); font-weight: 500;
  font-size: 18px; margin-bottom: 8px;
}
.modal .modal-body {
  font-family: var(--font-mono); font-size: 12px;
  color: var(--danger); background: rgba(176, 85, 78, 0.08);
  border: 1px solid rgba(176, 85, 78, 0.25);
  padding: 10px 12px; white-space: pre-wrap; margin-bottom: 14px;
}
.modal .modal-actions { display: flex; gap: 8px; justify-content: flex-end; }

.spinner {
  width: 24px; height: 24px; border-radius: 999px;
  border: 3px solid var(--line-2); border-top-color: var(--stone-blue);
  animation: spin 0.9s linear infinite; margin-bottom: 10px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ─────────────  Upload modal + drop zone  ───────────── */
.upload-modal { max-width: 560px; }
.upload-modal .upload-hint {
  font-size: 13px; color: var(--ink-2); margin: 0 0 14px 0; line-height: 1.5;
}
.upload-modal .upload-hint code {
  font-family: var(--font-mono); font-size: 12px;
  color: var(--ink); background: var(--surface-2);
  padding: 1px 5px;
}
.upload-drop {
  border: 2px dashed var(--line-2);
  padding: 28px 16px; text-align: center;
  background: var(--surface-2);
  cursor: pointer;
  transition: background var(--d-fast) var(--ease-out),
              border-color var(--d-fast) var(--ease-out);
}
.upload-drop:hover, .upload-drop:focus { border-color: var(--stone-blue); outline: none; }
.upload-drop.drag-over {
  border-color: var(--stone-blue);
  background: rgba(91, 134, 153, 0.08);
}
.upload-drop-icon { font-size: 28px; margin-bottom: 6px; opacity: 0.7; }
.upload-drop-main {
  font-family: var(--font-display); font-size: 15px;
  color: var(--ink); font-weight: 500; margin-bottom: 4px;
}
.upload-drop-main strong { color: var(--stone-blue); }
.upload-drop-sub {
  font-family: var(--font-body); font-size: 12px; color: var(--ink-3);
}
.link-btn {
  background: none; border: none; padding: 0;
  color: var(--stone-blue); font: inherit; cursor: pointer;
  text-decoration: underline; text-underline-offset: 2px;
}
.link-btn:hover { color: var(--gulf-blue); }

.upload-list {
  margin-top: 14px;
  display: flex; flex-direction: column; gap: 4px;
  max-height: 240px; overflow-y: auto;
}
.upload-list .file-row {
  display: flex; justify-content: space-between; gap: 12px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  font-family: var(--font-mono); font-size: 11px;
  color: var(--ink-2);
}
.upload-list .file-row .name {
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;
}
.upload-list .file-row.ok  { color: var(--success); border-color: rgba(74, 138, 111, 0.35); }
.upload-list .file-row.err { color: var(--danger);  border-color: rgba(176, 85, 78, 0.35); }

/* Window-wide drop overlay: appears only while user is dragging files */
.drop-overlay {
  position: fixed; inset: 0; z-index: 60;
  background: rgba(19, 32, 40, 0.82);
  display: flex; align-items: center; justify-content: center;
  pointer-events: none;   /* overlay never blocks drops; the window listener handles them */
}
.drop-overlay-inner {
  border: 2px dashed var(--stone-blue);
  padding: 40px 50px; background: rgba(91, 134, 153, 0.08);
  text-align: center; max-width: 520px;
}
.drop-overlay-icon { font-size: 44px; margin-bottom: 10px; }
.drop-overlay-title {
  font-family: var(--font-display);
  font-size: 20px; color: var(--white-sand); font-weight: 500;
  letter-spacing: -0.01em;
}
.drop-overlay-sub {
  font-family: var(--font-mono); font-size: 11px;
  letter-spacing: var(--tracking-eyebrow); text-transform: uppercase;
  color: rgba(247, 245, 236, 0.7); margin-top: 6px;
}

/* ─────────────  Actions row (inline Edit/Dismiss etc)  ───────────── */
.actions-row, .item-card .actions-row {
  display: flex; gap: 8px; flex-wrap: wrap; align-items: center;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--line);
}

/* ─────────────  Footer  ───────────── */
footer.app-footer {
  max-width: 1400px; margin: 0 auto; padding: 20px 24px;
  color: var(--ink-3);
  font-family: var(--font-mono);
  font-size: 10px; letter-spacing: var(--tracking-eyebrow);
  text-transform: uppercase;
  border-top: 1px solid var(--line);
  display: flex; justify-content: space-between; gap: 14px; flex-wrap: wrap;
}

/* ─────────────  Reduced motion  ───────────── */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* ─────────────  Print — editorial paper layout (Phase 2)  ───────────── */

/* DOM element inserted by renderPM() is hidden — the running header is
   delivered via @page margin boxes instead so it sits in the top margin,
   never inside the content area, and therefore never overlaps items. */
.print-running-header { display: none; }

@page {
  size: letter;
  margin: 0.6in 0.6in 0.55in 0.6in;
  @top-left {
    content: "ROSS BUILT · MONDAY BINDER";
    font-family: "JetBrains Mono", monospace;
    font-size: 7.5pt;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(59, 88, 100, 0.55);
    padding-bottom: 3pt;
  }
  @top-right {
    content: counter(page) " / " counter(pages);
    font-family: "JetBrains Mono", monospace;
    font-size: 7.5pt;
    letter-spacing: 0.1em;
    color: rgba(59, 88, 100, 0.55);
    padding-bottom: 3pt;
  }
}

@media print {
  /* Quiet everything */
  * {
    animation: none !important;
    transition: none !important;
  }
  a { color: var(--slate-tile) !important; text-decoration: none !important; }
  a[href]::after { content: ""; }

  /* Paper — pure white, tighter type scale for print density */
  html, body {
    background: #ffffff !important;
    color: var(--slate-tile) !important;
    font-size: 9.5pt;
    line-height: 1.4;
  }
  main { padding: 0 !important; max-width: 100% !important; }
  .pm-view > * { margin-bottom: 0 !important; }

  /* Hide screen-only chrome */
  .app-header,
  .agenda-roadmap,
  #quickTools,
  .refresh-last,
  .refresh-status,
  .modal-backdrop,
  .job-filter-row,
  .actions-row,
  .meeting-header-actions,
  .email-btn,
  .danger-ghost,
  footer.app-footer { display: none !important; }

  /* Hide per-card interactive chrome but keep the item content */
  .item-card .actions-row,
  .item-card select,
  .item-card .status-select { display: none !important; }

  /* Phase 5 — strip every tip affordance in print: no underline, no info
     icon, no tooltip pseudo-element. PMs print clean text. */
  .tip { border-bottom: none !important; }
  .tip::after { display: none !important; }
  .tip-icon { display: none !important; }

  /* Phase 6 — Subs comparison row print behavior */
  .subs-comparison-toggle { display: none !important; }
  .vol-disclosure-icon { display: none !important; }
  .vol-popover { display: none !important; }
  .vol-disclosure-print {
    display: block !important;
    font-family: "JetBrains Mono", monospace;
    font-size: 8.5pt;
    font-style: italic;
    color: rgba(59, 88, 100, 0.60);
    letter-spacing: 0;
    margin-top: 2pt;
  }
  /* Comparison bar SVG renders fine in print — no override needed */
  .cmp-delta { color: var(--slate-tile) !important; }

  /* Expand every collapsible so the body prints */
  details { display: block !important; }
  details > summary { display: none !important; }
  details > .section-body {
    display: block !important;
    padding: 0 !important;
    border-top: none !important;
  }

  /* Flatten nested paper: transparent cards, hairline borders only */
  .section, .card, .meeting-section, details,
  .ataglance, .agenda-roadmap, details.collapsible {
    background: transparent !important;
    border-color: rgba(59,88,100,0.2) !important;
    box-shadow: none !important;
  }

  /* Page layout — each major section on its own page */
  #sec-lookbehind, #sec-siteactivity, #sec-headsup,
  #sec-w2, #sec-w4, #sec-w8,
  #sec-issues, #sec-financial, #sec-general {
    page-break-before: always;
  }
  #sec-open { page-break-before: auto; }   /* flows after meeting header */

  .meeting-section {
    page-break-inside: auto;
    margin-bottom: 0 !important;
    padding: 0 !important;
    border: none !important;
    orphans: 3;
    widows: 3;
  }
  .meeting-section > header {
    padding-bottom: 3pt; margin-bottom: 8pt;
    border-bottom: 1.5pt solid var(--slate-tile) !important;
    page-break-after: avoid;
  }

  /* Keep item cards and dashboard bar whole across page breaks */
  .item-card, .lb-card, .lookahead-card, .issue-card, .headsup-card,
  .sa-card, .job-overview-row, .overview-rollup,
  .financial-row, .issue-row, .transcript-entry,
  .appendix-table tr, .general-note-card {
    page-break-inside: avoid;
    background: transparent !important;
    color: var(--slate-tile) !important;
    border: 1pt solid rgba(59,88,100,0.2) !important;
  }
  /* Preserve job-color left edge on site-activity + overview cards in print */
  .sa-card, .job-overview-row {
    border-left: 3pt solid var(--job-color, rgba(59,88,100,0.4)) !important;
  }
  .ataglance { page-break-inside: avoid; }
  h1, h2, h3 { page-break-after: avoid; }

  /* Typography (px → pt, tight editorial scale) */
  h1 { font-size: 20pt !important; color: var(--slate-tile) !important; line-height: 1.1; }
  h2 { font-size: 13pt !important; color: var(--slate-tile) !important; line-height: 1.15; }
  h3 { font-size: 10.5pt !important; color: var(--slate-tile) !important; }
  .eyebrow, .mono-label, .priority-group-head, .lb-week, .appx-id, .appx-when {
    font-size: 7.5pt !important;
    color: rgba(59, 88, 100, 0.7) !important;
  }
  .section-subhead {
    font-size: 9pt !important;
    color: rgba(59, 88, 100, 0.75) !important;
    margin-bottom: 6pt !important;
  }
  .id-mono, .item-card .id-mono, .item-card .id { font-size: 8pt !important; }

  /* Ataglance bar: slate ink, stacked labels */
  .ataglance {
    border: 1pt solid rgba(59,88,100,0.2) !important;
    padding: 6pt 0 !important;
    margin-bottom: 6pt !important;
  }
  .ataglance .stat { padding: 0 14pt !important; border-right: 1pt solid rgba(59,88,100,0.15) !important; gap: 2pt !important; }
  .ataglance .stat:last-child { border-right: none !important; }
  .ataglance .stat-num { font-size: 15pt !important; color: var(--slate-tile) !important; }
  .ataglance .stat.accent .stat-num { color: var(--danger) !important; }
  .ataglance .stat-label { font-size: 7.5pt !important; }

  /* Pen-markup checkboxes — Open Items only */
  #sec-open .item-card .action-text::before {
    content: "☐  ";
    font-size: 13pt;
    vertical-align: -1pt;
    color: var(--slate-tile);
  }

  /* PM sign-off block at the end of every meeting section */
  .meeting-section::after {
    content: "PM INITIAL ________     DATE ________";
    display: block;
    margin-top: 6pt;
    padding-top: 4pt;
    border-top: 1pt solid rgba(59,88,100,0.2);
    font-family: "JetBrains Mono", monospace;
    font-size: 8pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(59, 88, 100, 0.6);
    text-align: right;
    page-break-before: avoid;
    break-before: avoid-page;
  }

  /* Update / notes — emphasized quoted annotation */
  .update-text, .item-card .update {
    color: rgba(59, 88, 100, 0.75) !important;
    font-style: italic;
    font-size: 8.5pt !important;
    border-left: 1pt solid rgba(59, 88, 100, 0.2) !important;
    padding-left: 6pt !important;
    margin-top: 3pt !important;
    line-height: 1.35;
  }

  /* Empty-state sections: slightly dim */
  .empty, .empty-state, .headsup-empty, .muted {
    opacity: 0.7;
  }

  /* Job-color left-edge bar stays — single color cue that survives monochrome scan */
  .item-card {
    position: relative;
    padding: 6pt 10pt 6pt 11pt !important;
    margin-bottom: 4pt !important;
  }
  .item-card .job-bar { display: block !important; }
  .item-card .card-top { gap: 6pt !important; margin-bottom: 2pt !important; }
  .item-card .action-text {
    font-size: 9.5pt !important;
    margin: 2pt 0 !important;
    line-height: 1.3;
  }
  /* Force action text to be fully expanded in print — PMs need full context on paper */
  .item-card .action-text[data-collapsible] .action-summary { display: none !important; }
  .item-card .action-text[data-collapsible] .action-full { display: inline !important; }
  .item-card .action-collapse-toggle { display: none !important; }
  .item-card .meta-row {
    font-size: 7.5pt !important;
    gap: 8pt !important;
    margin-top: 2pt !important;
  }
  .priority-group { margin-bottom: 8pt !important; }
  .priority-group-head { margin-bottom: 4pt !important; }
  /* Job section wrapping in print: clear separation without wasting paper */
  .job-section { margin-bottom: 10pt !important; padding-top: 2pt !important; }
  .job-section + .job-section {
    margin-top: 6pt !important;
    padding-top: 8pt !important;
    border-top: 1pt solid rgba(59,88,100,0.2) !important;
    page-break-before: auto;
  }
  .job-section-head { margin-bottom: 5pt !important; padding-bottom: 2pt !important; }
  .job-section-head h3 { font-size: 11pt !important; font-weight: 500; }
  .job-section-head .job-section-count { font-size: 7.5pt !important; }
  .job-section-head .job-section-total { font-size: 9pt !important; }
  .lb-card, .lookahead-card, .issue-card, .headsup-card {
    padding: 6pt 10pt !important;
    margin-bottom: 4pt !important;
  }
  .financial-row, .issue-row {
    padding: 4pt 8pt !important;
    margin-bottom: 3pt !important;
    font-size: 9pt !important;
  }
  .financial-list li {
    padding: 3pt 0 !important;
    font-size: 9pt !important;
    gap: 12pt !important;
  }
  .financial-list .amt {
    font-size: 8.5pt !important;
    min-width: 70pt !important;
  }
  .financial-list li > span:last-child { font-size: 9pt !important; }
  .financial-total {
    padding: 5pt 0 !important;
    margin-bottom: 6pt !important;
    gap: 12pt !important;
  }
  .financial-total .total-label { font-size: 8pt !important; min-width: 70pt !important; }
  .financial-total .total-num { font-size: 11pt !important; }
  .lb-grid, .lookahead-grid, .headsup-grid { gap: 8pt !important; }

  /* Tab-switch safety: pm-view should never be mid-fade in print */
  .pm-view { opacity: 1 !important; transform: none !important; }
  .pm-view .section { opacity: 1 !important; transform: none !important; }

  /* Running header now lives in @page margin boxes (above); the old
     position:fixed DOM element is suppressed in print as well. */
  .print-running-header { display: none !important; }

  /* ───── Jobs analytics tab (print) ───── */
  .jobs-view {
    padding: 0 !important;
  }
  .jobs-view-head h1 { font-size: 18pt !important; margin: 0 0 4pt; }
  .jobs-view-head .muted { font-size: 9pt !important; }
  .jobs-portfolio-rollup {
    border: 1pt solid rgba(59,88,100,0.25) !important;
    padding: 6pt 0 !important;
    margin-bottom: 10pt !important;
    page-break-inside: avoid;
  }
  .jobs-portfolio-rollup .rollup-stat {
    padding: 2pt 12pt !important;
    border-right: 1pt solid rgba(59,88,100,0.18) !important;
    font-size: 8pt !important;
  }
  .jobs-portfolio-rollup .rollup-stat b {
    font-size: 12pt !important;
    color: var(--slate-tile) !important;
  }
  .ja-card {
    page-break-inside: avoid;
    page-break-after: always;
    background: transparent !important;
    border: 1pt solid rgba(59,88,100,0.20) !important;
    border-left: 3pt solid var(--job-color, rgba(59,88,100,0.4)) !important;
    padding: 12pt 14pt !important;
    margin-bottom: 0 !important;
  }
  .ja-card:last-child { page-break-after: auto; }
  .ja-head { margin-bottom: 8pt !important; padding-bottom: 6pt !important; }
  .ja-title h2 { font-size: 14pt !important; }
  .ja-stats {
    grid-template-columns: repeat(7, 1fr) !important;
    gap: 6pt !important;
    margin-bottom: 6pt !important;
  }
  .ja-stat .lbl { font-size: 7pt !important; }
  .ja-stat .val { font-size: 14pt !important; }
  .ja-stat .val .sub { font-size: 8pt !important; }
  .ja-histogram {
    margin: 8pt 0 !important;
    padding: 6pt 0 !important;
    page-break-inside: avoid;
  }
  .ja-histogram svg { max-height: 90pt; }
  .ja-grid {
    grid-template-columns: 180pt 1fr !important;
    gap: 12pt !important;
    page-break-inside: avoid;
  }
  .ja-section h3 { font-size: 8pt !important; }
  .ja-rank { font-size: 9pt !important; }
  .phase-table { font-size: 8.5pt !important; }
  .phase-table th { font-size: 7pt !important; padding: 3pt 6pt !important; }
  .phase-table td { padding: 3pt 6pt !important; }
  .pt-status { font-size: 7.5pt !important; padding: 1pt 5pt !important; }
  /* Multi-burst badge — darker amber on print for AA contrast on white paper.
     Screen --warn (#C98A3B) ~3:1 on white; #b85400 raises this above 4.5:1. */
  .pt-status.multi-burst {
    color: #b85400 !important;
    border-color: #b85400 !important;
    background: transparent !important;
  }
  .pt-note { font-size: 7.5pt !important; }
  /* Phase row + its sub-attribution row stay together on the page. */
  .phase-table tr.phase-main-row,
  .phase-table tr.phase-subs-row { page-break-inside: avoid; }
  .phase-table tr.phase-main-row { page-break-after: avoid; }
  .pt-subs { font-size: 7.5pt !important; }
  .phase-subs-row > td { padding: 1pt 6pt 3pt 14pt !important; }
  .ja-events { margin-top: 8pt !important; padding-top: 6pt !important; }
  .ja-event { font-size: 8.5pt !important; }
  .ja-event-label, .ja-event-date { font-size: 7pt !important; }

  /* ───── Subs analytics tab (print) ───── */
  .subs-view-head h1 { font-size: 18pt !important; }
  .subs-filter, .subs-table-head { display: none !important; }
  .overlap-panel {
    page-break-inside: avoid;
    border: 1pt solid rgba(59,88,100,0.25) !important;
    border-left: 2pt solid var(--warn) !important;
    padding: 8pt 10pt !important;
    margin: 8pt 0 !important;
  }
  .overlap-panel h3 { font-size: 9pt !important; }
  .ov-row {
    grid-template-columns: 180pt 56pt 1fr !important;
    font-size: 9pt !important;
    padding: 2pt 0 !important;
  }
  .ov-jobtag { font-size: 7pt !important; padding: 0 4pt !important; }
  .subs-table { font-size: 8.5pt !important; page-break-inside: auto; }
  .subs-table thead { display: table-header-group; }
  .subs-table thead th { font-size: 7pt !important; padding: 3pt 6pt !important; }
  .subs-table tbody tr { page-break-inside: avoid; }
  .subs-table td { padding: 2pt 6pt !important; }
  .sub-spark { display: none !important; }  /* save space — recent col already shows magnitude */
  .rel-pct { font-size: 7.5pt !important; padding: 0 4pt !important; }
  /* Phase breakdown — PMs need this on paper for sub conversations.
     Force the hidden rows visible and hide the (now meaningless) chevron.
     Keep each sub's main row + phase row glued together so a sub's data
     never splits across pages. */
  .subs-table .sub-row,
  .subs-table .sub-phases { page-break-inside: avoid !important; }
  .subs-table .sub-row { page-break-after: avoid !important; }
  .sub-toggle, .sub-toggle-pad { display: none !important; }
  .sub-phases[hidden] { display: table-row !important; }
  .sub-phases > td {
    padding: 1pt 6pt 4pt 14pt !important;
    background: transparent !important;
  }
  .sub-phase-list { font-size: 7.5pt !important; gap: 1pt !important; }
  .sub-phase-list li { grid-template-columns: 140pt 50pt 1fr !important; gap: 4pt !important; }
  .sub-phase-jobs { font-size: 7pt !important; }
  /* Phase 19 — build-stage / trade-category section headers stay visible
     in print. Chevrons hidden; nested phase-l1 forced expanded so the
     printed PDF shows the full schedule-time breakdown without a click. */
  .subs-expand-all { display: none !important; }
  .subs-table tbody.subs-section-head td {
    background: transparent !important;
    padding: 8pt 0 2pt 0 !important;
    border-bottom: 0.5pt solid rgba(0,0,0,0.4) !important;
  }
  .subs-table tbody.subs-section-head h3 { font-size: 11pt !important; }
  .subs-table tbody.subs-section-head .ssh-eyebrow { font-size: 6.5pt !important; }
  .subs-table tbody.subs-section-head .ssh-count { font-size: 7pt !important; }
  .subs-table tbody.subs-cat-head td {
    background: transparent !important;
    padding: 4pt 4pt 2pt 4pt !important;
    border-top: 0.25pt solid rgba(0,0,0,0.2) !important;
    border-bottom: 0.25pt solid rgba(0,0,0,0.2) !important;
  }
  .subs-table tbody.subs-cat-head .sch-name { font-size: 8.5pt !important; }
  .subs-table tbody.subs-cat-head .sch-count { font-size: 7pt !important; }
  .phase-toggle { display: none !important; }
  .phase-l1 .phase-jobs { display: flex !important; }
  .phase-l1 .phase-l1-row { grid-template-columns: 0px 130pt 50pt 1fr !important; }
  .phase-l2-row { grid-template-columns: 0px 100pt 35pt 60pt 1fr !important; }
  .phase-l2-bullet { display: none !important; }
}

"""


# ---------------------------------------------------------------------------
# Client-side JavaScript (all in the generated HTML)
# ---------------------------------------------------------------------------

JS_TEMPLATE = r"""
/* ============================================================
   Monday Binder — client runtime
   ============================================================ */
const ALL_BINDERS = {ALL_BINDERS_JSON};
const TRANSCRIPT_HISTORY = {TRANSCRIPT_HISTORY_JSON};
const JOB_COLORS = {JOB_COLORS_JSON};
const PM_ORDER = {PM_ORDER_JSON};
const JOBS_DATA = {JOBS_DATA_JSON};
const SUBS_DATA = {SUBS_DATA_JSON};
const PHASE_DURATIONS = {PHASE_DURATIONS_JSON};
const TOOLTIPS = {TOOLTIPS_JSON};
const JOBS_TAB = '__JOBS__';
const SUBS_TAB = '__SUBS__';
const STATUS_MIGRATION = {
  'OPEN':'NOT_STARTED','IN PROGRESS':'IN_PROGRESS','IN_PROGRESS':'IN_PROGRESS',
  'DONE':'COMPLETE','KILLED':'COMPLETE','COMPLETE':'COMPLETE','BLOCKED':'BLOCKED',
  'NOT_STARTED':'NOT_STARTED','DISMISSED':'DISMISSED'
};
const CLOSED = new Set(['COMPLETE','DISMISSED']);
const TYPE_LIST = ['SELECTION','CONFIRMATION','PRICING','SCHEDULE','CO_INVOICE','FIELD','FOLLOWUP'];

let CURRENT_PM = PM_ORDER.find(pm => ALL_BINDERS[pm]);
let DATA = null;
let JOB_FILTER = 'all';

// Ensure item statuses/type are normalized & each item has an id.
function normalize(binder) {
  const items = binder.items || [];
  items.forEach(i => {
    i.status = STATUS_MIGRATION[i.status] || i.status;
    if (!i.type) i.type = 'FOLLOWUP';
  });
  return binder;
}

function ns(s) { return STATUS_MIGRATION[s] || s; }
function isActive(s) { return !CLOSED.has(ns(s)); }
// Phase 5 — wrap a label in a hover-tooltip span if it's in the dictionary.
// Mirrors generate_monday_binder.hint() so terms behave the same in the
// Python-rendered packets and the JS-rendered binder. Class is .tip (not
// .hint — that class is taken by the eyebrow style).
function hint(label) {
  if (label === null || label === undefined) return '';
  const key = String(label).trim().toUpperCase();
  const def = TOOLTIPS[key];
  const safe = escapeHtml(label);
  if (!def) return safe;
  const safeDef = escapeHtml(def);
  return '<span class="tip" tabindex="0" data-hint="' + safeDef + '">' + safe +
    '<svg class="tip-icon" viewBox="0 0 16 16" aria-hidden="true">' +
      '<circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.25"/>' +
      '<circle cx="8" cy="5" r="0.9" fill="currentColor"/>' +
      '<line x1="8" y1="7.5" x2="8" y2="12" stroke="currentColor" stroke-width="1.25" stroke-linecap="round"/>' +
    '</svg></span>';
}

function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}
function jobColor(job) { return JOB_COLORS[job] || '#525252'; }

function daysBetween(a, b) {
  const d1 = new Date(a), d2 = new Date(b);
  return Math.floor((d2 - d1) / 86400000);
}
function todayStr() { return new Date().toISOString().slice(0, 10); }
function agingFlag(item) {
  if (item.aging_flag) return item.aging_flag;
  if (!item.opened) return 'fresh';
  const days = Math.max(0, daysBetween(item.opened, todayStr()));
  if (days < 7) return 'fresh';
  if (days < 14) return 'aging';
  if (days < 30) return 'stale';
  return 'abandoned';
}
function agingRank(f) { return { abandoned: 0, stale: 1, aging: 2, fresh: 3 }[f] ?? 4; }
function priorityRank(p) { return { URGENT: 0, HIGH: 1, NORMAL: 2 }[p] ?? 3; }

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
  if (isNaN(+d)) return iso;
  return d.toLocaleDateString('en-US', { month: '2-digit', day: '2-digit', year: '2-digit' });
}
function formatLongDate(iso) {
  if (!iso) return '';
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
  if (isNaN(+d)) return iso;
  return d.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
}
function formatDateTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(+d)) return iso;
  return d.toLocaleString('en-US', { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

/* ============================================================
   Tab machinery
   ============================================================ */
function initTabs() {
  const container = document.getElementById('tabs');
  const pmTabs = PM_ORDER.filter(pm => ALL_BINDERS[pm]).map(pm => {
    const b = ALL_BINDERS[pm];
    const activeCount = (b.items || []).filter(i => isActive(i.status)).length;
    return `<button class="tab" role="tab" data-pm="${escapeHtml(pm)}" aria-selected="false">
      ${escapeHtml(pm)}<span class="tab-count">${activeCount}</span></button>`;
  }).join('');
  // "Jobs" + "Subs" analytics tabs — separate from per-PM meeting docs.
  const jobsCount = Object.keys(JOBS_DATA || {}).filter(k => k !== '__portfolio__').length;
  const jobsTab = `<button class="tab tab-jobs" role="tab" data-pm="${JOBS_TAB}" aria-selected="false" title="All-jobs daily-log analytics">
    Jobs<span class="tab-count">${jobsCount}</span></button>`;
  const subsCount = (SUBS_DATA && SUBS_DATA.subs) ? SUBS_DATA.subs.length : 0;
  const subsTab = `<button class="tab tab-subs" role="tab" data-pm="${SUBS_TAB}" aria-selected="false" title="Subcontractor performance + reliability">
    Subs<span class="tab-count">${subsCount}</span></button>`;
  container.innerHTML = pmTabs + jobsTab + subsTab;
  container.querySelectorAll('.tab').forEach(t => {
    t.addEventListener('click', () => activateTab(t.dataset.pm));
  });
}

function activateTab(pm) {
  CURRENT_PM = pm;
  document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-selected', t.dataset.pm === pm ? 'true' : 'false'));
  const view = document.getElementById('pmView');
  view.classList.add('switching');
  if (pm === JOBS_TAB) {
    DATA = null;
    setTimeout(() => {
      view.innerHTML = renderJobsView();
      wireJobsView();
      view.classList.remove('switching');
    }, 50);
    return;
  }
  if (pm === SUBS_TAB) {
    DATA = null;
    setTimeout(() => {
      view.innerHTML = renderSubsView();
      wireSubsView();
      view.classList.remove('switching');
    }, 50);
    return;
  }
  DATA = normalize(JSON.parse(JSON.stringify(ALL_BINDERS[pm])));
  JOB_FILTER = 'all';
  setTimeout(() => {
    render();
    view.classList.remove('switching');
  }, 180);
}

/* ============================================================
   Render orchestrator
   ============================================================ */
function render() {
  const view = document.getElementById('pmView');
  const pmName = DATA.meta?.pm || CURRENT_PM;
  const weekNum = DATA.meta?.week != null ? `Wk ${DATA.meta.week}` : '';
  const dateShort = (() => {
    const d = DATA.meta?.date;
    if (!d) return '';
    const [y, m, day] = d.split('-').map(Number);
    return (m && day && y) ? `${m}/${day}/${y}` : d;
  })();
  const runningHeaderParts = ['Ross Built', pmName, [weekNum, dateShort].filter(Boolean).join(' · ')].filter(Boolean);
  view.innerHTML = `
    <div class="print-running-header">${escapeHtml(runningHeaderParts.join('  ·  '))}</div>
    <div class="section"><div class="meeting-header">
      <div class="eyebrow">Weekly Meeting Binder</div>
      <div class="meeting-header-row">
        <h1>${escapeHtml(pmName)}</h1>
        <div class="meeting-header-actions">${renderHeaderEmailButton()}</div>
      </div>
      <div class="meeting-header-meta">${renderMeetingMeta()}</div>
      <div class="hint">${renderBinderGeneratedLine()}</div>
    </div></div>

    <nav class="section agenda-roadmap">${renderAgenda()}</nav>

    ${renderMissedLogsBanner()}

    <div class="section ataglance">${renderAtAGlance()}</div>

    <details class="section collapsible quick-tools" id="quickTools">
      <summary><span class="chev">▸</span><span>Tools</span><span class="summary-count">search · filter · print</span></summary>
      <div class="section-body"><div class="tools-row">${renderQuickTools()}</div></div>
    </details>

    <details class="section collapsible transcript-history">
      <summary><span class="chev">▸</span><span>Transcript history</span>
        <span class="summary-count">${(TRANSCRIPT_HISTORY[CURRENT_PM] || []).length} processed</span></summary>
      <div class="section-body">${renderTranscriptHistory()}</div>
    </details>

    <section class="section meeting-section" id="sec-open">${renderSection1_Open()}</section>
    <section class="section meeting-section" id="sec-lookbehind">${renderSection2_LookBehind()}</section>
    <section class="section meeting-section" id="sec-headsup">${renderSection2_5_HeadsUp()}</section>
    <section class="section meeting-section" id="sec-w2">${renderLookaheadSection(2, '2-Week Look-Ahead', 'Must be confirmed: start, duration, sub')}</section>
    <section class="section meeting-section" id="sec-w4">${renderLookaheadSection(4, '4-Week Look-Ahead', 'Sequencing + confirmations pending')}</section>
    <section class="section meeting-section" id="sec-w8">${renderLookaheadSection(8, '8-Week Look-Ahead', 'Long-lead materials · selections gates')}</section>
    <section class="section meeting-section" id="sec-issues">${renderSection6_Issues()}</section>
    ${(() => { const s = renderSection7_Financial(); return s ? `<section class="section meeting-section" id="sec-financial">${s}</section>` : ''; })()}
    ${(() => { const s = renderSection8_General(); return s ? `<section class="section meeting-section" id="sec-general">${s}</section>` : ''; })()}

    <details class="section collapsible">
      <summary><span class="chev">▸</span><span>Reconciliation vs. BT daily logs</span>
        <span class="summary-count">${(DATA.reconciliation || []).length}</span></summary>
      <div class="section-body">${renderReconciliation()}</div>
    </details>

    <details class="section collapsible">
      <summary><span class="chev">▸</span><span>Completed items</span>
        <span class="summary-count">${(DATA.items || []).filter(i => ns(i.status) === 'COMPLETE').length}</span></summary>
      <div class="section-body">${renderAppendixTable('COMPLETE')}</div>
    </details>

    <details class="section collapsible">
      <summary><span class="chev">▸</span><span>Dismissed items</span>
        <span class="summary-count">${(DATA.items || []).filter(i => ns(i.status) === 'DISMISSED').length}</span></summary>
      <div class="section-body">${renderAppendixTable('DISMISSED')}</div>
    </details>
  `;
  // Stagger
  const sections = view.querySelectorAll('.section');
  sections.forEach((s, i) => { s.style.animationDelay = `${Math.min(i, 10) * 40}ms`; });
  wireAgenda();
  wireJobFilter();
}

function renderMeetingMeta() {
  const m = DATA.meta || {};
  const dateLong = formatLongDate(m.date);
  const type = m.type ? `${m.type.charAt(0)}${m.type.slice(1).toLowerCase()} meeting` : '';
  const week = m.week ? `Week ${m.week}` : '';
  return [dateLong, week, type].filter(Boolean).join(' · ');
}
function renderBinderGeneratedLine() {
  return `Generated ${document.body.dataset.generated || ''}`;
}

/* ============================================================
   Agenda roadmap
   ============================================================ */
const AGENDA = [
  { id: 'sec-open',       label: 'Open items',       time: '5 min' },
  { id: 'sec-lookbehind', label: 'Last 2 weeks',     time: '2 min' },
  { id: 'sec-headsup',    label: 'Heads Up',         time: '2 min' },
  { id: 'sec-w2',         label: '2-Week',           time: '4 min' },
  { id: 'sec-w4',         label: '4-Week',           time: '2 min' },
  { id: 'sec-w8',         label: '8-Week',           time: '2 min' },
  { id: 'sec-issues',     label: 'Issues',           time: '3 min' },
  { id: 'sec-financial',  label: 'Financial',        time: '2 min' },
  { id: 'sec-general',    label: 'General notes',    time: '2 min' },
];
function renderAgenda() {
  // Skip agenda pills for sections we hide when empty (Financial / General notes
  // may not render if their data arrays are empty — keep the agenda numbering
  // accurate by filtering them out here too).
  const finEmpty = !((DATA.financial || []).length);
  const genEmpty = !((DATA.generalNotes || []).length);
  const visible = AGENDA.filter(a => !(a.id === 'sec-financial' && finEmpty) && !(a.id === 'sec-general' && genEmpty));
  return visible.map((a, i) => `
    <button class="agenda-pill" data-scroll="${a.id}">
      <span class="num">${i + 1}</span>
      <span>${a.label}</span>
      <span class="time">${a.time}</span>
    </button>`).join('');
}
function wireAgenda() {
  // Event delegation so re-renders don't orphan listeners.
  const view = document.getElementById('pmView');
  if (!view || view.dataset.agendaWired === '1') return;
  view.dataset.agendaWired = '1';
  view.addEventListener('click', (e) => {
    const pill = e.target.closest('.agenda-pill');
    if (!pill || !pill.dataset.scroll) return;
    const el = document.getElementById(pill.dataset.scroll);
    if (!el) return;
    // Compute absolute Y — offsetTop chains don't always handle sticky headers
    // correctly, so use getBoundingClientRect + current scroll.
    const rect = el.getBoundingClientRect();
    const target = window.scrollY + rect.top - 60; // 60px leeway for sticky header
    // Prefer smooth, but fall back to instant if the page is scrolled by something else.
    window.scrollTo({ top: target, left: 0, behavior: 'smooth' });
    // Safety net: force the scroll after 50ms in case smooth scroll was pre-empted.
    setTimeout(() => {
      if (Math.abs(window.scrollY - target) > 40) window.scrollTo(0, target);
    }, 50);
  });
}

/* ============================================================
   At-a-glance strip
   ============================================================ */
/* Missed-logs banner — shows when this PM's jobs have logged less than the
   weekday count this month. Surfaces accountability at the top of the meeting
   doc so missed logs don't go unnoticed. */
function renderMissedLogsBanner() {
  const pmMissed = (JOBS_DATA && JOBS_DATA.__portfolio__ && JOBS_DATA.__portfolio__.pm_missed) || {};
  const data = pmMissed[CURRENT_PM];
  if (!data || !data.current_month_missed) return '';

  const total = data.current_month_missed;
  const trailing3 = data.trailing_3mo_missed;
  const severity = total >= 8 ? 'high' : total >= 3 ? 'mid' : 'low';
  const perJob = (data.per_job || [])
    .filter(j => j.current_month_missed > 0)
    .sort((a, b) => b.current_month_missed - a.current_month_missed)
    .map(j => {
      const col = jobColor(j.short_name);
      return `<span class="missed-pill" style="--job-color:${col}">${escapeHtml(j.short_name)}<b>${j.current_month_missed}</b></span>`;
    }).join('');

  const dormantLine = (data.dormant_jobs && data.dormant_jobs.length)
    ? `<p class="missed-banner-dormant">Dormant (${data.dormant_jobs.length}, excluded from total): ${data.dormant_jobs.map(j => escapeHtml(j)).join(', ')}</p>`
    : '';
  return `<div class="missed-banner ${severity}">
    <div class="missed-banner-head">
      <span class="missed-icon">⚠</span>
      <span class="missed-title">${total} missed log day${total === 1 ? '' : 's'} this month</span>
      <span class="missed-sub">· ${trailing3} in last 3 mo</span>
    </div>
    <div class="missed-banner-detail">${perJob}</div>
    ${dormantLine}
    <p class="missed-banner-note">Daily logs missed on workdays (excluding weekends + US federal holidays). Consistent logs feed every analytic in this binder — gaps degrade the signal.</p>
  </div>`;
}

function renderAtAGlance() {
  const items = DATA.items || [];
  const open = items.filter(i => isActive(i.status));
  const urgent = open.filter(i => i.priority === 'URGENT').length;
  const stale = open.filter(i => ['stale', 'abandoned'].includes(agingFlag(i))).length;
  const done = items.filter(i => ns(i.status) === 'COMPLETE').length;
  const total = open.length + done;
  const ppc = total ? Math.round(100 * done / total) : 0;
  return `
    <div class="stat"><span class="stat-num">${open.length}</span>&nbsp;<span class="stat-label">${hint('open')}</span></div>
    <span class="sep">·</span>
    <div class="stat ${urgent ? 'accent' : ''}"><span class="stat-num">${urgent}</span>&nbsp;<span class="stat-label">${hint('URGENT')}</span></div>
    <span class="sep">·</span>
    <div class="stat"><span class="stat-num">${stale}</span>&nbsp;<span class="stat-label">${hint('stale 14d+')}</span></div>
    <span class="sep">·</span>
    <div class="stat"><span class="stat-num">${ppc}%</span>&nbsp;<span class="stat-label">${hint('PPC')}</span></div>
  `;
}

/* ============================================================
   Quick tools (search, filters, print)
   ============================================================ */
function renderQuickTools() {
  const pmEsc = escapeHtml(CURRENT_PM || '');
  const firstName = (CURRENT_PM || '').split(' ')[0] || 'PM';
  return `
    <input type="search" class="search" id="qtSearch" placeholder="Filter items…">
    <span class="tool-sep">·</span>
    <select id="qtPriority"><option value="">All priorities</option><option>URGENT</option><option>HIGH</option><option>NORMAL</option></select>
    <select id="qtStatus"><option value="">All statuses</option><option>NOT_STARTED</option><option>IN_PROGRESS</option><option>BLOCKED</option><option>COMPLETE</option><option>DISMISSED</option></select>
    <span class="tool-sep">·</span>
    <button class="ghost small" onclick="window.print()" aria-label="Print">🖨 Print</button>
    <button class="email-btn" data-pm="${pmEsc}" data-location="tools" onclick="emailPM('${pmEsc}', this)" aria-label="Email ${pmEsc}">📧 Email ${escapeHtml(firstName)}</button>
  `;
}

function renderHeaderEmailButton() {
  const pmEsc = escapeHtml(CURRENT_PM || '');
  const firstName = (CURRENT_PM || '').split(' ')[0] || 'PM';
  return `<button class="email-btn" data-pm="${pmEsc}" data-location="header" onclick="emailPM('${pmEsc}', this)" aria-label="Email ${pmEsc}">📧 Email ${escapeHtml(firstName)}</button>`;
}

/* ============================================================
   Email — generate PDF + open Outlook draft
   ============================================================ */
async function emailPM(pmName, btn) {
  if (!btn) btn = document.querySelector(`.email-btn[data-pm="${CSS.escape(pmName)}"]`);
  if (!btn) return;
  const original = btn.innerHTML;
  btn.disabled = true;
  btn.classList.remove('success');
  btn.textContent = '📧 Preparing PDF…';
  try {
    const res = await fetch(`/email/${encodeURIComponent(pmName)}`, { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (res.ok && data.success) {
      btn.classList.add('success');
      btn.textContent = '📧 Draft opened in Outlook';
      setTimeout(() => {
        btn.classList.remove('success');
        btn.disabled = false;
        btn.innerHTML = original;
      }, 3500);
    } else {
      const msg = (data && data.message) || `HTTP ${res.status}`;
      // Outlook COM may have failed but PDF was generated — surface the mailto fallback path.
      const draft = data && data.draft;
      if (draft && draft.mailto_url) {
        const open = confirm(
          `Outlook COM couldn't open a draft.\n\n${draft.reason || msg}\n\n` +
          `PDF saved to:\n${data.pdf_path}\n\n` +
          `Click OK to open a mailto: draft — you'll need to attach the PDF manually.`
        );
        if (open) window.location.href = draft.mailto_url;
      } else {
        alert(`Email failed: ${msg}`);
      }
      btn.disabled = false;
      btn.innerHTML = original;
    }
  } catch (err) {
    alert(`Email failed: ${err.message || err}`);
    btn.disabled = false;
    btn.innerHTML = original;
  }
}

/* ============================================================
   Transcript history
   ============================================================ */
function renderTranscriptHistory() {
  const hist = TRANSCRIPT_HISTORY[CURRENT_PM] || [];
  if (hist.length === 0) {
    return `<div class="transcript-entry empty">No transcripts processed yet. System will track each future processing.</div>`;
  }
  return `<div class="transcript-log">${hist.map(h => {
    const dt = formatDateTime(h.processed_at);
    const fname = h.transcript ? escapeHtml(h.transcript) : '<em>transcript not matched</em>';
    let deltaHtml = '';
    if (h.delta != null) {
      const cls = h.delta >= 0 ? 'delta-pos' : 'delta-neg';
      const sign = h.delta > 0 ? '+' : '';
      deltaHtml = `<span class="${cls}">${h.pre_count} → ${h.post_count} (${sign}${h.delta})</span>`;
    } else if (h.post_count != null) {
      deltaHtml = `<span>${h.post_count} items (first binder)</span>`;
    }
    const recon = h.reconciliation_entries ? ` · ${h.reconciliation_entries} reconciliation entries` : '';
    return `
      <div class="transcript-entry">
        <div class="filename">${fname}</div>
        <div class="line">Processed ${dt}</div>
        <div class="line">${deltaHtml}${recon}</div>
      </div>`;
  }).join('')}</div>`;
}

/* ============================================================
   Section 1 — open items (grouped by JOB, then by priority)
   ============================================================ */
function renderSection1_Open() {
  const items = (DATA.items || []).filter(i => isActive(i.status));
  const jobs = [...new Set(items.map(i => i.job || 'Unknown'))].sort();
  const jobChips = renderJobChips(jobs, items);
  const filtered = JOB_FILTER === 'all' ? items : items.filter(i => (i.job || '') === JOB_FILTER);

  // Group items by job. For single-job PMs this still works — one job block
  // renders without extra visual noise. For multi-job PMs (Bob, Jason, Lee,
  // Nelson) this keeps each job's items distinct so Krauss and Ruthven don't
  // intermingle in the same priority bucket.
  const byJob = {};
  filtered.forEach(i => { (byJob[i.job || 'Unknown'] = byJob[i.job || 'Unknown'] || []).push(i); });
  const jobsInView = Object.keys(byJob).sort();

  const priorityGroups = (list) => {
    const groups = [['URGENT', 'urgent'], ['HIGH', 'high'], ['NORMAL', 'normal']];
    return groups.map(([prio, cls]) => {
      const plist = list.filter(i => i.priority === prio);
      if (!plist.length) return '';
      plist.sort((a, b) => agingRank(agingFlag(a)) - agingRank(agingFlag(b)));
      return `
        <div class="priority-group">
          <div class="priority-group-head">
            <span class="dot ${cls}"></span>
            <span>${prio}</span>
            <span class="group-count">${plist.length}</span>
          </div>
          <div class="item-stack">${plist.map(renderItemCard).join('')}</div>
        </div>`;
    }).join('');
  };

  const jobBlocks = jobsInView.map(job => {
    const list = byJob[job];
    const col = jobColor(job);
    const body = priorityGroups(list) || '<p class="muted">No active items.</p>';
    return `
      <div class="job-section" data-job="${escapeHtml(job)}">
        <div class="job-section-head">
          <span class="dot" style="background:${col}"></span>
          <h3>${escapeHtml(job)}</h3>
          <span class="job-section-count">${list.length}</span>
        </div>
        ${body}
      </div>`;
  }).join('');

  return `
    <header>
      <div class="eyebrow">Section 1</div>
      <h2>Open items</h2>
      <span class="time-tag">5 min</span>
    </header>
    <div class="job-filter-row" id="jobFilterRow">${jobChips}</div>
    ${jobBlocks || '<p class="muted">No active items.</p>'}
  `;
}

/* Heuristic job extraction — scan text for any of this PM's job names.
   Used by sections whose schema doesn't carry an explicit job field yet
   (issues, financial). First match wins. */
function inferJobFromText(text, jobs) {
  if (!text || !jobs || !jobs.length) return 'General';
  const t = text.toLowerCase();
  for (const j of jobs) {
    if (!j) continue;
    const pat = new RegExp('\\b' + j.replace(/[.*+?^${}()|[\\]\\\\]/g, '\\\\$&').toLowerCase() + '\\b');
    if (pat.test(t)) return j;
  }
  return 'General';
}

function renderJobChips(jobs, items) {
  const all = items.length;
  const allChip = `<button class="chip with-count" aria-pressed="${JOB_FILTER === 'all'}" data-job="all">All <span class="count">${all}</span></button>`;
  const perJob = jobs.map(j => {
    const count = items.filter(i => (i.job || '') === j).length;
    const col = jobColor(j);
    return `<button class="chip with-count" aria-pressed="${JOB_FILTER === j}" data-job="${escapeHtml(j)}">
      <span class="dot" style="background:${col}"></span>${escapeHtml(j)}<span class="count">${count}</span></button>`;
  }).join('');
  return allChip + perJob;
}

function wireJobFilter() {
  const row = document.getElementById('jobFilterRow');
  if (!row) return;
  row.querySelectorAll('.chip').forEach(c => {
    c.addEventListener('click', () => {
      JOB_FILTER = c.dataset.job;
      // Re-render just Section 1 in place
      const sec = document.getElementById('sec-open');
      sec.innerHTML = renderSection1_Open();
      wireJobFilter();
    });
  });
}

function renderItemCard(item) {
  const job = item.job || '—';
  const col = jobColor(job);
  const type = item.type || 'FOLLOWUP';
  const af = agingFlag(item);
  const daysOpen = (typeof item.days_open === 'number') ? item.days_open : Math.max(0, daysBetween(item.opened || todayStr(), todayStr()));
  const aging = af === 'fresh' ? '' : `<span class="aging-badge ${af}" title="${daysOpen} days open">${{'aging':'7d+','stale':'14d+','abandoned':'30d+'}[af]}</span>`;
  const prioCls = (item.priority || 'NORMAL').toLowerCase();
  const opts = ['NOT_STARTED','IN_PROGRESS','BLOCKED','COMPLETE','DISMISSED']
    .map(s => `<option ${s === ns(item.status) ? 'selected' : ''}>${s}</option>`).join('');
  const btEvidence = (DATA.reconciliation || []).some(r => r.item_id === item.id);

  // Action text: collapsible on screen, fully expanded in print.
  // Summary = first sentence OR first 80 chars at a word boundary.
  const fullAction = item.action || '';
  const isLong = fullAction.length > 80;
  let summary = fullAction;
  if (isLong) {
    const sentMatch = fullAction.match(/^[^.!?]*[.!?]/);
    if (sentMatch && sentMatch[0].length >= 30 && sentMatch[0].length <= 120) {
      summary = sentMatch[0].trim();
    } else {
      const cut = fullAction.lastIndexOf(' ', 80);
      summary = fullAction.slice(0, cut > 40 ? cut : 80).trim() + '…';
    }
  }
  const actionHtml = isLong
    ? `<div class="action-text" data-collapsible="1" data-expanded="0">
        <span class="action-summary">${escapeHtml(summary)}</span>
        <span class="action-full">${escapeHtml(fullAction)}</span>
        <button type="button" class="action-collapse-toggle" onclick="toggleItemAction(this)" aria-expanded="false" aria-label="Expand action text">▾</button>
      </div>`
    : `<div class="action-text">${escapeHtml(fullAction)}</div>`;

  return `
    <article class="item-card" data-id="${item.id}" style="--job-color:${col}">
      <div class="job-bar" style="background:${col}"></div>
      <div class="card-body">
        <div class="card-top">
          <span class="type-badge type-${type}">${type}</span>
          <span class="job-label">${escapeHtml(job)}</span>
          <span class="id-mono">${escapeHtml(item.id || '')}</span>
          ${aging}
          <span class="priority-pill"><span class="dot ${prioCls}"></span>${item.priority || 'NORMAL'}</span>
        </div>
        ${actionHtml}
        <div class="meta-row">
          <span><span class="eyebrow">Owner</span>${escapeHtml(item.owner || '—')}</span>
          <span><span class="eyebrow">Due</span>${escapeHtml(formatDate(item.due))}</span>
          <span><span class="eyebrow">Opened</span>${escapeHtml(formatDate(item.opened))}</span>
        </div>
        ${item.update ? `<div class="update-text">${escapeHtml(item.update)}</div>` : ''}
        <div class="actions-row">
          <select onchange="updateStatus('${item.id}', this.value)">${opts}</select>
          ${btEvidence ? '<button class="ghost small" onclick="scrollToRecon(\'' + escapeHtml(item.id) + '\')" title="Jump to reconciliation entry">BT evidence</button>' : ''}
          <button class="ghost small" onclick="openEdit('${item.id}')">Edit</button>
          <button class="danger-ghost small" onclick="dismissItem('${item.id}')">Dismiss</button>
        </div>
      </div>
    </article>
  `;
}

/* Toggle expand/collapse on action-text. data-expanded controls visibility via CSS;
   the chevron rotates 180deg when expanded. Print CSS forces full text visible. */
function toggleItemAction(btn) {
  const wrap = btn.closest('.action-text[data-collapsible]');
  if (!wrap) return;
  const expanded = wrap.dataset.expanded === '1';
  wrap.dataset.expanded = expanded ? '0' : '1';
  btn.setAttribute('aria-expanded', expanded ? 'false' : 'true');
}

/* ============================================================
   Jobs analytics tab — own sheet, per-job lifetime + monthly trends
   Pulls from JOBS_DATA (computed in Python from BT daily-logs.json).
   Each card is one canonical job (Fish, Pou, Drummond, ...). PMs see
   only their meeting docs; this tab is for portfolio-wide review.
   ============================================================ */
function renderJobsView(filterPM) {
  const data = JOBS_DATA || {};
  const portfolio = filterPM ? null : (data.__portfolio__ || {});
  let keys = Object.keys(data).filter(k => k !== '__portfolio__');
  if (filterPM) {
    keys = keys.filter(k => data[k].pm === filterPM);
  }
  if (keys.length === 0) {
    return `<div class="jobs-view-empty">
      <h2>Jobs</h2>
      <p class="muted"><em>No daily-log data yet. Run a refresh to scrape Buildertrend.</em></p>
    </div>`;
  }

  // Order: by PM (matches PM_ORDER), then alphabetical within PM
  const order = [];
  for (const pm of PM_ORDER) {
    const sorted = keys.filter(k => data[k].pm === pm).sort();
    order.push(...sorted);
  }
  // Append any orphans (no PM mapping)
  keys.filter(k => !order.includes(k)).forEach(k => order.push(k));

  // Portfolio rollup — use Python-computed totals when unfiltered;
  // recompute on the fly when filtered to a single PM.
  let pf = portfolio;
  if (filterPM) {
    const subset = order.map(k => data[k]);
    const subs = new Set();
    let pdays = 0, dd = 0, ii = 0, ld = 0;
    for (const j of subset) {
      const lt = j.lifetime || {};
      pdays += lt.total_person_days || 0;
      dd += lt.delivery_days || 0;
      ii += lt.inspection_days || 0;
      ld += lt.total_days || 0;
      (j.top_crews || []).forEach(c => subs.add((c.name || '').trim().toLowerCase()));
    }
    pf = {
      jobs: subset.length,
      unique_subs: subs.size,
      total_person_days: pdays,
      delivery_days: dd,
      inspection_days: ii,
      total_log_days: ld,
    };
  }
  // Phase 17 — tooltips on each rollup stat for the Jobs view.
  const rollup = `<div class="jobs-portfolio-rollup">
    <span class="rollup-stat" title="Distinct daily log entries (1 per calendar date)."><b>${pf.jobs ?? order.length}</b> active jobs</span>
    <span class="rollup-stat" title="Distinct subcontractors that appeared in any daily log."><b>${(pf.unique_subs ?? 0).toLocaleString()}</b> unique subs</span>
    <span class="rollup-stat" title="Sum of daily workforce headcount across all logs. Approximate labor metric."><b>${(pf.total_person_days ?? 0).toLocaleString()}</b> person-days</span>
    <span class="rollup-stat" title="Distinct days with a delivery_details entry."><b>${pf.delivery_days ?? 0}</b> delivery days</span>
    <span class="rollup-stat" title="Distinct days with an inspection_details entry."><b>${pf.inspection_days ?? 0}</b> inspection days</span>
    <span class="rollup-stat" title="Distinct daily log entries across all jobs."><b>${(pf.total_log_days ?? 0).toLocaleString()}</b> total log days</span>
  </div>`;

  const cards = order.map(k => renderJobAnalyticsCard(data[k])).join('');

  // Phase 17 — Phase Glossary access from the Jobs tab as well. Same
  // overlay as on the Subs tab — single source of truth.
  const jobsControls = `<div class="subs-view-controls">
    <button type="button" class="subs-glossary-btn" onclick="openGlossary()" title="Open the BT phase glossary — every parent_group_activity tag explained.">📖 Phase Glossary</button>
  </div>`;

  // Phase 18 — Phase Durations panel sits above the per-job cards. Lets
  // the operator answer "how long does Plumbing Rough In typically take,
  // and is this job slow?" without scrolling through 11 cards.
  const phaseDurationsPanel = renderPhaseDurationsPanel(filterPM);

  return `
    <div class="jobs-view">
      <header class="jobs-view-head">
        <div>
          <div class="eyebrow">Daily-log analytics</div>
          <h1>Jobs</h1>
          <p class="muted">Lifetime per-job activity from Buildertrend daily logs. Updated each refresh.</p>
        </div>
      </header>
      ${rollup}
      ${jobsControls}
      ${phaseDurationsPanel}
      <div class="jobs-card-list">${cards}</div>
    </div>`;
}

/* Phase 18 — phase-centric duration table. Pivots PHASE_DURATIONS data
   into a sortable + filterable table where each row is one phase tag
   and the columns aggregate cross-job stats (median, p25-p75, range,
   job_count, active_count). Click a row to expand into per-job detail
   with benchmark badges. */
let PHASE_DUR_SORT = 'sequence';     // sequence | median | active | volume
let PHASE_DUR_FILTER = '';
let PHASE_DUR_FILTER_PM = '';        // null/'' = portfolio-wide
let PHASE_DUR_EXPANDED = new Set();  // phase-tag set tracked across re-renders

function renderPhaseDurationsPanel(filterPM) {
  const phases = PHASE_DURATIONS && typeof PHASE_DURATIONS === 'object'
    ? Object.entries(PHASE_DURATIONS)
    : [];
  if (!phases.length) {
    return `<section class="phase-dur-panel">
      <header class="phase-dur-head"><h3>Phase Durations</h3></header>
      <p class="muted">No phase data yet — refresh BT logs.</p>
    </section>`;
  }
  PHASE_DUR_FILTER_PM = filterPM || '';

  // PM filter: when a PM is selected, restrict each phase's by_job view
  // to only their jobs. Phase rows with zero jobs after filter are
  // dropped. Summary stats are recomputed against the filtered set so
  // numbers reflect "this PM's portfolio" not the whole company.
  const pmJobs = new Set();
  if (filterPM && typeof JOBS_DATA === 'object') {
    for (const [k, v] of Object.entries(JOBS_DATA)) {
      if (k !== '__portfolio__' && v && v.pm === filterPM) pmJobs.add(v.short_name || k);
    }
  }
  const visiblePhases = phases.map(([tag, e]) => {
    let by_job = e.by_job;
    let summary = e.summary;
    if (filterPM && pmJobs.size) {
      const fjobs = {};
      for (const [j, jd] of Object.entries(by_job)) if (pmJobs.has(j)) fjobs[j] = jd;
      if (Object.keys(fjobs).length === 0) return null;
      summary = recomputePhaseSummary(fjobs);
      by_job = fjobs;
    }
    return [tag, {category: e.category, by_job, summary}];
  }).filter(Boolean);

  // Filter by name match
  const nf = (PHASE_DUR_FILTER || '').toLowerCase();
  const filteredPhases = nf
    ? visiblePhases.filter(([tag]) => tag.toLowerCase().includes(nf))
    : visiblePhases;

  // Sort
  const SEQ_ORDER = ['Site/Excavation','Engineering/Insp','Concrete','Pavers/Hardscape',
    'Framing','Carpentry/Stairs','Roofing','Siding','Stucco/Plaster','Insulation',
    'Windows/Doors','Plumbing','Electrical','HVAC','Audio/Video','Drywall',
    'Tile/Floor','Trim/Finish','Paint','Cabinetry','Stone/Counters','Appliances',
    'Interior Design','Pool/Spa','Landscape','Fence/Gate','Metal/Welding'];
  const seqIdx = (cat) => {
    const i = SEQ_ORDER.indexOf(cat);
    return i < 0 ? 99 : i;
  };
  // Sample-size gate for sorts that depend on a stable median. Phases
  // with <3 jobs go to the bottom of "median duration" sort because
  // their displayed median is suppressed anyway.
  const sortFn = {
    'sequence': (a, b) => {
      const ai = seqIdx(a[1].category), bi = seqIdx(b[1].category);
      if (ai !== bi) return ai - bi;
      return a[0].localeCompare(b[0]);
    },
    'median': (a, b) => {
      const aIns = a[1].summary.job_count < 3 ? 1 : 0;
      const bIns = b[1].summary.job_count < 3 ? 1 : 0;
      if (aIns !== bIns) return aIns - bIns;  // insufficient → bottom
      return (b[1].summary.median_days || 0) - (a[1].summary.median_days || 0);
    },
    'active': (a, b) => (b[1].summary.active_count || 0) - (a[1].summary.active_count || 0),
    'volume': (a, b) => (b[1].summary.total_active_days || 0) - (a[1].summary.total_active_days || 0),
  }[PHASE_DUR_SORT] || sortFn['sequence'];
  filteredPhases.sort(sortFn);

  const rows = filteredPhases.map(([tag, e]) => renderPhaseDurationRow(tag, e)).join('');

  const sortBtn = (key, label) =>
    `<button type="button" class="pd-sort-btn ${PHASE_DUR_SORT === key ? 'active' : ''}" data-pd-sort="${key}">${label}</button>`;
  const pmHint = filterPM ? ` <span class="muted" style="font-size:11px">(${escapeHtml(filterPM)}'s jobs only)</span>` : '';

  return `<section class="phase-dur-panel">
    <header class="phase-dur-head">
      <h3 title="Cross-job duration aggregates per parent_group_activity tag.">Phase Durations${pmHint}</h3>
      <div class="phase-dur-controls">
        <input type="search" class="pd-filter" placeholder="Filter phases…" value="${escapeHtml(PHASE_DUR_FILTER)}">
        <span class="muted" style="font-size:10px; letter-spacing:0.04em; text-transform:uppercase">Sort:</span>
        ${sortBtn('sequence', 'Build sequence')}
        ${sortBtn('median', 'Median duration')}
        ${sortBtn('active', 'Active jobs')}
        ${sortBtn('volume', 'Total volume')}
      </div>
    </header>
    <table class="phase-dur-table">
      <thead><tr>
        <th class="pd-col-phase">Phase</th>
        <th class="pd-col-cat">Category</th>
        <th class="right">${hint('Med')}</th>
        <th class="right">${hint('P25-P75')}</th>
        <th class="right">${hint('Range')}</th>
        <th class="right">${hint('Span')}</th>
        <th class="right">${hint('Jobs')}</th>
        <th class="right">${hint('Active')}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    ${filteredPhases.length === 0 ? '<p class="muted" style="padding:12px">— no phases match the current filter —</p>' : ''}
  </section>`;
}

/* Recompute a phase summary against a filtered by_job dict. Same math as
   compute_phase_durations on the Python side. */
function recomputePhaseSummary(by_job) {
  const days_vals = Object.values(by_job).map(j => j.days).filter(d => d).sort((a,b) => a-b);
  const span_vals = Object.values(by_job).map(j => j.calendar_span_days).filter(d => d).sort((a,b) => a-b);
  const subsSet = new Set();
  let active_count = 0;
  let total_active = 0;
  for (const j of Object.values(by_job)) {
    (j.subs || []).forEach(s => subsSet.add(s));
    if (j.status === 'ongoing') active_count++;
    total_active += j.days || 0;
  }
  const pct = (arr, p) => {
    if (!arr.length) return 0;
    if (arr.length === 1) return arr[0];
    const k = (arr.length - 1) * p;
    const f = Math.floor(k);
    const c = Math.min(f + 1, arr.length - 1);
    if (f === c) return arr[f];
    return arr[f] + (arr[c] - arr[f]) * (k - f);
  };
  return {
    median_days: Math.round(pct(days_vals, 0.5) * 10) / 10,
    p25_days:    Math.round(pct(days_vals, 0.25) * 10) / 10,
    p75_days:    Math.round(pct(days_vals, 0.75) * 10) / 10,
    min_days:    days_vals[0] || 0,
    max_days:    days_vals[days_vals.length - 1] || 0,
    median_span: Math.round(pct(span_vals, 0.5) * 10) / 10,
    job_count:   Object.keys(by_job).length,
    sub_count:   subsSet.size,
    active_count,
    total_active_days: total_active,
  };
}

function renderPhaseDurationRow(tag, e) {
  const s = e.summary;
  const insufficient = s.job_count < 3;
  const isExpanded = PHASE_DUR_EXPANDED.has(tag);
  const chev = isExpanded ? '▾' : '▸';
  const insufficientCell = `<span class="muted">— ${hint('(insufficient samples)')}</span>`;
  const medCell = insufficient ? insufficientCell : `${s.median_days}d`;
  const p25_75Cell = insufficient ? '' : `${s.p25_days}-${s.p75_days}d`;
  const rangeCell = `${s.min_days}-${s.max_days}d`;
  const spanCell = insufficient ? '' : `${s.median_span}d`;
  const activeCls = s.active_count > 0 ? ' pd-active-cell' : '';
  const safeTagId = `pd-${tag.replace(/[^a-z0-9]+/gi, '-').toLowerCase()}`;

  // Per-job detail rows (always rendered, hidden until row is expanded —
  // keeps the print layout fully expanded too).
  const byJobEntries = Object.entries(e.by_job).sort((a, b) => (b[1].days || 0) - (a[1].days || 0));
  const jobRows = byJobEntries.map(([job, jd]) => {
    let badge = '<span class="job-badge nomark"></span>';
    if (!insufficient && jd.days) {
      if (jd.days < s.p25_days) {
        badge = `<span class="job-badge fast">${hint('⚡ below median')}</span>`;
      } else if (jd.days > s.p75_days) {
        badge = `<span class="job-badge slow">${hint('⚠ above median')}</span>`;
      } else {
        badge = `<span class="job-badge norm">${hint('✓ within range')}</span>`;
      }
    }
    const subStr = (jd.subs && jd.subs.length) ? jd.subs.slice(0, 2).map(escapeHtml).join(' · ') : '<span class="muted">—</span>';
    const statusStr = jd.status === 'ongoing' ? '<span class="job-status-ongoing">ongoing</span>' : (jd.ended ? `complete ${escapeHtml(jd.ended)}` : 'complete');
    return `<tr class="pd-job-row">
      <td class="pd-job-name" title="Job that has logged this phase.">${escapeHtml(job)}</td>
      <td class="right pd-job-days">${jd.days}d</td>
      <td>${badge}</td>
      <td class="right pd-job-span" title="Calendar span: first log → last log for this phase at this job.">${jd.calendar_span_days}d span</td>
      <td class="pd-job-subs">${subStr}</td>
      <td class="pd-job-status">${statusStr}</td>
    </tr>`;
  }).join('');
  const detailRow = `<tr class="pd-detail-row" data-pd-tag="${escapeHtml(tag)}" id="${safeTagId}-detail" ${isExpanded ? '' : 'hidden'}>
    <td colspan="8">
      <table class="pd-detail-table"><tbody>${jobRows}</tbody></table>
    </td>
  </tr>`;

  return `<tr class="pd-row" data-pd-tag="${escapeHtml(tag)}" id="${safeTagId}">
    <td class="pd-col-phase">
      <button type="button" class="pd-toggle" aria-expanded="${isExpanded}" aria-controls="${safeTagId}-detail" title="Click to see per-job breakdown.">${chev}</button>
      <span class="pd-phase-name">${escapeHtml(tag)}</span>
    </td>
    <td class="pd-col-cat"><span class="cat-tag">${escapeHtml(e.category)}</span></td>
    <td class="right pd-num">${medCell}</td>
    <td class="right pd-num">${p25_75Cell}</td>
    <td class="right pd-num">${rangeCell}</td>
    <td class="right pd-num">${spanCell}</td>
    <td class="right pd-num">${s.job_count}</td>
    <td class="right pd-num${activeCls}">${s.active_count}</td>
  </tr>${detailRow}`;
}

function renderJobAnalyticsCard(j) {
  const col = jobColor(j.short_name);
  const lt = j.lifetime || {};
  const phaseShort = shortPhase(j.phase || '');

  // Last log freshness
  const age = lt.last_log_age_days;
  let ageStr = age != null ? (age === 0 ? 'today' : age === 1 ? 'yesterday' : `${age}d ago`) : '—';
  const ageWarn = (age != null && age >= 3) ? ' ⚠' : '';

  // Top crews — single column, top 10
  const crewsHtml = (j.top_crews || []).slice(0, 10).map(c =>
    `<li><span class="ja-crew-name">${escapeHtml(c.name)}</span><span class="ja-crew-days">${c.days}d</span></li>`
  ).join('') || '<li class="muted">—</li>';

  // Latest events — limit to 3
  const latest = (events, label) => {
    if (!events || !events.length) return '';
    return `<div class="ja-event"><span class="ja-event-label">${label}</span> <span class="ja-event-date">${formatDate(events[0].date)}</span> — ${escapeHtml((events[0].details || events[0].text || '').slice(0, 130))}${(events[0].details || events[0].text || '').length > 130 ? '…' : ''}</div>`;
  };
  const recentEvents = [
    latest(j.delivery_events, 'Delivery'),
    latest(j.inspection_events, 'Inspection'),
    latest(j.notable_events, 'Notable'),
  ].filter(Boolean).join('');

  return `
    <article class="ja-card" style="--job-color:${col}">
      <header class="ja-head">
        <div class="ja-title">
          ${statusBadge(j.status)}
          <h2>${escapeHtml(j.short_name)}</h2>
          <span class="ja-addr">${escapeHtml(j.address || '')}</span>
        </div>
        <div class="ja-meta">
          <span class="ja-pm">PM · ${escapeHtml(j.pm || '—')}</span>
          ${phaseShort ? `<span class="ja-phase" title="${escapeHtml(j.phase)}">${escapeHtml(phaseShort)}</span>` : ''}
          ${j.target_co && j.target_co !== '—' ? `<span class="ja-co">CO ${escapeHtml(j.target_co)}</span>` : ''}
        </div>
      </header>

      <div class="ja-stats">
        <div class="ja-stat"><div class="lbl">${hint('Total log-days')}</div><div class="val">${lt.total_days ?? '—'}</div></div>
        <div class="ja-stat"><div class="lbl">${hint('Person-days')}</div><div class="val">${(lt.total_person_days ?? 0).toLocaleString()}</div></div>
        <div class="ja-stat"><div class="lbl">${hint('Avg crew')}</div><div class="val">${lt.avg_workforce ?? '—'}<span class="sub"> · pk ${lt.peak_workforce ?? '—'}</span></div></div>
        <div class="ja-stat"><div class="lbl">${hint('Unique subs')}</div><div class="val">${lt.unique_crews ?? '—'}</div></div>
        <div class="ja-stat"><div class="lbl">${hint('Delivery days')}</div><div class="val">${lt.delivery_days ?? 0}</div></div>
        <div class="ja-stat"><div class="lbl">${hint('Inspection days')}</div><div class="val">${lt.inspection_days ?? 0}</div></div>
        <div class="ja-stat ${ageWarn ? 'warn' : ''}"><div class="lbl">${hint('Last log')}</div><div class="val">${ageStr}${ageWarn}</div></div>
      </div>

      ${renderWorkforceHistogram(j.monthly || [], col)}

      <div class="ja-grid">
        <section class="ja-section">
          <h3>Subs by days on site</h3>
          <ol class="ja-rank">${crewsHtml}</ol>
        </section>
        <section class="ja-section ja-section-wide">
          <h3>Phase durations · activity timeline</h3>
          ${renderPhaseTable(j.phase_durations || [])}
        </section>
      </div>

      ${recentEvents ? `<section class="ja-events"><h3>Latest events</h3>${recentEvents}</section>` : ''}
    </article>
  `;
}

/* Big monthly workforce histogram — replaces the trio of sparklines.
   Bars = monthly person-days, with axis ticks + value labels. */
function renderWorkforceHistogram(monthly, jobColor) {
  if (!monthly || !monthly.length) return '';
  const w = 720, h = 130, padL = 30, padR = 10, padT = 14, padB = 22;
  const innerW = w - padL - padR;
  const innerH = h - padT - padB;
  const max = Math.max(1, ...monthly.map(m => m.person_days || 0));
  const barGap = 2;
  const barW = innerW / monthly.length - barGap;

  // Y-axis ticks at 0, 50%, 100%
  const yTicks = [0, Math.round(max / 2), max].map(v => {
    const y = padT + innerH - (v / max) * innerH;
    return `<line x1="${padL}" x2="${w - padR}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-width="0.5"/>
            <text x="${padL - 4}" y="${y + 3}" text-anchor="end" font-size="9" fill="var(--ink-3)" font-family="JetBrains Mono, ui-monospace, monospace">${v}</text>`;
  }).join('');

  // Bars + value labels for non-zero months
  const bars = monthly.map((m, i) => {
    const v = m.person_days || 0;
    const x = padL + i * (barW + barGap);
    const barH = (v / max) * innerH;
    const y = padT + innerH - barH;
    const label = (i === 0 || i === monthly.length - 1 || i % 2 === 0) ? m.label : '';
    const valLabel = v > 0 && barH > 14
      ? `<text x="${x + barW / 2}" y="${y - 3}" text-anchor="middle" font-size="9" fill="var(--ink-2)" font-family="JetBrains Mono, ui-monospace, monospace">${v}</text>`
      : '';
    const axisLabel = label
      ? `<text x="${x + barW / 2}" y="${h - 6}" text-anchor="middle" font-size="9" fill="var(--ink-3)" font-family="JetBrains Mono, ui-monospace, monospace">${escapeHtml(label)}</text>`
      : '';
    return `<rect x="${x}" y="${y}" width="${barW}" height="${barH}" fill="${jobColor}" opacity="${v ? 0.9 : 0.15}"><title>${escapeHtml(m.label)}: ${v} person-days · ${m.logs} logged days</title></rect>${valLabel}${axisLabel}`;
  }).join('');

  return `<figure class="ja-histogram">
    <figcaption>Workforce · ${hint('person-days')} per month (last ${monthly.length} mo)</figcaption>
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Monthly workforce histogram">
      ${yTicks}
      ${bars}
    </svg>
  </figure>`;
}

/* Phase/activity table — chronological list of every parent_group_activity
   with substantial-burst duration, status, and active-day count. */
function renderPhaseTable(phases) {
  if (!phases || !phases.length) {
    return '<p class="muted"><em>No structured activity tags logged yet.</em></p>';
  }
  const rows = phases.map(p => {
    const startedLabel = formatMonthYear(p.first);
    const endedLabel = p.ongoing ? '—' : formatMonthYear(p.last);
    let durationCell;
    let statusCell;
    const dayWord = (n) => n === 1 ? 'day' : 'days';
    if (p.pattern === 'substantial') {
      const activeBit = p.active_days < p.duration_days
        ? `<span class="pt-active">${p.active_days} active</span>` : '';
      durationCell = `<span class="pt-days">${p.duration_days} ${dayWord(p.duration_days)}</span>${activeBit}`;
      statusCell = p.ongoing
        ? `<span class="pt-status ongoing">${hint('Ongoing')}</span>`
        : `<span class="pt-status complete">${hint('Complete')}</span>`;
    } else if (p.pattern === 'multi-burst') {
      // Multiple distinct work bursts that cumulatively are real work.
      // Show span (with gaps) plus active-day count.
      durationCell = `<span class="pt-days">${p.duration_days} ${dayWord(p.duration_days)}</span><span class="pt-active">${p.active_days} active</span>`;
      statusCell = p.ongoing
        ? `<span class="pt-status multi-burst">${hint('Multi-burst')} · ${hint('active')}</span>`
        : `<span class="pt-status multi-burst">${hint('Multi-burst')}</span>`;
    } else {
      durationCell = `<span class="pt-active">${p.active_days} active ${dayWord(p.active_days)}</span>`;
      statusCell = p.ongoing
        ? `<span class="pt-status intermittent ongoing">${hint('Intermittent')} · ${hint('active')}</span>`
        : `<span class="pt-status intermittent">${hint('Intermittent')}</span>`;
    }
    const burstNote = p.num_substantial_bursts > 1
      ? `<span class="pt-bursts" title="${p.num_substantial_bursts} substantial work periods">+${p.num_substantial_bursts - 1}</span>`
      : '';
    // Sub-attribution row — top 3 subs on this phase (by day count), middot-
    // separated. Renders as a borderless row visually subordinate to the main
    // phase row above it.
    const subs = (p.top_subs || []).filter(s => s && s.name);
    let subsRow = '';
    if (subs.length) {
      const dayWordSubs = (n) => n === 1 ? 'day' : 'days';
      const subText = subs
        .map(s => `${escapeHtml(s.name)} <span class="pt-subs-days">${s.days} ${dayWordSubs(s.days)}</span>`)
        .join(' · ');
      subsRow = `<tr class="phase-subs-row">
        <td colspan="5"><span class="pt-subs">${subText}</span></td>
      </tr>`;
    }
    return `<tr class="phase-main-row">
      <td class="pt-name">${escapeHtml(p.name)}</td>
      <td class="pt-when">${startedLabel}</td>
      <td class="pt-when">${endedLabel}</td>
      <td class="pt-dur">${durationCell}${burstNote}</td>
      <td>${statusCell}</td>
    </tr>${subsRow}`;
  }).join('');
  return `<table class="phase-table">
    <thead>
      <tr>
        <th>Activity</th><th>Started</th><th>Ended</th><th>Duration</th><th>Status</th>
      </tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
  <p class="pt-note">Duration = longest substantial work burst (≥3d, ≥35% density). Activities with sparse one-off visits show as "Intermittent" with active-day count instead of inflated span.</p>`;
}

function formatMonthYear(iso) {
  if (!iso) return '—';
  const d = new Date(iso + 'T00:00:00');
  if (isNaN(+d)) return iso;
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
}

/* ============================================================
   Subs analytics tab — own sheet, lifetime + recent performance
   per subcontractor. Sortable table + overlap-concerns callout.
   ============================================================ */
let SUBS_SORT = { key: 'reliability_pct', dir: 'desc' };  // Default: best-to-worst within each trade group
let SUBS_FILTER = '';
let SUBS_CATEGORY_FILTER = '';
let SUBS_HIDE_STALE = true;  // Hide subs not seen in >365 days by default
let SUBS_ONLY_COMPARISON = true;  // Phase 6 — default ON: hide subs with insufficient comparison samples
let SUBS_VIEW_MODE = 'table';  // 'table' (default) or 'phase-seq' (Phase 17)
let SUBS_ALL_EXPANDED = false;  // Phase 19 — global expand-all toggle for the Subs table view

// Phase 17 — build-sequence section map. Each section lists which sub
// categories belong, in left-to-right build order. A sub appears in the
// section that owns its primary category. Internal Crew (Ross Built)
// also gets pinned at the bottom under Closeout per the prompt's spec.
const PHASE_SEQ_SECTIONS = [
  { key: 'pre',     name: 'Pre-Construction & Site',  cats: ['Site/Excavation', 'Engineering/Insp'] },
  { key: 'found',   name: 'Foundation & Concrete',    cats: ['Concrete', 'Pavers/Hardscape'] },
  { key: 'env',     name: 'Framing & Envelope',       cats: ['Framing', 'Carpentry/Stairs', 'Roofing', 'Siding', 'Stucco/Plaster', 'Insulation', 'Windows/Doors', 'Waterproofing'] },
  { key: 'mep',     name: 'Rough-In (MEP)',           cats: ['Plumbing', 'Electrical', 'HVAC', 'Audio/Video'] },
  { key: 'drywall', name: 'Drywall & Insulation',     cats: ['Drywall'] },
  { key: 'finint',  name: 'Finishes (Interior)',      cats: ['Tile/Floor', 'Trim/Finish', 'Paint', 'Cabinetry', 'Stone/Counters', 'Appliances', 'Interior Design'] },
  { key: 'finext',  name: 'Finishes (Exterior)',      cats: ['Pool/Spa', 'Landscape', 'Fence/Gate', 'Metal/Welding'] },
  { key: 'close',   name: 'Closeout',                 cats: ['Internal Crew', 'Cleaning', 'Materials/Supplier', 'Solar/Energy', 'Elevator', 'Other Trade'] },
];

function renderSubsView(filterPM) {
  let all = (SUBS_DATA && SUBS_DATA.subs) || [];
  let portfolio = (SUBS_DATA && SUBS_DATA.portfolio) || {};
  let overlap = (SUBS_DATA && SUBS_DATA.overlap_concerns) || [];

  if (filterPM) {
    // Restrict to subs that have ever touched any of this PM's jobs.
    const pmJobs = new Set();
    for (const [k, v] of Object.entries(JOBS_DATA || {})) {
      if (k !== '__portfolio__' && v && v.pm === filterPM) pmJobs.add(v.short_name);
    }
    all = all.filter(s => (s.lifetime_jobs || []).some(j => pmJobs.has(j)));
    overlap = overlap.filter(s => (s.active7_jobs || []).some(j => pmJobs.has(j)));
    portfolio = {
      total_subs: all.length,
      active_30d: all.filter(s => s.recent_days > 0).length,
      total_absences_30d: all.reduce((sum, s) => sum + (s.recent_absences || 0), 0),
      overlap_count: overlap.length,
    };
  }

  if (!all.length) {
    return `<div class="jobs-view-empty">
      <h2>Subs</h2>
      <p class="muted"><em>No daily-log data yet. Run a refresh to scrape Buildertrend.</em></p>
    </div>`;
  }

  const rollup = `<div class="jobs-portfolio-rollup">
    <span class="rollup-stat"><b>${portfolio.total_subs ?? all.length}</b> total subs</span>
    <span class="rollup-stat"><b>${portfolio.active_30d ?? 0}</b> active last 30d</span>
    <span class="rollup-stat ${portfolio.total_absences_30d ? 'warn' : ''}"><b>${portfolio.total_absences_30d ?? 0}</b> absences last 30d</span>
    <span class="rollup-stat ${portfolio.overlap_count ? 'warn' : ''}"><b>${portfolio.overlap_count ?? 0}</b> on 3+ jobs this week</span>
  </div>`;

  const overlapPanel = overlap.length ? renderOverlapPanel(overlap) : '';
  const categoriesPanel = renderCategoriesPanel(all, filterPM);
  const mainPanel = SUBS_VIEW_MODE === 'phase-seq'
    ? renderSubsPhaseSeqView(all)
    : renderSubsTable(all);
  // Phase 17 — view-mode toggle and Phase Glossary button. Lives at the
  // top of the Subs tab so both layouts share the same header chrome.
  const viewToggle = `<div class="subs-view-controls">
    <div class="subs-view-toggle" role="tablist" aria-label="Subs view mode">
      <button type="button" class="${SUBS_VIEW_MODE === 'table' ? 'active' : ''}" data-view-mode="table" role="tab" aria-selected="${SUBS_VIEW_MODE === 'table'}">Table</button>
      <button type="button" class="${SUBS_VIEW_MODE === 'phase-seq' ? 'active' : ''}" data-view-mode="phase-seq" role="tab" aria-selected="${SUBS_VIEW_MODE === 'phase-seq'}">Phase Sequence</button>
    </div>
    <button type="button" class="subs-glossary-btn" onclick="openGlossary()" title="Open the BT phase glossary — every parent_group_activity tag explained.">📖 Phase Glossary</button>
  </div>`;

  return `
    <div class="jobs-view subs-view">
      <header class="jobs-view-head">
        <div>
          <div class="eyebrow">Subcontractor performance</div>
          <h1>Subs</h1>
          <p class="muted">Lifetime + recent (last 30 days) activity across every job. Updated each refresh.</p>
        </div>
      </header>
      ${rollup}
      ${viewToggle}
      ${overlapPanel}
      ${categoriesPanel}
      ${mainPanel}
    </div>`;
}

/* Phase 17 — Phase Sequence view. Groups subs by build-order section
   (Foundation → Closeout) instead of the alphabetical/recent table.
   Each section is a card grid sorted by recent activity. A sub appears
   once, in the section that owns its primary category. */
function renderSubsPhaseSeqView(rows) {
  const filtered = rows.filter(s => {
    if (SUBS_HIDE_STALE && s.last_seen_age_days != null && s.last_seen_age_days > 365) return false;
    if (SUBS_FILTER && !s.name.toLowerCase().includes(SUBS_FILTER.toLowerCase())) return false;
    return true;
  });
  // Phase 18 — multi-category subs appear in EACH applicable section.
  // For each sub, walk their categories list; when no category matches a
  // section, fall through to Closeout (Other-Trade catch-all). When a
  // sub has multiple categories spanning sections (e.g. SmartShield in
  // Audio/Video + Electrical), they show up once per section.
  const buckets = new Map(PHASE_SEQ_SECTIONS.map(s => [s.key, []]));
  for (const s of filtered) {
    const cats = Array.isArray(s.categories) && s.categories.length > 0
      ? s.categories
      : [s.category];
    const placedSections = new Set();
    for (const c of cats) {
      for (const sec of PHASE_SEQ_SECTIONS) {
        if (sec.cats.includes(c)) {
          if (!placedSections.has(sec.key)) {
            buckets.get(sec.key).push(s);
            placedSections.add(sec.key);
          }
          break;
        }
      }
    }
    if (placedSections.size === 0) buckets.get('close').push(s);
  }
  const sortByRecent = (a, b) => {
    const ar = a.last_seen_age_days == null ? 99999 : a.last_seen_age_days;
    const br = b.last_seen_age_days == null ? 99999 : b.last_seen_age_days;
    return ar - br;
  };
  const sections = PHASE_SEQ_SECTIONS.map(sec => {
    const subs = (buckets.get(sec.key) || []).slice().sort(sortByRecent);
    // Phase 18 — denser tabular row layout (one tr per sub) replaces the
    // prior card grid. Click to expand re-uses the Phase 17 disclosure.
    const rows = subs.map(s => {
      const lastStr = s.last_seen_age_days == null ? '—'
        : s.last_seen_age_days === 0 ? 'today'
        : s.last_seen_age_days === 1 ? 'yesterday'
        : `${s.last_seen_age_days}d ago`;
      const recent = (s.recent_days > 0) ? `${s.recent_days}d` : '<span class="muted">—</span>';
      const cats = Array.isArray(s.categories) && s.categories.length > 0
        ? s.categories : [s.category || '—'];
      const catCell = cats.map(c => `<span class="cat-tag">${escapeHtml(c)}</span>`).join('');
      return `<tr class="phase-seq-row" data-sub-key="${escapeHtml(s.key || s.name)}">
        <td class="pseq-name">${escapeHtml(s.name)}</td>
        <td class="pseq-cat">${catCell}</td>
        <td class="right pseq-num" title="Distinct days in last 30 calendar days.">${recent}</td>
        <td class="right pseq-num" title="Distinct calendar dates this sub appeared in BT daily logs.">${s.lifetime_days}d</td>
        <td class="right pseq-num" title="Distinct jobs this sub has touched.">${s.lifetime_jobs_count}</td>
        <td class="right pseq-recent">${escapeHtml(lastStr)}</td>
      </tr>`;
    }).join('');
    const tableHtml = subs.length
      ? `<table class="phase-seq-table">
          <thead><tr>
            <th>Sub</th>
            <th>Category</th>
            <th class="right">Recent</th>
            <th class="right">Lifetime</th>
            <th class="right">Jobs</th>
            <th class="right">Last seen</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>`
      : '<p class="muted" style="font-size:11px; padding-left:2px">— no subs in this section —</p>';
    return `<section class="phase-seq-section" data-section="${sec.key}">
      <header class="phase-seq-head">
        <h4>${escapeHtml(sec.name)}</h4>
        <span class="phase-seq-count">${subs.length} ${subs.length === 1 ? 'sub' : 'subs'}</span>
      </header>
      ${tableHtml}
    </section>`;
  }).join('');

  return `<div class="phase-seq-wrap">
    <div class="subs-table-head">
      <input type="search" class="subs-filter" placeholder="Filter subs by name…" value="${escapeHtml(SUBS_FILTER)}">
      <span class="muted subs-table-count">${filtered.length} of ${rows.length} subs across ${PHASE_SEQ_SECTIONS.length} build-stage sections</span>
    </div>
    ${sections}
  </div>`;
}

function renderCategoriesPanel(filteredSubs, filterPM) {
  // Build categories from the current sub list (could be filtered by PM)
  const cats = {};
  for (const s of filteredSubs) {
    const cat = s.category || 'Other Trade';
    const c = cats[cat] = cats[cat] || {
      name: cat, subs: [], total_days: 0, total_recent: 0, total_absences: 0,
      jobs_touched: new Set(),
    };
    c.subs.push(s);
    c.total_days += s.lifetime_days;
    c.total_recent += s.recent_days;
    c.total_absences += s.lifetime_absences;
    (s.lifetime_jobs || []).forEach(j => c.jobs_touched.add(j));
  }
  const cats_arr = Object.values(cats).map(c => {
    c.sub_count = c.subs.length;
    c.avg_days_per_sub = c.sub_count > 0 ? +(c.total_days / c.sub_count).toFixed(1) : 0;
    c.top_subs = c.subs.slice().sort((a, b) => b.lifetime_days - a.lifetime_days).slice(0, 3);
    c.jobs_count = c.jobs_touched.size;
    return c;
  }).sort((a, b) => b.total_days - a.total_days);

  if (cats_arr.length === 0) return '';

  const cards = cats_arr.map(c => {
    const isFiltered = SUBS_CATEGORY_FILTER === c.name;
    const tops = c.top_subs.map(s =>
      `<li><span class="cat-sub-name">${escapeHtml(s.name)}</span><span class="cat-sub-days">${s.lifetime_days}d</span></li>`
    ).join('');
    return `<article class="cat-card ${isFiltered ? 'active' : ''}" data-cat="${escapeHtml(c.name)}" tabindex="0" role="button" aria-pressed="${isFiltered}">
      <header class="cat-card-head">
        <h4>${escapeHtml(c.name)}</h4>
        <span class="cat-count">${c.sub_count} ${c.sub_count === 1 ? 'sub' : 'subs'}</span>
      </header>
      <div class="cat-stats">
        <span><b>${c.total_days.toLocaleString()}</b> total days</span>
        <span><b>${c.avg_days_per_sub}</b> avg per sub</span>
        <span><b>${c.jobs_count}</b> jobs touched</span>
        ${c.total_recent ? `<span><b>${c.total_recent}</b> recent (30d)</span>` : ''}
      </div>
      <ol class="cat-top">${tops}</ol>
    </article>`;
  }).join('');

  const clearBtn = SUBS_CATEGORY_FILTER
    ? `<button class="cat-clear" data-cat="">Clear filter (${escapeHtml(SUBS_CATEGORY_FILTER)})</button>`
    : '';

  return `<section class="cats-panel">
    <div class="cats-head">
      <h3>Trade categories — click to filter table below</h3>
      ${clearBtn}
    </div>
    <div class="cats-grid">${cards}</div>
  </section>`;
}

function renderOverlapPanel(overlap) {
  const rows = overlap.slice(0, 12).map(s => {
    const jobs = (s.active7_jobs || []).map(j => `<span class="ov-jobtag" style="background:${jobColor(j)}">${escapeHtml(j)}</span>`).join('');
    return `<div class="ov-row">
      <span class="ov-name">${escapeHtml(s.name)}</span>
      <span class="ov-count">${s.active7_count} jobs</span>
      <span class="ov-jobs">${jobs}</span>
    </div>`;
  }).join('');
  return `<section class="ja-section overlap-panel">
    <h3>Overlap concerns · subs on 3+ jobs in last 7 days</h3>
    <p class="pt-note">A sub spread across many active jobs simultaneously can signal overcommitment or scheduling conflicts. Worth a quick check.</p>
    <div class="ov-list">${rows}</div>
  </section>`;
}

// Phase 6 — comparison bar component. Renders a 120×16 px horizontal bar:
//   - Light slate strip   = full trade range (min → max)
//   - Darker slate band    = trade P25 → P75 (typical)
//   - Filled tick          = this sub's value, colored green/amber/gray
//   - Numerical label      = sub's value rendered to the right of the SVG
//
// `state` is "good" (within P25–P75), "off" (above P75 or below P25), or
// "gray" (insufficient samples). When state === "gray", caller should display
// "(insufficient samples)" pill instead of a numeric label.
//
// All inputs are numbers (no null guards) — caller passes 0/0/0/0/0 + label
// "(insufficient samples)" when data is missing.
function comparisonBar(value, p25, p75, rangeMin, rangeMax, state, label, tooltip) {
  const w = 120, h = 16;
  // When the trade range collapses (min === max), force a thin spread so the
  // bar still draws something visible.
  let lo = rangeMin, hi = rangeMax;
  if (hi <= lo) hi = lo + 1;
  const xFor = v => Math.max(0, Math.min(w, ((v - lo) / (hi - lo)) * w));
  const stripY = h * 0.45;
  const stripH = h * 0.20;
  const xP25 = xFor(p25), xP75 = xFor(p75);
  const xVal = xFor(value);
  const tickColor = state === 'good'
    ? 'var(--success)'
    : state === 'off'
      ? 'var(--warn)'
      : 'rgba(59, 88, 100, 0.3)';
  const stripCls = state === 'gray' ? 'cmp-strip cmp-strip-empty' : 'cmp-strip';
  const bandCls  = state === 'gray' ? 'cmp-band cmp-band-empty'  : 'cmp-band';
  const valLabel = state === 'gray'
    ? '<span class="cmp-label cmp-label-empty">(insufficient samples)</span>'
    : `<span class="cmp-label">${escapeHtml(label || '')}</span>`;
  const tickEl = state === 'gray'
    ? ''
    : `<rect class="cmp-tick" x="${(xVal - 1.5).toFixed(1)}" y="2" width="3" height="${h - 4}" fill="${tickColor}"/>`;
  const tipAttr = tooltip ? ` data-hint="${escapeHtml(tooltip)}"` : '';
  const tipCls = tooltip ? ' tip' : '';
  return `<span class="cmp-bar-wrap${tipCls}"${tipAttr}${tooltip ? ' tabindex="0"' : ''}>
    <svg class="cmp-bar" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">
      <rect class="${stripCls}" x="0" y="${stripY}" width="${w}" height="${stripH}"/>
      ${state === 'gray' ? '' : `<rect class="${bandCls}" x="${xP25.toFixed(1)}" y="${stripY}" width="${(xP75 - xP25).toFixed(1)}" height="${stripH}"/>`}
      ${tickEl}
    </svg>
    ${valLabel}
  </span>`;
}

// Phase 6 — pure-CSS popover that surfaces the dropped volume columns
// (Recent 30d days/jobs, Lifetime days/jobs, Absences). Hidden in print —
// the print path uses .vol-disclosure-print instead (italic line under the
// sub name).
function volumeDisclosureHtml(s) {
  const recentJobs   = s.recent_jobs_count || 0;
  const recent       = (s.recent_days || 0);
  const lifetimeJobs = s.lifetime_jobs_count || 0;
  const lifetime     = (s.lifetime_days || 0);
  const absLife      = s.lifetime_absences || 0;
  const absRecent    = s.recent_absences || 0;
  const dl = `
    <dl class="vol-popover">
      <dt>Recent (30d)</dt><dd>${recent} day(s), ${recentJobs} job(s)</dd>
      <dt>Lifetime</dt>    <dd>${lifetime} day(s), ${lifetimeJobs} job(s)</dd>
      <dt>Absences</dt>    <dd>${absLife} (${absRecent} in last 30d)</dd>
    </dl>`;
  return `<span class="vol-disclosure">
    <button type="button" class="vol-disclosure-icon" aria-label="Volume details">ⓘ</button>
    ${dl}
  </span>`;
}

// Print-only single-line summary that takes the popover's place when printed.
function volumeDisclosurePrint(s) {
  const recent       = (s.recent_days || 0);
  const lifetime     = (s.lifetime_days || 0);
  const lifetimeJobs = s.lifetime_jobs_count || 0;
  const absLife      = s.lifetime_absences || 0;
  return `<span class="vol-disclosure-print">${recent}d recent · ${lifetime}d lifetime / ${lifetimeJobs} jobs · ${absLife} absences</span>`;
}

function renderSubsTable(rows) {
  const sortIndicator = (key) =>
    SUBS_SORT.key === key ? (SUBS_SORT.dir === 'asc' ? ' ▲' : ' ▼') : '';
  // Phase 6 — comparison-first columns. Volume metrics (Recent days/jobs,
  // Lifetime days/jobs, Absences) moved off the row; reachable via the
  // ⓘ popover at row end (and as an italic line below the sub name in print).
  const cols = [
    { key: 'name',                       label: 'Sub',                  sortable: true,  align: 'left'  },
    { key: 'category',                   label: 'Category',             sortable: true,  align: 'left'  },
    { key: 'sub_median_days_in_trade',   label: 'Duration vs peers',    sortable: true,  align: 'left'  },
    { key: 'reliability_pct',            label: 'Reliability vs peers', sortable: true,  align: 'left'  },
    { key: 'recent_days',                label: 'Recent activity',      sortable: true,  align: 'left'  },
    { key: 'last_seen_age_days',         label: 'Last seen',            sortable: true,  align: 'right' },
    { key: '__info__',                   label: '',                     sortable: false, align: 'right' },
  ];
  const head = cols.map(c => {
    // Phase 5: prefer the centralized TOOLTIPS dict via hint() — falls back
    // to the column's local `tip` string if the label isn't in TOOLTIPS yet.
    const wrapped = hint(c.label);
    const wasWrapped = wrapped !== escapeHtml(c.label);
    const fallbackTitle = (!wasWrapped && c.tip) ? ` title="${escapeHtml(c.tip)}"` : '';
    const labelHtml = wasWrapped ? wrapped : escapeHtml(c.label);
    return `<th class="${c.align === 'right' ? 'right' : ''}"${fallbackTitle}${c.sortable ? ` data-sort="${c.key}" role="button" tabindex="0"` : ''}>${labelHtml}${c.sortable ? sortIndicator(c.key) : ''}</th>`;
  }).join('');

  // Apply filter + sort
  const filterLc = (SUBS_FILTER || '').toLowerCase();
  let filtered = rows;
  // Stale subs (last seen > 365 days ago) are hidden by default — they pollute
  // the active-roster view. Toggle pill in the table header restores them.
  const staleCount = rows.filter(r => r.last_seen_age_days != null && r.last_seen_age_days > 365).length;
  if (SUBS_HIDE_STALE) {
    filtered = filtered.filter(r => !(r.last_seen_age_days != null && r.last_seen_age_days > 365));
  }
  if (filterLc) {
    filtered = filtered.filter(r => r.name.toLowerCase().includes(filterLc));
  }
  if (SUBS_CATEGORY_FILTER) {
    filtered = filtered.filter(r => (r.category || '') === SUBS_CATEGORY_FILTER);
  }
  // Phase 6 — "Show only subs with comparison data" filter chip. Hides subs
  // where BOTH duration and reliability come back insufficient. A sub with
  // adequate samples in either column still shows.
  const insufficientCount = rows.filter(r => r.dur_insufficient && r.rel_insufficient).length;
  if (SUBS_ONLY_COMPARISON) {
    filtered = filtered.filter(r => !(r.dur_insufficient && r.rel_insufficient));
  }

  // Sort comparator — used to sort within each trade subsection
  const sortRows = (arr) => arr.slice().sort((a, b) => {
    const k = SUBS_SORT.key;
    let av = a[k], bv = b[k];
    if (k === 'last_seen_age_days') {
      av = av == null ? Number.POSITIVE_INFINITY : av;
      bv = bv == null ? Number.POSITIVE_INFINITY : bv;
    }
    if (k === 'reliability_pct') {
      av = av == null ? -1 : av;
      bv = bv == null ? -1 : bv;
    }
    if (k === 'sub_median_days_in_trade') {
      av = av == null ? Number.POSITIVE_INFINITY : av;
      bv = bv == null ? Number.POSITIVE_INFINITY : bv;
    }
    if (typeof av === 'string') {
      const cmp = av.localeCompare(bv);
      return SUBS_SORT.dir === 'asc' ? cmp : -cmp;
    }
    return SUBS_SORT.dir === 'asc' ? av - bv : bv - av;
  });

  const colCount = cols.length;

  // Phase 19 — group filtered rows by build-stage section, then by trade
  // category within section. A sub with multiple categories appears once
  // under each applicable trade subsection so it's directly comparable to
  // peers in every trade it actually does. Order: PHASE_SEQ_SECTIONS,
  // then sec.cats[] order within each section.
  const subsByCategory = new Map();  // category → [sub, …]
  for (const s of filtered) {
    const cats = Array.isArray(s.categories) && s.categories.length > 0
      ? s.categories
      : [s.category || 'Other Trade'];
    for (const c of cats) {
      if (!subsByCategory.has(c)) subsByCategory.set(c, []);
      subsByCategory.get(c).push(s);
    }
  }

  // Render a single sub row + its (hidden by default) phase breakdown row.
  // Pulled out so we can reuse it for every trade subsection.
  const renderSubRow = (s) => {
    const lastAge = s.last_seen_age_days;
    const lastStr = lastAge == null ? '—'
      : lastAge === 0 ? 'today'
      : lastAge === 1 ? 'yesterday'
      : `${lastAge}d ago`;
    const lastWarn = (lastAge != null && lastAge >= 14) ? ' warn' : '';

    // Phase 6 — Duration vs Peers cell
    const dur = s.trade_dur || {};
    let durationCell;
    if (s.dur_insufficient) {
      durationCell = comparisonBar(0, 0, 0, 0, 1, 'gray', '', `Not enough data yet — sub has ${s.sub_instances_in_trade || 0} instance(s); trade has ${dur.instances || 0} across ${dur.subs || 0} sub(s).`);
    } else {
      const v = s.sub_median_days_in_trade;
      const inBand = v >= dur.p25 && v <= dur.p75;
      const state = inBand ? 'good' : 'off';
      const tooltip = `${s.name}'s median is ${v}d. Trade range: ${dur.min}–${dur.max}d, typical ${dur.p25}–${dur.p75}d. Based on ${dur.instances} completed phase instances across ${dur.subs} sub(s).`;
      durationCell = comparisonBar(v, dur.p25, dur.p75, dur.min, dur.max, state, `${v}d`, tooltip);
    }

    // Phase 6 — Reliability vs Peers cell
    const rel = s.trade_rel || {};
    const reliability = s.reliability_pct;
    let reliabilityCell;
    if (reliability == null) {
      reliabilityCell = '<span class="muted">—</span>';
    } else if (s.rel_insufficient) {
      reliabilityCell = `<span class="rel-pct rel-mid">${reliability}%</span>
        <span class="cmp-label-empty">(insufficient samples)</span>`;
    } else {
      const delta = reliability - rel.avg;
      const deltaCls = delta >= 0 ? 'cmp-delta-good'
        : delta >= -10 ? 'cmp-delta-mid'
        : 'cmp-delta-bad';
      const sign = delta > 0 ? '+' : '';
      const tooltip = `Trade average reliability for ${s.category}: ${rel.avg}%. Based on ${rel.subs} subs with \u226510 lifetime days.`;
      reliabilityCell = `<span class="rel-pct">${reliability}%</span>
        <span class="cmp-delta ${deltaCls} tip" tabindex="0" data-hint="${escapeHtml(tooltip)}">(${sign}${delta} vs trade)</span>`;
    }

    // Phase 6 — Recent Activity cell. Sparkline + 30-day count side-by-side.
    const sparkCells = renderSubSparkCells(s);
    const recentCount = s.recent_days > 0
      ? `<span class="cmp-recent-num">${s.recent_days}d</span>`
      : '<span class="muted">—</span>';
    const recentActivityCell = `<span class="cmp-recent">${recentCount}<span class="sub-spark">${sparkCells}</span></span>`;
    const phases = Array.isArray(s.phase_breakdown) ? s.phase_breakdown : [];
    const subKey = escapeHtml(s.key || s.name);
    // ID-safe slug (no spaces/punctuation) for the aria-controls + id linkage.
    // The data-sub-key still carries the canonical lowercase key for matching.
    const subIdSlug = (s.key || s.name).replace(/[^a-z0-9]+/gi, '-').toLowerCase();
    // Chevron is rendered only when there's a breakdown to show — short-tenure
    // subs (lifetime_days < 5) get an empty array from Python and look the
    // same as before. This keeps the trade-category click-to-filter behavior
    // intact and doesn't change row look for low-volume subs.
    // Phase 16 — tooltip reflects which attribution path produced the
    // breakdown. Other Trade / Internal Crew use solo-day fallback (only
    // days where the sub was alone on site); everyone else is filtered to
    // their trade family. Lets users know whether to read the rows as
    // "what they did" vs "what they were tagged for on solo days."
    const SOLO_CATS = new Set(['Other Trade', 'Internal Crew']);
    const breakdownTitle = SOLO_CATS.has(s.category)
      ? 'Solo-day phase mix (only days where this sub was alone on site)'
      : `Phases within ${s.category || 'trade'} family`;
    const toggleBtn = phases.length > 0
      ? `<button type="button" class="sub-toggle" aria-expanded="false" aria-controls="sub-phases-${subIdSlug}" title="${escapeHtml(breakdownTitle)}">▸</button> `
      : '<span class="sub-toggle-pad" aria-hidden="true"></span>';
    let phasesRow = '';
    if (phases.length > 0) {
      const items = phases.map((p, pi) => renderPhaseL1Item(p, pi, s.key || s.name)).join('');
      phasesRow = `<tr class="sub-phases" data-sub-key="${subKey}" id="sub-phases-${subIdSlug}" hidden>
        <td colspan="${colCount}"><ul class="sub-phase-list">${items}</ul></td>
      </tr>`;
    }
    // Phase 18 — multi-category badge support. SUBS_DATA exposes both
    // `category` (legacy single primary) and `categories` (list). Render
    // the list as comma-separated mini badges; falls back to single tag
    // when categories isn't populated.
    const cats = Array.isArray(s.categories) && s.categories.length > 0
      ? s.categories
      : [s.category || '—'];
    const catCell = cats.map(c => `<span class="cat-tag" title="Trade family this sub is credited for via the Phase 16 family filter.">${escapeHtml(c)}</span>`).join('');
    // Phase 19 — auto-expand state honors SUBS_ALL_EXPANDED so the
    // "Expand all" toggle reveals every sub's phase breakdown without
    // a per-row click.
    const expanded = SUBS_ALL_EXPANDED && phases.length > 0;
    const toggleSym = expanded ? '▾' : '▸';
    const toggleAria = expanded ? 'true' : 'false';
    const toggleBtnExp = phases.length > 0
      ? `<button type="button" class="sub-toggle" aria-expanded="${toggleAria}" aria-controls="sub-phases-${subIdSlug}" title="${escapeHtml(breakdownTitle)}">${toggleSym}</button> `
      : '<span class="sub-toggle-pad" aria-hidden="true"></span>';
    let phasesRowExp = '';
    if (phases.length > 0) {
      const items = phases.map((p, pi) => renderPhaseL1Item(p, pi, s.key || s.name)).join('');
      phasesRowExp = `<tr class="sub-phases" data-sub-key="${subKey}" id="sub-phases-${subIdSlug}"${expanded ? '' : ' hidden'}>
        <td colspan="${colCount}"><ul class="sub-phase-list">${items}</ul></td>
      </tr>`;
    }
    return `<tr class="sub-row" data-sub-key="${subKey}">
      <td>${toggleBtnExp}<span class="sub-name">${escapeHtml(s.name)}</span>${volumeDisclosurePrint(s)}</td>
      <td>${catCell}</td>
      <td>${durationCell}</td>
      <td>${reliabilityCell}</td>
      <td>${recentActivityCell}</td>
      <td class="right${lastWarn}">${escapeHtml(lastStr)}</td>
      <td class="right">${volumeDisclosureHtml(s)}</td>
    </tr>${phasesRowExp}`;
  };

  // Phase 19 — render one trade-category subsection (header + sub rows).
  // Used inside each build-stage section. catSubs is already filtered to
  // this category and may be empty (skip rendering then).
  const renderTradeSubsection = (cat, catSubs) => {
    if (!catSubs.length) return '';
    const sortedSubs = sortRows(catSubs);
    const subRowsHtml = sortedSubs.map(renderSubRow).join('');
    const catHead = `<tbody class="subs-cat-head">
      <tr><td colspan="${colCount}">
        <span class="sch-name">${escapeHtml(cat)}</span>
        <span class="sch-count">${sortedSubs.length} sub${sortedSubs.length === 1 ? '' : 's'}</span>
      </td></tr>
    </tbody>`;
    return catHead + `<tbody class="subs-trade-body">${subRowsHtml}</tbody>`;
  };

  // Phase 19 — render one build-stage section (Pre-Construction & Site,
  // Foundation & Concrete, …). Iterates the section's cats[] in declared
  // order so trades stay in their natural rough-in sequence inside MEP,
  // finishes inside Finishes Interior, etc. Skips the entire section if
  // none of its cats have any matching subs.
  const renderStageSection = (sec) => {
    const blocks = sec.cats.map(cat => renderTradeSubsection(cat, subsByCategory.get(cat) || [])).filter(Boolean);
    if (!blocks.length) return '';
    const totalSubs = sec.cats.reduce((n, c) => n + ((subsByCategory.get(c) || []).length), 0);
    const sectionHead = `<tbody class="subs-section-head">
      <tr><td colspan="${colCount}">
        <span class="ssh-eyebrow">Build stage</span>
        <h3>${escapeHtml(sec.name)}</h3>
        <span class="ssh-count">${totalSubs} sub${totalSubs === 1 ? '' : 's'}</span>
      </td></tr>
    </tbody>`;
    return sectionHead + blocks.join('');
  };

  const sectionsHtml = PHASE_SEQ_SECTIONS.map(renderStageSection).filter(Boolean).join('');

  // Subs whose category didn't fall into any PHASE_SEQ_SECTIONS bucket
  // (shouldn't happen post-Phase-18 but guards new categories) — drop
  // them into a final "Unsectioned" pseudo-section so they're not lost.
  const placedCats = new Set();
  for (const sec of PHASE_SEQ_SECTIONS) for (const c of sec.cats) placedCats.add(c);
  const unplacedCats = Array.from(subsByCategory.keys()).filter(c => !placedCats.has(c));
  let unsectionedHtml = '';
  if (unplacedCats.length) {
    const blocks = unplacedCats.map(c => renderTradeSubsection(c, subsByCategory.get(c) || [])).filter(Boolean);
    if (blocks.length) {
      const total = unplacedCats.reduce((n, c) => n + ((subsByCategory.get(c) || []).length), 0);
      unsectionedHtml = `<tbody class="subs-section-head">
        <tr><td colspan="${colCount}">
          <span class="ssh-eyebrow">Build stage</span>
          <h3>Unsectioned</h3>
          <span class="ssh-count">${total} sub${total === 1 ? '' : 's'}</span>
        </td></tr>
      </tbody>` + blocks.join('');
    }
  }

  // Build-stage summary count for the table-head label.
  let totalRowCount = 0;
  for (const arr of subsByCategory.values()) totalRowCount += arr.length;

  const stalePill = staleCount > 0
    ? `<button type="button" class="subs-stale-toggle ${SUBS_HIDE_STALE ? '' : 'active'}" onclick="toggleSubsStale()" title="Stale = last seen more than 365 days ago">
        ${SUBS_HIDE_STALE ? `Show stale subs (${staleCount})` : `Hiding stale (${staleCount})`}
      </button>`
    : '';
  const staleNote = (SUBS_HIDE_STALE && staleCount > 0)
    ? ` <span class="subs-stale-note">(${staleCount} stale hidden)</span>` : '';
  const expandAllBtn = `<button type="button" class="subs-expand-all ${SUBS_ALL_EXPANDED ? 'active' : ''}" onclick="toggleSubsExpandAll()" title="Expand or collapse every sub's phase breakdown">${SUBS_ALL_EXPANDED ? 'Collapse all' : 'Expand all phases'}</button>`;
  return `<section class="subs-table-wrap">
    <div class="subs-table-head">
      <input type="search" class="subs-filter" placeholder="Filter subs by name…" value="${escapeHtml(SUBS_FILTER)}">
      ${expandAllBtn}
      ${stalePill}
      <button type="button" class="subs-comparison-toggle ${SUBS_ONLY_COMPARISON ? 'active' : ''}" onclick="toggleSubsOnlyComparison()" title="Hide subs that don't have enough samples to compare against trade peers">
        ${SUBS_ONLY_COMPARISON ? `Comparison data only (${insufficientCount} hidden)` : `Show all subs (${insufficientCount} insufficient)`}
      </button>
      <span class="muted subs-table-count">${filtered.length} sub${filtered.length === 1 ? '' : 's'} in ${totalRowCount} placement${totalRowCount === 1 ? '' : 's'} across build stages${staleNote}</span>
    </div>
    <table class="subs-table">
      <thead><tr>${head}</tr></thead>
      ${sectionsHtml}
      ${unsectionedHtml}
    </table>
  </section>`;
}

function toggleSubsStale() {
  SUBS_HIDE_STALE = !SUBS_HIDE_STALE;
  const view = document.getElementById('pmView');
  if (!view) return;
  view.innerHTML = renderSubsView();
  wireSubsView();
}

// Phase 6 — toggle "show only subs with comparison data" chip.
function toggleSubsOnlyComparison() {
  SUBS_ONLY_COMPARISON = !SUBS_ONLY_COMPARISON;
  const view = document.getElementById('pmView');
  if (!view) return;
  view.innerHTML = renderSubsView();
  wireSubsView();
}

function renderSubSparkCells(s) {
  // 13-month tiny inline bars showing days-on-site per month
  const data = s.monthly_days || [];
  if (!data.length) return '';
  const max = Math.max(1, ...data);
  return data.map(v => {
    const opacity = v ? Math.max(0.2, v / max) : 0.1;
    const h = v ? Math.max(2, Math.round((v / max) * 10)) : 1;
    return `<span class="sub-spark-cell" style="height:${h}px; opacity:${opacity}" title="${v} days"></span>`;
  }).join('');
}

/* Phase 17 / 19 — render a single Level-1 phase entry inside the expanded
   sub row. Shows the schedule item (e.g. "Plumbing Rough In") with the
   sub's average duration on it, plus a benchmark comparison against the
   portfolio median. Click the phase chevron to expand into the per-job
   breakdown (Level 2). Phase 19 dropped the Level-3 (per-date) drill-down
   because it added clutter without helping schedule comparisons. */
function renderPhaseL1Item(p, idx, subKey) {
  const safeSubKey = (subKey || '').replace(/[^a-z0-9]+/gi, '-').toLowerCase();
  const isResidual = (p.phase || '').startsWith('On-site') || (p.phase || '').startsWith('Multi-sub');
  const phaseId = `phase-${safeSubKey}-${idx}`;
  const dayTip = isResidual && (p.phase || '').startsWith('On-site')
    ? "Days this sub was on site but BT didn't log a matching trade activity. Reflects Buildertrend logging gaps, not work that wasn't done."
    : (isResidual && (p.phase || '').startsWith('Multi-sub'))
      ? "Days this sub was on site alongside other subs. Phase mix can't be cleanly attributed to one sub. Internal Crew handling."
      : "Distinct days credited to this phase via the trade-family filter. Sub was on site AND a matching trade activity was logged.";

  // Benchmark lookup — only show median/comparison for non-residual rows
  // when sample size is adequate.
  let metaText = '';
  if (!isResidual) {
    const bench = (SUBS_DATA && SUBS_DATA.phase_benchmarks) ? SUBS_DATA.phase_benchmarks[p.phase] : null;
    const showBench = bench && bench.sample_size >= 3;
    const avg = (typeof p.avg_days_per_job === 'number') ? p.avg_days_per_job : null;
    const jobCountStr = (p.job_count != null) ? `${p.job_count} job${p.job_count === 1 ? '' : 's'}` : '';
    const avgStr = (avg != null) ? `<span class="phase-avg" title="Average days per job for this sub on this schedule item.">avg <b>${avg}d</b>/job</span>` : '';
    const minMaxStr = (typeof p.min_days_per_job === 'number' && typeof p.max_days_per_job === 'number' && p.min_days_per_job !== p.max_days_per_job)
      ? `<span title="Fastest and slowest of this sub's runs on this schedule item.">range ${p.min_days_per_job}–${p.max_days_per_job}d</span>`
      : '';
    const benchStr = showBench
      ? `<span class="meta-bench" title="Portfolio median days per job for this schedule item, across every sub in this trade (sample size ${bench.sample_size}).">trade median ${bench.median_days_per_job}d</span>`
      : (bench
          ? `<span class="meta-bench" style="opacity:0.5" title="Sample size ${bench.sample_size} — too small to benchmark.">no benchmark</span>`
          : '');
    metaText = [jobCountStr, avgStr, minMaxStr, benchStr].filter(Boolean).join(' &middot; ');
  }

  // Phase 19 — Level 2 (per-job) is now a flat info row. The click-to-drill
  // chevron from Phase 17 is gone (Level 3 was removed); a small bullet
  // marks each job entry instead. Keeps the per-job "Markgraf 16d ⚡ below
  // median" line that's actually useful for spotting outliers.
  let level2Html = '';
  if (!isResidual && Array.isArray(p.jobs) && p.jobs.length > 0) {
    const bench = (SUBS_DATA && SUBS_DATA.phase_benchmarks) ? SUBS_DATA.phase_benchmarks[p.phase] : null;
    const showBadge = bench && bench.sample_size >= 3;
    const items = p.jobs.map((j, ji) => {
      if (typeof j === 'string') {
        return `<li class="phase-l2"><div class="phase-l2-row"><span class="phase-l2-bullet">●</span><span class="job-name">${escapeHtml(j)}</span></div></li>`;
      }
      let badge = '<span class="job-badge nomark"></span>';
      if (showBadge) {
        if (j.days < bench.p25) {
          badge = `<span class="job-badge fast">${hint('⚡ below median')}</span>`;
        } else if (j.days > bench.p75) {
          badge = `<span class="job-badge slow">${hint('⚠ above median')}</span>`;
        } else {
          badge = `<span class="job-badge norm">${hint('✓ within range')}</span>`;
        }
      }
      const statusCls = j.status === 'ongoing' ? ' job-status-ongoing' : '';
      const span = (j.calendar_span_days != null) ? `${j.calendar_span_days}d span` : '';
      const datesPart = `${escapeHtml(j.first_date || '')} → ${escapeHtml(j.last_date || '')}${span ? ' (' + escapeHtml(span) + ')' : ''}`;
      const jobId = `${phaseId}-job-${ji}`;
      return `<li class="phase-l2" data-phase="${escapeHtml(p.phase)}" data-job="${escapeHtml(j.job)}" data-job-idx="${ji}" id="${jobId}">
        <div class="phase-l2-row">
          <span class="phase-l2-bullet" aria-hidden="true">●</span>
          <span class="job-name">${escapeHtml(j.job)}</span>
          <span class="job-days" title="Distinct days this sub worked this schedule item on this specific job.">${j.days}d</span>
          ${badge}
          <span class="job-span${statusCls}" title="Calendar days from first log to last log. Span includes weekends and idle days.">${datesPart}${j.status === 'ongoing' ? ' · ongoing' : ''}</span>
        </div>
      </li>`;
    }).join('');
    level2Html = `<ul class="phase-jobs">${items}</ul>`;
  }

  if (isResidual) {
    return `<li class="phase-l1 phase-residual" data-phase="${escapeHtml(p.phase)}">
      <div class="phase-l1-row">
        <span class="phase-toggle-pad"></span>
        <span class="sub-phase-name" title="${escapeHtml(dayTip)}">${escapeHtml(p.phase)}</span>
        <span class="sub-phase-days" title="${escapeHtml(dayTip)}">${p.days}d (${p.pct}%)</span>
        <span class="sub-phase-meta"></span>
      </div>
    </li>`;
  }

  // Phase 19 — auto-expand state honors SUBS_ALL_EXPANDED.
  const expanded = !!SUBS_ALL_EXPANDED;
  const expandedClass = expanded ? ' expanded' : '';
  const toggleSym = expanded ? '▾' : '▸';
  const toggleAria = expanded ? 'true' : 'false';
  return `<li class="phase-l1${expandedClass}" data-phase="${escapeHtml(p.phase)}" id="${phaseId}">
    <div class="phase-l1-row">
      <button type="button" class="phase-toggle" aria-expanded="${toggleAria}" title="Click to see per-job breakdown.">${toggleSym}</button>
      <span class="sub-phase-name">${escapeHtml(p.phase)}</span>
      <span class="sub-phase-days" title="${escapeHtml(dayTip)}">${p.days}d (${p.pct}%)</span>
      <span class="sub-phase-meta">${metaText}</span>
    </div>
    ${level2Html}
  </li>`;
}

/* Render combined "PM analytics" view (filtered Jobs + Subs) into #pmView.
   Called via CDP by email_sender.py to produce a per-PM analytics PDF. */
function activatePMAnalytics(pmName) {
  const view = document.getElementById('pmView');
  document.querySelectorAll('.tab').forEach(t => t.setAttribute('aria-selected', 'false'));
  const ts = new Date().toLocaleString('en-US', { dateStyle: 'long', timeStyle: 'short' });
  const jobsHtml = renderJobsView(pmName);
  const subsHtml = renderSubsView(pmName);
  view.innerHTML = `
    <div class="pm-analytics" data-pm="${escapeHtml(pmName)}">
      <header class="pm-analytics-head">
        <div class="eyebrow">Production analytics — ${escapeHtml(pmName)}</div>
        <h1>Jobs &amp; Subs activity</h1>
        <p class="muted">Lifetime + recent (last 30 days) site reality from Buildertrend daily logs. Generated ${escapeHtml(ts)}.</p>
      </header>
      <section class="pm-analytics-jobs">${jobsHtml}</section>
      <section class="pm-analytics-subs">${subsHtml}</section>
    </div>`;
  return 'ok';
}

function wireSubsView() {
  const view = document.getElementById('pmView');
  // Header sort clicks
  view.querySelectorAll('.subs-table thead th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (SUBS_SORT.key === key) {
        SUBS_SORT.dir = SUBS_SORT.dir === 'desc' ? 'asc' : 'desc';
      } else {
        SUBS_SORT.key = key;
        SUBS_SORT.dir = (key === 'name') ? 'asc' : 'desc';
      }
      view.innerHTML = renderSubsView();
      wireSubsView();
    });
  });
  // Category card clicks — filter the table to that category, toggle off if same
  view.querySelectorAll('.cat-card[data-cat]').forEach(card => {
    const click = () => {
      const cat = card.dataset.cat;
      SUBS_CATEGORY_FILTER = (SUBS_CATEGORY_FILTER === cat) ? '' : cat;
      view.innerHTML = renderSubsView();
      wireSubsView();
    };
    card.addEventListener('click', click);
    card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); click(); } });
  });
  view.querySelectorAll('.cat-clear').forEach(b => b.addEventListener('click', () => {
    SUBS_CATEGORY_FILTER = '';
    view.innerHTML = renderSubsView();
    wireSubsView();
  }));
  // Phase 17 — view-mode toggle (Table / Phase Sequence)
  view.querySelectorAll('.subs-view-toggle button[data-view-mode]').forEach(btn => {
    btn.addEventListener('click', () => {
      const mode = btn.dataset.viewMode;
      if (mode && mode !== SUBS_VIEW_MODE) {
        SUBS_VIEW_MODE = mode;
        view.innerHTML = renderSubsView();
        wireSubsView();
      }
    });
  });
  // Filter
  const filterInput = view.querySelector('.subs-filter');
  if (filterInput) {
    filterInput.addEventListener('input', (e) => {
      SUBS_FILTER = e.target.value;
      // Keep focus on the input across re-render
      const cursor = e.target.selectionStart;
      view.innerHTML = renderSubsView();
      wireSubsView();
      const newInput = view.querySelector('.subs-filter');
      if (newInput) {
        newInput.focus();
        newInput.setSelectionRange(cursor, cursor);
      }
    });
  }
  // Phase-breakdown chevron — event-delegated on each tbody so the handler
  // survives table re-renders without rebinding per-row. Re-renders happen
  // on sort/filter/category clicks; expanded state is intentionally NOT
  // persisted across re-renders since rows can be reordered or filtered out.
  view.querySelectorAll('.subs-table tbody').forEach(tbody => {
    tbody.addEventListener('click', (e) => {
      // Sub-row chevron — Level 1 (sub) → expand phase list
      const subBtn = e.target.closest('.sub-toggle');
      if (subBtn) {
        e.stopPropagation();
        const tr = subBtn.closest('tr.sub-row');
        if (!tr) return;
        const key = tr.dataset.subKey;
        const phasesRow = tbody.querySelector(`tr.sub-phases[data-sub-key="${CSS.escape(key)}"]`);
        if (!phasesRow) return;
        const isOpen = subBtn.getAttribute('aria-expanded') === 'true';
        subBtn.setAttribute('aria-expanded', String(!isOpen));
        subBtn.textContent = isOpen ? '▸' : '▾';
        if (isOpen) phasesRow.setAttribute('hidden', '');
        else phasesRow.removeAttribute('hidden');
        return;
      }
      // Phase chevron — Level 1 (phase) → expand per-job list
      const phaseBtn = e.target.closest('.phase-toggle');
      if (phaseBtn) {
        e.stopPropagation();
        const li = phaseBtn.closest('.phase-l1');
        if (!li) return;
        const isOpen = phaseBtn.getAttribute('aria-expanded') === 'true';
        phaseBtn.setAttribute('aria-expanded', String(!isOpen));
        phaseBtn.textContent = isOpen ? '▸' : '▾';
        li.classList.toggle('expanded', !isOpen);
        return;
      }
    });
  });
}

/* Phase 19 — global expand/collapse for the entire Subs table. Walks the
   DOM directly instead of full re-rendering so the filter input keeps
   focus and the user's filter text isn't disturbed. The state variable
   SUBS_ALL_EXPANDED is also read by renderSubsTable on subsequent
   re-renders (sort/filter/category clicks) so the chosen state persists. */
function toggleSubsExpandAll() {
  SUBS_ALL_EXPANDED = !SUBS_ALL_EXPANDED;
  const view = document.getElementById('pmView');
  if (!view) return;
  const sym = SUBS_ALL_EXPANDED ? '▾' : '▸';
  const aria = SUBS_ALL_EXPANDED ? 'true' : 'false';
  view.querySelectorAll('.sub-toggle').forEach(btn => {
    btn.setAttribute('aria-expanded', aria);
    btn.textContent = sym;
  });
  view.querySelectorAll('tr.sub-phases').forEach(tr => {
    if (SUBS_ALL_EXPANDED) tr.removeAttribute('hidden');
    else tr.setAttribute('hidden', '');
  });
  view.querySelectorAll('.phase-toggle').forEach(btn => {
    btn.setAttribute('aria-expanded', aria);
    btn.textContent = sym;
  });
  view.querySelectorAll('.phase-l1').forEach(li => {
    li.classList.toggle('expanded', SUBS_ALL_EXPANDED);
  });
  const btn = view.querySelector('.subs-expand-all');
  if (btn) {
    btn.classList.toggle('active', SUBS_ALL_EXPANDED);
    btn.textContent = SUBS_ALL_EXPANDED ? 'Collapse all' : 'Expand all phases';
  }
}

/* Phase 18 — Jobs tab event wiring. Currently just powers the Phase
   Durations panel (sort buttons, filter input, expand-row toggles).
   Per-PM filters are routed via re-render rather than DOM mutation
   so the summary stats stay in sync. */
function wireJobsView() {
  const view = document.getElementById('pmView');
  if (!view) return;
  // Sort buttons
  view.querySelectorAll('.pd-sort-btn[data-pd-sort]').forEach(btn => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.pdSort;
      if (k && k !== PHASE_DUR_SORT) {
        PHASE_DUR_SORT = k;
        const panel = view.querySelector('.phase-dur-panel');
        if (panel) {
          panel.outerHTML = renderPhaseDurationsPanel(PHASE_DUR_FILTER_PM || null);
          wireJobsView();
        }
      }
    });
  });
  // Filter input — debounced via raf
  const filt = view.querySelector('.pd-filter');
  if (filt) {
    filt.addEventListener('input', (e) => {
      PHASE_DUR_FILTER = e.target.value;
      const cursor = e.target.selectionStart;
      const panel = view.querySelector('.phase-dur-panel');
      if (panel) {
        panel.outerHTML = renderPhaseDurationsPanel(PHASE_DUR_FILTER_PM || null);
        wireJobsView();
        const f2 = view.querySelector('.pd-filter');
        if (f2) { f2.focus(); f2.setSelectionRange(cursor, cursor); }
      }
    });
  }
  // Expand-row toggles (event-delegated on the table body)
  const tbody = view.querySelector('.phase-dur-table tbody');
  if (tbody) {
    tbody.addEventListener('click', (e) => {
      const btn = e.target.closest('.pd-toggle');
      if (!btn) return;
      e.stopPropagation();
      const tr = btn.closest('tr.pd-row');
      if (!tr) return;
      const tag = tr.dataset.pdTag;
      const detail = tbody.querySelector(`tr.pd-detail-row[data-pd-tag="${CSS.escape(tag)}"]`);
      if (!detail) return;
      const isOpen = btn.getAttribute('aria-expanded') === 'true';
      btn.setAttribute('aria-expanded', String(!isOpen));
      btn.textContent = isOpen ? '▸' : '▾';
      if (isOpen) {
        detail.setAttribute('hidden', '');
        PHASE_DUR_EXPANDED.delete(tag);
      } else {
        detail.removeAttribute('hidden');
        PHASE_DUR_EXPANDED.add(tag);
      }
    });
  }
}

/* Phase-duration Gantt — chronological timeline of parent_group_activities
   with span bars + duration labels. Each bar shows first→last calendar
   appearance; ongoing phases render in the job color, completed in muted ink. */
function renderPhaseGantt(phases, jobFirst, jobLast, jobColorVar) {
  if (!phases || !phases.length) return '';
  const start = new Date(jobFirst);
  const end = new Date(jobLast);
  const totalDays = Math.max(1, Math.round((end - start) / 86400000) + 1);

  // Month-tick labels along the top axis: every ~60 days, plus first/last
  const ticks = [];
  if (totalDays > 0) {
    const step = totalDays > 365 ? 90 : totalDays > 180 ? 45 : 30;
    let cursor = 0;
    while (cursor < totalDays) {
      const d = new Date(start.getTime() + cursor * 86400000);
      ticks.push({ pct: (cursor / totalDays) * 100, label: d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) });
      cursor += step;
    }
    // Always include end
    ticks.push({ pct: 100, label: end.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }) });
  }
  const tickHtml = ticks.map(t =>
    `<span class="ph-tick" style="left:${t.pct.toFixed(2)}%">${escapeHtml(t.label)}</span>`
  ).join('');

  const rows = phases.map(p => {
    // Primary bar — the LONGEST burst (focused phase period)
    const pStart = new Date(p.first);
    const pEnd = new Date(p.last);
    const offsetDays = Math.max(0, (pStart - start) / 86400000);
    const widthDays = Math.max(0.5, (pEnd - pStart) / 86400000 + 1);
    const offsetPct = (offsetDays / totalDays) * 100;
    const widthPct = (widthDays / totalDays) * 100;
    // Lifetime overlay — faint bar showing the full span (incl. return visits)
    const lifeStart = new Date(p.lifetime_first || p.first);
    const lifeEnd = new Date(p.lifetime_last || p.last);
    const lifeOffsetDays = Math.max(0, (lifeStart - start) / 86400000);
    const lifeWidthDays = Math.max(0.5, (lifeEnd - lifeStart) / 86400000 + 1);
    const lifeOffsetPct = (lifeOffsetDays / totalDays) * 100;
    const lifeWidthPct = (lifeWidthDays / totalDays) * 100;
    const showLifetime = (p.num_bursts || 1) > 1;

    const tip = `${p.name} · primary burst ${formatDate(p.first)} → ${formatDate(p.last)} · ${p.duration_days}d span · ${p.active_days} active days${
      showLifetime ? ` · ${p.num_bursts} bursts total spanning ${p.lifetime_span_days}d` : ''
    }`;

    return `<div class="ph-row">
      <div class="ph-name" title="${escapeHtml(p.name)}">${escapeHtml(p.name)}</div>
      <div class="ph-bar-wrap">
        ${showLifetime ? `<div class="ph-bar-life" style="left:${lifeOffsetPct.toFixed(2)}%; width:${lifeWidthPct.toFixed(2)}%;"></div>` : ''}
        <div class="ph-bar ${p.ongoing ? 'ongoing' : ''}" style="left:${offsetPct.toFixed(2)}%; width:${widthPct.toFixed(2)}%;" title="${escapeHtml(tip)}"></div>
      </div>
      <div class="ph-stat">
        <span class="ph-days">${p.duration_days}d</span>
        ${p.active_days < p.duration_days ? `<span class="ph-active">${p.active_days} active</span>` : ''}
        ${showLifetime ? `<span class="ph-bursts" title="${p.num_bursts} return visits over ${p.lifetime_span_days}d">+${p.num_bursts - 1}</span>` : ''}
        ${p.ongoing ? '<span class="ph-ongoing">ongoing</span>' : ''}
      </div>
    </div>`;
  }).join('');

  return `<div class="ja-phases">
    <h3>Phase durations · timeline</h3>
    <div class="ph-axis">${tickHtml}</div>
    <div class="ph-gantt">${rows}</div>
    <p class="ph-legend">Solid bar = longest focused work burst (≤14-day gaps). Faint bar = full lifecycle span when phase recurred. <span class="ph-legend-ongoing">●</span> active in last 14 days · <span class="ph-legend-done">●</span> completed · +N badge = return visits.</p>
  </div>`;
}

/* SVG sparkline (line) — small inline, no chart lib. */
function sparkline(values, opts) {
  opts = opts || {};
  const color = opts.color || 'var(--accent)';
  if (!values || values.length === 0) return '';
  const w = 220, h = 36, pad = 2;
  const max = Math.max(1, ...values);
  const stepX = (w - 2 * pad) / Math.max(1, values.length - 1);
  const points = values.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - (v / max) * (h - 2 * pad);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');
  const lastV = values[values.length - 1];
  const lastX = pad + (values.length - 1) * stepX;
  const lastY = h - pad - (lastV / max) * (h - 2 * pad);
  return `<svg class="ja-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(opts.ariaLabel || 'sparkline')}">
    <polyline points="${points}" fill="none" stroke="${color}" stroke-width="1.5"/>
    <circle cx="${lastX.toFixed(1)}" cy="${lastY.toFixed(1)}" r="2.5" fill="${color}"/>
    <text x="${(lastX - 4).toFixed(1)}" y="${(lastY - 5).toFixed(1)}" text-anchor="end" font-size="9" fill="${color}" font-family="JetBrains Mono, ui-monospace, monospace">${lastV}</text>
  </svg>`;
}

/* SVG sparkbars (bar) — small inline. */
function sparkbars(values, opts) {
  opts = opts || {};
  const color = opts.color || 'var(--accent)';
  if (!values || values.length === 0) return '';
  const w = 220, h = 36, pad = 2;
  const max = Math.max(1, ...values);
  const barW = (w - 2 * pad) / values.length - 1;
  const bars = values.map((v, i) => {
    const x = pad + i * (barW + 1);
    const barH = (v / max) * (h - 2 * pad - 8);
    const y = h - pad - barH;
    return `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${barH.toFixed(1)}" fill="${color}" opacity="${v ? 0.85 : 0.2}"/>`;
  }).join('');
  return `<svg class="ja-spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="${escapeHtml(opts.ariaLabel || 'sparkbars')}">${bars}</svg>`;
}

/* ============================================================
   (deprecated) Top-of-doc per-PM Jobs overview — superseded by
   the dedicated Jobs analytics tab. Functions kept callable but
   no longer wired into the per-PM render() flow.
   ============================================================ */
function shortPhase(verbose) {
  if (!verbose) return '';
  // Phase strings from Claude follow "PhaseName — details, details, ..."
  // pattern; take the first clause as the canonical short label.
  const dashSplit = verbose.split(/[\u2014—-]\s/, 2)[0].trim();
  if (dashSplit && dashSplit.length <= 60) return dashSplit;
  return verbose.length > 60 ? verbose.slice(0, 57) + '…' : verbose;
}

function statusBadge(status) {
  const s = (status || '').toLowerCase();
  if (s === 'green') return '<span class="status-badge green" title="green">●</span>';
  if (s === 'amber' || s === 'yellow') return '<span class="status-badge amber" title="amber">●</span>';
  if (s === 'red') return '<span class="status-badge red" title="red">●</span>';
  return '<span class="status-badge muted" title="unknown">●</span>';
}

function renderJobsOverview() {
  const jobs = DATA.jobs || [];
  const lb = (DATA.lookBehind && DATA.lookBehind.per_job) || {};
  const stats = DATA.dailyLogStats || {};

  const head = `<header>
    <div class="eyebrow">Project briefing</div>
    <h2>Jobs overview</h2>
    <span class="time-tag">scan</span>
  </header>
  <p class="section-subhead">Phase, status, and 14-day site reality across every job.</p>`;

  if (!jobs.length) {
    return head + `<p class="muted"><em>No jobs configured for this PM.</em></p>`;
  }

  const rows = jobs.map(j => renderJobOverviewRow(j, lb[j.name] || {}, stats[j.name] || {})).join('');
  const rollup = renderJobsRollup(jobs, lb, stats);
  return head + `<div class="jobs-overview-grid">${rows}</div>${rollup}`;
}

function renderJobOverviewRow(j, lbData, stats) {
  const col = jobColor(j.name);
  const phaseShort = shortPhase(j.phase || '');
  const phaseFull = j.phase || '';
  const wf = lbData.workforce || stats.workforce_stats || {};

  const days = lbData.days_on_site ?? stats.days_with_logs ?? '—';
  let wfStr = '—';
  if (wf.avg != null) {
    const tgt = wf.inferred_target_range ? ` (tgt ${wf.inferred_target_range})` : (wf.peak != null ? ` · peak ${wf.peak}` : '');
    wfStr = `${wf.avg} avg${tgt}`;
  }

  // Top crews — prefer lookBehind's pre-formatted strings, fall back to dailyLogStats
  const lbTop = Array.isArray(lbData.top_crews) ? lbData.top_crews.slice(0, 3) : [];
  let topCrewsStr;
  if (lbTop.length > 0) {
    topCrewsStr = lbTop.map(s => escapeHtml(s)).join(' · ');
  } else {
    const fromStats = Object.entries(stats.crew_day_counts || {}).slice(0, 3);
    topCrewsStr = fromStats.length > 0
      ? fromStats.map(([n, d]) => `${escapeHtml(n)} <span class="sa-mono">(${d}d)</span>`).join(' · ')
      : '—';
  }

  const deliveries = lbData.deliveries ?? stats.delivery_days ?? 0;
  const inspections = lbData.inspections_passed ?? stats.inspection_days ?? 0;
  const missedCount = Array.isArray(stats.missed_business_days) ? stats.missed_business_days.length : null;

  const cvp = lbData.completion_vs_plan || '';
  const cvpShort = cvp.length > 110 ? cvp.slice(0, 107) + '…' : cvp;

  const lastAge = stats.last_log_age_days;
  let lastStr = '';
  let lastWarn = '';
  if (lastAge != null) {
    lastStr = lastAge === 0 ? 'today' : lastAge === 1 ? 'yesterday' : `${lastAge}d ago`;
    if (lastAge >= 3) lastWarn = ' ⚠';
  }

  const targetCO = j.targetCO && j.targetCO !== '—' ? j.targetCO : null;

  return `
    <article class="job-overview-row" style="--job-color:${col}">
      <div class="jor-head">
        ${statusBadge(j.status)}
        <span class="jor-name">${escapeHtml(j.name)}${j.address ? ` <span class="jor-addr">${escapeHtml(j.address)}</span>` : ''}</span>
        ${phaseShort ? `<span class="jor-phase" title="${escapeHtml(phaseFull)}">${escapeHtml(phaseShort)}</span>` : ''}
        ${targetCO ? `<span class="jor-co">CO ${escapeHtml(targetCO)}</span>` : ''}
      </div>
      <div class="jor-stats">
        <span class="jor-stat"><span class="lbl">days</span> ${days}</span>
        <span class="jor-stat"><span class="lbl">crew</span> ${escapeHtml(wfStr)}</span>
        <span class="jor-stat"><span class="lbl">deliv</span> ${deliveries}</span>
        <span class="jor-stat"><span class="lbl">insp</span> ${inspections}</span>
        ${missedCount != null ? `<span class="jor-stat ${missedCount ? 'warn' : ''}"><span class="lbl">missed</span> ${missedCount}</span>` : ''}
        ${lastStr ? `<span class="jor-stat ${lastWarn ? 'warn' : ''}"><span class="lbl">last log</span> ${escapeHtml(lastStr)}${lastWarn}</span>` : ''}
      </div>
      <div class="jor-crews"><span class="lbl">top crews</span> ${topCrewsStr}</div>
      ${cvpShort ? `<div class="jor-progress">${escapeHtml(cvpShort)}</div>` : ''}
    </article>`;
}

function renderJobsRollup(jobs, lb, stats) {
  let totalDays = 0, totalDeliveries = 0, totalInspections = 0;
  let totalPersonDays = 0, totalMissed = 0;
  const uniqueSubs = new Set();

  for (const j of jobs) {
    const ld = lb[j.name] || {};
    const st = stats[j.name] || {};
    totalDays       += Number(ld.days_on_site ?? st.days_with_logs ?? 0);
    totalDeliveries += Number(ld.deliveries ?? st.delivery_days ?? 0);
    totalInspections+= Number(ld.inspections_passed ?? st.inspection_days ?? 0);
    if (st.workforce_stats && st.workforce_stats.total_person_days)
      totalPersonDays += st.workforce_stats.total_person_days;
    if (Array.isArray(st.missed_business_days))
      totalMissed += st.missed_business_days.length;
    Object.keys(st.crew_day_counts || {}).forEach(c => uniqueSubs.add(c));
  }

  return `<div class="overview-rollup">
    <span class="rollup-stat"><b>${jobs.length}</b> jobs</span>
    <span class="rollup-stat"><b>${uniqueSubs.size}</b> unique subs</span>
    <span class="rollup-stat"><b>${totalPersonDays}</b> person-days</span>
    <span class="rollup-stat"><b>${totalDeliveries}</b> deliveries</span>
    <span class="rollup-stat"><b>${totalInspections}</b> inspections</span>
    <span class="rollup-stat ${totalMissed ? 'warn' : ''}"><b>${totalMissed}</b> missed weekdays</span>
  </div>`;
}

/* ============================================================
   Section 2.1 — Site activity (per-job daily-log mini panels)
   Computed at HTML-render time from BT daily-logs.json. Reflects
   actual site reality from Buildertrend, not transcripts.
   ============================================================ */
function renderSiteActivity() {
  const stats = DATA.dailyLogStats || {};
  const meta  = DATA.dailyLogStatsMeta || {};
  const jobs  = DATA.jobs || [];
  const head = `<header>
    <div class="eyebrow">Section 2.1</div>
    <h2>Site activity — last 14 days</h2>
    <span class="time-tag">2 min</span>
  </header>
  <p class="section-subhead">From Buildertrend daily logs. Working days exclude weekends and US federal holidays.</p>`;

  if (meta.error) {
    return head + `<p class="muted"><em>Daily-log data unavailable: ${escapeHtml(meta.error)}</em></p>`;
  }
  if (!Object.keys(stats).length) {
    return head + `<p class="muted"><em>No daily-log data for this PM.</em></p>`;
  }

  const staleNote = meta.stale
    ? `<p class="sa-stale">⚠ Buildertrend data is stale (last scrape ${meta.age_hours ? meta.age_hours.toFixed(1) + 'h' : '?'} ago).</p>`
    : '';

  const cards = jobs.map(j => {
    const shortName = j.name;
    const s = stats[shortName];
    if (!s) return '';
    if (s.note) {
      const col = jobColor(shortName);
      return `<article class="sa-card empty" style="--job-color:${col}">
        <header class="sa-head">
          <span class="sa-job"><span class="dot" style="background:${col}"></span>${escapeHtml(shortName)}</span>
        </header>
        <p class="sa-empty">${escapeHtml(s.note)}</p>
      </article>`;
    }
    if ((s.total_logs ?? 0) === 0) {
      // Job exists in scraper data but had no logs in the 14-day window —
      // dormant/on-hold, not actually missing daily logs.
      const col = jobColor(shortName);
      return `<article class="sa-card empty" style="--job-color:${col}">
        <header class="sa-head">
          <span class="sa-job"><span class="dot" style="background:${col}"></span>${escapeHtml(shortName)}</span>
          <span class="sa-last">No activity in window</span>
        </header>
        <p class="sa-empty">No daily logs in the last 14 days. Job appears inactive — recent activity, if any, is outside this window.</p>
      </article>`;
    }
    return renderSiteActivityCard(shortName, s);
  }).filter(Boolean).join('');

  return head + staleNote + `<div class="sa-grid">${cards}</div>`;
}

function renderSiteActivityCard(shortName, s) {
  const col = jobColor(shortName);

  // Last log + age warning
  const lastDateStr = s.last_log_date ? formatDate(s.last_log_date) : '—';
  let ageStr = '';
  let ageWarn = '';
  if (s.last_log_age_days != null) {
    ageStr = s.last_log_age_days === 0 ? 'today'
           : s.last_log_age_days === 1 ? 'yesterday'
           : `${s.last_log_age_days}d ago`;
    if (s.last_log_age_days >= 3) ageWarn = ' ⚠';
  }

  // Logs / weekdays
  const logged = s.business_days_logged ?? s.days_with_logs ?? 0;
  const total  = s.business_days_in_window ?? s.days_expected ?? 0;
  const logsRatio = total > 0 ? `${logged} / ${total}` : `${logged}`;

  // Missed weekdays — list dates compactly, cap at 6 with overflow indicator
  const missed = s.missed_business_days || [];
  let missedStr = '—';
  if (missed.length > 0) {
    const shown = missed.slice(0, 6).map(d => formatDate(d)).join(', ');
    missedStr = missed.length > 6
      ? `${shown}, +${missed.length - 6} more`
      : shown;
  }

  // Workforce
  const wf = s.workforce_stats;
  const wfStr = wf
    ? `avg ${wf.avg} · peak ${wf.peak} · ${wf.total_person_days} person-days`
    : '—';

  // Top crews — top 3 by days-on-site
  const crewEntries = Object.entries(s.crew_day_counts || {}).slice(0, 3);
  const crewsStr = crewEntries.length === 0
    ? '—'
    : crewEntries.map(([n, d]) => `${escapeHtml(n)} <span class="sa-mono">(${d}d)</span>`).join(' · ');

  // Absences — top 3
  const absentEntries = Object.entries(s.absent_crew_frequency || {}).slice(0, 3);
  const absentStr = absentEntries.length === 0
    ? '—'
    : absentEntries.map(([n, d]) => `${escapeHtml(n)} <span class="sa-mono">(${d}d)</span>`).join(' · ');

  // Inspections — count + latest snippet
  const inspStr = renderEventSummary(s.inspection_events || [], s.inspection_days || 0);
  const delivStr = renderEventSummary(s.delivery_events || [], s.delivery_days || 0);

  return `
    <article class="sa-card" style="--job-color:${col}">
      <header class="sa-head">
        <span class="sa-job"><span class="dot" style="background:${col}"></span>${escapeHtml(shortName)}</span>
        <span class="sa-last">Last: ${lastDateStr}${ageStr ? ` <span class="sa-mono">(${ageStr})</span>` : ''}${ageWarn}</span>
      </header>
      <dl class="sa-stats">
        <dt>Logs</dt>        <dd>${logsRatio} weekdays</dd>
        <dt>Missed</dt>      <dd class="${missed.length ? 'sa-warn' : ''}">${missedStr}</dd>
        <dt>Workforce</dt>   <dd>${wfStr}</dd>
        <dt>Top crews</dt>   <dd>${crewsStr}</dd>
        <dt>Absences</dt>    <dd>${absentStr}</dd>
        <dt>Inspections</dt> <dd>${inspStr}</dd>
        <dt>Deliveries</dt>  <dd>${delivStr}</dd>
      </dl>
    </article>`;
}

function renderEventSummary(events, dayCount) {
  // Use day count (matches the "Logs X/Y weekdays" semantic). Latest event
  // detail is appended if a meaningful text snippet was captured.
  const days = dayCount || 0;
  if (!days) return '—';
  const dayStr = `${days} day${days === 1 ? '' : 's'}`;
  if (!events || events.length === 0) return dayStr;
  const latest = events[0]; // events are newest-first
  const snippet = (latest.details || '').replace(/\s+/g, ' ').trim();
  const snippetShort = snippet.length > 70 ? snippet.slice(0, 70) + '…' : snippet;
  return `${dayStr} · latest ${formatDate(latest.date)}${snippetShort ? ' — ' + escapeHtml(snippetShort) : ''}`;
}

/* ============================================================
   Section 2 — lookBehind
   ============================================================ */
function renderSection2_LookBehind() {
  const lb = DATA.lookBehind;
  const head = `<header>
    <div class="eyebrow">Section 2</div>
    <h2>Last 2 weeks vs. plan</h2>
    <span class="time-tag">2 min</span>
  </header>`;
  if (!lb || !lb.per_job || Object.keys(lb.per_job).length === 0) {
    return head + `<p class="muted"><em>No prior-week data yet. Process this PM's transcript through the pipeline to populate this section.</em></p>`;
  }
  const weekStr = lb.week_of || '';
  const cards = Object.entries(lb.per_job).map(([job, d]) => {
    if (d.status && /no activity/i.test(d.status)) {
      return `<div class="lb-card">
        <div class="lb-head">
          <span class="lb-job"><span class="dot" style="background:${jobColor(job)}"></span>${escapeHtml(job)}</span>
          <span class="lb-week">${escapeHtml(weekStr)}</span>
        </div>
        <div class="empty-state">No activity logged for this job in the 14-day window.</div>
      </div>`;
    }
    const wf = d.workforce || {};
    const ppc = d.completion_vs_plan || '';
    const varianceClass = /green|on|strong|good/i.test(d.completion_vs_plan || '') || /good|strong|on target/i.test(d.ppc_narrative || '') ? 'variance-good' : '';
    const ppcMatch = (d.completion_vs_plan || '').match(/(\d{1,3})\s*%/);
    const ppcNum = ppcMatch ? ppcMatch[1] + '%' : (d.completion_vs_plan || '—');
    const topActs = Array.isArray(d.top_activities) ? d.top_activities : [];
    const topCrews = Array.isArray(d.top_crews) ? d.top_crews : [];
    const notable = Array.isArray(d.notable_events) ? d.notable_events : [];
    const missed = Array.isArray(d.missed_subs) ? d.missed_subs : [];
    return `<div class="lb-card">
      <div class="lb-head">
        <span class="lb-job"><span class="dot" style="background:${jobColor(job)}"></span>${escapeHtml(job)}</span>
        <span class="lb-week">${escapeHtml(weekStr)}</span>
      </div>
      <div class="ppc-block">
        <div class="ppc-num">${escapeHtml(ppcNum)}</div>
        <div class="ppc-label">${escapeHtml(ppc) || 'Completion vs plan'}</div>
      </div>
      ${wf.avg !== undefined ? `<div class="lb-row"><strong>Workforce</strong> · ${wf.avg} avg · ${wf.peak ?? '—'} peak · ${wf.low ?? '—'} low · target ${escapeHtml(wf.inferred_target_range || '—')}${wf.variance_note ? ` <span class="${varianceClass}">· ${escapeHtml(wf.variance_note)}</span>` : ''}</div>` : ''}
      <div class="lb-row"><strong>${d.days_on_site ?? 0}</strong> days on site · <strong>${d.inspections_passed ?? 0}</strong> inspections · <strong>${d.deliveries ?? 0}</strong> deliveries</div>
      <div class="lb-pair-grid">
        <div><h4>Top activities</h4><ul>${topActs.map(a => `<li>${escapeHtml(a)}</li>`).join('') || '<li class="muted">—</li>'}</ul></div>
        <div><h4>Top crews</h4><ul>${topCrews.map(c => `<li>${escapeHtml(c)}</li>`).join('') || '<li class="muted">—</li>'}</ul></div>
      </div>
      ${notable.length ? `<div class="lb-notable"><h4>Notable events</h4><ul>${notable.map(n => `<li>${escapeHtml(n)}</li>`).join('')}</ul></div>` : ''}
      ${missed.length ? `<div class="lb-missed"><strong>Missed subs:</strong> ${missed.map(escapeHtml).join(' · ')}</div>` : ''}
      ${d.ppc_narrative ? `<div class="lb-narrative">${escapeHtml(d.ppc_narrative)}</div>` : ''}
    </div>`;
  }).join('');
  return head + `<div class="lb-grid">${cards}</div>`;
}

/* ============================================================
   Section 2.5 — Heads Up (next week's risks)
   ============================================================ */
const HEADSUP_CATEGORIES = [
  { key: 'aging_into_stale',        label: 'Aging into stale (>14d)',        color: 'amber'  },
  { key: 'subs_to_watch',           label: 'Subs to watch',                  color: 'red'    },
  { key: 'sequencing_risks',        label: 'Sequencing risks',               color: 'orange' },
  { key: 'selections_due_this_week', label: 'Selections due this week',      color: 'blue'   },
  { key: 'client_trust_signals',    label: 'Client trust signals',           color: 'red'    },
  { key: 'exterior_work_flags',     label: 'Exterior / weather flags',       color: 'gray'   },
];
function allHeadsUpEmpty(hu) {
  if (!hu || typeof hu !== 'object') return true;
  return HEADSUP_CATEGORIES.every(c => !Array.isArray(hu[c.key]) || hu[c.key].length === 0);
}
function headsUpFields(category, e) {
  const s = (k) => (e && e[k] != null) ? String(e[k]) : '';
  switch (category) {
    case 'aging_into_stale': {
      const meta = [s('item_id') ? `Item ${s('item_id')}` : '',
                    s('current_age_days') ? `${s('current_age_days')}d open` : '',
                    s('due') ? `due ${s('due')}` : ''].filter(Boolean).join(' · ');
      return { primary: s('why_it_matters') || `Aging: ${s('item_id')}`,
               meta, action: s('action') };
    }
    case 'subs_to_watch':
      return { primary: s('crew') ? `${s('crew')}: ${s('concern')}` : s('concern'),
               meta: '', action: s('action_needed') || s('action') };
    case 'sequencing_risks':
      return { primary: s('risk'), meta: s('downstream_impact'),
               action: s('mitigating_action') || s('action') };
    case 'selections_due_this_week': {
      const meta = [s('item_id') ? `Item ${s('item_id')}` : '',
                    s('due') ? `due ${s('due')}` : ''].filter(Boolean).join(' · ');
      return { primary: s('selection') || s('why_it_matters') || 'Selection',
               meta, action: s('cost_of_wrong_choice') || s('action') };
    }
    case 'client_trust_signals':
      return { primary: s('concern') || 'Trust signal', meta: '', action: s('action') };
    default:
      return { primary: s('risk') || s('concern') || 'Flag', meta: '', action: s('action') };
  }
}
/* Infer which job a headsUp entry belongs to. Priority: explicit .job →
   item_id prefix (FISH-004 → Fish) → text heuristic. Falls back to "General"
   if nothing matches (e.g. PM-level observations, cross-job risks). */
function inferHeadsUpJob(entry, pmJobs) {
  if (entry.job) return entry.job;
  const itemId = entry.item_id || '';
  if (itemId) {
    const prefix = itemId.split('-')[0].toUpperCase();
    for (const j of pmJobs) {
      const jp = j.replace(/[^A-Za-z]/g, '').slice(0, 4).toUpperCase();
      const jpPad = jp.length < 4 ? jp + '_'.repeat(4 - jp.length) : jp;
      if (prefix === jp || prefix === jpPad) return j;
    }
  }
  const texts = [entry.concern, entry.risk, entry.why_it_matters, entry.action_needed,
                 entry.mitigating_action, entry.downstream_impact, entry.selection,
                 entry.cost_of_wrong_choice, entry.action, entry.crew].filter(Boolean);
  for (const t of texts) {
    const j = inferJobFromText(t, pmJobs);
    if (j !== 'General') return j;
  }
  return 'General';
}

function renderHeadsUpCard(categoryKey, colorClass, entry) {
  const f = headsUpFields(categoryKey, entry);
  const metaLine   = f.meta   ? `<div class="meta">${escapeHtml(f.meta)}</div>` : '';
  const actionLine = f.action ? `<div class="action"><span>${escapeHtml(f.action)}</span></div>` : '';
  return `<div class="headsup-card ${colorClass}">
    <div class="primary">${escapeHtml(f.primary || '')}</div>
    ${metaLine}
    ${actionLine}
  </div>`;
}

function renderSection2_5_HeadsUp() {
  const hu = DATA.headsUp;
  const head = `<header>
    <div class="eyebrow">Section 3</div>
    <h2>Heads Up — next week</h2>
    <span class="time-tag">2 min</span>
  </header>
  <p class="section-subhead">Forward-looking risks. Review before Monday kickoff.</p>`;
  if (!hu || allHeadsUpEmpty(hu)) {
    return head + `<p class="headsup-empty"><em>No heads-up data. Process this PM's transcript through the pipeline to populate next-week risk analysis.</em></p>`;
  }

  const pmJobs = (DATA.jobs || []).map(j => j.name).filter(Boolean);

  // Group entries by (job, category) so each job's risks stay together.
  const byJob = {};
  HEADSUP_CATEGORIES.forEach(cat => {
    const entries = Array.isArray(hu[cat.key]) ? hu[cat.key] : [];
    entries.forEach(e => {
      const job = inferHeadsUpJob(e, pmJobs);
      byJob[job] = byJob[job] || {};
      (byJob[job][cat.key] = byJob[job][cat.key] || []).push(e);
    });
  });

  const jobOrder = [...pmJobs, 'General'].filter(j => byJob[j]);
  Object.keys(byJob).forEach(k => { if (!jobOrder.includes(k)) jobOrder.push(k); });

  return head + jobOrder.map(job => {
    const jobHu = byJob[job];
    const col = job === 'General' ? 'var(--ink-3)' : jobColor(job);
    const jobEntryCount = Object.values(jobHu).reduce((s, arr) => s + arr.length, 0);
    const categoryBlocks = HEADSUP_CATEGORIES.map(cat => {
      const entries = jobHu[cat.key] || [];
      if (!entries.length) return '';
      const cards = entries.map(e => renderHeadsUpCard(cat.key, cat.color, e)).join('');
      return `<div class="headsup-block">
        <div class="headsup-block-head">${escapeHtml(cat.label)}<span class="count">· ${entries.length}</span></div>
        ${cards}
      </div>`;
    }).join('');
    return `<div class="job-section" data-job="${escapeHtml(job)}">
      <div class="job-section-head">
        <span class="dot" style="background:${col}"></span>
        <h3>${escapeHtml(job)}</h3>
        <span class="job-section-count">${jobEntryCount}</span>
      </div>
      <div class="headsup-grid">${categoryBlocks}</div>
    </div>`;
  }).join('');
}

/* ============================================================
   Sections 3/4/5 — lookAhead
   ============================================================ */
function renderLookaheadSection(weeks, title, hint) {
  const key = `w${weeks}`;
  const la = DATA.lookAhead?.[key] || [];
  const byJob = {};
  la.forEach(e => { (byJob[e.job || 'Unknown'] = byJob[e.job || 'Unknown'] || []).push(e); });
  const sectionNum = { 2: 4, 4: 5, 8: 6 }[weeks];
  const time = { 2: '4 min', 4: '2 min', 8: '2 min' }[weeks];
  const head = `<header>
    <div class="eyebrow">Section ${sectionNum}</div>
    <h2>${escapeHtml(title)}</h2>
    <span class="time-tag">${time}</span>
  </header>
  <p class="section-subhead">${escapeHtml(hint)}</p>`;
  if (la.length === 0) {
    return head + `<p class="muted"><em>No items currently in this horizon.</em></p>`;
  }
  const cards = Object.entries(byJob).map(([job, items]) => {
    const col = jobColor(job);
    return `<div class="lookahead-card">
      <h4><span class="dot" style="background:${col}"></span>${escapeHtml(job)}</h4>
      <ul>${items.map(e => `<li>${escapeHtml(e.text || '')}</li>`).join('')}</ul>
    </div>`;
  }).join('');
  return head + `<div class="lookahead-grid">${cards}</div>`;
}

/* ============================================================
   Section 6 — issues (grouped by JOB, then by type)
   ============================================================ */
function renderSection6_Issues() {
  const issues = DATA.issues || [];
  const head = `<header>
    <div class="eyebrow">Section 7</div>
    <h2>Issues</h2>
    <span class="time-tag">3 min</span>
  </header>`;
  if (!issues.length) {
    return head + `<p class="muted"><em>No issues logged.</em></p>`;
  }
  const pmJobs = (DATA.jobs || []).map(j => j.name).filter(Boolean);

  // Prefer the explicit .job field if present; otherwise heuristic-match
  // against the PM's job names in the issue text.
  const byJob = {};
  issues.forEach(is => {
    const job = is.job || inferJobFromText(is.text || '', pmJobs);
    (byJob[job] = byJob[job] || []).push(is);
  });

  const jobOrder = [...pmJobs, 'General'].filter(j => byJob[j]);
  // Catch any unexpected labels that aren't in pmJobs
  Object.keys(byJob).forEach(k => { if (!jobOrder.includes(k)) jobOrder.push(k); });

  return head + jobOrder.map(job => {
    const list = byJob[job];
    const col = job === 'General' ? 'var(--ink-3)' : jobColor(job);
    const byType = {};
    list.forEach(is => { (byType[is.type || 'Other'] = byType[is.type || 'Other'] || []).push(is); });
    const typeBlocks = Object.entries(byType).map(([type, tlist]) => `
      <div class="issue-group">
        <h4>${escapeHtml(type)} <span class="muted">(${tlist.length})</span></h4>
        ${tlist.map(is => {
          const chronic = /\[CHRONIC\]/i.test(is.text || '');
          const text = (is.text || '').replace(/^\s*\[CHRONIC\]\s*/i, '');
          return `<div class="issue-card ${chronic ? 'chronic' : ''}">
            ${chronic ? '<span class="chronic-label">CHRONIC</span>' : ''}
            <div class="issue-text">${escapeHtml(text)}</div>
          </div>`;
        }).join('')}
      </div>`).join('');
    return `
      <div class="job-section" data-job="${escapeHtml(job)}">
        <div class="job-section-head">
          <span class="dot" style="background:${col}"></span>
          <h3>${escapeHtml(job)}</h3>
          <span class="job-section-count">${list.length}</span>
        </div>
        ${typeBlocks}
      </div>`;
  }).join('');
}

/* ============================================================
   Section 7 — financial
   ============================================================ */
function renderSection7_Financial() {
  const fin = DATA.financial || [];
  // Hide section entirely when no financial data — empty pages waste print real estate.
  if (!fin.length) return '';
  const head = `<header>
    <div class="eyebrow">Section 8</div>
    <h2>Financial</h2>
    <span class="time-tag">2 min</span>
  </header>`;
  const pmJobs = (DATA.jobs || []).map(j => j.name).filter(Boolean);

  // Parse amount + assign job (explicit .job field first, then heuristic).
  let grandTotal = 0;
  let hasAny = false;
  const parsed = fin.map(f => {
    const t = f.text || '';
    const m = t.match(/\$\s*([\d.,]+)\s*([KMkm])?/);
    let val = 0;
    let amt = '—';
    if (m) {
      val = parseFloat(m[1].replace(/,/g, '')) || 0;
      if (/[Kk]/.test(m[2] || '')) val *= 1000;
      else if (/[Mm]/.test(m[2] || '')) val *= 1000000;
      grandTotal += val;
      hasAny = true;
      amt = '$' + Math.round(val).toLocaleString();
    }
    const job = f.job || inferJobFromText(t, pmJobs);
    return { amt, text: t, job, val };
  });

  const byJob = {};
  parsed.forEach(p => { (byJob[p.job] = byJob[p.job] || []).push(p); });
  const jobOrder = [...pmJobs, 'General'].filter(j => byJob[j]);
  Object.keys(byJob).forEach(k => { if (!jobOrder.includes(k)) jobOrder.push(k); });

  const grandTotalHtml = hasAny ? `<div class="financial-total">
    <span class="total-label">Total open exposure</span>
    <span class="total-num">~$${Math.round(grandTotal).toLocaleString()}</span>
  </div>` : '';

  const jobBlocks = jobOrder.map(job => {
    const list = byJob[job];
    const col = job === 'General' ? 'var(--ink-3)' : jobColor(job);
    const jobTotal = list.reduce((s, p) => s + p.val, 0);
    const jobTotalHtml = jobTotal > 0
      ? `<span class="job-section-total">~$${Math.round(jobTotal).toLocaleString()}</span>`
      : '';
    const rows = list.map(p => `
      <li><span class="amt">${escapeHtml(p.amt)}</span><span>${escapeHtml(p.text)}</span></li>
    `).join('');
    return `
      <div class="job-section" data-job="${escapeHtml(job)}">
        <div class="job-section-head">
          <span class="dot" style="background:${col}"></span>
          <h3>${escapeHtml(job)}</h3>
          <span class="job-section-count">${list.length}</span>
          ${jobTotalHtml}
        </div>
        <ul class="financial-list">${rows}</ul>
      </div>`;
  }).join('');

  return head + grandTotalHtml + jobBlocks;
}

/* ============================================================
   Section 8 — General notes (cross-job / non-job observations)
   ============================================================ */
function renderSection8_General() {
  const notes = DATA.generalNotes || [];
  // Hide section entirely when no general notes — empty pages waste print real estate.
  if (!notes.length) return '';
  const head = `<header>
    <div class="eyebrow">Section 9</div>
    <h2>General notes</h2>
    <span class="time-tag">2 min</span>
  </header>
  <p class="section-subhead">Cross-job observations, workflow items, or anything that didn't fit a specific job.</p>`;
  const cards = notes.map(n => {
    const ctx = n.context ? `<div class="note-context">${escapeHtml(n.context)}</div>` : '';
    const chronic = /\[CHRONIC\]/i.test(n.text || '');
    const text = (n.text || '').replace(/^\s*\[CHRONIC\]\s*/i, '');
    return `<div class="general-note-card ${chronic ? 'chronic' : ''}">
      ${chronic ? '<span class="chronic-label">CHRONIC</span>' : ''}
      ${ctx}
      <div class="note-text">${escapeHtml(text)}</div>
    </div>`;
  }).join('');
  return head + `<div class="general-notes">${cards}</div>`;
}

/* ============================================================
   Appendix — reconciliation, completed, dismissed
   ============================================================ */
function renderReconciliation() {
  const recon = DATA.reconciliation || [];
  if (!recon.length) return '<p class="muted"><em>No reconciliation entries.</em></p>';
  const ORDER = ['contradiction', 'gap', 'auto_transition', 'silent_activity'];
  const LABEL = { contradiction: 'Contradictions', gap: 'Gaps', auto_transition: 'Auto-transitions', silent_activity: 'Silent activity' };
  const grouped = {};
  recon.forEach(r => { (grouped[r.type] = grouped[r.type] || []).push(r); });
  const keys = [...ORDER.filter(k => grouped[k]), ...Object.keys(grouped).filter(k => !ORDER.includes(k))];
  return keys.map(k => `
    <div class="recon-group">
      <h4>${escapeHtml(LABEL[k] || k)} (${grouped[k].length})</h4>
      ${grouped[k].map(e => `<div class="recon-card ${escapeHtml(k)}" data-item-id="${escapeHtml(e.item_id || '')}">
        ${e.log_date ? `<span class="recon-date">${escapeHtml(e.log_date)}</span>` : ''}
        ${e.item_id ? `<span class="recon-itemid">${escapeHtml(e.item_id)}</span>` : ''}
        <span class="recon-text">${escapeHtml(e.text || '')}</span>
      </div>`).join('')}
    </div>
  `).join('');
}

function renderAppendixTable(whichStatus) {
  const items = (DATA.items || []).filter(i => ns(i.status) === whichStatus);
  if (!items.length) return '<p class="muted"><em>None.</em></p>';
  items.sort((a, b) => (b.closed_date || b.opened || '').localeCompare(a.closed_date || a.opened || ''));
  return `<table class="appendix-table"><tbody>${items.map(i => `
    <tr>
      <td class="appx-job" style="--job-color:${jobColor(i.job || '')};color:${jobColor(i.job || '')}">${escapeHtml(i.job || '—')}</td>
      <td class="appx-id">${escapeHtml(i.id || '')}</td>
      <td>${escapeHtml(i.action || '')}</td>
      <td>${escapeHtml(i.owner || '')}</td>
      <td class="appx-when">${whichStatus === 'DISMISSED' ? 'dismissed' : 'closed'} ${escapeHtml(formatDate(i.closed_date))}</td>
    </tr>
  `).join('')}</tbody></table>`;
}

/* ============================================================
   Actions — status / dismiss / edit / scroll-to-recon
   ============================================================ */
function updateStatus(id, s) {
  const item = DATA.items.find(i => i.id === id);
  if (!item) return;
  item.status = s;
  if (CLOSED.has(s) && !item.closed_date) item.closed_date = todayStr();
  render();
}
function dismissItem(id) {
  const item = DATA.items.find(i => i.id === id);
  if (!item) return;
  if (!confirm(`Dismiss ${id}? Marks it erroneously placed, NOT complete.`)) return;
  item.status = 'DISMISSED';
  item.closed_date = todayStr();
  render();
}
function openEdit(id) {
  const item = DATA.items.find(i => i.id === id);
  if (!item) return;
  openModal(`Edit ${id}`, `
    <form id="editForm">
      <div style="margin-bottom:10px;"><label class="eyebrow">Action</label><br>
        <textarea name="action" rows="3" style="width:100%;">${escapeHtml(item.action || '')}</textarea></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div><label class="eyebrow">Owner</label><br><input name="owner" value="${escapeHtml(item.owner || '')}" style="width:100%;"></div>
        <div><label class="eyebrow">Due</label><br><input type="date" name="due" value="${escapeHtml(item.due || '')}" style="width:100%;"></div>
        <div><label class="eyebrow">Priority</label><br>
          <select name="priority" style="width:100%;">
            ${['URGENT','HIGH','NORMAL'].map(p => `<option ${p === item.priority ? 'selected' : ''}>${p}</option>`).join('')}
          </select>
        </div>
        <div><label class="eyebrow">Type</label><br>
          <select name="type" style="width:100%;">
            ${TYPE_LIST.map(t => `<option ${t === (item.type || 'FOLLOWUP') ? 'selected' : ''}>${t}</option>`).join('')}
          </select>
        </div>
      </div>
      <div style="margin-bottom:10px;"><label class="eyebrow">Update note</label><br>
        <textarea name="update" rows="2" style="width:100%;">${escapeHtml(item.update || '')}</textarea></div>
    </form>
    <p class="hint">Changes are session-only — the file on disk is the source of truth.</p>
  `, [
    { label: 'Cancel', cb: closeModal },
    { label: 'Save', primary: true, cb: () => {
      const fd = new FormData(document.getElementById('editForm'));
      item.action = fd.get('action'); item.owner = fd.get('owner');
      item.due = fd.get('due'); item.priority = fd.get('priority');
      item.type = fd.get('type'); item.update = fd.get('update');
      closeModal(); render();
    }},
  ]);
}
function scrollToRecon(id) {
  const appendix = [...document.querySelectorAll('details.collapsible summary')].find(s => /Reconciliation/i.test(s.textContent));
  if (appendix) {
    appendix.parentElement.open = true;
    setTimeout(() => {
      const card = [...document.querySelectorAll('.recon-card')].find(c => c.dataset.itemId === id);
      if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        card.style.background = '#fef9c3';
        setTimeout(() => { card.style.background = ''; }, 1400);
      }
    }, 60);
  }
}

/* ============================================================
   Modal helpers
   ============================================================ */
function openModal(title, bodyHtml, buttons) {
  const root = document.getElementById('modalRoot');
  root.innerHTML = `
    <div class="modal-backdrop">
      <div class="modal">
        <h3>${escapeHtml(title)}</h3>
        <div class="modal-body">${bodyHtml}</div>
        <div class="modal-actions" id="modalActions"></div>
      </div>
    </div>`;
  const actions = document.getElementById('modalActions');
  buttons.forEach(b => {
    const btn = document.createElement('button');
    btn.textContent = b.label;
    if (b.primary) btn.classList.add('accent');
    btn.addEventListener('click', b.cb);
    actions.appendChild(btn);
  });
}
function closeModal() { document.getElementById('modalRoot').innerHTML = ''; }

/* ============================================================
   Upload transcripts (drag-drop + /upload server integration)
   ============================================================ */
function openUploadModal() {
  document.getElementById('uploadModal').hidden = false;
}
function closeUploadModal() {
  const m = document.getElementById('uploadModal');
  m.hidden = true;
  document.getElementById('uploadList').innerHTML = '';
  document.getElementById('uploadInput').value = '';
  document.getElementById('uploadProcessBtn').hidden = true;
}

async function uploadFiles(files) {
  const list = document.getElementById('uploadList');
  const processBtn = document.getElementById('uploadProcessBtn');
  if (!files || !files.length) return;

  // Immediate pending feedback so the user sees the files were picked up
  list.innerHTML = Array.from(files).map(f =>
    `<div class="file-row"><span class="name">${escapeHtml(f.name)}</span><span>uploading…</span></div>`
  ).join('');

  const fd = new FormData();
  for (const f of files) fd.append('files', f, f.name);

  try {
    const res = await fetch('/upload', { method: 'POST', body: fd });
    const data = await res.json();
    const rows = (data.results || []).map(r => r.ok
      ? `<div class="file-row ok"><span class="name">${escapeHtml(r.name)}</span><span>uploaded · ${Math.round((r.size||0)/1024)} KB</span></div>`
      : `<div class="file-row err"><span class="name">${escapeHtml(r.name)}</span><span>${escapeHtml(r.error || 'error')}</span></div>`
    ).join('');
    list.innerHTML = rows + (data.inbox_pending
      ? `<div class="file-row"><span class="name">inbox pending</span><span>${data.inbox_pending} file(s)</span></div>`
      : '');
    const anyOk = (data.results || []).some(r => r.ok);
    processBtn.hidden = !anyOk;
  } catch (err) {
    list.innerHTML = `<div class="file-row err"><span class="name">upload failed</span><span>${escapeHtml(err.message || String(err))}</span></div>`;
  }
}

async function uploadThenProcess() {
  closeUploadModal();
  await refreshPipeline(false);
}

function initUploadHandlers() {
  const drop = document.getElementById('uploadDrop');
  const input = document.getElementById('uploadInput');
  const overlay = document.getElementById('dropOverlay');
  if (!drop || !input) return;

  // Click anywhere in the drop box → browse
  drop.addEventListener('click', () => input.click());
  drop.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); input.click(); }
  });

  // Browse-picker change
  input.addEventListener('change', (e) => {
    if (e.target.files && e.target.files.length) uploadFiles(e.target.files);
  });

  // Drop zone drag visuals
  ['dragenter', 'dragover'].forEach(ev => {
    drop.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); drop.classList.add('drag-over'); });
  });
  ['dragleave', 'drop'].forEach(ev => {
    drop.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); drop.classList.remove('drag-over'); });
  });
  drop.addEventListener('drop', (e) => {
    if (e.dataTransfer && e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });

  // Window-wide drag target — any file dragged over the page triggers the overlay
  let dragCounter = 0;
  window.addEventListener('dragenter', (e) => {
    if (!e.dataTransfer || !Array.from(e.dataTransfer.types || []).includes('Files')) return;
    dragCounter++;
    if (overlay) overlay.hidden = false;
  });
  window.addEventListener('dragover', (e) => {
    // Required to make drop work; prevents default browser "open file" behavior
    if (e.dataTransfer && Array.from(e.dataTransfer.types || []).includes('Files')) {
      e.preventDefault();
    }
  });
  window.addEventListener('dragleave', (e) => {
    dragCounter = Math.max(0, dragCounter - 1);
    if (dragCounter === 0 && overlay) overlay.hidden = true;
  });
  window.addEventListener('drop', (e) => {
    dragCounter = 0;
    if (overlay) overlay.hidden = true;
    if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
    e.preventDefault();
    openUploadModal();
    uploadFiles(e.dataTransfer.files);
  });
}

/* ============================================================
   Refresh pipeline (server.py integration)
   ============================================================ */
const REFRESH_POLL_MS = 2000;
let _pollTimer = null;
function isServed() { return location.protocol === 'http:' || location.protocol === 'https:'; }

async function refreshPipeline(force) {
  if (!isServed()) {
    alert('Double-click start-monday.bat to use the refresh button.');
    return;
  }
  const btn = document.getElementById('refreshBtn');
  btn.disabled = true; btn.textContent = 'Working…';
  openModal(force ? 'Force refresh' : 'Refreshing', '<div class="spinner"></div><div class="modal-body" id="refreshBody">Starting pipeline…</div>',
    []);
  try {
    const r = await fetch('/refresh' + (force ? '?force=1' : ''), { method: 'POST' });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(j.reason || ('HTTP ' + r.status));
    }
    pollStatus();
  } catch (e) { finishRefresh({ errors: [e.message || String(e)] }); }
}
function pollStatus() {
  if (_pollTimer) clearTimeout(_pollTimer);
  const tick = async () => {
    try {
      const r = await fetch('/status', { cache: 'no-cache' });
      const s = await r.json();
      applyStatus(s);
      if (['done','error','idle'].includes(s.phase) && s.finished_at) {
        finishRefresh(s); return;
      }
      _pollTimer = setTimeout(tick, REFRESH_POLL_MS);
    } catch (e) {
      _pollTimer = setTimeout(tick, REFRESH_POLL_MS * 2);
    }
  };
  tick();
}
function applyStatus(s) {
  const badge = document.getElementById('refreshStatus');
  if (badge) {
    badge.dataset.phase = s.captcha_needed ? 'captcha' : (s.phase || 'idle');
    badge.textContent = s.captcha_needed ? 'CAPTCHA' : (s.phase || 'idle');
  }
  const body = document.getElementById('refreshBody');
  if (body) body.textContent = s.progress_message || ('Phase: ' + s.phase);
  if (s.captcha_needed) {
    const bb = document.getElementById('refreshBody');
    if (bb) bb.textContent = 'Buildertrend login required. A browser window opened with the CAPTCHA — solve it, then return here. The scraper will continue automatically.';
  }
}
function finishRefresh(s) {
  if (_pollTimer) { clearTimeout(_pollTimer); _pollTimer = null; }
  const btn = document.getElementById('refreshBtn');
  btn.disabled = false; btn.textContent = 'Refresh everything';
  const errs = s.errors || [];
  if (errs.length) {
    openModal('Refresh finished with errors', `<div class="modal-errors">${errs.map(escapeHtml).join('\n')}</div><div class="modal-body">Actions: ${(s.actions_taken || []).join(' · ') || 'none'}</div>`,
      [{ label: 'Close', cb: closeModal }]);
    const badge = document.getElementById('refreshStatus');
    if (badge) { badge.dataset.phase = 'error'; badge.textContent = 'error'; }
    return;
  }
  openModal('Done', `<div class="modal-body">Actions: ${(s.actions_taken || []).join(' · ') || 'none'}${s.duration_sec ? ' (' + s.duration_sec + 's)' : ''}. Reloading…</div>`, []);
  const badge = document.getElementById('refreshStatus');
  if (badge) { badge.dataset.phase = 'done'; badge.textContent = 'done'; }
  if (s.last_refresh) {
    const last = document.getElementById('refreshLast');
    if (last) last.textContent = 'Last refresh: ' + new Date(s.last_refresh).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
  setTimeout(() => { window.location.reload(); }, 1000);
}

(async () => {
  if (!isServed()) return;
  try {
    const r = await fetch('/status', { cache: 'no-cache' });
    const s = await r.json();
    applyStatus(s);
    if (s.last_refresh) {
      const last = document.getElementById('refreshLast');
      if (last) last.textContent = 'Last refresh: ' + new Date(s.last_refresh).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    if (['scraping','processing','regenerating','starting'].includes(s.phase)) pollStatus();
  } catch (e) { /* no server */ }
})();

/* ============================================================
   Chat assistant — Q&A over binders + jobs + subs via /chat
   ============================================================ */
let CHAT_HISTORY = [];

function initChat() {
  const fab = document.getElementById('chatFab');
  const panel = document.getElementById('chatPanel');
  const closeBtn = document.getElementById('chatClose');
  const clearBtn = document.getElementById('chatClearBtn');
  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');
  const messages = document.getElementById('chatMessages');

  if (!fab || !panel) return;

  // Restore prior session
  try {
    const saved = JSON.parse(localStorage.getItem('rossbuilt_chat_history') || '[]');
    CHAT_HISTORY = Array.isArray(saved) ? saved : [];
  } catch (e) { CHAT_HISTORY = []; }
  renderChatMessages();

  fab.addEventListener('click', () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden) input.focus();
  });
  closeBtn.addEventListener('click', () => { panel.hidden = true; });
  clearBtn.addEventListener('click', () => {
    if (!confirm('Clear conversation history?')) return;
    CHAT_HISTORY = [];
    persistChatHistory();
    renderChatMessages();
  });

  // Submit on Enter (Shift+Enter inserts newline)
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = '';

    CHAT_HISTORY.push({ role: 'user', content: q });
    persistChatHistory();
    renderChatMessages();

    const placeholder = appendChatMsg('assistant thinking', '…thinking…');
    const sendBtn = document.getElementById('chatSend');
    if (sendBtn) sendBtn.disabled = true;

    try {
      const res = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q,
          history: CHAT_HISTORY.slice(-12, -1), // exclude the just-pushed question
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (data.answer) {
        CHAT_HISTORY.push({ role: 'assistant', content: data.answer });
        persistChatHistory();
        renderChatMessages();
      } else {
        placeholder.classList.remove('thinking');
        placeholder.classList.add('error');
        placeholder.textContent = `Error: ${data.error || `HTTP ${res.status}`}`;
      }
    } catch (err) {
      placeholder.classList.remove('thinking');
      placeholder.classList.add('error');
      placeholder.textContent = `Network error: ${err.message || err}`;
    } finally {
      if (sendBtn) sendBtn.disabled = false;
    }
  });
}

function appendChatMsg(klass, text) {
  const messages = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = `chat-msg ${klass}`;
  div.textContent = text;
  messages.appendChild(div);
  messages.scrollTop = messages.scrollHeight;
  return div;
}

function renderChatMessages() {
  const messages = document.getElementById('chatMessages');
  if (!messages) return;
  if (CHAT_HISTORY.length === 0) {
    messages.innerHTML = `<div class="chat-msg system">
      <strong>Ask anything about your data.</strong> I have full context on:
      <ul>
        <li>Per-PM binders — action items, lookahead, issues, financial</li>
        <li>Per-job daily-log analytics — workforce, deliveries, inspections, phase durations</li>
        <li>Subcontractor performance — lifetime + recent activity, absences, reliability, categories</li>
      </ul>
      Try: <em>"Which subs are spread across 3+ jobs?"</em> · <em>"How long did Plumbing rough take on Drummond vs Pou?"</em>
    </div>`;
    return;
  }
  messages.innerHTML = CHAT_HISTORY.map(m =>
    `<div class="chat-msg ${m.role}">${escapeHtml(m.content)}</div>`
  ).join('');
  messages.scrollTop = messages.scrollHeight;
}

function persistChatHistory() {
  try {
    localStorage.setItem('rossbuilt_chat_history', JSON.stringify(CHAT_HISTORY.slice(-30)));
  } catch (e) {}
}

/* Kick things off */
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  activateTab(CURRENT_PM);
  initUploadHandlers();
  initChat();
});
"""


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ross Built · Monday Binders</title>
<meta name="viewport" content="width=1280">
<style>
{CSS}
</style>
</head>
<body data-generated="{GENERATED_AT}">

<header class="app-header">
  <div class="app-header-inner">
    <div class="logo"><em>Ross Built</em> · Monday Binders</div>
    <nav class="tabs" id="tabs" role="tablist"></nav>
    <span class="refresh-status" id="refreshStatus" data-phase="idle">idle</span>
    <span class="refresh-last" id="refreshLast">Last refresh: —</span>
    <button class="ghost small" id="uploadBtn" onclick="openUploadModal()" title="Drop transcripts to add to inbox">📥 Upload</button>
    <button class="accent" id="refreshBtn" onclick="refreshPipeline(false)">Refresh everything</button>
    <button class="ghost small" onclick="refreshPipeline(true)" title="Bypass 6-hour freshness check">Force scrape</button>
  </div>
</header>

<main>
  <div class="pm-view" id="pmView"></div>
</main>

<footer class="app-footer">
  <span>Ross Built · Monday binder · {GENERATED_LINE}</span>
  <span>{DASHBOARD_LINE}</span>
</footer>

<!-- Upload modal — hidden until opened by user or window-wide file drop -->
<div class="modal-backdrop" id="uploadModal" hidden onclick="if(event.target===this)closeUploadModal()">
  <div class="modal upload-modal" role="dialog" aria-labelledby="uploadTitle" aria-modal="true">
    <div class="modal-title" id="uploadTitle">Upload transcripts</div>
    <p class="upload-hint">Drop .txt files from Plaud (or any source) into the box below. Files are saved to <code>transcripts/inbox/</code> and you'll pick when to run them through Opus.</p>
    <div class="upload-drop" id="uploadDrop" tabindex="0" role="button" aria-label="Click to browse files or drop here">
      <div class="upload-drop-icon">📥</div>
      <div class="upload-drop-main">Drop <strong>.txt</strong> files here</div>
      <div class="upload-drop-sub">or <button type="button" class="link-btn" onclick="document.getElementById('uploadInput').click()">click to browse</button></div>
      <input type="file" id="uploadInput" multiple accept=".txt,text/plain" hidden>
    </div>
    <div class="upload-list" id="uploadList"></div>
    <div class="modal-actions">
      <button type="button" class="ghost small" onclick="closeUploadModal()">Close</button>
      <button type="button" class="accent" id="uploadProcessBtn" onclick="uploadThenProcess()" hidden>Process now</button>
    </div>
  </div>
</div>

<!-- Window-wide drop overlay — appears only while the user is dragging files anywhere over the page -->
<div class="drop-overlay" id="dropOverlay" hidden>
  <div class="drop-overlay-inner">
    <div class="drop-overlay-icon">📥</div>
    <div class="drop-overlay-title">Drop transcripts to upload</div>
    <div class="drop-overlay-sub">.txt files only · saved to inbox/</div>
  </div>
</div>

<div id="modalRoot"></div>

<!-- Phase 17 — Phase Glossary overlay. Single source of truth shared by
     the Subs and Jobs tabs. Opens via openGlossary() from either tab.
     Closes on backdrop click, the × button, or Escape. -->
<div class="glossary-overlay" id="glossaryOverlay" onclick="if(event.target===this)closeGlossary()">
  <div class="glossary-panel" role="dialog" aria-labelledby="glossaryTitle" aria-modal="true">
    <button type="button" class="gloss-close" onclick="closeGlossary()" aria-label="Close">×</button>
    <h2 id="glossaryTitle">Phase Glossary</h2>
    <div class="glossary-sub">Buildertrend schedule phases · Jake-confirmed for Ross Built coastal builds</div>
    <input type="search" class="glossary-search" placeholder="Filter phases…" oninput="filterGlossary(this.value)">
    <div id="glossaryBody">
      <h3>Concrete / Foundation</h3>
      <dl>
        <dt>Pilings</dt><dd>Driven concrete pilings for elevated coastal foundations</dd>
        <dt>Foundation</dt><dd>Footings, grade beams, slab prep before stem wall</dd>
        <dt>Stem Wall</dt><dd>CMU stem wall lay-up between foundation and first floor</dd>
        <dt>Slab</dt><dd>First-floor concrete slab pour</dd>
        <dt>CIP Beams - 1L</dt><dd>Cast-in-place concrete beams at first level</dd>
        <dt>CIP Beams - 2L</dt><dd>Cast-in-place concrete beams at second level</dd>
        <dt>Masonry Walls - 1L</dt><dd>CMU block walls at level 1</dd>
        <dt>Masonry Walls - 2L</dt><dd>CMU block walls at level 2</dd>
        <dt>Masonry Walls - 3L</dt><dd>CMU block walls at level 3</dd>
      </dl>
      <h3>Plumbing / Gas</h3>
      <dl>
        <dt>Under-Slab</dt><dd>Plumbing runs before slab pour (drain lines, sleeves)</dd>
        <dt>Plumbing/Gas Rough In</dt><dd>In-wall plumbing pre-drywall (hot/cold lines, drains, gas lines)</dd>
        <dt>Plumbing/Gas Trim Out</dt><dd>Final fixture install post-finishes (toilets, sinks, faucets, gas appliances)</dd>
      </dl>
      <h3>Electrical</h3>
      <dl>
        <dt>Electrical Rough In</dt><dd>All wire pulls and box install pre-drywall</dd>
        <dt>Electrical Trim Out</dt><dd>Device install post-paint (switches, outlets, fixtures, devices)</dd>
      </dl>
      <h3>Low Voltage</h3>
      <dl>
        <dt>Low Voltage Rough In</dt><dd>Wire pulls for AV, networking, security, alarm pre-drywall</dd>
        <dt>Low Voltage Trim Out</dt><dd>Device install post-paint (panels, screens, sensors, mounts)</dd>
      </dl>
      <h3>HVAC</h3>
      <dl>
        <dt>HVAC Rough In</dt><dd>Duct install, line sets, equipment placement pre-drywall</dd>
        <dt>HVAC Trim Out</dt><dd>Final equipment hookup, register install, commissioning, startup</dd>
      </dl>
      <h3>Envelope</h3>
      <dl>
        <dt>Framing</dt><dd>Wood and steel framing</dd>
        <dt>Roof Trusses</dt><dd>Truss set</dd>
        <dt>Roofing</dt><dd>Roof system install (membrane, tile, shingles)</dd>
        <dt>Siding</dt><dd>Exterior siding install</dd>
        <dt>Exterior Windows/Doors</dt><dd>Exterior windows and doors install</dd>
        <dt>Stucco</dt><dd>Exterior stucco / plaster</dd>
        <dt>Insulation</dt><dd>Wall and ceiling insulation</dd>
      </dl>
      <h3>Interior Finishes</h3>
      <dl>
        <dt>Drywall</dt><dd>Hang, tape, finish, sand</dd>
        <dt>Interior Painting</dt><dd>Wall and ceiling paint (BT does not split prep/paint/stain)</dd>
        <dt>Interior Tile</dt><dd>Floor and wall tile setting</dd>
        <dt>Wood Flooring</dt><dd>Hardwood install and finish</dd>
        <dt>Interior Trim</dt><dd>Baseboards, casings, crown, jam</dd>
        <dt>Interior Stairs</dt><dd>Treads, risers, handrails</dd>
        <dt>Cabinetry</dt><dd>Cabinet install</dd>
        <dt>Countertops</dt><dd>Stone / quartz install</dd>
        <dt>Appliances</dt><dd>Appliance install and hookup</dd>
      </dl>
      <h3>Site / Exterior</h3>
      <dl>
        <dt>Site Work</dt><dd>Excavation, grading, dirt work</dd>
        <dt>Driveway</dt><dd>Concrete or paver driveway install</dd>
        <dt>Exterior Pavers</dt><dd>Patio, walkway, pool deck pavers</dd>
        <dt>Exterior Decking</dt><dd>Wood / composite deck install</dd>
        <dt>Exterior Stairs</dt><dd>Outdoor stair construction</dd>
        <dt>Exterior Painting</dt><dd>Exterior paint and stain</dd>
        <dt>Exterior Ceilings</dt><dd>Exterior soffit and porch ceilings</dd>
        <dt>Pool</dt><dd>Pool shell, finish, equipment</dd>
        <dt>Landscaping</dt><dd>Plants, irrigation, sod</dd>
        <dt>Fencing</dt><dd>Fence install</dd>
      </dl>
      <h3>Closeout</h3>
      <dl>
        <dt>Final Touches</dt><dd>Pre-CO punch and corrections</dd>
        <dt>Final Punch Out</dt><dd>Post-CO punch and warranty</dd>
        <dt>Obtain C.O.</dt><dd>Certificate of Occupancy submission</dd>
      </dl>
      <h3>Pre-Construction (Cross-Trade)</h3>
      <dl>
        <dt>Plan Review</dt><dd>Permit and plan review activity</dd>
        <dt>Pre-Construction</dt><dd>Pre-build coordination</dd>
        <dt>Estimating</dt><dd>Cost estimation</dd>
        <dt>Finalize Contract</dt><dd>Contract execution</dd>
      </dl>
      <div class="gloss-note">
        <h4>Note on day counts</h4>
        <p>All "Xd" values refer to distinct calendar dates with a logged BT daily log entry. Weekends and no-log days are excluded. Per-job breakdown shows days the sub worked that phase on a specific job. "calendar span" shows time elapsed between first and last log on that job (includes weekends and idle days). Cross-sub benchmarks (median, p25, p75) are computed across all (sub × job × phase) triples in the data. Sample sizes &lt;3 are suppressed to avoid statistical noise.</p>
        <h4>Note on phase status</h4>
        <p><strong>Complete</strong> — substantial work burst ended (≥3 active days, ≥35% density). <strong>Ongoing</strong> — substantial burst still active. <strong>Intermittent</strong> — sparse one-off visits, below burst thresholds. <strong>Multi-burst</strong> — 3+ distinct bursts, ≥7 total active days (stop-and-start work).</p>
        <h4>Note on residual days</h4>
        <p>"On-site (no matching phase tag)" = days the sub was on site but Buildertrend's <code>parent_group_activities</code> field was not populated by the supervisor. Reflects BT data quality, not missed work. For Internal Crew (Ross Built Crew), residual is "Multi-sub days (not solo-attributable)" — phase mix unknowable when other subs are also on site.</p>
      </div>
    </div>
  </div>
</div>
<script>
function openGlossary() {
  const el = document.getElementById('glossaryOverlay');
  if (el) el.classList.add('open');
}
function closeGlossary() {
  const el = document.getElementById('glossaryOverlay');
  if (el) el.classList.remove('open');
  // Reset filter when closing so reopening shows everything
  const search = document.querySelector('#glossaryOverlay .glossary-search');
  if (search) search.value = '';
  filterGlossary('');
}
function filterGlossary(q) {
  const body = document.getElementById('glossaryBody');
  if (!body) return;
  const needle = (q || '').trim().toLowerCase();
  body.querySelectorAll('dl').forEach(dl => {
    let anyMatch = false;
    const dts = dl.querySelectorAll('dt');
    dts.forEach(dt => {
      const dd = dt.nextElementSibling;
      const text = (dt.textContent + ' ' + (dd ? dd.textContent : '')).toLowerCase();
      const match = !needle || text.includes(needle);
      dt.style.display = match ? '' : 'none';
      if (dd) dd.style.display = match ? '' : 'none';
      if (match) anyMatch = true;
    });
    // Hide the section header (h3 sibling) if all dts hidden
    const h3 = dl.previousElementSibling;
    if (h3 && h3.tagName === 'H3') h3.style.display = anyMatch ? '' : 'none';
    dl.style.display = anyMatch ? '' : 'none';
  });
}
// Close glossary on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    const el = document.getElementById('glossaryOverlay');
    if (el && el.classList.contains('open')) closeGlossary();
  }
});
</script>

<!-- Chat assistant — searches binders + analytics via Claude API -->
<button class="chat-fab" id="chatFab" aria-label="Open chat assistant" title="Ask anything about jobs, subs, schedules">💬</button>
<aside class="chat-panel" id="chatPanel" hidden role="dialog" aria-label="Chat assistant">
  <header class="chat-head">
    <span class="chat-title">Ask anything · Ross Built ops</span>
    <div class="chat-head-actions">
      <button class="chat-clear-btn" id="chatClearBtn" title="Clear conversation">Clear</button>
      <button class="chat-close" id="chatClose" aria-label="Close">×</button>
    </div>
  </header>
  <div class="chat-messages" id="chatMessages"></div>
  <form class="chat-form" id="chatForm">
    <textarea id="chatInput" placeholder="Which subs missed days last month? Which jobs are on the Plumbing critical path? How many deliveries hit Krauss in March?" rows="2"></textarea>
    <button type="submit" id="chatSend" class="accent">Send</button>
  </form>
</aside>

<script>
{JS}
</script>

</body>
</html>
"""


# PM_JOBS, JOB_NAME_MAP, JOB_TO_PM, DAILY_LOGS_PATH imported from constants.py.


def _parse_log_date(date_str: str, context: date | None = None) -> date | None:
    """BT log dates: 'Wed, Apr 22, 2026' (with year) or 'Wed, Apr 22' (current year inferred)."""
    if not date_str:
        return None
    s = date_str.strip()
    for fmt in ("%a, %b %d, %Y", "%a, %d %b %Y", "%b %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    ctx = context or date.today()
    for fmt in ("%a, %b %d", "%b %d", "%a, %d %b", "%d %b"):
        try:
            d = datetime.strptime(s, fmt).date().replace(year=ctx.year)
            if d > ctx:
                d = d.replace(year=ctx.year - 1)
            return d
        except ValueError:
            continue
    return None


def _safe_int(v):
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        try:
            return int(float(v))
        except (ValueError, TypeError):
            return None


def _is_meaningful(s) -> bool:
    if not s:
        return False
    t = s.strip().lower()
    return t not in ("", "none", "n/a", "na", "-", "—")


# BT form labels that leak through the legacy crews-string parser. Filter out.
BT_FORM_LABELS = {
    "on site", "daily workforce", "absent crew(s)", "absent crews", "none",
    "parent group activity", "parent group activities",
    "inspections?", "inspections", "deliveries?", "deliveries",
    "read more", "read less", "n/a", "na",
}

# BT template / instruction phrases that leak into crews_clean. Real sub names
# never contain these — used as a soft veto.
_TEMPLATE_PHRASES = (
    "summary", "list crews", "notable discussions", "scheduled but did not",
    "what each crew", "list of", "etc.)", "list the", "owner meetings",
    "list crews scheduled", "jobsite activity",
)


SUB_CATEGORY_PATTERNS = [
    ("Concrete",        r"\bconcrete\b|\bcip\b|\bmasonry\b|\bgrade services?\b|\bfoundation\b|\bpiling\b"),
    ("Framing",         r"\bframing\b|\btruss\b|\bcarpentry\b|carpenter|\bframer\b"),
    ("Plumbing",        r"\bplumb|\bgas\s|\bwater\s|\bsewer\b"),
    ("Electrical",      r"\belectric|\belectrician\b"),
    ("HVAC",            r"\bhvac\b|\bclimatic\b|conditioning|\bhead air\b|\bduct\b|\bcooling\b"),
    ("Roofing",         r"\broof"),
    ("Stucco/Plaster",  r"\bstucco\b|\bplaster"),
    ("Drywall",         r"\bdrywall\b|\bsheetrock\b"),
    ("Tile/Floor",      r"\btile\b|\bflooring\b|\bfloor\b|\bhardwood\b|\bcarpet\b"),
    ("Paint",           r"\bpaint"),
    ("Pool/Spa",        r"\bpool\b|\bspa\b"),
    ("Insulation",      r"\binsulation\b|\bspray foam\b|\bfoam\s+(?:insul|spray)"),
    ("Waterproofing",   r"\bwaterproof|\bcoatrite\b|\bsealant|stop[\s-]?leak\b|\bweather[\s-]?(?:proof|seal)"),
    ("Windows/Doors",   r"\bwindow|\bdoor\b|\bglass\b|\bglazing\b"),
    ("Cabinetry",       r"\bcabinet|\bmillwork\b|\bcucine\b"),
    ("Trim/Finish",     r"\btrim\b|finish\s+carp"),
    ("Site/Excavation", r"\bsite\s*work\b|\bexcavat|\bdirt\b|\blot\b|\bclearing\b|\bdrilling\b"),
    ("Landscape",       r"\blandscap|\bsod\b|\birrigat|\bnursery\b"),
    ("Engineering/Insp",r"\bengineer|\binspect|\btruss\s*design"),
    ("Appliances",      r"\bappliance|fuse\s+specialty"),
    ("Audio/Video",     r"\baudio\b|\bav\b|\blow voltage\b|\bsmart"),
    ("Interior Design", r"\binterior design|\bdesign|\bdecor"),
    ("Fence/Gate",      r"\bfence\b|\bgate\b"),
    ("Pavers/Hardscape",r"\bpaver|\bhardscape\b"),
    ("Stone/Counters",  r"\bcounter|\bgranite\b|\bquartz\b|\bstone\b|\bvolcano\b|\bmarble\b"),
    ("Siding",          r"\bsiding\b|\bsoffit\b|\bfascia\b|\bcladding\b"),
    ("Carpentry/Stairs",r"\bstair|\bbalust|\brailing\b|\bhandrail\b"),
    ("Metal/Welding",   r"\bweld|\bmetal\s+fab|\bironwork\b|\bsteel\s+(?:fab|work|erect)"),
    ("Materials/Supplier", r"\blumber\b|\bbuilding\s+products\b|\bsupply\s+(?:co|company|inc|llc)|\bsupplier\b|\bhardware\b"),
    ("Cleaning",        r"\bcleaning\b|\bjanitorial\b"),
    ("Elevator",        r"\belevator\b|\blift\s+(?:co|service)"),
    ("Solar/Energy",    r"\bsolar\b|\bphotovoltaic|\bpv\b|\benergy\s+solutions"),
    ("Internal Crew",   r"^ross built"),
]
_SUB_CATEGORY_RX = [(c, re.compile(p, re.I)) for (c, p) in SUB_CATEGORY_PATTERNS]


# Phase 14 audit — when a sub's name doesn't match any regex (returns
# "Other Trade"), fall back to the dominant parent_group_activity tag from
# their daily-log history. Activity → category mapping below; thresholds
# enforced in classify_sub: ≥40 % of work AND ≥10 lifetime days.
#
# Phase 16 expansion: this same mapping now also drives the trade-family
# filter in compute_subs_performance_data — only credit a sub for activity
# tags whose category matches the sub's own category. Tags mapped to None
# are cross-trade (close-out, admin) and don't credit any classified sub;
# they still count for Other Trade / Internal Crew via solo-day fallback.
ACTIVITY_TO_CATEGORY: dict[str, str | None] = {
    "Interior Trim": "Trim/Finish",
    "Interior Tile": "Tile/Floor",
    "Wood Flooring": "Tile/Floor",
    "Drywall": "Drywall",
    "Exterior Windows/Doors": "Windows/Doors",
    "Siding": "Siding",
    "Stucco": "Stucco/Plaster",
    "Cabinetry": "Cabinetry",
    "Pool": "Pool/Spa",
    "Roofing": "Roofing",
    "Roof Trusses": "Framing",
    "Framing": "Framing",
    "Foundation": "Concrete",
    "Pilings": "Concrete",
    "Plumbing/Gas Rough In": "Plumbing",
    "Plumbing/Gas Trim Out": "Plumbing",
    "Under-Slab":            "Plumbing",
    "Electrical Rough In": "Electrical",
    "Electrical Trim Out": "Electrical",
    "HVAC Rough In": "HVAC",
    "HVAC Trim Out": "HVAC",
    "Low Voltage Rough In": "Audio/Video",
    "Low Voltage Trim Out": "Audio/Video",
    "Insulation": "Insulation",
    "Site Work": "Site/Excavation",
    "Landscaping": "Landscape",
    "Exterior Painting": "Paint",
    "Interior Painting": "Paint",
    # Phase 14 follow-up — additional activity tags surfaced during the
    # post-SA3 audit. Each maps a dominant parent_group_activity to its
    # natural trade category for sparse-name subs.
    "Interior Stairs":   "Carpentry/Stairs",
    "Exterior Stairs":   "Carpentry/Stairs",
    "Exterior Decking":  "Carpentry/Stairs",
    "Exterior Pavers":   "Pavers/Hardscape",
    "Driveway":          "Pavers/Hardscape",
    "Countertops":       "Stone/Counters",
    "Appliances":        "Appliances",
    "Exterior Ceilings": "Trim/Finish",
    "Fencing":           "Fence/Gate",
    # Phase 16 — concrete/masonry phase tags that surface on the larger
    # foundation jobs. All credit Concrete-family subs.
    "Slab":              "Concrete",
    "Stem Wall":         "Concrete",
    "CIP Beams - 1L":    "Concrete",
    "CIP Beams - 2L":    "Concrete",
    "Masonry Walls - 1L":"Concrete",
    "Masonry Walls - 2L":"Concrete",
    "Masonry Walls - 3L":"Concrete",
    # Cross-trade tags — close-out and admin activities that any sub on
    # site might be supporting. Mapped to None so the trade-family filter
    # never credits them. Other Trade / Internal Crew can still pick them
    # up via solo-day fallback.
    "Final Punch Out":   None,
    "Final Touches":     None,
    "Plan Review":       None,
    "Pre-Construction":  None,
    "Estimating":        None,
    "Obtain C.O.":       None,
    "Finalize Contract": None,
}

# Minimum lifetime days + dominance share required to reclassify a sub
# off "Other Trade" using its activity distribution. Below either bar,
# the sub stays "Other Trade" — too sparse to trust the signal.
_RECLASSIFY_MIN_DAYS = 10
_RECLASSIFY_MIN_SHARE = 0.40

# Manual category overrides for subs the audit identified that neither the
# name regex nor the activity fallback can classify cleanly. Typically
# multi-trade general contractors whose work spreads across many phases
# (no single phase ≥40 % of total). Keyed by lowercased name; checked
# BEFORE the regex pass so it always wins.
_MANUAL_CATEGORY_OVERRIDES: dict[str, str] = {
    "all valencia construction llc": "Framing",         # Phase 14 audit: GC, top phase Framing 18%
    "coatrite llc":                  "Waterproofing",   # confirmed by operator: waterproofing contractor
    "captain cool llc":              "HVAC",            # confirmed by operator: AC contractor
}

# Phase 18 — multi-category overrides. Some subs work across multiple
# trade families (e.g. low-voltage electricians who also do AV).
# `_MULTI_CATEGORY_OVERRIDES[name_lower]` returns the full categories
# list; primary classification still flows through classify_sub, but
# the family filter in compute_subs_performance_data uses this list
# (any match) when deciding which activity tags to credit.
#
# Empty by default — Phase 18 detection heuristic produced 25 candidates
# but most look like co-presence noise. SmartShield's user-confirmed
# "Audio/Video + Low Voltage" is a no-op in our model since both LV
# tags already map to the Audio/Video category. Add real multi-trade
# subs here as the operator confirms them.
_MULTI_CATEGORY_OVERRIDES: dict[str, list[str]] = {
    # "smartshield homes llc": ["Audio/Video", "Electrical"],  # candidate, awaiting confirmation
}


def _activity_to_category(activity_name: str) -> str | None:
    """Return canonical category for a parent_group_activity tag, or None
    if the tag has no mapping. Pure dict lookup — case-sensitive on tag."""
    if not activity_name:
        return None
    return ACTIVITY_TO_CATEGORY.get(activity_name.strip())


def classify_sub(
    name: str,
    top_activity: tuple[str, float] | None = None,
    lifetime_days: int = 0,
) -> str:
    """Two-step classifier.

    1. Regex match on the sub's name (existing logic, takes precedence).
    2. If regex returns 'Other Trade' AND ``top_activity`` is provided, fall
       back to the dominant parent_group_activity. Reclassification is
       gated on _RECLASSIFY_MIN_DAYS and _RECLASSIFY_MIN_SHARE so sparse
       subs stay 'Other Trade'.

    Args:
        name: sub display name (canonicalized upstream).
        top_activity: ``(activity_name, share_of_total)`` where share is
            0.0–1.0 — the most-frequent parent_group_activity for this
            sub across all daily logs. Pass None to skip step 2.
        lifetime_days: total days on site (any job) — used for the
            ≥10 day minimum.
    """
    s = (name or "").strip()
    # Manual overrides take precedence — handles multi-trade GCs the regex
    # + activity fallback can't classify cleanly.
    manual = _MANUAL_CATEGORY_OVERRIDES.get(s.lower())
    if manual:
        return manual
    for cat, rx in _SUB_CATEGORY_RX:
        if rx.search(s):
            return cat
    # Regex didn't match — try activity fallback before giving up.
    if top_activity and lifetime_days >= _RECLASSIFY_MIN_DAYS:
        act_name, share = top_activity
        if share >= _RECLASSIFY_MIN_SHARE:
            mapped = _activity_to_category(act_name)
            if mapped:
                return mapped
    return "Other Trade"


# Manual canonicalization map for sub names that appear in multiple variants
# in the BT daily logs. Keyed by lowercased variant → canonical display form.
# When new duplicates are spotted (e.g. by reviewing the Subs tab for near-twins),
# add entries here rather than letting them inflate the count and split history.
SUB_NAME_CANONICALIZATIONS: dict[str, str] = {
    # Sight to See: 69 vs 39 — pick the no-comma form (more common, simpler).
    "sight to see construction llc": "Sight to See Construction LLC",
    "sight to see construction, llc": "Sight to See Construction LLC",
    # DB Improvement Services: 67 vs 10 — drop the LLC suffix.
    "db improvement services": "DB Improvement Services",
    "db improvement services, llc": "DB Improvement Services",
    # Cosmetic typo / whitespace fixes
    "manatee county utilitiy department": "Manatee County Utility Department",
    "altered state of mine , llc": "Altered State Of Mine, LLC",
}


def _canonicalize_sub_name(name: str) -> str:
    """Map known variant spellings of a sub to their canonical form before
    aggregation. Pure lookup — does not mutate names without a table entry."""
    if not name:
        return name
    key = name.strip().lower()
    return SUB_NAME_CANONICALIZATIONS.get(key, name.strip())


def _is_real_crew_name(name) -> bool:
    s = (name or "").strip()
    if not s or len(s) < 3 or len(s) > 60:
        return False
    low = s.lower()
    if low in BT_FORM_LABELS:
        return False
    # ZZ-prefix scheduling placeholders ("ZZ - Inspection", "ZZ-2026-...").
    # BT users prefix temporary entries with ZZ to sort them to the bottom.
    if re.match(r"^zz\s*-", low):
        return False
    # BT log section headers and sentence fragments leaking through as crew names.
    # These come from PMs typing notes into the wrong field on BT.
    if low.startswith("discussions/events"):
        return False
    if "discussions/events" in low:
        return False
    if low.startswith("met with"):
        return False
    if low.startswith("site meeting"):
        return False
    if low.startswith("on site"):
        return False
    # "Additional details" is a BT form section header that occasionally
    # leaks into the crews field (Phase 14 audit — 34 lifetime days).
    if low.startswith("additional details"):
        return False
    # Strip BT annotations like " (#)", " - 1", " -" and recheck against labels.
    # Catches leaks like "on site (#) - 1" where "on site" is the actual label.
    core = re.split(r"\s*[(\-]", s, maxsplit=1)[0].strip().lower()
    if core and core in BT_FORM_LABELS:
        return False
    if s.rstrip().endswith("-"):
        return False
    if "[BLOCKED" in s or "Base64" in s:
        return False
    # Numbered-list items leak in from notes_full ("1. Waiting for plumbers...")
    if re.match(r"^\d+[\.\)]\s", s):
        return False
    # Long parentheticals are template instructions, not names like "Smith (Lead)".
    if "(" in s and ")" in s and len(s) > 35:
        return False
    # Parenthetical-summary leaks ("(Summary of...)").
    if s.startswith("(") and ("summary" in low or "..." in s):
        return False
    if any(p in low for p in _TEMPLATE_PHRASES):
        return False
    # Sentence-like phrases (log notes leaking through as crew names)
    SENTENCE_MARKERS = (
        "rescheduled", "waiting for", "we need", "needs to", "pending",
        "will be", "should be", "completed by", "set up a", "did not",
        "scheduled for", "expected to", "loads of", "package delivered",
        "brought out", "underway", "went through", "team brought",
        "delivered.", "was delivered", " - went ", " - completed",
    )
    if any(m in low for m in SENTENCE_MARKERS):
        return False
    # Names ending in a period are nearly always sentences, not company names.
    # (Real names with periods like "Inc." don't end in a single period — they
    # have additional context, e.g. "Inc.", "LLC.", or end with "Inc" etc.)
    if s.rstrip().endswith(".") and not re.search(r"\b(Inc|LLC|Co|Ltd|Corp)\.?$", s.rstrip()):
        return False
    # Bare activity-tag names that are the parent_group_activity itself
    # (e.g. "Site Work" leaking from a misformed crews_clean entry).
    BARE_ACTIVITY_TAGS = {
        "site work", "interior trim", "interior tile", "drywall", "stucco",
        "framing", "pool", "siding", "insulation", "cabinetry",
    }
    if low in BARE_ACTIVITY_TAGS:
        return False
    return True


def compute_jobs_lifetime_data(binders: dict[str, dict], today: date) -> dict:
    """Build per-job lifetime analytics from BT daily logs + binder phase metadata.

    Output is keyed by canonical short name (Fish, Pou, etc.). Each value carries:
      - meta (PM owner, phase, status, address, target_co, full_key)
      - lifetime totals (total_logs, total_days, total_person_days, avg/peak workforce,
        delivery/inspection days, top crews/activities, date range, last_log_age_days)
      - monthly[] — last 13 months: {ym, logs, person_days, deliveries, inspections,
        missed_weekdays} for sparkline rendering
    """
    out: dict[str, dict] = {"__portfolio__": {}}
    if not DAILY_LOGS_PATH.exists():
        return out
    try:
        data = json.loads(DAILY_LOGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return out

    # Track every unique sub across the entire portfolio (case-insensitive
    # dedupe) so the rollup line shows the true number, not a top-N union.
    portfolio_subs_lc: set[str] = set()
    portfolio_phase_durations: dict[str, list[int]] = {}

    by_job = data.get("byJob", {}) or {}
    holidays_set: set[date] = set()
    # Build a 2-year holiday window for missed-weekday computation; spans current
    # year and prior 12 months.
    yrs = sorted({today.year, today.year - 1, today.year - 2})
    holidays_set = set(_holidays_pkg.country_holidays("US", years=yrs).keys())

    # Reverse map full BT key → canonical short name
    full_to_short = {full: short for short, full in JOB_NAME_MAP.items()}

    # Pull phase/status/address from binders. A job lives under one PM's binder.
    job_meta: dict[str, dict] = {}
    for pm_name, b in binders.items():
        for j in (b.get("jobs") or []):
            short = j.get("name")
            if not short:
                continue
            job_meta[short] = {
                "pm": pm_name,
                "phase": j.get("phase", ""),
                "status": j.get("status", ""),
                "address": j.get("address", ""),
                "target_co": j.get("targetCO", ""),
            }

    # Window-end for last_log_age = today
    for full_key, records in by_job.items():
        short = full_to_short.get(full_key)
        if not short:
            # Skip non-job buckets like "Field Crew (Ross Built)"
            continue

        days_with_logs: set[date] = set()
        crew_days: dict[str, set[date]] = {}
        activity_days: dict[str, set[date]] = {}
        phase_dates: dict[str, list[date]] = {}
        # phase_subs[activity_tag][crew_name] = set of dates where (sub on site)
        # AND (phase tag active) within this job. Powers per-phase sub
        # attribution in the Jobs view phase-durations table.
        phase_subs: dict[str, dict[str, set[date]]] = {}
        absent_days: dict[str, set[date]] = {}
        delivery_days: set[date] = set()
        inspection_days: set[date] = set()
        delivery_events: list[dict] = []
        inspection_events: list[dict] = []
        notable_events: list[dict] = []
        wf_values: list[int] = []
        # Monthly aggregates: ym_str -> dict
        monthly: dict[str, dict] = {}

        for rec in records:
            d = _parse_log_date(rec.get("date", ""), context=today)
            if d is None:
                continue
            days_with_logs.add(d)
            ym = f"{d.year:04d}-{d.month:02d}"
            m = monthly.setdefault(ym, {
                "ym": ym, "logs": 0, "person_days": 0, "deliveries": 0,
                "inspections": 0, "log_days": set(),
            })
            m["logs"] += 1
            m["log_days"].add(d)
            wf = _safe_int(rec.get("daily_workforce"))
            if wf is not None:
                wf_values.append(wf)
                m["person_days"] += wf

            # Crews
            crews_clean = rec.get("crews_clean")
            if not (isinstance(crews_clean, list) and crews_clean):
                # Fallback: parse legacy crews string (semicolon-separated, mixed labels)
                raw = (rec.get("crews") or "")
                crews_clean = [p.strip() for p in raw.split(";") if p.strip()]
            # Canonical crews on site this day — captured here for both top-crews
            # tally and per-phase sub attribution below.
            day_crews_canon: list[str] = []
            for c in crews_clean or []:
                if not _is_real_crew_name(c):
                    continue
                c = _canonicalize_sub_name(c)
                crew_days.setdefault(c, set()).add(d)
                portfolio_subs_lc.add(c.strip().lower())
                day_crews_canon.append(c)

            # Absences
            for c in (rec.get("absent_crews") or []):
                c = (c or "").strip()
                if c:
                    absent_days.setdefault(c, set()).add(d)

            # Activities — use parent_group_activities (structured tags). The
            # raw `activity` field is freeform PM text and includes job-role
            # labels ("Superintendent") + scraper artifacts ("[BLOCKED:...]").
            for tag in (rec.get("parent_group_activities") or []):
                tag = (tag or "").strip()
                if tag and len(tag) <= 60 and tag.lower() not in BT_FORM_LABELS:
                    activity_days.setdefault(tag, set()).add(d)
                    phase_dates.setdefault(tag, []).append(d)
                    # Attribute every sub on site this day to this phase tag.
                    sub_map = phase_subs.setdefault(tag, {})
                    for cc in day_crews_canon:
                        sub_map.setdefault(cc, set()).add(d)

            # Inspections / deliveries — gate on meaningful content, not the
            # `hasInspections`/`hasDeliveries` flags. Those flags over-fire
            # because BT renders the section header on every log; the regex
            # in the scraper picks up the label even when the body is "None".
            insp = (rec.get("inspection_details") or "").strip()
            if _is_meaningful(insp):
                inspection_days.add(d)
                m["inspections"] += 1
                inspection_events.append({"date": d.isoformat(), "details": insp[:200]})
            deliv = (rec.get("delivery_details") or "").strip()
            if _is_meaningful(deliv):
                delivery_days.add(d)
                m["deliveries"] += 1
                delivery_events.append({"date": d.isoformat(), "details": deliv[:200]})
            other = (rec.get("other_notable_activities") or "").strip()
            if _is_meaningful(other):
                notable_events.append({"date": d.isoformat(), "text": other[:300]})

        if not days_with_logs:
            continue

        first_log = min(days_with_logs)
        last_log = max(days_with_logs)

        # Sort + truncate top lists
        top_crews = sorted(
            ({"name": k, "days": len(v)} for k, v in crew_days.items()),
            key=lambda x: -x["days"],
        )[:15]
        top_activities = sorted(
            ({"name": k, "days": len(v)} for k, v in activity_days.items()),
            key=lambda x: -x["days"],
        )[:10]
        top_absences = sorted(
            ({"name": k, "days": len(v)} for k, v in absent_days.items()),
            key=lambda x: -x["days"],
        )[:10]
        delivery_events.sort(key=lambda e: e["date"], reverse=True)
        inspection_events.sort(key=lambda e: e["date"], reverse=True)
        notable_events.sort(key=lambda e: e["date"], reverse=True)

        # Phase durations — substantial-burst detection. Group activity dates
        # into bursts (≤7-day consecutive gaps). A burst counts as "substantial"
        # only if it spans ≥3 days AND has ≥3 active days AND density (active /
        # duration) ≥ 35%. This filters out pre-phase planning visits and
        # post-phase touch-ups so "Interior Paint" reads as 25d, not 100d.
        BURST_GAP = 7
        SUBST_MIN_DURATION = 3
        SUBST_MIN_ACTIVE = 3
        SUBST_MIN_DENSITY = 0.35

        phase_durations = []
        for act, dates in phase_dates.items():
            if not dates:
                continue
            sorted_dates = sorted(set(dates))
            bursts = [[sorted_dates[0]]]
            for d in sorted_dates[1:]:
                if (d - bursts[-1][-1]).days <= BURST_GAP:
                    bursts[-1].append(d)
                else:
                    bursts.append([d])

            burst_summaries = []
            for b in bursts:
                dur = (b[-1] - b[0]).days + 1
                act_days = len(b)
                density = act_days / dur if dur > 0 else 0
                substantial = (dur >= SUBST_MIN_DURATION
                               and act_days >= SUBST_MIN_ACTIVE
                               and density >= SUBST_MIN_DENSITY)
                burst_summaries.append({
                    "first": b[0], "last": b[-1],
                    "duration_days": dur, "active_days": act_days,
                    "density": round(density, 2),
                    "substantial": substantial,
                })

            substantial_bursts = [b for b in burst_summaries if b["substantial"]]
            full_first = sorted_dates[0]
            full_last = sorted_dates[-1]
            total_active = len(sorted_dates)

            if substantial_bursts:
                # Pick the longest substantial burst as the primary "phase"
                primary = max(substantial_bursts, key=lambda b: (b["duration_days"], b["active_days"]))
                pattern = "substantial"
                primary_duration = primary["duration_days"]
                primary_active = primary["active_days"]
                primary_first = primary["first"].isoformat()
                primary_last = primary["last"].isoformat()
                ongoing = (today - primary["last"]).days <= 14
                num_subst = len(substantial_bursts)
            elif len(bursts) >= 3 and total_active >= 7:
                # Multi-burst pattern: no single burst is substantial, but the
                # phase has ≥3 distinct work bursts and ≥7 cumulative active
                # days (e.g., HVAC Rough In split across 3 site visits with
                # 2-3 days each). Cumulatively this IS real work — don't
                # bucket as "Intermittent". Span = first to last burst (with
                # gaps). Phase 14 audit: third real-world phase pattern.
                pattern = "multi-burst"
                primary_duration = (full_last - full_first).days + 1
                primary_active = total_active
                primary_first = full_first.isoformat()
                primary_last = full_last.isoformat()
                ongoing = (today - full_last).days <= 14
                num_subst = 0
            else:
                # No substantial burst — only sporadic activity. Don't inflate.
                pattern = "intermittent"
                primary_duration = None
                primary_active = total_active
                primary_first = full_first.isoformat()
                primary_last = full_last.isoformat()
                ongoing = (today - full_last).days <= 14
                num_subst = 0

            # Per-phase sub attribution: rank crews by unique day count on this
            # phase tag within this job. Filter Ross Built Crew unless they're
            # the top contributor — internal team often gets credit when an
            # external sub did the actual work (Phase 14 audit finding).
            sub_map = phase_subs.get(act, {})
            sub_ranked = sorted(
                ({"name": k, "days": len(v)} for k, v in sub_map.items() if k),
                key=lambda x: (-x["days"], x["name"]),
            )
            if sub_ranked:
                # Identify Ross Built Crew (case/spacing-tolerant).
                def _is_rbc(nm: str) -> bool:
                    return (nm or "").strip().lower() == "ross built crew"
                top_name = sub_ranked[0]["name"]
                if not _is_rbc(top_name):
                    sub_ranked = [s for s in sub_ranked if not _is_rbc(s["name"])]
            top_subs = sub_ranked[:3]

            phase_durations.append({
                "name": act,
                "pattern": pattern,                # "substantial" | "multi-burst" | "intermittent"
                "first": primary_first,
                "last": primary_last,
                "duration_days": primary_duration,  # None when intermittent
                "active_days": primary_active,
                "lifetime_first": full_first.isoformat(),
                "lifetime_last": full_last.isoformat(),
                "lifetime_span_days": (full_last - full_first).days + 1,
                "lifetime_active_days": total_active,
                "num_substantial_bursts": num_subst,
                "num_total_bursts": len(bursts),
                "ongoing": ongoing,
                "top_subs": top_subs,
            })
        # Sort chronologically by first substantial date.
        phase_durations.sort(key=lambda p: p["first"])

        # Monthly series: last 13 months ending in current month, anchored to today
        series = []
        cur = date(today.year, today.month, 1)
        for _ in range(13):
            ym = f"{cur.year:04d}-{cur.month:02d}"
            m = monthly.get(ym)
            month_end = date(cur.year, cur.month, 28)
            # Find last day of month (handle non-28 months)
            next_month = date(cur.year + (1 if cur.month == 12 else 0), 1 if cur.month == 12 else cur.month + 1, 1)
            last_of_month = next_month - timedelta(days=1)
            # Compute weekday gaps in this month
            weekday_count = 0
            d = cur
            while d <= last_of_month:
                if d.weekday() < 5 and d not in holidays_set:
                    weekday_count += 1
                d += timedelta(days=1)
            log_days_in_month = m["log_days"] if m else set()
            missed = max(0, weekday_count - len({ld for ld in log_days_in_month if ld.weekday() < 5 and ld not in holidays_set}))
            series.append({
                "ym": ym,
                "label": cur.strftime("%b %y"),
                "logs": m["logs"] if m else 0,
                "person_days": m["person_days"] if m else 0,
                "deliveries": m["deliveries"] if m else 0,
                "inspections": m["inspections"] if m else 0,
                "weekdays_in_month": weekday_count,
                "missed_weekdays": missed,
            })
            # Step back one month
            cur = date(cur.year - (1 if cur.month == 1 else 0), 12 if cur.month == 1 else cur.month - 1, 1)
        series.reverse()  # oldest → newest, left → right

        meta = job_meta.get(short, {})
        out[short] = {
            "short_name": short,
            "full_key": full_key,
            # Operator-precedence: Python parses `A or B if C else D` as
            # `A or (B if C else D)`. We want to ALWAYS prefer meta["address"]
            # when set, then fall back to a derived address only when both
            # meta is empty AND the full_key carries the address suffix.
            "address": (meta.get("address", "").replace(short + "-", "")) or (full_key.split("-", 1)[-1] if "-" in full_key else ""),
            "pm": meta.get("pm") or JOB_TO_PM.get(short, ""),
            "phase": meta.get("phase", ""),
            "status": meta.get("status", ""),
            "target_co": meta.get("target_co", ""),
            "lifetime": {
                "total_logs": len(records),
                "total_days": len(days_with_logs),
                "first_log": first_log.isoformat(),
                "last_log": last_log.isoformat(),
                "last_log_age_days": (today - last_log).days,
                "total_person_days": sum(wf_values),
                "avg_workforce": round(sum(wf_values) / len(wf_values), 1) if wf_values else 0,
                "peak_workforce": max(wf_values) if wf_values else 0,
                "delivery_days": len(delivery_days),
                "inspection_days": len(inspection_days),
                "unique_crews": len(crew_days),
            },
            "top_crews": top_crews,
            "top_activities": top_activities,
            "top_absences": top_absences,
            "phase_durations": phase_durations,
            "delivery_events": delivery_events[:15],
            "inspection_events": inspection_events[:15],
            "notable_events": notable_events[:15],
            "monthly": series,
        }

    # Per-PM missed log aggregation — sum missed weekdays across each PM's
    # jobs over the last 30 days, broken down per job. Used by the JS to
    # render a "missed logs" banner on each PM's tab so accountability is
    # surfaced (a PM forgetting daily logs is a leading indicator of trouble).
    pm_missed: dict[str, dict] = {}
    for pm_name in PM_JOBS:
        per_job = []
        dormant_jobs: list[str] = []
        total_recent = 0
        total_lifetime = 0
        for short in PM_JOBS[pm_name]:
            j = out.get(short)
            if not j:
                continue
            monthly = j.get("monthly", []) or []
            recent = sum(m.get("missed_weekdays", 0) for m in monthly[-1:])  # current month
            recent3 = sum(m.get("missed_weekdays", 0) for m in monthly[-3:])  # last 3 mo
            lifetime_missed = sum(m.get("missed_weekdays", 0) for m in monthly)
            last_age = (j.get("lifetime", {}) or {}).get("last_log_age_days")
            # Dormant jobs (no log in 30+ days) shouldn't inflate the active
            # missed-logs banner — they signal a closed/paused job, not
            # neglect on this PM's part. Track them separately.
            is_dormant = last_age is not None and last_age > 30
            if is_dormant:
                if recent > 0 or recent3 > 0:
                    dormant_jobs.append(short)
                continue
            per_job.append({
                "short_name": short,
                "current_month_missed": recent,
                "trailing_3mo_missed": recent3,
                "last_log_age_days": last_age,
            })
            total_recent += recent
            total_lifetime += lifetime_missed
        pm_missed[pm_name] = {
            "current_month_missed": total_recent,
            "trailing_3mo_missed": sum(p["trailing_3mo_missed"] for p in per_job),
            "lifetime_missed": total_lifetime,
            "per_job": per_job,
            "dormant_jobs": dormant_jobs,
        }

    pf_jobs = [v for k, v in out.items() if k != "__portfolio__"]
    out["__portfolio__"] = {
        "jobs": len(pf_jobs),
        "unique_subs": len(portfolio_subs_lc),
        "total_log_days": sum((j.get("lifetime", {}) or {}).get("total_days", 0) for j in pf_jobs),
        "total_person_days": sum((j.get("lifetime", {}) or {}).get("total_person_days", 0) for j in pf_jobs),
        "delivery_days": sum((j.get("lifetime", {}) or {}).get("delivery_days", 0) for j in pf_jobs),
        "inspection_days": sum((j.get("lifetime", {}) or {}).get("inspection_days", 0) for j in pf_jobs),
        "pm_missed": pm_missed,
    }
    return out


def compute_phase_durations(jobs_data: dict, today: date) -> dict:
    """Phase 18 — pivot per-job phase data into a phase-first lookup.

    For each parent_group_activities tag that appears anywhere in the
    portfolio, gather all (job, phase) pairs and aggregate cross-job
    statistics: median / p25 / p75 / min / max active days, plus median
    calendar span. Cross-trade tags (category=None — Final Punch Out,
    Plan Review, etc.) are excluded since they aren't phase work in the
    same comparable sense.

    Output shape:
        {
          "Plumbing/Gas Rough In": {
              "category": "Plumbing",
              "by_job": {
                  "Markgraf": {"days": 16, "calendar_span_days": 54,
                              "subs": ["Gator Plumbing"],
                              "status": "complete", "ended": "2025-12-08"},
                  ...
              },
              "summary": {
                  "median_days": 14, "p25_days": 11.5, "p75_days": 15.5,
                  "min_days": 10, "max_days": 16, "median_span": 24,
                  "job_count": 4, "sub_count": 1, "active_count": 0,
                  "total_active_days": 54,
              }
          },
          ...
        }
    """
    def _percentile(sorted_vals: list, pct: float):
        if not sorted_vals:
            return 0
        if len(sorted_vals) == 1:
            return sorted_vals[0]
        k = (len(sorted_vals) - 1) * pct
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        if f == c:
            return sorted_vals[f]
        return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

    pivot: dict[str, dict] = {}
    for short, jdata in jobs_data.items():
        if short == "__portfolio__":
            continue
        if not isinstance(jdata, dict):
            continue
        for p in jdata.get("phase_durations", []) or []:
            tag = p.get("name")
            if not tag:
                continue
            cat = ACTIVITY_TO_CATEGORY.get(tag)
            if cat is None:
                # Cross-trade tag — not a comparable phase, skip.
                continue
            entry = pivot.setdefault(tag, {
                "category": cat,
                "by_job": {},
            })
            entry["by_job"][short] = {
                "days": p.get("lifetime_active_days") or p.get("active_days") or 0,
                "calendar_span_days": p.get("lifetime_span_days") or p.get("duration_days") or 0,
                "subs": [s.get("name") for s in (p.get("top_subs") or []) if s.get("name")],
                "status": "ongoing" if p.get("ongoing") else "complete",
                "ended": p.get("lifetime_last") or p.get("last") or "",
                "pattern": p.get("pattern") or "",
                "first": p.get("lifetime_first") or p.get("first") or "",
            }

    # Compute summary stats per phase.
    for tag, entry in pivot.items():
        by_job = entry["by_job"]
        days_vals = sorted(j["days"] for j in by_job.values() if j["days"])
        span_vals = sorted(j["calendar_span_days"] for j in by_job.values() if j["calendar_span_days"])
        subs_set: set[str] = set()
        for j in by_job.values():
            for s in j.get("subs", []) or []:
                subs_set.add(s)
        entry["summary"] = {
            "median_days":  round(_percentile(days_vals, 0.5),  1) if days_vals else 0,
            "p25_days":     round(_percentile(days_vals, 0.25), 1) if days_vals else 0,
            "p75_days":     round(_percentile(days_vals, 0.75), 1) if days_vals else 0,
            "min_days":     days_vals[0]  if days_vals else 0,
            "max_days":     days_vals[-1] if days_vals else 0,
            "median_span":  round(_percentile(span_vals, 0.5), 1) if span_vals else 0,
            "job_count":    len(by_job),
            "sub_count":    len(subs_set),
            "active_count": sum(1 for j in by_job.values() if j.get("status") == "ongoing"),
            "total_active_days": sum(j["days"] for j in by_job.values()),
        }

    return pivot


def compute_subs_performance_data(today: date) -> dict:
    """Per-subcontractor performance + reliability data, derived from BT daily logs.

    Each sub gets:
      - lifetime: total days on site, jobs touched, first/last seen, absences,
        reliability % = days_on / (days_on + days_absent)
      - recent: same metrics restricted to last 30 days
      - active_now: # of jobs they're currently active on (last 7 days)
      - monthly_days: last 12 months of days-on-site per month (sparkline)

    Plus "overlap concerns" — subs simultaneously active on ≥3 jobs in last 7 days,
    which can signal overcommitment.
    """
    if not DAILY_LOGS_PATH.exists():
        return {"subs": {}, "overlap_concerns": [], "portfolio": {}}
    try:
        data = json.loads(DAILY_LOGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"subs": {}, "overlap_concerns": [], "portfolio": {}}

    full_to_short = {full: short for short, full in JOB_NAME_MAP.items()}
    by_job = data.get("byJob", {}) or {}

    # sub_key (lowercase) → aggregated record
    subs: dict[str, dict] = {}
    cutoff_30 = today - timedelta(days=30)
    cutoff_7 = today - timedelta(days=7)
    def get_or_create(name: str) -> dict:
        key = name.strip().lower()
        if key not in subs:
            subs[key] = {
                "name": name.strip(),  # display name (first form seen)
                "all_days": set(),     # set[date]
                "all_jobs": set(),     # set[short name]
                "absences": set(),     # set[date]
                "abs_jobs": set(),     # set[short name] where absent
                "recent_days": set(),
                "recent_jobs": set(),
                "recent_absences": set(),
                "active7_jobs": set(),
                "monthly_days": {},    # ym -> set of dates
                "first_seen": None,
                "last_seen": None,
                "job_day_counts": {},  # short_name -> count
                # all_jobdays: set[(short_name, date)] — every (job, date)
                # pair this sub appeared on. Different from all_days (which
                # is calendar-distinct) when a sub worked two jobs on the
                # same calendar day; that's ~15 % of (sub, date) pairs in
                # practice and is what enables per-job arithmetic to sum
                # cleanly. Used as the denominator for phase_breakdown
                # percentages so sum(jobs[].days) == phase.days holds.
                "all_jobdays": set(),
                # phase_jobdays_raw: tag -> dict[short_name -> set[date]] of
                # log-days where this sub appeared at this job under this
                # parent_group_activities tag. Cross-product (every sub on
                # site × every tag on the log × the specific job). Used to
                # derive the dominant-phase signal classify_sub consumes
                # for "Other Trade" reclassification, and also to produce
                # the per-job breakdown in the Phase 17 UI.
                #
                # phase_jobdays_solo: same shape, restricted to days where
                # this sub was the ONLY real crew on site. Used for the
                # solo-day attribution fallback when the sub's category is
                # "Other Trade" or "Internal Crew".
                #
                # Phase 17: replaces the prior flat phase_days_raw +
                # phase_jobs_raw pair. Per-job arithmetic now sums cleanly
                # (sum over jobs of len(set per job) = phase.days) and the
                # active_dates list for Level-3 drill-down comes for free.
                "phase_jobdays_raw": {},
                "phase_jobdays_solo": {},
            }
        return subs[key]

    for full_key, records in by_job.items():
        short = full_to_short.get(full_key)
        if not short:
            continue
        for rec in records:
            d = _parse_log_date(rec.get("date", ""), context=today)
            if d is None:
                continue
            ym = f"{d.year:04d}-{d.month:02d}"

            # Crews on site
            crews_clean = rec.get("crews_clean")
            if not (isinstance(crews_clean, list) and crews_clean):
                raw = rec.get("crews") or ""
                crews_clean = [p.strip() for p in raw.split(";") if p.strip()]
            # Pre-compute the cleaned phase-tag list for this record once so we
            # can attribute it to every crew without re-parsing per-crew. Tags
            # are filtered the same way compute_jobs_lifetime_data does — drop
            # BT form labels and overly long freeform strings.
            rec_phase_tags = []
            for tag in (rec.get("parent_group_activities") or []):
                tag = (tag or "").strip()
                if tag and len(tag) <= 60 and tag.lower() not in BT_FORM_LABELS:
                    rec_phase_tags.append(tag)
            # Filter to real crews once so we can compute is_solo and avoid
            # repeating _is_real_crew_name inside the per-sub loop. Solo-day
            # status is what powers the Other-Trade fallback in Phase 16.
            real_crews = [
                _canonicalize_sub_name(c)
                for c in (crews_clean or [])
                if _is_real_crew_name(c)
            ]
            is_solo = len(real_crews) == 1

            for c in real_crews:
                rec_sub = get_or_create(c)
                rec_sub["all_days"].add(d)
                rec_sub["all_jobs"].add(short)
                rec_sub["all_jobdays"].add((short, d))
                rec_sub["job_day_counts"][short] = rec_sub["job_day_counts"].get(short, 0) + 1
                rec_sub["monthly_days"].setdefault(ym, set()).add(d)
                if rec_sub["first_seen"] is None or d < rec_sub["first_seen"]:
                    rec_sub["first_seen"] = d
                if rec_sub["last_seen"] is None or d > rec_sub["last_seen"]:
                    rec_sub["last_seen"] = d
                if d >= cutoff_30:
                    rec_sub["recent_days"].add(d)
                    rec_sub["recent_jobs"].add(short)
                if d >= cutoff_7:
                    rec_sub["active7_jobs"].add(short)
                # Raw cross-product (every sub on site × every tag × this
                # specific job) — feeds both the dominant-phase signal
                # classify_sub uses for Other Trade reclassification AND
                # the Phase 17 per-job breakdown. The dict-of-dict shape
                # `tag -> short -> set[date]` lets per-job arithmetic sum
                # cleanly (sum over jobs of len(set) == phase total).
                for tag in rec_phase_tags:
                    by_job_dict = rec_sub["phase_jobdays_raw"].setdefault(tag, {})
                    by_job_dict.setdefault(short, set()).add(d)
                    if is_solo:
                        by_job_dict_solo = rec_sub["phase_jobdays_solo"].setdefault(tag, {})
                        by_job_dict_solo.setdefault(short, set()).add(d)

            # Absences
            for c in (rec.get("absent_crews") or []):
                c = (c or "").strip()
                if not _is_real_crew_name(c):
                    continue
                c = _canonicalize_sub_name(c)
                rec_sub = get_or_create(c)
                rec_sub["absences"].add(d)
                rec_sub["abs_jobs"].add(short)
                if d >= cutoff_30:
                    rec_sub["recent_absences"].add(d)

    # Build flat output with derived metrics
    out_subs = []
    for key, s in subs.items():
        days = len(s["all_days"])
        absences = len(s["absences"])
        reliability = (days / (days + absences) * 100) if (days + absences) > 0 else None
        recent_days = len(s["recent_days"])
        recent_absences = len(s["recent_absences"])
        recent_reliability = (recent_days / (recent_days + recent_absences) * 100) if (recent_days + recent_absences) > 0 else None
        last_seen = s["last_seen"]
        last_age = (today - last_seen).days if last_seen else None

        # 13-month trailing series of days-on-site (oldest → newest, left → right)
        monthly = []
        cur = date(today.year, today.month, 1)
        for _ in range(13):
            ym = f"{cur.year:04d}-{cur.month:02d}"
            monthly.append({"ym": ym, "days": len(s["monthly_days"].get(ym, set()))})
            cur = date(cur.year - (1 if cur.month == 1 else 0), 12 if cur.month == 1 else cur.month - 1, 1)
        monthly.reverse()

        # Activity-based classification fallback — used by classify_sub when
        # name regex returns "Other Trade". Pick the dominant phase tag from
        # the RAW (pre-filter) signal and its share of total days.
        # classify_sub enforces the ≥10-day, ≥40 % thresholds; we just hand
        # it the raw signal here. Sum across jobs to recover the
        # set[date]-style count the existing classify_sub contract expects.
        top_activity_pair: tuple[str, float] | None = None
        if s["phase_jobdays_raw"] and days > 0:
            tag_totals = {
                tag: sum(len(jdates) for jdates in jdict.values())
                for tag, jdict in s["phase_jobdays_raw"].items()
            }
            top_tag, top_total = max(tag_totals.items(), key=lambda kv: kv[1])
            top_activity_pair = (top_tag, top_total / days)

        category = classify_sub(
            s["name"],
            top_activity=top_activity_pair,
            lifetime_days=days,
        )

        # Phase 18 — multi-category support. categories is always a list,
        # populated either from the user-confirmed _MULTI_CATEGORY_OVERRIDES
        # or as a single-element list around the regex/fallback primary.
        # Family filter below tests `tag.category in categories` so a sub
        # with ["Audio/Video", "Electrical"] is credited for tags from
        # either family.
        manual_multi = _MULTI_CATEGORY_OVERRIDES.get(s["name"].strip().lower())
        if manual_multi:
            categories = list(manual_multi)
            # Ensure the primary classify_sub result is in the list — keeps
            # the sub's "Category" column display consistent with their
            # name-regex match.
            if category not in categories:
                categories.insert(0, category)
        else:
            categories = [category]

        # Phase 16 — hybrid attribution. For classified subs (any category
        # other than Other Trade / Internal Crew) we apply a trade-family
        # filter: only credit phase tags whose ACTIVITY_TO_CATEGORY entry
        # matches the sub's own category. For Other Trade and Internal Crew
        # (Ross Built — multi-trade GC) we use solo-day attribution: only
        # count tags from days where this sub was the only real crew on
        # site. Either path produces percentages summing to ≤100 % because
        # a (job, day) pair contributes at most one phase-day per tag, and
        # the residual "On-site (no matching phase tag)" row picks up days
        # without any credited tag.
        SOLO_FALLBACK_CATEGORIES = ("Other Trade", "Internal Crew")
        # Solo fallback fires when ANY of the sub's categories is in the
        # solo-fallback set (typically just single-category Other Trade /
        # Internal Crew — multi-category subs are by definition not in
        # that set). Effectively unchanged from Phase 16 for the common
        # case; the `any()` guard handles the unlikely future where a sub
        # has Other Trade + something else.
        use_solo = any(c in SOLO_FALLBACK_CATEGORIES for c in categories)

        if use_solo:
            phase_jobdays_src = s["phase_jobdays_solo"]
        else:
            # Family filter — keep tags whose category matches ANY of the
            # sub's categories (Phase 18 multi-category support).
            phase_jobdays_src = {
                tag: jdict
                for tag, jdict in s["phase_jobdays_raw"].items()
                if ACTIVITY_TO_CATEGORY.get(tag) in categories
            }

        # Total job-days = sum of (job, date) pairs the sub appeared on.
        # This is the denominator for percentage math so per-job arithmetic
        # closes cleanly. Calendar-distinct lifetime_days stays separate
        # for the column display since users think of it that way.
        total_jobday = len(s["all_jobdays"])

        # Phase breakdown — skip low-volume subs (lifetime_days < 5) because
        # % shares are too noisy to be meaningful. Phases with fewer than
        # 2 (job, date) pairs are dropped before we compute shares so a
        # one-off tag doesn't dilute the residual or steal a slice of pie.
        phase_breakdown: list[dict] = []
        if days >= 5 and total_jobday > 0:
            # Surviving tags: keep only those with ≥2 (job, date) pairs.
            # Per-tag job-day count = sum across jobs.
            surviving = {}
            for tag, jdict in phase_jobdays_src.items():
                jobday_count = sum(len(d_set) for d_set in jdict.values())
                if jobday_count >= 2:
                    surviving[tag] = jdict

            # Fractional credit — when multiple surviving tags land on the
            # same (job, date) pair (e.g. a Tile sub at one site with both
            # Interior Tile and Wood Flooring tagged the same day) split
            # credit equally across them so percentages sum to ≤100 %. The
            # integer "days" field still shows the raw day count for
            # honesty; only the share denominator uses fractional credit.
            jobday_to_tags: dict = {}
            for tag, jdict in surviving.items():
                for jshort, dset in jdict.items():
                    for d2 in dset:
                        jobday_to_tags.setdefault((jshort, d2), []).append(tag)
            credit: dict = {tag: 0.0 for tag in surviving}
            for tags_on_jobday in jobday_to_tags.values():
                share = 1.0 / len(tags_on_jobday)
                for tag in tags_on_jobday:
                    credit[tag] = credit.get(tag, 0.0) + share

            # Build per-tag entries with rich per-job breakdown (Phase 17).
            ranked: list[dict] = []
            for tag, jdict in surviving.items():
                # Per-job rows
                per_job: list[dict] = []
                for jshort, dset in jdict.items():
                    if not dset:
                        continue
                    sorted_dates = sorted(dset)
                    first_d = sorted_dates[0]
                    last_d = sorted_dates[-1]
                    span = (last_d - first_d).days + 1
                    # "ongoing" if the sub is still actively working this
                    # phase at this job — last log within last 14 days.
                    status = "ongoing" if (today - last_d).days <= 14 else "complete"
                    per_job.append({
                        "job": jshort,
                        "days": len(dset),
                        "first_date": first_d.isoformat(),
                        "last_date": last_d.isoformat(),
                        "calendar_span_days": span,
                        "status": status,
                    })
                per_job.sort(key=lambda j: -j["days"])

                day_counts = [j["days"] for j in per_job]
                phase_total = sum(day_counts)
                pct = round(credit.get(tag, 0.0) / total_jobday * 100) if total_jobday else 0
                ranked.append({
                    "phase": tag,
                    "days": phase_total,
                    "pct": pct,
                    "jobs": per_job,
                    "job_count": len(per_job),
                    "avg_days_per_job": round(sum(day_counts) / len(day_counts), 1) if day_counts else 0,
                    "min_days_per_job": min(day_counts) if day_counts else 0,
                    "max_days_per_job": max(day_counts) if day_counts else 0,
                })
            ranked.sort(key=lambda p: -p["days"])
            phase_breakdown = ranked

            # Residual — (job, date) pairs without any credited phase tag.
            # For family-filtered subs this is "non-trade days" (punch
            # work, supporting crews); for solo-fallback subs it's
            # multi-sub days that couldn't be cleanly attributed. Only
            # emit the row when there's something there.
            residual_jobdays = total_jobday - len(jobday_to_tags)
            if residual_jobdays > 0:
                residual_label = (
                    "Multi-sub days (not solo-attributable)"
                    if use_solo
                    else "On-site (no matching phase tag)"
                )
                phase_breakdown.append({
                    "phase": residual_label,
                    "days": residual_jobdays,
                    "pct": round(residual_jobdays / total_jobday * 100) if total_jobday else 0,
                    "jobs": [],
                    "job_count": 0,
                    "avg_days_per_job": 0,
                    "min_days_per_job": 0,
                    "max_days_per_job": 0,
                })

        out_subs.append({
            "name": s["name"],
            "key": key,
            "category": category,
            "categories": categories,
            "lifetime_days": days,
            "lifetime_jobs": sorted(s["all_jobs"]),
            "lifetime_jobs_count": len(s["all_jobs"]),
            "lifetime_absences": absences,
            "reliability_pct": round(reliability) if reliability is not None else None,
            "recent_days": recent_days,
            "recent_jobs": sorted(s["recent_jobs"]),
            "recent_jobs_count": len(s["recent_jobs"]),
            "recent_absences": recent_absences,
            "recent_reliability_pct": round(recent_reliability) if recent_reliability is not None else None,
            "active7_jobs": sorted(s["active7_jobs"]),
            "active7_count": len(s["active7_jobs"]),
            "first_seen": s["first_seen"].isoformat() if s["first_seen"] else None,
            "last_seen": last_seen.isoformat() if last_seen else None,
            "last_seen_age_days": last_age,
            "job_day_counts": s["job_day_counts"],
            "monthly_days": [m["days"] for m in monthly],
            "phase_breakdown": phase_breakdown,
        })

    # Overlap concerns: subs active on ≥3 jobs in last 7 days
    overlap = sorted(
        [s for s in out_subs if s["active7_count"] >= 3],
        key=lambda x: -x["active7_count"],
    )

    # Category aggregation — group subs by trade category for cross-sub
    # comparison ("how does Plumbing Co A compare to Plumbing Co B").
    cat_agg: dict[str, dict] = {}
    for s in out_subs:
        cat = s["category"]
        c = cat_agg.setdefault(cat, {
            "name": cat,
            "subs": [],
            "total_days": 0,
            "total_recent_days": 0,
            "total_absences": 0,
            "total_jobs_touched": set(),
        })
        c["subs"].append({
            "name": s["name"],
            "lifetime_days": s["lifetime_days"],
            "lifetime_jobs_count": s["lifetime_jobs_count"],
            "recent_days": s["recent_days"],
            "reliability_pct": s["reliability_pct"],
            "last_seen_age_days": s["last_seen_age_days"],
        })
        c["total_days"] += s["lifetime_days"]
        c["total_recent_days"] += s["recent_days"]
        c["total_absences"] += s["lifetime_absences"]
        for j in s["lifetime_jobs"]:
            c["total_jobs_touched"].add(j)

    categories = []
    for c in cat_agg.values():
        c["sub_count"] = len(c["subs"])
        c["jobs_touched"] = sorted(c["total_jobs_touched"])
        c["jobs_touched_count"] = len(c["total_jobs_touched"])
        # Days-per-sub (normalized): how much each sub averages within this category
        c["avg_days_per_sub"] = round(c["total_days"] / c["sub_count"], 1) if c["sub_count"] else 0
        # Days-per-sub-per-job (more normalized — adjusts for sub-job spread)
        sub_jobs_total = sum(s["lifetime_jobs_count"] for s in c["subs"]) or 1
        c["avg_days_per_subjob"] = round(c["total_days"] / sub_jobs_total, 1)
        # Top 5 subs in category by lifetime days
        c["top_subs"] = sorted(c["subs"], key=lambda s: -s["lifetime_days"])[:5]
        c.pop("total_jobs_touched", None)
        c.pop("subs", None)  # stay compact in output (full subs list is in SUBS_DATA.subs)
        categories.append(c)
    categories.sort(key=lambda c: -c["total_days"])

    # Portfolio totals
    active_30d = sum(1 for s in out_subs if s["recent_days"] > 0)
    total_abs_30d = sum(s["recent_absences"] for s in out_subs)

    # Phase 17 — cross-sub phase benchmarks. For each phase tag, gather the
    # per-(sub, job) day counts from every sub whose category aligns with
    # the phase's family (so a Plumbing sub's Electrical-tagged days don't
    # pollute the Plumbing/Gas Rough In benchmark — those wouldn't be
    # credited under the Phase 16 family filter anyway). Compute median /
    # p25 / p75 / min / max / sample_size. Sample sizes <3 are still
    # reported here; the UI suppresses badges when sample_size < 3.
    bench_samples: dict[str, list[int]] = {}
    for s_out in out_subs:
        sub_cats = s_out.get("categories") or [s_out.get("category")]
        for p in s_out.get("phase_breakdown", []) or []:
            tag = p.get("phase")
            if not tag or tag.startswith("On-site") or tag.startswith("Multi-sub"):
                continue
            # Only count phase data points where the tag's family is in
            # the sub's categories list — same gate as the Phase 18
            # multi-category family filter that produced phase_breakdown.
            if ACTIVITY_TO_CATEGORY.get(tag) not in sub_cats:
                continue
            for j in p.get("jobs", []) or []:
                jdays = j.get("days")
                if isinstance(jdays, int) and jdays > 0:
                    bench_samples.setdefault(tag, []).append(jdays)

    def _percentile(sorted_vals: list[int], pct: float) -> int | float:
        if not sorted_vals:
            return 0
        if len(sorted_vals) == 1:
            return sorted_vals[0]
        # Linear-interpolation percentile, matching numpy default.
        k = (len(sorted_vals) - 1) * pct
        f = int(k)
        c = min(f + 1, len(sorted_vals) - 1)
        if f == c:
            return sorted_vals[f]
        return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)

    phase_benchmarks: dict[str, dict] = {}
    for tag, samples in bench_samples.items():
        samples_sorted = sorted(samples)
        phase_benchmarks[tag] = {
            "median_days_per_job": round(_percentile(samples_sorted, 0.5), 1),
            "p25": round(_percentile(samples_sorted, 0.25), 1),
            "p75": round(_percentile(samples_sorted, 0.75), 1),
            "min": samples_sorted[0],
            "max": samples_sorted[-1],
            "sample_size": len(samples_sorted),
        }

    # Phase 6 — trade-level comparison aggregates. Per category, compute the
    # P25/P75/min/max of subs' median days-on-phase, plus the average
    # reliability of subs in that category with enough days to be meaningful.
    # Each sub gets decorated with their trade's aggregates so the JS can
    # render Duration vs Peers + Reliability vs Peers in a single row pass
    # without recomputing.
    #
    # Thresholds — defined here so they're easy to tune:
    PHASE6_TRADE_DURATION_MIN_INSTANCES = 3   # trade needs ≥3 phase instances
    PHASE6_SUB_DURATION_MIN_INSTANCES   = 2   # this sub needs ≥2 own instances
    PHASE6_TRADE_RELIABILITY_MIN_SUBS   = 3   # trade needs ≥3 qualifying subs
    PHASE6_RELIABILITY_MIN_DAYS         = 10  # qualifying = ≥10 lifetime days

    # Per-sub: gather (job, days) tuples for phases in this sub's category.
    sub_dur_samples: dict[str, list[int]] = {}    # sub_key → [days, days, ...]
    cat_dur_samples: dict[str, list[int]] = {}    # cat    → [days, days, ...] (all subs combined, raw instances)
    cat_sub_medians: dict[str, list[float]] = {}  # cat    → [sub1_median, sub2_median, ...]
    cat_rel_samples: dict[str, list[int]] = {}    # cat    → [reliability%, ...] (subs with ≥10 days)

    for s in out_subs:
        cat = s.get("category") or "—"
        cats_list = s.get("categories") or [cat]
        sub_key_local = s["key"]
        per_instance_days: list[int] = []
        for p in s.get("phase_breakdown", []) or []:
            tag = p.get("phase")
            if not tag or tag.startswith("On-site") or tag.startswith("Multi-sub"):
                continue
            tag_cat = ACTIVITY_TO_CATEGORY.get(tag)
            if tag_cat not in cats_list:
                continue
            for j in p.get("jobs", []) or []:
                jd = j.get("days")
                if isinstance(jd, int) and jd > 0:
                    per_instance_days.append(jd)
                    cat_dur_samples.setdefault(cat, []).append(jd)
        sub_dur_samples[sub_key_local] = per_instance_days
        if per_instance_days:
            sub_med = _percentile(sorted(per_instance_days), 0.5)
            cat_sub_medians.setdefault(cat, []).append(sub_med)
        if (s.get("lifetime_days") or 0) >= PHASE6_RELIABILITY_MIN_DAYS and s.get("reliability_pct") is not None:
            cat_rel_samples.setdefault(cat, []).append(s["reliability_pct"])

    trade_dur_aggs: dict[str, dict] = {}
    for cat, sub_medians in cat_sub_medians.items():
        instances = cat_dur_samples.get(cat, [])
        if len(instances) < PHASE6_TRADE_DURATION_MIN_INSTANCES:
            trade_dur_aggs[cat] = {"insufficient": True, "instances": len(instances), "subs": len(sub_medians)}
            continue
        sub_medians_sorted = sorted(sub_medians)
        all_inst_sorted = sorted(instances)
        trade_dur_aggs[cat] = {
            "insufficient": False,
            "p25": round(_percentile(sub_medians_sorted, 0.25), 1),
            "p75": round(_percentile(sub_medians_sorted, 0.75), 1),
            "min": all_inst_sorted[0],
            "max": all_inst_sorted[-1],
            "instances": len(instances),
            "subs": len(sub_medians),
        }

    trade_rel_aggs: dict[str, dict] = {}
    for cat, rels in cat_rel_samples.items():
        if len(rels) < PHASE6_TRADE_RELIABILITY_MIN_SUBS:
            trade_rel_aggs[cat] = {"insufficient": True, "subs": len(rels)}
            continue
        trade_rel_aggs[cat] = {
            "insufficient": False,
            "avg": round(sum(rels) / len(rels)),
            "subs": len(rels),
        }

    # Decorate each sub with their category's aggregates + their own median.
    for s in out_subs:
        cat = s.get("category") or "—"
        own_samples = sub_dur_samples.get(s["key"], [])
        sub_median = round(_percentile(sorted(own_samples), 0.5), 1) if own_samples else None
        s["sub_median_days_in_trade"] = sub_median
        s["sub_instances_in_trade"]   = len(own_samples)
        s["trade_dur"] = trade_dur_aggs.get(cat, {"insufficient": True, "instances": 0, "subs": 0})
        s["trade_rel"] = trade_rel_aggs.get(cat, {"insufficient": True, "subs": 0})
        # Convenience flags consumed by the JS row renderer
        s["dur_insufficient"] = bool(
            s["trade_dur"].get("insufficient")
            or sub_median is None
            or len(own_samples) < PHASE6_SUB_DURATION_MIN_INSTANCES
        )
        s["rel_insufficient"] = bool(
            s["trade_rel"].get("insufficient")
            or s.get("reliability_pct") is None
        )

    return {
        "subs": out_subs,
        "overlap_concerns": overlap,
        "categories": categories,
        "phase_benchmarks": phase_benchmarks,
        "trade_aggregates": {
            "duration": trade_dur_aggs,
            "reliability": trade_rel_aggs,
        },
        "portfolio": {
            "total_subs": len(out_subs),
            "active_30d": active_30d,
            "total_absences_30d": total_abs_30d,
            "overlap_count": len(overlap),
            "category_count": len(categories),
        },
    }


def _attach_daily_log_stats(pm: str, binder: dict, today: date) -> None:
    """Compute fresh per-job daily-log stats and inject under binder['dailyLogStats'].

    Uses fetch_for_pm at render time so the panel reflects live BT data, not the
    point-in-time snapshot embedded in the binder JSON. Window is anchored to
    today (not the binder's meeting date) so the panel always shows current
    site reality. Adds weekday-aware business-day counts (excluding US federal
    holidays) on top of the calendar gap_days that fetch_for_pm already returns.
    """
    daily = fetch_for_pm(pm, today.isoformat(), lookback_days=14)
    meta = (daily or {}).get("meta", {}) or {}
    summary = (daily or {}).get("summary", {}) or {}
    raw = (daily or {}).get("raw_entries", []) or []

    if meta.get("error") or not summary:
        binder["dailyLogStats"] = {}
        binder["dailyLogStatsMeta"] = {
            "error": meta.get("error", "no daily-log data"),
            "stale": meta.get("stale", False),
        }
        return

    # Group logged dates by short_name from raw_entries
    dates_by_job: dict[str, set[date]] = {}
    for e in raw:
        job = e.get("job")
        ds = e.get("date")
        if not (job and ds):
            continue
        try:
            dates_by_job.setdefault(job, set()).add(date.fromisoformat(ds))
        except ValueError:
            continue

    try:
        ws = date.fromisoformat(meta["window_start"])
        we = date.fromisoformat(meta["window_end"])
    except (KeyError, ValueError, TypeError):
        ws = we = None

    holidays_set: set[date] = set()
    biz_days: list[date] = []
    if ws and we:
        years = list(range(ws.year, we.year + 1))
        holidays_set = set(_holidays_pkg.country_holidays("US", years=years).keys())
        cursor = ws
        while cursor <= we:
            if cursor.weekday() < 5 and cursor not in holidays_set:
                biz_days.append(cursor)
            cursor += timedelta(days=1)

    enriched: dict[str, dict] = {}
    for short_name, s in summary.items():
        s_out = dict(s)
        # Skip weekday-count enrichment for jobs with no scraper records — they
        # already carry a `note` and the JS renders them as an empty card.
        if not s.get("note") and biz_days:
            logged = dates_by_job.get(short_name, set())
            missed = [d.isoformat() for d in biz_days if d not in logged]
            s_out["business_days_in_window"] = len(biz_days)
            s_out["business_days_logged"] = len(biz_days) - len(missed)
            s_out["missed_business_days"] = missed
            if logged:
                last = max(logged)
                s_out["last_log_date"] = last.isoformat()
                s_out["last_log_age_days"] = (today - last).days
            else:
                s_out["last_log_date"] = None
                s_out["last_log_age_days"] = None
        enriched[short_name] = s_out

    binder["dailyLogStats"] = enriched
    binder["dailyLogStatsMeta"] = {
        "window_start": meta.get("window_start"),
        "window_end": meta.get("window_end"),
        "stale": meta.get("stale", False),
        "age_hours": meta.get("age_hours"),
    }


# ===========================================================================
# Phase 4 — Per-PM packet rendering
#
# Splits the Monday output into two products:
#   - monday-binder.html (Jake's binder, unchanged) — full company-wide analytics
#   - pm-packet-{slug}.html (one per PM) — scoped to their jobs only, no analytics
#
# render_pm_packet() emits a self-contained static HTML file (no JS). It reuses
# the shared CSS via the module-level CSS variable so the visual layer stays
# in sync with monday-binder.html. The Email button (email_sender.py) prints
# the packet HTML through CDP for the per-PM PDF.
# ===========================================================================

PM_PACKET_OUTPUT = SCRIPT_DIR  # packets land alongside monday-binder.html

# Phase tags that suppress the missed-logs alert on the cover. A job in
# closeout / pre-active / post-CO punch isn't expected to generate daily logs,
# so showing "missed N weekdays" against a PM for those jobs is just noise.
MISSED_LOGS_SUPPRESS_TAGS = (
    "CLOSEOUT", "POST-CO", "CO DELIVERED",
    "PRE-CONSTRUCTION", "PRE-ACTIVE", "SCHEDULE BASELINE",
    "FOUNDATION / EARLY FRAMING",
)


def _pm_slug(pm: str) -> str:
    """nelson-belanger from 'Nelson Belanger'."""
    return re.sub(r"[^a-z0-9]+", "-", pm.lower()).strip("-")


def _esc(s) -> str:
    """Minimal HTML escape — packet templates assemble strings, not jinja."""
    if s is None:
        return ""
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _phase_tag_suppresses_missed_logs(phase: str) -> bool:
    p = (phase or "").upper()
    return any(tag in p for tag in MISSED_LOGS_SUPPRESS_TAGS)


def _fmt_meeting_date(iso: str) -> str:
    """2026-04-23 -> 'Mon · Apr 23, 2026'. Built by parts because Windows
    strftime can't handle non-ASCII chars in the format string."""
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return f"{d.strftime('%a')} \u00b7 {d.strftime('%b')} {d.day}, {d.year}"


def _fmt_short_date(iso) -> str:
    """2026-04-23 -> 'Apr 23'. No leading zero on day, cross-platform."""
    if not iso:
        return ""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return f"{d.strftime('%b')} {d.day}"


def _pm_dashboard_counts(pm: str, binder: dict, today: date) -> dict:
    """Open / urgent / stale / PPC counts scoped to this PM only."""
    open_n = urgent = stale_n = done_n = 0
    for item in (binder.get("items") or []):
        status = _norm_status(item.get("status", ""))
        if status in CLOSED_STATUSES:
            if status == "COMPLETE":
                done_n += 1
            continue
        open_n += 1
        if (item.get("priority") or "").upper() == "URGENT":
            urgent += 1
        if _aging_flag(item, today) in ("stale", "abandoned"):
            stale_n += 1
    total = open_n + done_n
    ppc = int(round(100 * done_n / total)) if total else 0
    return {"open": open_n, "urgent": urgent, "stale": stale_n, "ppc": ppc}


# ---- Section renderers ----------------------------------------------------

def _render_cover(pm: str, binder: dict, jobs_data: dict, today: date,
                  generated_at: str) -> str:
    meta = binder.get("meta", {}) or {}
    meeting_date = _fmt_meeting_date(meta.get("date", ""))
    week = meta.get("week")
    mtype = (meta.get("type") or "").lower()
    type_tag = "Site meeting" if mtype == "site" else "Office meeting"

    pm_jobs = [j.get("name") for j in (binder.get("jobs") or []) if j.get("name")]
    jobs_inline = '<span class="sep">·</span>'.join(_esc(n) for n in pm_jobs) or "—"

    counts = _pm_dashboard_counts(pm, binder, today)
    urgent_cls = " accent" if counts["urgent"] > 0 else ""

    return f"""
<section class="cover">
  <div class="brand-mark">Ross Built · {_esc(pm.upper())} · Weekly</div>
  <h1>Production · {hint('Week')} {_esc(week or '')}</h1>
  <div class="meeting-meta">{_esc(meeting_date)} &nbsp;·&nbsp; {_esc(type_tag)}</div>
  <div class="jobs-line">{jobs_inline}</div>
  <div class="stat-row">
    <div class="stat-tile"><span class="num">{counts['open']}</span><span class="lbl">{hint('Open items')}</span></div>
    <div class="stat-tile{urgent_cls}"><span class="num">{counts['urgent']}</span><span class="lbl">{hint('Urgent')}</span></div>
    <div class="stat-tile"><span class="num">{counts['stale']}</span><span class="lbl">{hint('Stale 14d+')}</span></div>
    <div class="stat-tile"><span class="num">{counts['ppc']}%</span><span class="lbl">{hint('PPC')}</span></div>
  </div>
  <div class="gen-line">Generated {_esc(generated_at)}</div>
</section>
"""


def _render_missed_logs(pm: str, binder: dict, jobs_data: dict) -> str:
    """Conditional: only render if PM has missed logs on at least one
    actively-producing job. Returns "" to skip."""
    pf = (jobs_data or {}).get("__portfolio__", {}) or {}
    pm_missed = (pf.get("pm_missed") or {}).get(pm) or {}
    per_job = pm_missed.get("per_job") or []
    if not per_job:
        return ""

    pm_jobs_meta = {j.get("name"): j for j in (binder.get("jobs") or []) if j.get("name")}

    qualifying = []
    for entry in per_job:
        short = entry.get("short_name")
        recent = int(entry.get("current_month_missed") or 0)
        if recent <= 0:
            continue
        meta = pm_jobs_meta.get(short) or {}
        phase = meta.get("phase") or ""
        if _phase_tag_suppresses_missed_logs(phase):
            continue
        # Also drop very-low-progress (<10%) or very-high-progress (>95%) inferred
        # from the phase tag — already covered above for the canonical tags, this
        # is just belt-and-suspenders for ad-hoc phase strings.
        qualifying.append({"short": short, "recent": recent, "phase": phase})

    if not qualifying:
        return ""

    rows = "".join(
        f'<li><strong>{_esc(q["short"])}</strong> — {q["recent"]} missed weekday(s) this month '
        f'<span class="muted">· {_esc(q["phase"])}</span></li>'
        for q in qualifying
    )
    total = sum(q["recent"] for q in qualifying)
    return f"""
<section class="missed-logs">
  <div class="missed-banner">
    <h3>{hint('Missed daily logs')} — {total} weekday(s) this month</h3>
    <ul>{rows}</ul>
  </div>
</section>
"""


def _render_open_items(pm: str, binder: dict, today: date) -> str:
    items = [i for i in (binder.get("items") or [])
             if _norm_status(i.get("status", "")) not in CLOSED_STATUSES]
    if not items:
        return ""

    # Group by job
    by_job: dict[str, list[dict]] = {}
    for it in items:
        by_job.setdefault(it.get("job") or "—", []).append(it)

    # Sort each job's items: URGENT > HIGH > NORMAL, then by due date
    def prio_rank(p):
        return {"URGENT": 0, "HIGH": 1, "NORMAL": 2}.get((p or "NORMAL").upper(), 3)
    for j, lst in by_job.items():
        lst.sort(key=lambda i: (prio_rank(i.get("priority")), i.get("due") or "9999"))

    # Job order: follow binder.jobs order
    pm_job_order = [j.get("name") for j in (binder.get("jobs") or []) if j.get("name")]
    ordered = [j for j in pm_job_order if j in by_job] + [j for j in by_job if j not in pm_job_order]

    blocks = []
    for job in ordered:
        cards = []
        for it in by_job[job]:
            prio = (it.get("priority") or "NORMAL").upper()
            prio_cls = ""
            prio_pill = ""
            if prio == "URGENT":
                prio_cls = "priority-urgent"
                prio_pill = f'<span class="pill pill-urgent">{hint("Urgent")}</span>'
            elif prio == "HIGH":
                prio_cls = "priority-high"
                prio_pill = f'<span class="pill">{hint("High")}</span>'
            stale_pill = ""
            if _aging_flag(it, today) in ("stale", "abandoned"):
                stale_pill = f'<span class="pill pill-stale">{hint("14d+")}</span>'
            ctx = it.get("update") or ""
            ctx_html = f'<div class="item-context">{_esc(ctx)}</div>' if ctx else ""
            cards.append(f"""
<div class="item">
  <span class="checkbox"></span>
  <span class="id">{_esc(it.get('id') or '')}</span>
  {prio_pill} {stale_pill}
  <span class="{prio_cls}"></span>
  <div class="item-action">{_esc(it.get('action') or '')}</div>
  <div class="item-meta">
    Owner {_esc(it.get('owner') or '—')} ·
    Due {_esc(_fmt_short_date(it.get('due')) or '—')} ·
    Opened {_esc(_fmt_short_date(it.get('opened')) or '—')}
  </div>
  {ctx_html}
</div>""")
        blocks.append(f"""
<div class="job-group">
  <h3>{_esc(job)}</h3>
  {''.join(cards)}
</div>""")

    return f"""
<section class="open-items">
  <header>
    <h2>Open items</h2>
    <span class="eyebrow">{len(items)} active</span>
  </header>
  {''.join(blocks)}
</section>
"""


def _render_lookahead(pm: str, binder: dict) -> tuple[str, dict]:
    """Single unified table merging w2/w4/w8 buckets.

    Auto-drops Confirm-by and Sub columns when no item carries data — never
    ships a column of blanks. Status is always shown (PM marks it during the
    week). Returns (html, meta) where meta carries row count and column flags
    for verification output.
    """
    la = binder.get("lookAhead") or {}
    rows: list[dict] = []
    bucket_label = {
        "w2": ("Next 2 weeks", 0),
        "w4": ("Within 30 days", 1),
        "w8": ("30+ days", 2),
    }
    for key in ("w2", "w4", "w8"):
        for it in (la.get(key) or []):
            if not isinstance(it, dict):
                continue
            label, order = bucket_label[key]
            rows.append({
                "task": it.get("text") or "",
                "job": it.get("job") or "",
                "window": label,
                "window_order": order,
                "confirm_by": it.get("confirm_by") or it.get("confirmBy") or "",
                "sub": it.get("sub") or "",
            })

    if not rows:
        return "", {"rows": 0, "confirm_by": False, "sub": False}

    rows.sort(key=lambda r: (r["window_order"],
                             r.get("confirm_by") or "9999-99-99",
                             r.get("job") or ""))

    show_confirm = any((r["confirm_by"] or "").strip() for r in rows)
    show_sub = any((r["sub"] or "").strip() for r in rows)

    # Column widths — redistribute when optional columns drop so the remaining
    # columns breathe instead of clinging to the original 7-col proportions.
    col_widths = {
        "cb": "3%",
        "task": "44%",
        "job": "11%",
        "window": "11%",
        "confirm": "10%",
        "sub": "9%",
        "status": "12%",
    }
    if not show_confirm and not show_sub:
        col_widths.update({"task": "55%", "job": "13%", "window": "12%", "status": "17%"})
    elif not show_confirm:
        col_widths.update({"task": "50%", "job": "12%", "window": "12%", "sub": "10%", "status": "13%"})
    elif not show_sub:
        col_widths.update({"task": "48%", "job": "12%", "window": "12%", "confirm": "11%", "status": "14%"})

    headers = [
        f'<th style="width:{col_widths["cb"]}"></th>',
        f'<th style="width:{col_widths["task"]}">Task</th>',
        f'<th style="width:{col_widths["job"]}">Job</th>',
        f'<th style="width:{col_widths["window"]}">{hint("Window")}</th>',
    ]
    if show_confirm:
        headers.append(f'<th style="width:{col_widths["confirm"]}">{hint("Confirm-by")}</th>')
    if show_sub:
        headers.append(f'<th style="width:{col_widths["sub"]}">Sub</th>')
    headers.append(f'<th style="width:{col_widths["status"]}">Status</th>')

    body_rows = []
    for r in rows:
        cells = [
            '<td class="cb"><span class="checkbox"></span></td>',
            f'<td>{_esc(r["task"])}</td>',
            f'<td>{_esc(r["job"])}</td>',
            f'<td><span class="window-pill">{_esc(r["window"])}</span></td>',
        ]
        if show_confirm:
            cells.append(f'<td>{_esc(_fmt_short_date(r["confirm_by"]) or "")}</td>')
        if show_sub:
            cells.append(f'<td>{_esc(r["sub"])}</td>')
        cells.append('<td><span class="status-line"></span></td>')
        body_rows.append(f'<tr>{"".join(cells)}</tr>')

    html = f"""
<section class="lookahead">
  <header>
    <h2>Look-ahead</h2>
    <span class="eyebrow">{len(rows)} item(s)</span>
  </header>
  <table class="lookahead">
    <thead><tr>{''.join(headers)}</tr></thead>
    <tbody>{''.join(body_rows)}</tbody>
  </table>
</section>
"""
    return html, {"rows": len(rows), "confirm_by": show_confirm, "sub": show_sub}


def _render_issues(pm: str, binder: dict) -> str:
    issues = binder.get("issues") or []
    if not issues:
        return ""
    rows = []
    for it in issues:
        if not isinstance(it, dict):
            continue
        tag = it.get("type") or "Note"
        rows.append(f"""
<div class="note-line">
  <span class="tag">{_esc(tag)}</span>{_esc(it.get('text') or '')}
</div>""")
    if not rows:
        return ""
    return f"""
<section class="issues">
  <header>
    <h2>Issues</h2>
    <span class="eyebrow">{len(rows)}</span>
  </header>
  {''.join(rows)}
</section>
"""


def _render_financial(pm: str, binder: dict) -> str:
    fin = binder.get("financial") or []
    rows = []
    for it in fin:
        if not isinstance(it, dict):
            continue
        text = (it.get("text") or "").strip()
        if not text:
            continue
        # Drop placeholder lines like "pre-steel, no cost events" — noise.
        low = text.lower()
        if any(p in low for p in ("no cost events", "no events to report", "no financial events")):
            continue
        rows.append(f'<div class="note-line">{_esc(text)}</div>')
    if not rows:
        return ""
    return f"""
<section class="financial">
  <header>
    <h2>Financial</h2>
    <span class="eyebrow">{len(rows)}</span>
  </header>
  {''.join(rows)}
</section>
"""


def _render_workforce_histogram(monthly: list[dict], job_color: str) -> str:
    """Static SVG version of the JS renderWorkforceHistogram. Same proportions."""
    if not monthly:
        return ""
    w, h = 720, 130
    pad_l, pad_r, pad_t, pad_b = 30, 10, 14, 22
    inner_w = w - pad_l - pad_r
    inner_h = h - pad_t - pad_b
    max_v = max(1, max((m.get("person_days") or 0) for m in monthly))
    bar_gap = 2
    bar_w = inner_w / len(monthly) - bar_gap

    y_ticks = []
    for v in (0, round(max_v / 2), max_v):
        y = pad_t + inner_h - (v / max_v) * inner_h
        y_ticks.append(
            f'<line x1="{pad_l}" x2="{w - pad_r}" y1="{y:.1f}" y2="{y:.1f}" '
            f'stroke="rgba(59,88,100,0.15)" stroke-width="0.5"/>'
            f'<text x="{pad_l - 4}" y="{y + 3:.1f}" text-anchor="end" font-size="9" '
            f'fill="rgba(59,88,100,0.55)" font-family="JetBrains Mono, monospace">{v}</text>'
        )

    bars = []
    for i, m in enumerate(monthly):
        v = m.get("person_days") or 0
        x = pad_l + i * (bar_w + bar_gap)
        bar_h = (v / max_v) * inner_h
        y = pad_t + inner_h - bar_h
        label = m.get("label") or ""
        show_axis_label = (i == 0 or i == len(monthly) - 1 or i % 2 == 0)
        val_label = ""
        if v > 0 and bar_h > 14:
            val_label = (
                f'<text x="{x + bar_w / 2:.1f}" y="{y - 3:.1f}" text-anchor="middle" '
                f'font-size="9" fill="rgba(59,88,100,0.7)" '
                f'font-family="JetBrains Mono, monospace">{v}</text>'
            )
        axis_label = ""
        if show_axis_label and label:
            axis_label = (
                f'<text x="{x + bar_w / 2:.1f}" y="{h - 6}" text-anchor="middle" '
                f'font-size="9" fill="rgba(59,88,100,0.55)" '
                f'font-family="JetBrains Mono, monospace">{_esc(label)}</text>'
            )
        opacity = 0.9 if v else 0.15
        bars.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
            f'fill="{job_color}" opacity="{opacity}"/>{val_label}{axis_label}'
        )

    return f"""
<figure class="histogram">
  <figcaption>Workforce · {hint('Person-days')} per month (last {len(monthly)} mo)</figcaption>
  <svg viewBox="0 0 {w} {h}" preserveAspectRatio="xMidYMid meet">
    {''.join(y_ticks)}
    {''.join(bars)}
  </svg>
</figure>
"""


def _render_job_page(job_meta: dict, job_data: dict, today: date) -> str:
    """One full page per job: header, stat tiles, sparkline, top-5 subs,
    active phases, latest events. Page-break-before: always."""
    short = job_meta.get("name") or ""
    address = job_meta.get("address") or ""
    phase = job_meta.get("phase") or ""
    target_co = job_meta.get("targetCO") or ""
    job_color = JOB_COLORS.get(short, "#5B8699")

    is_dormant_or_closeout = _phase_tag_suppresses_missed_logs(phase)

    if not job_data:
        # No daily-log lifetime data for this job (e.g., Biales 2026 — no
        # scraper records yet). Still render a minimal page so the PM sees it.
        target_line = f" · CO target {_esc(_fmt_short_date(target_co))}" if target_co else ""
        return f"""
<section class="job-page">
  <header>
    <h2>{_esc(short)}</h2>
    <div class="meta-line">{_esc(address)} · {_esc(phase)}{target_line}</div>
  </header>
  <p class="no-active-line">No daily-log records yet — job is in {_esc(phase) or 'pre-active'}.</p>
</section>
"""

    lifetime = job_data.get("lifetime", {}) or {}
    last_age = lifetime.get("last_log_age_days")
    last_age_pill = ""
    if not is_dormant_or_closeout and isinstance(last_age, int) and last_age > 3:
        last_age_pill = f'<span class="pill-stale-3">{last_age}d</span>'
    last_log_text = lifetime.get("last_log") or "—"
    if last_log_text and last_log_text != "—":
        last_log_text = _fmt_short_date(last_log_text)

    target_line = f" · CO target {_esc(_fmt_short_date(target_co))}" if target_co else ""

    # Top 5 subs by days
    top5 = (job_data.get("top_crews") or [])[:5]
    sub_tiles = "".join(
        f'<div class="sub-tile"><span class="sub-name">{_esc(s.get("name"))}</span>'
        f'<span class="sub-days">{s.get("days")} day(s)</span></div>'
        for s in top5
    ) or '<div class="sub-tile muted">No crew records.</div>'

    # Active phases — substantial bursts that are ongoing OR last activity < 14d
    phases = job_data.get("phase_durations") or []
    active = []
    for p in phases:
        if p.get("ongoing"):
            active.append(p)
            continue
        last = p.get("last")
        if last:
            try:
                last_d = date.fromisoformat(last)
                if (today - last_d).days <= 14:
                    active.append(p)
            except ValueError:
                pass

    if active:
        active_rows = []
        for p in active:
            subs = p.get("top_subs") or []
            sub_text = ", ".join(_esc(s.get("name")) for s in subs[:3])
            if len(subs) > 3:
                sub_text += f' <span class="muted">+{len(subs) - 3} more</span>'
            dur = p.get("duration_days")
            dur_text = f"{dur}d" if dur else f"{p.get('active_days', 0)}d active"
            ongoing_pill = (f'<span class="status-pill ongoing">{hint("Ongoing")}</span>'
                            if p.get("ongoing")
                            else f'<span class="status-pill">Recent</span>')
            active_rows.append(f"""
<tr>
  <td>{_esc(p.get('name'))}</td>
  <td>{_esc(_fmt_short_date(p.get('first')))}</td>
  <td>{dur_text}</td>
  <td>{ongoing_pill}</td>
  <td>{sub_text}</td>
</tr>""")
        active_html = f"""
<table class="phase-active">
  <thead><tr>
    <th>Phase</th><th>Started</th><th>Duration</th><th>Status</th><th>Top subs</th>
  </tr></thead>
  <tbody>{''.join(active_rows)}</tbody>
</table>
"""
    else:
        active_html = f'<p class="no-active-line">No active phases — job is in {_esc(phase) or "—"}.</p>'

    # Latest events — Delivery / Inspection / Notable, one row each (most recent only)
    deliveries = job_data.get("delivery_events") or []
    inspections = job_data.get("inspection_events") or []
    notables = job_data.get("notable_events") or []
    event_rows = []
    if deliveries:
        e = deliveries[0]
        event_rows.append(
            f'<div class="row"><span class="tag">Delivery</span>'
            f'<span class="when">{_esc(_fmt_short_date(e.get("date")))}</span>'
            f'{_esc(e.get("details"))}</div>'
        )
    if inspections:
        e = inspections[0]
        event_rows.append(
            f'<div class="row"><span class="tag">Inspection</span>'
            f'<span class="when">{_esc(_fmt_short_date(e.get("date")))}</span>'
            f'{_esc(e.get("details"))}</div>'
        )
    if notables:
        e = notables[0]
        event_rows.append(
            f'<div class="row"><span class="tag">Notable</span>'
            f'<span class="when">{_esc(_fmt_short_date(e.get("date")))}</span>'
            f'{_esc(e.get("text"))}</div>'
        )

    events_html = ""
    if event_rows:
        events_html = f"""
<div class="events-block">
  <h3>Latest events</h3>
  {''.join(event_rows)}
</div>
"""

    avg = lifetime.get("avg_workforce") or 0
    peak = lifetime.get("peak_workforce") or 0

    return f"""
<section class="job-page">
  <header>
    <h2>{_esc(short)}</h2>
    <div class="meta-line">{_esc(address)} · {_esc(phase)}{target_line}</div>
  </header>
  <div class="job-stats">
    <div class="tile"><span class="num">{lifetime.get('total_days', 0)}</span><span class="lbl">{hint('Log-days')}</span></div>
    <div class="tile"><span class="num">{lifetime.get('total_person_days', 0)}</span><span class="lbl">{hint('Person-days')}</span></div>
    <div class="tile"><span class="num">{avg}</span><span class="lbl">{hint('Avg crew')} · peak {peak}</span></div>
    <div class="tile"><span class="num">{_esc(last_log_text)}</span><span class="lbl">{hint('Last log')} {last_age_pill}</span></div>
  </div>
  {_render_workforce_histogram(job_data.get('monthly') or [], job_color)}
  <div class="eyebrow" style="margin-top:8pt">Top 5 subs · days on site</div>
  <div class="subs-strip">{sub_tiles}</div>
  <div class="eyebrow">{hint('Active')} phases</div>
  {active_html}
  {events_html}
</section>
"""


# ---- Top-level render -----------------------------------------------------

PM_PACKET_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{TITLE}</title>
<style>
{CSS}
{PACKET_CSS}
</style>
</head>
<body>
<main class="packet">
{BODY}
</main>
</body>
</html>
"""


PM_PACKET_CSS = r"""
/* ─────────────  Phase 4 — PM packet overrides (static print)  ───────────── */

body { background: #ffffff; color: var(--slate-tile); font-size: 10pt; line-height: 1.45; }
main.packet {
  max-width: 7.4in; margin: 0 auto;
  padding: 0.4in 0.5in 0.5in 0.5in;
}

.packet section { margin: 0 0 16pt 0; padding: 0; border: none; background: transparent; }
.packet section > header {
  display: flex; align-items: baseline; justify-content: space-between;
  border-bottom: 1.25pt solid var(--slate-tile);
  padding-bottom: 4pt; margin-bottom: 10pt;
}
.packet section > header h2 {
  font-family: var(--font-display); font-size: 16pt; font-weight: 500;
  margin: 0; letter-spacing: -0.01em;
}
.packet .eyebrow {
  font-family: var(--font-mono); font-size: 8.5pt;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: rgba(59, 88, 100, 0.55); font-weight: 500;
}
.packet h1, .packet h2, .packet h3, .packet h4 {
  font-family: var(--font-display); font-weight: 500;
  letter-spacing: -0.01em; color: var(--slate-tile);
}

/* Cover */
.cover { padding: 0; margin: 0 0 22pt 0; border: none; }
.cover .brand-mark {
  font-family: var(--font-mono); font-weight: 600; font-size: 10pt;
  letter-spacing: 0.16em; text-transform: uppercase;
  color: var(--stone-blue); margin-bottom: 14pt;
}
.cover h1 {
  font-size: 26pt; line-height: 1.1; margin: 0 0 6pt 0;
}
.cover .meeting-meta { font-size: 11pt; color: rgba(59, 88, 100, 0.75); margin-bottom: 4pt; }
.cover .jobs-line { font-size: 11pt; color: var(--slate-tile); margin-bottom: 14pt; }
.cover .jobs-line .sep { color: rgba(59, 88, 100, 0.35); padding: 0 6pt; }
.cover .stat-row {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 8pt;
  margin: 12pt 0 8pt 0;
}
.cover .stat-tile {
  border: 0.75pt solid rgba(59, 88, 100, 0.25);
  padding: 8pt 10pt;
}
.cover .stat-tile .num {
  font-family: var(--font-display); font-size: 22pt; font-weight: 500;
  letter-spacing: -0.02em; line-height: 1; display: block;
}
.cover .stat-tile.accent .num { color: var(--danger); }
.cover .stat-tile .lbl {
  font-family: var(--font-mono); font-size: 8pt; letter-spacing: 0.14em;
  text-transform: uppercase; color: rgba(59, 88, 100, 0.55);
  margin-top: 4pt; display: block;
}
.cover .gen-line {
  font-family: var(--font-mono); font-size: 8pt; color: rgba(59, 88, 100, 0.55);
  letter-spacing: 0.1em; text-transform: uppercase;
  text-align: right; margin-top: 18pt;
}

/* Item card */
.item {
  border: 0.75pt solid rgba(59, 88, 100, 0.20);
  padding: 8pt 10pt; margin-bottom: 6pt;
  page-break-inside: avoid;
}
.item .checkbox {
  display: inline-block; width: 10pt; height: 10pt;
  border: 1pt solid var(--slate-tile);
  margin-right: 6pt; vertical-align: middle;
}
.item .id {
  font-family: var(--font-mono); font-size: 8pt; letter-spacing: 0.1em;
  color: rgba(59, 88, 100, 0.55); margin-right: 6pt;
}
.item .pill {
  display: inline-block; font-family: var(--font-mono); font-size: 7.5pt;
  padding: 1pt 5pt; border: 0.5pt solid rgba(59, 88, 100, 0.4);
  letter-spacing: 0.08em; text-transform: uppercase; margin-right: 4pt;
}
.item .pill-stale { border-color: var(--warn); color: var(--warn); }
.item .pill-urgent { border-color: var(--danger); color: var(--danger); }
.item .item-action { margin: 4pt 0 2pt 0; font-size: 10pt; }
.item .item-meta {
  font-family: var(--font-mono); font-size: 8pt;
  color: rgba(59, 88, 100, 0.55); letter-spacing: 0.04em;
}
.item .item-context {
  font-style: italic; font-size: 9pt; color: rgba(59, 88, 100, 0.7);
  margin-top: 4pt;
}

.job-group { margin-bottom: 12pt; }
.job-group h3 {
  font-size: 12.5pt; margin: 0 0 6pt 0;
  border-bottom: 0.5pt dashed rgba(59, 88, 100, 0.25);
  padding-bottom: 2pt;
}

/* Look-ahead */
table.lookahead {
  width: 100%; border-collapse: collapse; font-size: 9pt; margin-top: 4pt;
  table-layout: fixed;
}
table.lookahead th {
  font-family: var(--font-mono); font-size: 7.5pt; font-weight: 500;
  letter-spacing: 0.1em; text-transform: uppercase;
  color: rgba(59, 88, 100, 0.6);
  border-bottom: 1pt solid var(--slate-tile);
  padding: 4pt 5pt; text-align: left;
}
table.lookahead td {
  padding: 5pt; border-bottom: 0.4pt solid rgba(59, 88, 100, 0.15);
  vertical-align: top; page-break-inside: avoid; word-wrap: break-word;
}
table.lookahead td.cb { width: 16pt; text-align: center; }
table.lookahead .checkbox {
  display: inline-block; width: 9pt; height: 9pt;
  border: 0.75pt solid var(--slate-tile);
}
table.lookahead .window-pill {
  font-family: var(--font-mono); font-size: 7pt; padding: 1pt 4pt;
  border: 0.5pt solid rgba(59, 88, 100, 0.35);
  letter-spacing: 0.08em; text-transform: uppercase; white-space: nowrap;
}
table.lookahead .status-line {
  border-bottom: 0.5pt solid rgba(59, 88, 100, 0.4);
  display: inline-block; width: 100%; min-width: 1in;
}

/* Missed logs banner */
.missed-banner {
  border: 1pt solid var(--warn); background: rgba(201, 138, 59, 0.05);
  padding: 8pt 10pt; margin-bottom: 14pt;
}
.missed-banner h3 {
  margin: 0 0 4pt 0; font-size: 12pt; color: var(--warn);
  border: none;
}
.missed-banner ul { margin: 4pt 0 0 16pt; padding: 0; font-size: 9pt; }
.missed-banner .muted { color: rgba(59, 88, 100, 0.55); }

/* Issues / Financial */
.note-line {
  padding: 6pt 0; border-bottom: 0.4pt solid rgba(59, 88, 100, 0.15);
  font-size: 9.5pt;
}
.note-line:last-child { border-bottom: none; }
.note-line .tag {
  font-family: var(--font-mono); font-size: 7.5pt; letter-spacing: 0.1em;
  text-transform: uppercase; color: rgba(59, 88, 100, 0.5);
  margin-right: 6pt;
}

/* Jobs at a glance — one page per job */
.job-page { page-break-before: always; margin: 0; }
.job-page > header {
  display: block; border-bottom: 1.25pt solid var(--slate-tile);
  padding-bottom: 4pt; margin-bottom: 10pt;
}
.job-page > header h2 {
  font-size: 18pt; margin: 0; font-weight: 500;
}
.job-page > header .meta-line {
  font-size: 9.5pt; color: rgba(59, 88, 100, 0.7); margin-top: 2pt;
}
.job-stats {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 6pt;
  margin: 8pt 0 12pt 0;
}
.job-stats .tile {
  border: 0.75pt solid rgba(59, 88, 100, 0.25);
  padding: 6pt 8pt;
}
.job-stats .tile .num {
  font-family: var(--font-display); font-size: 17pt; font-weight: 500;
  line-height: 1; letter-spacing: -0.02em; display: block;
}
.job-stats .tile .lbl {
  font-family: var(--font-mono); font-size: 7.5pt; letter-spacing: 0.12em;
  text-transform: uppercase; color: rgba(59, 88, 100, 0.55);
  margin-top: 4pt; display: block;
}
.job-stats .pill-stale-3 {
  display: inline-block; margin-left: 4pt;
  font-family: var(--font-mono); font-size: 7pt;
  border: 0.5pt solid var(--warn); color: var(--warn);
  padding: 0pt 3pt; letter-spacing: 0.06em; text-transform: uppercase;
}
.histogram { margin: 10pt 0; page-break-inside: avoid; }
.histogram figcaption {
  font-family: var(--font-mono); font-size: 7.5pt;
  letter-spacing: 0.12em; text-transform: uppercase;
  color: rgba(59, 88, 100, 0.55); margin-bottom: 4pt;
}
.histogram svg { width: 100%; height: 110px; display: block; }
.subs-strip {
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 6pt;
  margin: 6pt 0 12pt 0;
}
.subs-strip .sub-tile {
  border: 0.5pt solid rgba(59, 88, 100, 0.2);
  padding: 5pt 6pt;
}
.subs-strip .sub-name { font-size: 9pt; line-height: 1.2; display: block; word-break: break-word; }
.subs-strip .sub-days {
  font-family: var(--font-mono); font-size: 8pt;
  color: rgba(59, 88, 100, 0.6); letter-spacing: 0.05em;
  margin-top: 2pt; display: block;
}
table.phase-active {
  width: 100%; border-collapse: collapse; font-size: 9pt;
  margin: 6pt 0 12pt 0;
}
table.phase-active th, table.phase-active td {
  padding: 4pt 6pt; border-bottom: 0.4pt solid rgba(59, 88, 100, 0.15);
  vertical-align: top; text-align: left;
}
table.phase-active th {
  font-family: var(--font-mono); font-size: 7.5pt; font-weight: 500;
  letter-spacing: 0.1em; text-transform: uppercase;
  color: rgba(59, 88, 100, 0.6);
  border-bottom: 1pt solid var(--slate-tile);
}
table.phase-active .status-pill {
  font-family: var(--font-mono); font-size: 7pt; padding: 1pt 4pt;
  border: 0.5pt solid rgba(59, 88, 100, 0.4);
  letter-spacing: 0.08em; text-transform: uppercase;
}
table.phase-active .status-pill.ongoing {
  border-color: var(--success); color: var(--success);
}
.events-block { margin-top: 8pt; }
.events-block h3 { font-size: 11pt; margin: 0 0 4pt 0; border: none; }
.events-block .row {
  font-size: 9pt; padding: 3pt 0;
  border-bottom: 0.4pt solid rgba(59, 88, 100, 0.15);
}
.events-block .row .tag {
  font-family: var(--font-mono); font-size: 7.5pt; letter-spacing: 0.1em;
  text-transform: uppercase; color: rgba(59, 88, 100, 0.55);
  display: inline-block; min-width: 70pt;
}
.events-block .row .when {
  font-family: var(--font-mono); font-size: 8pt;
  color: rgba(59, 88, 100, 0.55); margin-right: 6pt;
}
.no-active-line {
  font-style: italic; font-size: 9.5pt;
  color: rgba(59, 88, 100, 0.6); margin: 6pt 0 12pt 0;
}

/* Print + page chrome (overrides the binder's @page block — last rule wins) */
@page {
  size: letter;
  margin: 0.55in 0.5in 0.5in 0.5in;
  @top-left {
    content: "PACKET_HEADER_LEFT_PLACEHOLDER";
    font-family: "JetBrains Mono", monospace;
    font-size: 7.5pt; letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(59, 88, 100, 0.55);
    padding-bottom: 3pt;
  }
  @top-right {
    content: counter(page) " / " counter(pages);
    font-family: "JetBrains Mono", monospace;
    font-size: 7.5pt; letter-spacing: 0.1em;
    color: rgba(59, 88, 100, 0.55);
    padding-bottom: 3pt;
  }
  @bottom-center {
    content: "PACKET_FOOTER_PLACEHOLDER";
    font-family: "JetBrains Mono", monospace;
    font-size: 7pt; letter-spacing: 0.08em;
    color: rgba(59, 88, 100, 0.4);
  }
}

@media screen {
  body { background: #f7f5ec; }
  main.packet {
    background: #ffffff;
    margin: 16px auto;
    box-shadow: 0 1px 3px rgba(59, 88, 100, 0.15);
  }
}
"""


def render_pm_packet(pm: str, binder: dict, jobs_data: dict, today: date,
                     generated_at: str) -> tuple[str, dict]:
    """Build a self-contained PM packet HTML.

    Returns (html, verification_meta). Conditional sections (missed-logs,
    issues, financial) are omitted entirely when empty — never ship a
    section heading with no body.
    """
    meta = binder.get("meta", {}) or {}
    meeting_iso = meta.get("date") or today.isoformat()
    meeting_label = _fmt_meeting_date(meeting_iso)

    sections_rendered: list[str] = ["cover"]
    sections_omitted: list[str] = []

    body_parts = [_render_cover(pm, binder, jobs_data, today, generated_at)]

    missed_html = _render_missed_logs(pm, binder, jobs_data)
    if missed_html:
        body_parts.append(missed_html)
        sections_rendered.append("missed-logs")
    else:
        sections_omitted.append("missed-logs")

    open_html = _render_open_items(pm, binder, today)
    if open_html:
        body_parts.append(open_html)
        sections_rendered.append("open-items")
    else:
        sections_omitted.append("open-items")

    la_html, la_meta = _render_lookahead(pm, binder)
    if la_html:
        body_parts.append(la_html)
        sections_rendered.append("look-ahead")
    else:
        sections_omitted.append("look-ahead")

    issues_html = _render_issues(pm, binder)
    if issues_html:
        body_parts.append(issues_html)
        sections_rendered.append("issues")
    else:
        sections_omitted.append("issues")

    financial_html = _render_financial(pm, binder)
    if financial_html:
        body_parts.append(financial_html)
        sections_rendered.append("financial")
    else:
        sections_omitted.append("financial")

    # One page per job
    pm_jobs = (binder.get("jobs") or [])
    job_names = []
    for job_meta in pm_jobs:
        short = job_meta.get("name")
        if not short:
            continue
        job_names.append(short)
        body_parts.append(_render_job_page(job_meta, jobs_data.get(short) or {}, today))

    if pm_jobs:
        sections_rendered.append(f"jobs-at-a-glance ({len(pm_jobs)})")

    body = "\n".join(body_parts)

    # Substitute @page running header / footer (must happen on the CSS string
    # before it's interpolated into the HTML).
    header_left = f"ROSS BUILT · {pm.upper()} WEEKLY · {_fmt_short_date(meeting_iso).upper()}"
    footer = f"Generated {generated_at} · For internal use only"
    packet_css = (PM_PACKET_CSS
                  .replace("PACKET_HEADER_LEFT_PLACEHOLDER", header_left)
                  .replace("PACKET_FOOTER_PLACEHOLDER", footer))

    title = f"{pm} — Weekly Packet · {meeting_label}"
    html = (PM_PACKET_HTML_TEMPLATE
            .replace("{TITLE}", _esc(title))
            .replace("{CSS}", CSS)
            .replace("{PACKET_CSS}", packet_css)
            .replace("{BODY}", body))

    # Verification meta
    open_items = [i for i in (binder.get("items") or [])
                  if _norm_status(i.get("status", "")) not in CLOSED_STATUSES]
    n_urgent = sum(1 for i in open_items if (i.get("priority") or "").upper() == "URGENT")
    n_high = sum(1 for i in open_items if (i.get("priority") or "").upper() == "HIGH")

    verif = {
        "pm": pm,
        "slug": _pm_slug(pm),
        "filename": f"pm-packet-{_pm_slug(pm)}.html",
        "size_kb": len(html.encode("utf-8")) / 1024,
        "estimated_pages": 2 + len(pm_jobs),  # rough: cover/items/look-ahead ~= 2pp + 1pp/job
        "sections_rendered": sections_rendered,
        "sections_omitted": sections_omitted,
        "open_items_total": len(open_items),
        "open_items_urgent": n_urgent,
        "open_items_high": n_high,
        "lookahead_rows": la_meta.get("rows", 0),
        "lookahead_confirm_by": la_meta.get("confirm_by", False),
        "lookahead_sub": la_meta.get("sub", False),
        "issues": len((binder.get("issues") or [])),
        "financial": sum(1 for f in (binder.get("financial") or []) if (f.get("text") or "").strip()),
        "job_pages": job_names,
    }
    return html, verif


def main() -> None:
    today = date.today()

    # Load binders.
    binders: dict[str, dict] = {}
    mtimes: dict[str, datetime] = {}
    for pm in PM_ORDER:
        b, mt = _load_binder(pm)
        if b is None:
            print(f"[WARN] no binder file for {pm} — skipping tab")
            continue
        # Inject fresh per-job daily-log stats from the scraper. Anchored to
        # `today` (not the binder's meeting date) so the panel always shows
        # current site reality. Failure here is non-fatal: the function
        # writes empty dicts and a meta.error message that the JS handles.
        try:
            _attach_daily_log_stats(pm, b, today)
        except Exception as e:
            print(f"[WARN] daily-log stats failed for {pm}: {e}", file=sys.stderr)
            b.setdefault("dailyLogStats", {})
            b.setdefault("dailyLogStatsMeta", {"error": str(e)})
        binders[pm] = b
        mtimes[pm] = mt

    if not binders:
        raise SystemExit("No binders found in " + str(BINDERS_DIR))

    # Fix #12 — analytics computations are wrapped in try/except so any single
    # failure (corrupt scraper file, missing field, library bug) still lets the
    # HTML render with empty fallbacks rather than aborting the whole run.
    try:
        jobs_data = compute_jobs_lifetime_data(binders, today)
    except Exception as e:
        print(f"[ERROR] compute_jobs_lifetime_data failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        jobs_data = {}

    try:
        subs_data = compute_subs_performance_data(today)
    except Exception as e:
        print(f"[ERROR] compute_subs_performance_data failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        subs_data = {}

    try:
        phase_durations_data = compute_phase_durations(jobs_data, today)
    except Exception as e:
        print(f"[ERROR] compute_phase_durations failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        phase_durations_data = {}

    try:
        history = build_transcript_history()
    except Exception as e:
        print(f"[ERROR] build_transcript_history failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        history = {pm: [] for pm in PM_ORDER}

    dash = dashboard_counts(binders, today)
    generated_at = datetime.now().strftime("%Y-%m-%d %I:%M %p").lstrip("0")
    generated_line = f"Generated {generated_at}"
    per_pm = [f"{pm.split()[0]}: {mtimes[pm].strftime('%m/%d %I:%M %p').lstrip('0')}" for pm in PM_ORDER if pm in mtimes]
    dashboard_line = (
        f"{dash['total_active']} open · {dash['urgent']} URGENT · "
        f"{dash['stale']} stale · PPC {dash['ppc']}% · "
        f"{dash['completed_today']} closed today · {dash['dismissed_total']} dismissed "
        f"· {' / '.join(per_pm)}"
    )

    # Embed JSON — readable indent for debuggability.
    all_binders_json      = json.dumps(binders, indent=2, ensure_ascii=False)
    history_json          = json.dumps(history, indent=2, ensure_ascii=False, default=str)
    job_colors_json       = json.dumps(JOB_COLORS, ensure_ascii=False)
    pm_order_json         = json.dumps([pm for pm in PM_ORDER if pm in binders], ensure_ascii=False)
    jobs_data_json        = json.dumps(jobs_data, indent=2, ensure_ascii=False, default=str)
    subs_data_json        = json.dumps(subs_data, indent=2, ensure_ascii=False, default=str)
    phase_durations_json  = json.dumps(phase_durations_data, indent=2, ensure_ascii=False, default=str)
    tooltips_json         = json.dumps(TOOLTIPS, ensure_ascii=False)

    js = (
        JS_TEMPLATE
        .replace("{ALL_BINDERS_JSON}", all_binders_json)
        .replace("{TRANSCRIPT_HISTORY_JSON}", history_json)
        .replace("{JOB_COLORS_JSON}", job_colors_json)
        .replace("{PM_ORDER_JSON}", pm_order_json)
        .replace("{JOBS_DATA_JSON}", jobs_data_json)
        .replace("{SUBS_DATA_JSON}", subs_data_json)
        .replace("{PHASE_DURATIONS_JSON}", phase_durations_json)
        .replace("{TOOLTIPS_JSON}", tooltips_json)
    )

    html = (
        HTML_TEMPLATE
        .replace("{CSS}", CSS)
        .replace("{JS}", js)
        .replace("{GENERATED_AT}", generated_at)
        .replace("{GENERATED_LINE}", generated_line)
        .replace("{DASHBOARD_LINE}", dashboard_line)
    )

    OUTPUT.write_text(html, encoding="utf-8")
    size_kb = len(html.encode("utf-8")) / 1024
    print(f"Monday binder regenerated -> {OUTPUT} ({size_kb:,.1f} KB, {len(binders)} PMs)")

    # ----- Phase 4 — emit one PM packet per binder ---------------------------
    print()
    print("=" * 64)
    print("PM PACKETS")
    print("=" * 64)
    for pm in PM_ORDER:
        if pm not in binders:
            continue
        try:
            packet_html, verif = render_pm_packet(
                pm=pm, binder=binders[pm], jobs_data=jobs_data,
                today=today, generated_at=generated_at,
            )
        except Exception as e:
            print(f"[ERROR] PM packet failed for {pm}: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            continue

        out_path = PM_PACKET_OUTPUT / verif["filename"]
        out_path.write_text(packet_html, encoding="utf-8")

        confirm_label = "shown" if verif["lookahead_confirm_by"] else "hidden"
        print()
        print("=" * 64)
        print(f"PM packet generated: {verif['pm']}")
        print(f"File: {verif['filename']}  ({verif['size_kb']:,.1f} KB)")
        print(f"Estimated pages: {verif['estimated_pages']}")
        print(f"Sections rendered: {', '.join(verif['sections_rendered'])}")
        print(f"Sections omitted:  {', '.join(verif['sections_omitted']) or 'none'}")
        print(f"Open items: {verif['open_items_total']} "
              f"({verif['open_items_urgent']} urgent, {verif['open_items_high']} high)")
        print(f"Look-ahead rows: {verif['lookahead_rows']}")
        print(f"Confirm-by column: {confirm_label}")
        print(f"Issues: {verif['issues']}")
        print(f"Financial entries: {verif['financial']}")
        print(f"Job pages: {', '.join(verif['job_pages']) or '(none)'}")
        print("=" * 64)


def _self_test_is_real_crew_name() -> None:
    """Smoke test for _is_real_crew_name. Run via:
        python -c "import generate_monday_binder as g; g._self_test_is_real_crew_name()"
    """
    test_cases_real = ["ML Concrete, LLC", "Gator Plumbing", "TNT Custom Painting"]
    test_cases_fake = [
        "ZZ - Inspection",
        "Discussions/Events - none",
        "Met with clients",
        "1. Waiting for plumbers",
        "Daily Workforce",
        "(Summary of...)",
        "Additional details",
        "Additional Details - notes",
    ]
    for name in test_cases_real:
        assert _is_real_crew_name(name), f"FAIL: should accept {name!r}"
    for name in test_cases_fake:
        assert not _is_real_crew_name(name), f"FAIL: should reject {name!r}"
    print("All _is_real_crew_name tests passed")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--test-crew-filter":
        _self_test_is_real_crew_name()
    else:
        main()
