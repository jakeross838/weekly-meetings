#!/usr/bin/env python3
"""
Ross Built PM Weekly — Transcript Processor
Reads transcripts from transcripts/inbox/, calls Claude API to extract
structured meeting data, updates per-PM binder JSON files.

Filename convention for transcripts in inbox:
    MM-DD_<PMFirstName>_<Type>_<optional>.txt
    e.g., 04-23_Nelson_Office.txt
          04-23_Lee_Site.txt
          04-15_Martin_Office_Fish.txt

Run: python process.py
Or:  double-click run-weekly.bat
"""

import hashlib
import io
import os
import sys
import json
import re
import time
from datetime import datetime, date
from pathlib import Path

# Load environment from .env (Supabase credentials, etc.) before anything
# else reads os.environ. python-dotenv does NOT override existing env vars,
# so setx-set ANTHROPIC_API_KEY still wins — .env is a backstop.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # .env loading is optional; existing setx flow keeps working

# Force UTF-8 on stdout/stderr so log messages with em-dashes (U+2014),
# right arrows (U+2192), and other non-ASCII chars don't blow up under
# the Windows cp1252 console codec. This MUST run before any print/log
# call — otherwise the first non-ASCII char crashes the script.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

try:
    import anthropic
except ImportError:
    print("ERROR: anthropic package not installed.")
    print("Run: pip install anthropic")
    sys.exit(1)

from fetch_daily_logs import fetch_for_pm as fetch_daily_logs
from constants import PM_JOBS, OLD_TO_NEW_STATUS, CLOSED_STATUSES

# =============================================================================
# CONFIG
# =============================================================================

SCRIPT_DIR = Path(__file__).parent.resolve()
INBOX_DIR = SCRIPT_DIR / "transcripts" / "inbox"
ARCHIVE_DIR = SCRIPT_DIR / "transcripts" / "processed"
SKIPPED_DIR = SCRIPT_DIR / "transcripts" / "skipped"
BINDERS_DIR = SCRIPT_DIR / "binders"
PRINT_DIR = SCRIPT_DIR / "print"
LOGS_DIR = SCRIPT_DIR / "logs"
API_RESPONSES_DIR = SCRIPT_DIR / "api-responses"
PROMPT_FILE = SCRIPT_DIR / "weekly-prompt.md"
LEDGER_FILE = SCRIPT_DIR / "state" / "processing-ledger.jsonl"

MODEL = "claude-opus-4-7"
MAX_TOKENS = 32000

# Keyword → canonical PM name. Includes first-name tokens and every job's
# short name so a transcript titled after the JOB ("Drummond Site Meeting")
# still routes to the right PM binder. Lowercase keys; filename is normalized
# to lowercase before lookup. Built from the shared PM_JOBS map so adding a
# job in constants.py automatically extends keyword coverage here.
PM_KEYWORDS = {
    "martin": "Martin Mannix",
    "jason":  "Jason Szykulski",
    "lee":    "Lee Worthy",          # Lee Worthy (PM), not Lee Ross (owner)
    "bob":    "Bob Mozine",
    "nelson": "Nelson Belanger",
}
for _pm, _jobs in PM_JOBS.items():
    for _job in _jobs:
        PM_KEYWORDS[_job.lower()] = _pm


# =============================================================================
# LOGGING
# =============================================================================

class Logger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.fp = open(self.log_file, "a", encoding="utf-8")
        self._write_header()

    def _write_header(self):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.fp.write(f"\n{'='*70}\nRUN START: {ts}\n{'='*70}\n")
        self.fp.flush()

    def info(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        self.fp.write(line + "\n")
        self.fp.flush()

    def error(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] ERROR: {msg}"
        print(line, file=sys.stderr)
        self.fp.write(line + "\n")
        self.fp.flush()

    def close(self):
        self.fp.write(f"RUN END: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        self.fp.close()


# =============================================================================
# UTILITIES
# =============================================================================

def parse_filename(filename: str):
    """
    Parse transcript filename to extract date, PM, and meeting type.
    Accepts a wide range of shapes so Plaud's default naming + ad-hoc user
    naming both work unchanged. Date formats supported (anywhere in name):
      - YYYY-MM-DD            "2026-04-28"
      - MM-DD                 "04-28"               (year inferred = current)
      - M-D, M-DD, MM-D       "4-28", "4-7"
      - M_D_YY, MM_DD_YY      "4_28_26"             (2-digit year → 20YY)
      - M-D-YY, MM-DD-YY      "4-28-26"
      - M/D/YY, MM/DD/YY      "4/28/26"
      - M_D_YYYY, etc.        "4_28_2026"
    Examples:
      - "MM-DD_Martin_Office.txt"
      - "04-23 Lee Worthy Office Production Meeting (Krauss_Ruthven)-transcript.txt"
      - "Martin Site Production Meeting 4_28_26.txt"
    PM lookup: scans tokens for first-name OR job-name matches in PM_KEYWORDS.
    Meeting type: scans for "site" or "office" substrings.
    Returns (date_str, pm_canonical_name, meeting_type) or None.
    """
    base = Path(filename).stem
    cleaned = re.sub(r"[()\[\]]", " ", base)

    # ---- Date extraction (try regexes against the full base string before
    # tokenization, so multi-token dates like "4_28_26" still match). We use
    # explicit non-digit boundaries instead of `\b` because underscore is a
    # word-char in regex — `\b` would fail at "23_" boundaries.
    LB, RB = r"(?:^|(?<=\D))", r"(?=\D|$)"
    date_str = None
    # 1) ISO YYYY-MM-DD
    m = re.search(rf"{LB}(\d{{4}})-(\d{{2}})-(\d{{2}}){RB}", base)
    if m:
        date_str = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    if not date_str:
        # 2) M[-_/]D[-_/]YY  or  M[-_/]D[-_/]YYYY  (single OR double digit)
        m = re.search(rf"{LB}(\d{{1,2}})[-_/](\d{{1,2}})[-_/](\d{{2,4}}){RB}", base)
        if m:
            mo, d, y = m.group(1), m.group(2), m.group(3)
            year = ("20" + y) if len(y) == 2 else y
            date_str = f"{year}-{mo.zfill(2)}-{d.zfill(2)}"
    if not date_str:
        # 3) M[-_/]D with no year — infer current year
        m = re.search(rf"{LB}(\d{{1,2}})[-_/](\d{{1,2}}){RB}", base)
        if m:
            mo, d = m.group(1), m.group(2)
            year = str(datetime.now().year)
            date_str = f"{year}-{mo.zfill(2)}-{d.zfill(2)}"
    if not date_str:
        return None

    # Validate the date is real (rejects junk like "99-99-26")
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None

    # ---- Tokenize for PM + meeting-type scan
    parts = [p for p in re.split(r"[_\s/]+", cleaned.lower()) if p]
    if not parts:
        return None

    # PM — first exact-match hit against PM_KEYWORDS (first name or job name).
    pm_name = None
    for p in parts:
        if p in PM_KEYWORDS:
            pm_name = PM_KEYWORDS[p]
            break
    if not pm_name:
        return None

    # Meeting type — scan all tokens for site/office.
    if any("site" in p for p in parts):
        mtype = "SITE"
    elif any("office" in p for p in parts):
        mtype = "OFFICE"
    else:
        return None

    return (date_str, pm_name, mtype)


def binder_path(pm_name: str) -> Path:
    return BINDERS_DIR / f"{pm_name.replace(' ', '_')}.json"


# =============================================================================
# SUPABASE SINK (additive — binder JSON remains source of truth)
# =============================================================================

def _pm_slug(pm_name: str) -> str:
    """First-name lowercase. 'Martin Mannix' -> 'martin'."""
    return pm_name.split()[0].lower() if pm_name else ""


_SUPABASE_CLIENT = None


def _supabase_client():
    """Lazy supabase client. Returns None when env is unset or supabase-py
    isn't installed so the sink is a no-op in dev environments without
    Supabase configured."""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client
    except ImportError:
        return None
    _SUPABASE_CLIENT = create_client(url, key)
    return _SUPABASE_CLIENT


_SUB_ALIAS_INDEX: list[tuple] | None = None  # cached: list of (compiled_regex, alias_len, sub_id)


def _sub_alias_index(client):
    """Build (and cache) a list of (regex, alias_length, sub_id) tuples from
    the Supabase `subs` table. Used to extract sub_id from binder item text
    so each upserted todo gets linked to a sub when a canonical alias matches."""
    global _SUB_ALIAS_INDEX
    if _SUB_ALIAS_INDEX is not None:
        return _SUB_ALIAS_INDEX
    try:
        resp = client.table("subs").select("id, aliases").execute()
    except Exception:
        _SUB_ALIAS_INDEX = []
        return _SUB_ALIAS_INDEX
    idx: list[tuple] = []
    for s in resp.data or []:
        for alias in s.get("aliases") or []:
            pat = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)", re.IGNORECASE)
            idx.append((pat, len(alias), s["id"]))
    _SUB_ALIAS_INDEX = idx
    return idx


def _extract_sub_id(text: str, client) -> str | None:
    """Scan text for the longest-matching canonical sub alias and return its
    sub_id. Returns None when nothing matches."""
    if not text:
        return None
    best: tuple[int, str] | None = None
    for pat, length, sub_id in _sub_alias_index(client):
        if pat.search(text):
            if best is None or length > best[0]:
                best = (length, sub_id)
    return best[1] if best else None


def _item_to_supabase_row(item: dict, pm_name: str, transcript_filename: str, client=None):
    """Map a binder item dict to a todos-table row. Returns None for items
    that should be skipped (DISMISSED). When `client` is provided, attempts
    to extract a sub_id from the item's action + update text."""
    status = (item.get("status") or "").upper()
    if status == "DISMISSED":
        return None

    def _date_or_none(s):
        if not s:
            return None
        try:
            return datetime.strptime(s, "%Y-%m-%d").date().isoformat()
        except Exception:
            return None

    def _datetime_or_none(s):
        d = _date_or_none(s)
        return f"{d}T00:00:00Z" if d else None

    completed_at = None
    if status == "COMPLETE":
        completed_at = _datetime_or_none(item.get("close_date") or item.get("closed_date"))

    action = item.get("action") or ""
    update = item.get("update") or ""
    sub_id = None
    if client is not None:
        try:
            sub_id = _extract_sub_id(f"{action}\n{update}", client)
        except Exception:
            sub_id = None  # never let sub extraction break the sink

    return {
        "id": item.get("id"),
        "pm_id": _pm_slug(pm_name),
        "job": item.get("job") or "",
        "title": action,
        "due_date": _date_or_none(item.get("due")),
        "priority": item.get("priority"),
        "status": status,
        "type": item.get("type"),
        "category": item.get("category"),
        "created_at": _datetime_or_none(item.get("opened")),
        "completed_at": completed_at,
        "source_transcript": transcript_filename,
        "source_excerpt": item.get("update"),
        "sub_id": sub_id,
    }


def sink_to_supabase(pm_name: str, binder: dict, transcript_filename: str, logger) -> int:
    """Upsert each binder item into Supabase todos. Failures log but never
    raise. Returns count of rows attempted (skipped DISMISSED items not
    counted). binder JSON write must already have completed; this is a
    secondary, failure-tolerant mirror."""
    client = _supabase_client()
    if client is None:
        logger.info("Supabase: client unavailable (missing env or import). Skipping sink.")
        return 0
    rows = []
    for item in binder.get("items", []) or []:
        row = _item_to_supabase_row(item, pm_name, transcript_filename, client=client)
        if row is None:
            continue
        if not row.get("id"):
            continue  # never upsert without a primary key
        rows.append(row)
    if not rows:
        logger.info(f"Supabase: no rows to upsert for {pm_name}.")
        return 0
    try:
        client.table("todos").upsert(rows, on_conflict="id").execute()
        logger.info(f"Supabase: upserted {len(rows)} rows for {pm_name}.")
        return len(rows)
    except Exception as e:
        logger.error(f"Supabase upsert failed for {pm_name}: {type(e).__name__}: {e}")
        return 0


def migrate_binder_items(binder: dict, logger) -> dict:
    """Normalize legacy status values and backfill missing `type` fields.

    Safe to call on already-migrated binders (idempotent). KILLED items keep their
    original update text as the "kill reason" so it's preserved in the final
    "Complete — <reason>" string.
    """
    items = binder.get("items", []) or []
    migrated_statuses = 0
    added_types = 0
    for item in items:
        raw_status = item.get("status", "")
        new_status = OLD_TO_NEW_STATUS.get(raw_status, raw_status)
        if new_status != raw_status:
            if raw_status == "KILLED":
                update = (item.get("update") or "").strip()
                if update.lower().startswith("complete"):
                    pass
                else:
                    reason = update or "killed"
                    item["update"] = f"Complete — {reason}"
            item["status"] = new_status
            migrated_statuses += 1
        if not item.get("type"):
            item["type"] = "FOLLOWUP"
            added_types += 1
    if migrated_statuses:
        logger.info(f"Migrated {migrated_statuses} item status value(s) to new schema.")
    if added_types:
        logger.info(f"WARN: backfilled {added_types} item(s) with default type=FOLLOWUP (prior binder pre-taxonomy).")
    return binder


def _parse_iso_date_safe(s: str):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def compute_item_aging(binder: dict, meeting_date: str, logger) -> dict:
    """Annotate each item with days_open, days_overdue, aging_flag, escalation_level.

    Uses meeting_date as "today". Safe on binders without items or with missing
    opened/due dates. For COMPLETE items, sets closed_date = meeting_date unless
    already present.
    """
    md = _parse_iso_date_safe(meeting_date)
    if md is None:
        logger.error(f"compute_item_aging: invalid meeting_date {meeting_date!r}; skipping.")
        return binder

    for item in binder.get("items", []) or []:
        opened = _parse_iso_date_safe(item.get("opened", ""))
        due = _parse_iso_date_safe(item.get("due", ""))

        days_open = (md - opened).days if opened else 0
        days_overdue = (md - due).days if due else 0
        item["days_open"] = days_open
        item["days_overdue"] = days_overdue

        if days_open < 7:
            flag, level = "fresh", 0
        elif days_open < 14:
            flag, level = "aging", 1
        elif days_open < 30:
            flag, level = "stale", 2
        else:
            flag, level = "abandoned", 3
        item["aging_flag"] = flag
        item["escalation_level"] = level

        if item.get("status") in CLOSED_STATUSES and not item.get("closed_date"):
            item["closed_date"] = md.isoformat()
    return binder


def load_binder(pm_name: str, logger) -> dict:
    """Load a PM's binder. If missing, return a minimal empty structure.

    Runs the item-taxonomy migration on load so prior binders with legacy status
    values (OPEN/DONE/KILLED/"IN PROGRESS") are normalized before being sent to
    Claude.
    """
    path = binder_path(pm_name)
    if not path.exists():
        logger.info(f"No existing binder for {pm_name}. Starting empty.")
        return {
            "meta": {"pm": pm_name, "date": "", "type": "", "week": 0},
            "jobs": [{"name": j, "phase": "", "status": "green", "targetCO": "—", "gp": "—", "address": ""}
                     for j in PM_JOBS.get(pm_name, [])],
            "lookAhead": {"w2": [], "w4": [], "w8": []},
            "items": [],
            "issues": [],
            "financial": [],
            "clarify": []
        }
    with open(path, "r", encoding="utf-8") as f:
        binder = json.load(f)
    return migrate_binder_items(binder, logger)


def save_binder(pm_name: str, binder: dict, logger):
    """Atomic write: write to a sibling .tmp then os.replace into place.

    email_sender._ensure_html_fresh may regenerate HTML mid-pipeline, and
    generate_monday_binder.py reads every binder JSON. A non-atomic write
    can present a half-written file to that reader. os.replace is atomic
    on Windows + POSIX so the reader always sees the previous full file
    or the new full file, never a partial.
    """
    path = binder_path(pm_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(binder, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    logger.info(f"Saved binder → {path.name}")


def backup_binder(pm_name: str, logger):
    """Before overwriting, snapshot the current binder to api-responses/ with timestamp."""
    src = binder_path(pm_name)
    if not src.exists():
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = API_RESPONSES_DIR / f"{pm_name.replace(' ', '_')}_backup_{ts}.json"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with open(src, "r", encoding="utf-8") as f_in, open(backup_path, "w", encoding="utf-8") as f_out:
        f_out.write(f_in.read())
    logger.info(f"Backed up prior binder → {backup_path.name}")


def highest_id_by_job(binder: dict) -> dict:
    """Return {job_prefix: highest_number} for ID auto-increment."""
    result = {}
    for item in binder.get("items", []):
        m = re.match(r"([A-Z_]+)-(\d+)", item.get("id", ""))
        if m:
            prefix = m.group(1)
            num = int(m.group(2))
            result[prefix] = max(result.get(prefix, 0), num)
    return result


def week_number(iso_date: str) -> int:
    d = datetime.strptime(iso_date, "%Y-%m-%d").date()
    return d.isocalendar()[1]


def read_prompt_template() -> str:
    if not PROMPT_FILE.exists():
        raise FileNotFoundError(f"Missing prompt file: {PROMPT_FILE}")
    return PROMPT_FILE.read_text(encoding="utf-8")


# =============================================================================
# PROCESSING LEDGER (SHA-based dedupe + failure-skip)
# =============================================================================

def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def append_ledger_record(record: dict):
    """Append one JSON line atomically.

    Uses the OS-level O_APPEND flag so concurrent writers (e.g. process.py
    and a manual ledger-edit tool) cannot tear records. The whole record is
    serialized first and emitted in a single os.write() call, which is
    atomic for sub-PIPE_BUF (~4KB) payloads on both POSIX and Windows.
    """
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    fd = os.open(LEDGER_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, line)
    finally:
        os.close(fd)


def load_ledger_index() -> dict:
    """Return {sha: latest_record}. Tolerates partial-line corruption."""
    if not LEDGER_FILE.exists():
        return {}
    index = {}
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sha = rec.get("sha256")
            if sha:
                index[sha] = rec
    return index


def ensure_ledger_seeded(logger):
    """One-time backfill: if ledger is missing, seed success entries from
    every file already in transcripts/processed/ so re-uploads don't get
    re-sent to Opus."""
    if LEDGER_FILE.exists():
        return
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    backfilled = 0
    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.txt")):
            try:
                sha = compute_sha256(f)
            except Exception as e:
                logger.error(f"Seed: could not hash {f.name}: {e}")
                continue
            append_ledger_record({
                "sha256": sha,
                "filename": f.name,
                "outcome": "success",
                "reason": "backfilled_from_processed",
                "processed_at": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
            })
            backfilled += 1
    logger.info(f"Initialized ledger {LEDGER_FILE.name} (backfilled {backfilled} entries from processed/).")


def archive_transcript(transcript_file: Path) -> Path:
    """Move transcript to processed/, appending a timestamp on name collision."""
    archive_dest = ARCHIVE_DIR / transcript_file.name
    archive_dest.parent.mkdir(parents=True, exist_ok=True)
    if archive_dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dest = ARCHIVE_DIR / f"{transcript_file.stem}_{ts}{transcript_file.suffix}"
    transcript_file.rename(archive_dest)
    return archive_dest


def skip_transcript(transcript_file: Path) -> Path:
    """Move an unprocessable transcript to transcripts/skipped/ for visibility.

    Same name-collision handling as archive_transcript. Used by
    process_transcript when the filename is unparseable or the transcript
    is too short — the SHA gets ledgered with outcome=skipped so subsequent
    runs don't re-process the same broken file.
    """
    SKIPPED_DIR.mkdir(parents=True, exist_ok=True)
    dest = SKIPPED_DIR / transcript_file.name
    if dest.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = SKIPPED_DIR / f"{transcript_file.stem}_{ts}{transcript_file.suffix}"
    transcript_file.rename(dest)
    return dest


def _ledger_skip(sha: str, transcript_file: Path, reason: str,
                 ledger_index: dict, logger,
                 pm_name: str = "", meeting_date: str = "", meeting_type: str = ""):
    """Record an outcome=skipped ledger entry so future runs see the SHA and
    short-circuit without re-attempting. Also moves the file to
    transcripts/skipped/ for visibility."""
    rec = {
        "sha256": sha,
        "filename": transcript_file.name,
        "pm": pm_name,
        "meeting_date": meeting_date,
        "meeting_type": meeting_type,
        "outcome": "skipped",
        "reason": reason,
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }
    append_ledger_record(rec)
    ledger_index[sha] = rec
    try:
        moved = skip_transcript(transcript_file)
        logger.info(f"Moved unprocessable transcript → skipped/{moved.name}")
    except Exception as e:
        logger.error(f"Could not move {transcript_file.name} to skipped/: {e}")


# =============================================================================
# CLAUDE API CALL
# =============================================================================

def call_claude(prompt_template: str, transcript: str, prior_binder: dict,
                pm_name: str, meeting_date: str, meeting_type: str,
                daily_logs, logger) -> dict:
    """Call Claude API. Return parsed JSON from the response."""
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    highest_ids = highest_id_by_job(prior_binder)
    highest_ids_str = ", ".join(f"{k}-{v:03d}" for k, v in highest_ids.items()) if highest_ids else "none"

    # Build the DAILY LOG CONTEXT section
    if daily_logs and not daily_logs.get("meta", {}).get("error"):
        stale_warning = "\n⚠️ STALE DATA — last scraper run was more than 48h ago.\n" if daily_logs.get("meta", {}).get("stale") else ""
        daily_logs_section = f"""

**DAILY LOG CONTEXT (from Buildertrend, last 14 days):**{stale_warning}
```json
{json.dumps(daily_logs, indent=2, default=str)}
```
"""
    else:
        daily_logs_section = "\n**DAILY LOG CONTEXT:** Not available this run. Proceed using transcript only.\n"

    # Build the user message
    user_msg = f"""{prompt_template}

---

## INPUTS

**META:** PM: {pm_name} | Date: {meeting_date} | Type: {meeting_type} | Highest-IDs: {highest_ids_str}

**PRIOR BINDER JSON:**
```json
{json.dumps(prior_binder, indent=2)}
```

**TRANSCRIPT:**
```
{transcript}
```
{daily_logs_section}
---

Produce the updated binder JSON per the schema. Output a single JSON code block, nothing else before it.
"""

    logger.info(f"Calling Claude API (model={MODEL}, est. input chars={len(user_msg)})")
    t0 = time.time()

    # Streaming is required when max_tokens * min-output-rate can exceed 10
    # minutes — true for MAX_TOKENS=32000 even on Opus. We accumulate the
    # full text from text_delta events; usage arrives on message_delta.
    try:
        input_tokens = 0
        output_tokens = 0
        text_parts: list[str] = []
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            for event in stream:
                etype = getattr(event, "type", None)
                if etype == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    if delta and getattr(delta, "type", "") == "text_delta":
                        text_parts.append(delta.text)
                elif etype == "message_start":
                    msg = getattr(event, "message", None)
                    if msg and getattr(msg, "usage", None):
                        input_tokens = msg.usage.input_tokens or 0
                elif etype == "message_delta":
                    usage = getattr(event, "usage", None)
                    if usage:
                        output_tokens = usage.output_tokens or 0
        raw_text = "".join(text_parts)
    except anthropic.APIError as e:
        logger.error(f"Anthropic API error: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error calling API: {e}")
        raise

    elapsed = time.time() - t0
    logger.info(f"API response received in {elapsed:.1f}s "
                f"(input tokens: {input_tokens}, output tokens: {output_tokens})")

    # Save raw response for audit
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = API_RESPONSES_DIR / f"{pm_name.replace(' ', '_')}_{ts}_raw.txt"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(raw_text, encoding="utf-8")
    logger.info(f"Raw response saved → {raw_path.name}")

    # Extract JSON from response
    json_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
    if not json_match:
        # Try without the json tag
        json_match = re.search(r"```\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
    if not json_match:
        # Last resort - try to find JSON in the raw text
        json_match = re.search(r"(\{[\s\S]*\})", raw_text)

    if not json_match:
        raise ValueError(f"Could not extract JSON from response. See {raw_path}")

    json_str = json_match.group(1)
    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        logger.error(f"First 500 chars: {json_str[:500]}")
        raise

    return parsed


# =============================================================================
# BINDER VALIDATION & MERGE
# =============================================================================

def validate_binder(binder: dict, pm_name: str, logger) -> bool:
    """Sanity check returned binder. Log warnings, return True if usable."""
    required = ["meta", "jobs", "lookAhead", "items"]
    missing = [k for k in required if k not in binder]
    if missing:
        logger.error(f"Binder missing required keys: {missing}")
        return False

    if binder.get("meta", {}).get("pm") != pm_name:
        logger.error(f"PM name mismatch: expected {pm_name}, got {binder.get('meta', {}).get('pm')}")
        return False

    # Check action items have required fields. A missing *priority* or
    # *status* is softened to a default + warning — Opus sometimes drops
    # them on long outputs and a binder-wide reject would throw away an
    # otherwise-good update. Hard fields (id, job, action, owner) still
    # reject because without them an item is unusable.
    VALID_CATEGORIES = {
        "SCHEDULE", "PROCUREMENT", "SUB-TRADE", "CLIENT",
        "QUALITY", "BUDGET", "ADMIN", "SELECTION",
    }
    item_errors = 0
    for i, item in enumerate(binder.get("items", [])):
        for req in ["id", "job", "action", "owner"]:
            if req not in item or not item.get(req):
                logger.error(f"Item #{i} missing or empty: {req}")
                item_errors += 1
        if not item.get("priority"):
            logger.info(f"Item #{i} ({item.get('id','?')}) missing priority — defaulting to NORMAL")
            item["priority"] = "NORMAL"
        if not item.get("status"):
            logger.info(f"Item #{i} ({item.get('id','?')}) missing status — defaulting to NOT_STARTED")
            item["status"] = "NOT_STARTED"
        # Phase 12 Part B — category + source soft validation. Default to
        # ADMIN with a flag rather than rejecting; backfill captures the rest.
        cat = item.get("category")
        if cat not in VALID_CATEGORIES:
            logger.info(f"Item #{i} ({item.get('id','?')}) category invalid/missing "
                        f"({cat!r}) — defaulting to ADMIN [needs manual review]")
            item["category"] = "ADMIN"
            item["_category_review"] = True
        if not item.get("source"):
            item["source"] = "transcript"
        # Phase 12 polish — close_date validation. When status is COMPLETE
        # or DISMISSED but no close_date was provided, fall back to the
        # meeting date so "Recently Completed" can render the item without
        # losing it. Soft validation: log + fill, never reject.
        status_upper = (item.get("status") or "").upper()
        if status_upper in ("COMPLETE", "DISMISSED"):
            cd = item.get("close_date") or item.get("closed_date")
            if not cd:
                fallback = binder.get("meta", {}).get("date")
                if fallback:
                    item["close_date"] = fallback
                    logger.info(f"Item #{i} ({item.get('id','?')}) status={status_upper} "
                                f"missing close_date — defaulted to meeting date {fallback}")
    if item_errors > 0:
        logger.error(f"{item_errors} item validation errors")
        return False

    # Warn on items with vague action text
    vague_patterns = [r"^(discuss|review|look into|check on|follow up)"]
    vague_count = 0
    for item in binder.get("items", []):
        action = item.get("action", "").lower()
        for pat in vague_patterns:
            if re.match(pat, action):
                logger.info(f"WARN: Possibly vague action '{item['id']}': {item['action'][:60]}...")
                vague_count += 1
                break
    if vague_count > 0:
        logger.info(f"{vague_count} items flagged as potentially vague. Review before distributing.")

    return True


# =============================================================================
# MAIN PROCESSING
# =============================================================================

def process_transcript(transcript_file: Path, ledger_index: dict, logger) -> str:
    """Process a single transcript file. Returns one of:
        'success'           — processed and saved
        'duplicate'         — SHA matches a prior success; moved to processed/, no API call
        'previously_failed' — SHA matches a prior failure; left in inbox
        'failure'           — failed this run (or unparseable filename / too short)
    """
    logger.info(f"\n--- Processing: {transcript_file.name} ---")

    # SHA guard FIRST — before parse/fetch/API. Same content under any name
    # is caught here.
    try:
        sha = compute_sha256(transcript_file)
    except Exception as e:
        logger.error(f"SKIP: could not hash file: {e}")
        return "failure"

    prior = ledger_index.get(sha)
    if prior:
        outcome = prior.get("outcome")
        orig = prior.get("filename", "?")
        if outcome == "success":
            archived = archive_transcript(transcript_file)
            logger.info(f"SKIP: SHA matches prior success ({orig}). Moved → processed/{archived.name} (no API call).")
            return "duplicate"
        elif outcome == "skipped":
            reason = prior.get("reason", "unknown")
            # Move to skipped/ if still in inbox (e.g. user re-uploaded the same broken file).
            try:
                moved = skip_transcript(transcript_file)
                logger.info(f"SKIP: SHA matches prior skip ({reason}). Moved → skipped/{moved.name}.")
            except Exception:
                logger.info(f"SKIP: SHA matches prior skip ({reason}). Already moved or unmovable.")
            return "previously_failed"
        else:
            reason = prior.get("reason", "unknown")
            logger.info(f"SKIP: SHA matches prior failure ({reason}). To retry, remove the line for sha {sha[:12]}… from {LEDGER_FILE.name}.")
            return "previously_failed"

    parsed = parse_filename(transcript_file.name)
    if not parsed:
        logger.error(f"SKIP: Could not parse filename. Expected: MM-DD_<PM>_<Site|Office>.txt")
        # Ledger this SHA so re-uploads of the same broken file don't loop.
        # User can fix the name + reupload (new SHA) to retry.
        _ledger_skip(sha, transcript_file, "unparseable_filename", ledger_index, logger)
        return "failure"

    meeting_date, pm_name, meeting_type = parsed
    logger.info(f"Parsed: PM={pm_name}, Date={meeting_date}, Type={meeting_type}")

    transcript = transcript_file.read_text(encoding="utf-8", errors="replace")
    if len(transcript.strip()) < 500:
        logger.error(f"SKIP: Transcript looks too short ({len(transcript)} chars)")
        # Ledger this SHA so the same truncated capture isn't re-tried each run.
        _ledger_skip(sha, transcript_file, "too_short", ledger_index, logger,
                     pm_name=pm_name, meeting_date=meeting_date, meeting_type=meeting_type)
        return "failure"

    prior_binder = load_binder(pm_name, logger)
    logger.info(f"Loaded prior binder: {len(prior_binder.get('items', []))} items, "
                f"{len(prior_binder.get('jobs', []))} jobs")

    # Fetch daily log context
    logger.info(f"Fetching daily log context for {pm_name} (14-day window)")
    try:
        daily_logs = fetch_daily_logs(pm_name, meeting_date, lookback_days=14)
        if daily_logs.get("meta", {}).get("error"):
            logger.error(f"Daily logs unavailable: {daily_logs['meta']['error']}")
            logger.info("Proceeding without daily log context.")
        elif daily_logs.get("meta", {}).get("stale"):
            logger.info("⚠️ Daily logs are STALE (last scrape > 48h ago). Proceeding with stale data.")
        else:
            summary_counts = {job: s.get("total_logs", 0) for job, s in daily_logs.get("summary", {}).items()}
            logger.info(f"Daily logs loaded: {summary_counts}")
    except Exception as e:
        logger.error(f"Error fetching daily logs: {e}")
        daily_logs = None
        logger.info("Proceeding without daily log context.")

    backup_binder(pm_name, logger)

    try:
        prompt_template = read_prompt_template()
    except FileNotFoundError as e:
        logger.error(str(e))
        return "failure"

    t_start = time.time()

    def _ledger_failure(reason: str):
        rec = {
            "sha256": sha,
            "filename": transcript_file.name,
            "pm": pm_name,
            "meeting_date": meeting_date,
            "meeting_type": meeting_type,
            "outcome": "failure",
            "reason": reason,
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "duration_sec": round(time.time() - t_start, 1),
        }
        append_ledger_record(rec)
        ledger_index[sha] = rec

    try:
        new_binder = call_claude(
            prompt_template, transcript, prior_binder,
            pm_name, meeting_date, meeting_type, daily_logs, logger
        )
    except Exception as e:
        logger.error(f"API call failed: {e}")
        _ledger_failure(f"api_error: {type(e).__name__}: {str(e)[:120]}")
        return "failure"

    # Ensure week number is set
    if "meta" in new_binder and meeting_date:
        new_binder["meta"]["week"] = week_number(meeting_date)

    # Normalize any legacy statuses Claude may have echoed back, then compute
    # aging/escalation fields (days_open, days_overdue, aging_flag,
    # escalation_level, closed_date) for every item.
    migrate_binder_items(new_binder, logger)
    compute_item_aging(new_binder, meeting_date, logger)

    if not validate_binder(new_binder, pm_name, logger):
        logger.error("Binder validation failed. Not saving.")
        _ledger_failure("validation_failed")
        return "failure"

    save_binder(pm_name, new_binder, logger)

    # Additive Supabase sink — failure-tolerant, never breaks the run.
    # binder JSON above remains the source of truth.
    sink_to_supabase(pm_name, new_binder, transcript_file.name, logger)

    archived = archive_transcript(transcript_file)
    logger.info(f"Moved transcript → processed/{archived.name}")

    # Ledger success
    success_rec = {
        "sha256": sha,
        "filename": transcript_file.name,
        "pm": pm_name,
        "meeting_date": meeting_date,
        "meeting_type": meeting_type,
        "outcome": "success",
        "items_count": len(new_binder.get("items", [])),
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "duration_sec": round(time.time() - t_start, 1),
    }
    append_ledger_record(success_rec)
    ledger_index[sha] = success_rec

    # Summary
    new_items = [i for i in new_binder.get("items", []) if "New this meeting" in i.get("update", "")]
    # Items have already been migrated by migrate_binder_items above, so legacy
    # status names ("OPEN", "IN PROGRESS", "BLOCKED") never appear here. Anything
    # not in CLOSED_STATUSES is considered active for aging purposes.
    aging = [i for i in new_binder.get("items", [])
             if i.get("status") not in CLOSED_STATUSES
             and days_old(i.get("opened", meeting_date), meeting_date) > 14]

    logger.info(f"SUCCESS: {len(new_binder.get('items', []))} total items, "
                f"{len(new_items)} new, {len(aging)} aging >14d")
    return "success"


def days_old(opened: str, now: str) -> int:
    try:
        d1 = datetime.strptime(opened, "%Y-%m-%d").date()
        d2 = datetime.strptime(now, "%Y-%m-%d").date()
        return (d2 - d1).days
    except Exception:
        return 0


def main():
    # Setup logger
    log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    logger = Logger(log_file)

    logger.info("Ross Built PM Weekly Processor")
    logger.info(f"Script dir: {SCRIPT_DIR}")

    # Ledger init runs unconditionally — pure local I/O, independent of API
    # key or inbox contents. First run backfills from processed/.
    ensure_ledger_seeded(logger)

    # API key check
    if not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY environment variable not set.")
        logger.error("Set it in Windows: System Properties > Environment Variables")
        logger.error("  or run: setx ANTHROPIC_API_KEY \"sk-ant-...\"")
        logger.close()
        sys.exit(1)

    # Find transcripts
    if not INBOX_DIR.exists():
        INBOX_DIR.mkdir(parents=True)
        logger.info(f"Created inbox: {INBOX_DIR}")

    transcripts = sorted(INBOX_DIR.glob("*.txt"))
    if not transcripts:
        logger.info("No transcripts in inbox. Drop *.txt files into transcripts/inbox/ and re-run.")
        logger.info(f"Filename format: MM-DD_<PM>_<Site|Office>.txt (e.g., 04-28_Nelson_Office.txt)")
        logger.info(f"  e.g., 04-28_Nelson_Office.txt")
        logger.close()
        return

    logger.info(f"Found {len(transcripts)} transcript(s) to process.")

    ledger_index = load_ledger_index()
    logger.info(f"Ledger loaded: {len(ledger_index)} prior entries.")

    success_count = 0
    duplicate_count = 0
    skipped_count = 0
    fail_count = 0
    for t in transcripts:
        try:
            outcome = process_transcript(t, ledger_index, logger)
            if outcome == "success":
                success_count += 1
            elif outcome == "duplicate":
                duplicate_count += 1
            elif outcome == "previously_failed":
                skipped_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"Uncaught exception processing {t.name}: {e}")
            fail_count += 1

    status_word = "DONE WITH FAILURES" if fail_count > 0 else "DONE"
    logger.info(f"\n=== {status_word}: {success_count} succeeded, {duplicate_count} duplicates skipped, "
                f"{skipped_count} prior-failure skipped, {fail_count} failed ===")
    if success_count > 0:
        logger.info(f"Open pm-binder.html in your browser to view.")
        logger.info(f"Use the Import button to load the updated JSON files from binders/")
    logger.close()

    # Exit non-zero on any failure so callers (dashboard / run_weekly.bat
    # / shell pipelines) can detect partial-failure runs. Exit 0 only on
    # all-clean (including the no-work case).
    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
