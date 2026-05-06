"""Ross Built Monday Ops — unified dashboard at http://localhost:8765.

Single Flask app, single page. Combines what used to be three artifacts:
  - the standalone PREVIEW-INDEX.html (8-card binder grid)
  - the old transcript drop UI
  - manual "scrape" + "refresh" actions previously only available from
    monday-binder-v1-archive/server.py

Layout (top → bottom):
  1. Sticky status bar — last auto-run from state/LAST_RUN_STATUS.txt + ISO week
  2. Monday Binder — 5 PM cards + 3 leadership cards (computed live from binders/)
  3. Transcript pipeline — drop zone + pending list + 3 action buttons
  4. Shared log tail — stdout/stderr from whichever subprocess is running

Subprocess concurrency: a single global lock. Any spawn route returns 409 if
another job is running. Polling pattern (no WebSockets).

Localhost-only (127.0.0.1:8765). Never binds 0.0.0.0.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml
from flask import Flask, Response, abort, jsonify, request, send_from_directory


# ----------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------
SCRIPT_DIR   = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.resolve()  # …/weekly-meetings

# render_helpers lives in monday-binder/ (sibling of transcript-ui/).
# That directory has a hyphen so it's not a Python package; add it to
# sys.path so the import works.
_MONDAY_BINDER_DIR = PROJECT_ROOT / "monday-binder"
if str(_MONDAY_BINDER_DIR) not in sys.path:
    sys.path.insert(0, str(_MONDAY_BINDER_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import render_helpers  # noqa: E402  — see sys.path insertions above
ASSETS_DIR   = PROJECT_ROOT / "monday-binder" / "assets"
INBOX        = PROJECT_ROOT / "transcripts" / "inbox"
PROCESS_PY   = PROJECT_ROOT / "process.py"

# Sibling buildertrend-scraper repo
SCRAPER_DIR  = PROJECT_ROOT.parent / "buildertrend-scraper"
SCRAPER_JS   = SCRAPER_DIR / "scrape-daily-logs.js"

# Build scripts (refresh)
BUILD_PAGES_PY        = PROJECT_ROOT / "monday-binder" / "build_pages.py"
BUILD_MEETING_PREP_PY = PROJECT_ROOT / "monday-binder" / "build_meeting_prep.py"

# Auto-run status + insights
STATUS_FILE  = PROJECT_ROOT / "state" / "LAST_RUN_STATUS.txt"
INSIGHTS_JSON = PROJECT_ROOT / "data" / "insights.json"
JOB_STAGES_JSON = PROJECT_ROOT / "data" / "job-stages.json"
EXCLUDED_YAML = PROJECT_ROOT / "config" / "excluded_jobs.yaml"

INBOX.mkdir(parents=True, exist_ok=True)

PORT = 8765

PM_BINDER = {
    "Nelson Belanger": "Nelson_Belanger",
    "Bob Mozine":      "Bob_Mozine",
    "Martin Mannix":   "Martin_Mannix",
    "Jason Szykulski": "Jason_Szykulski",
    "Lee Worthy":      "Lee_Worthy",
}

PM_SLUGS = {pm: pm.lower().replace(" ", "-") for pm in PM_BINDER}


app = Flask(__name__, static_folder=None)


# ----------------------------------------------------------------------
# Subprocess job state (single global lock)
# ----------------------------------------------------------------------
_state_lock = threading.Lock()
_state = {
    "running": False,
    "action": None,           # "process" | "scrape" | "refresh" | None
    "started_at": None,
    "finished_at": None,
    "exit_code": None,
    "lines": [],              # list[str] — captured stdout+stderr
}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%H:%M:%S")


def _push(line: str) -> None:
    with _state_lock:
        _state["lines"].append(line)


def _claim_job(action: str) -> bool:
    """Atomic: try to mark a job as running. Returns False if another
    job is already running."""
    with _state_lock:
        if _state["running"]:
            return False
        _state["running"] = True
        _state["action"] = action
        _state["started_at"] = _ts()
        _state["finished_at"] = None
        _state["exit_code"] = None
        _state["lines"] = []
    return True


def _release_job(exit_code: int) -> None:
    with _state_lock:
        _state["running"] = False
        _state["finished_at"] = _ts()
        _state["exit_code"] = exit_code


def _spawn_one(cmd: list[str], cwd: Path, label: str) -> int:
    """Spawn one subprocess and stream stdout into _state['lines']."""
    _push(f"[{_ts()}] $ {' '.join(str(c) for c in cmd)}  (cwd={cwd})")
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        _push(f"[{_ts()}] ERROR: failed to spawn {label}: {e}")
        return -1
    assert proc.stdout is not None
    for line in proc.stdout:
        _push(line.rstrip("\n"))
    proc.wait()
    _push(f"[{_ts()}] {label} exited with code {proc.returncode}")
    return proc.returncode


def _run_process_thread() -> None:
    rc = _spawn_one([sys.executable, str(PROCESS_PY)], PROJECT_ROOT, "process.py")
    _release_job(rc)


def _run_scrape_thread() -> None:
    if not SCRAPER_JS.exists():
        _push(f"[{_ts()}] ERROR: scraper not found at {SCRAPER_JS}")
        _release_job(-1)
        return
    rc = _spawn_one(["node", "scrape-daily-logs.js", "--incremental"],
                   SCRAPER_DIR, "scrape-daily-logs.js")
    _release_job(rc)


def _run_refresh_thread() -> None:
    rc1 = _spawn_one([sys.executable, str(BUILD_PAGES_PY)], PROJECT_ROOT, "build_pages.py")
    if rc1 != 0:
        _push(f"[{_ts()}] build_pages.py failed (exit={rc1}); aborting before build_meeting_prep")
        _release_job(rc1)
        return
    rc2 = _spawn_one([sys.executable, str(BUILD_MEETING_PREP_PY)], PROJECT_ROOT, "build_meeting_prep.py")
    _release_job(rc2)


def _run_email_pm_thread(pm_slug: str) -> None:
    """Phase 13 — render the unified PM packet live, generate ONE PDF in a
    temp dir, open an Outlook draft with the attachment.

    Uses Outlook .Display() not .Send() — the user reviews the draft and
    clicks Send manually. Matches the v1 email_sender.py pattern.
    """
    import tempfile

    rc = 0
    try:
        if pm_slug not in render_helpers.SLUG_TO_PM:
            _push(f"[{_ts()}] ERROR: unknown PM slug '{pm_slug}'")
            rc = 1
            return
        pm_name = render_helpers.SLUG_TO_PM[pm_slug]

        # Email config
        dist_path = PROJECT_ROOT / "config" / "distribution.json"
        if not dist_path.exists():
            _push(f"[{_ts()}] ERROR: config/distribution.json missing")
            rc = 1
            return
        try:
            dist = json.loads(dist_path.read_text(encoding="utf-8"))
        except Exception as e:
            _push(f"[{_ts()}] ERROR: distribution.json invalid: {e}")
            rc = 1
            return
        to_addr = (dist.get("pm_emails") or {}).get(pm_name)
        if not to_addr:
            _push(f"[{_ts()}] ERROR: no email mapped for '{pm_name}' in distribution.json")
            rc = 1
            return
        always_cc = dist.get("always_cc") or []

        _push(f"[{_ts()}] Rendering unified PM packet for {pm_name}...")
        ctx = render_helpers.load_context()
        top_5 = render_helpers.compute_top_5_by_pm(ctx)
        tracking = render_helpers.compute_tracking(ctx, top_5, persist=False)

        edge = render_helpers.find_edge()
        if edge is None:
            _push(f"[{_ts()}] ERROR: Edge not found. Set EDGE_BINARY env var.")
            rc = 1
            return

        tmpdir = Path(tempfile.mkdtemp(prefix="rb_email_pm_"))
        attachments: list[str] = []
        try:
            html = render_helpers.render_pm_packet(ctx, pm_slug, tracking)
            _push(f"[{_ts()}] Printing packet PDF via Edge ...")
            pdf_bytes = render_helpers.html_to_pdf_bytes(html, edge_path=edge, timeout=90)
            pdf_path = tmpdir / f"{pm_slug}-packet.pdf"
            pdf_path.write_bytes(pdf_bytes)
            attachments.append(str(pdf_path))
            _push(f"[{_ts()}]   {pdf_path.name} -> {len(pdf_bytes):,} bytes")

            # Build subject / body
            first = pm_name.split()[0]
            today_iso = ctx.today
            subject = f"Production Meeting -- {first} -- {today_iso}"
            body_lines = [
                f"Hi {first},",
                "",
                f"Attached is your production document for the week of {today_iso}.",
                "",
                "This is your packet only -- your jobs, your open items, your look-ahead.",
                "The full company-wide analytics live with Jake.",
                "",
                "Please print, mark up throughout the week as items progress or complete,",
                "and bring your marked copy to next week's meeting.",
                "",
                "Anything urgent, text Jake directly.",
                "",
                "-- Ross Built",
            ]
            body = "\n".join(body_lines)

            # Open Outlook draft (Display, not Send -- user reviews then clicks)
            try:
                import pythoncom       # type: ignore
                import win32com.client  # type: ignore
            except ImportError as e:
                _push(f"[{_ts()}] ERROR: pywin32 not installed ({e}). Cannot open Outlook draft.")
                _push(f"[{_ts()}]        PDFs are at: {tmpdir}")
                rc = 1
                return

            pythoncom.CoInitialize()
            try:
                outlook = win32com.client.Dispatch("Outlook.Application")
                mail = outlook.CreateItem(0)  # 0 = olMailItem
                mail.To = to_addr
                if always_cc:
                    mail.CC = "; ".join(always_cc)
                mail.Subject = subject
                mail.Body = body
                for p in attachments:
                    mail.Attachments.Add(str(Path(p).resolve()))
                mail.Display()  # opens draft window; user reviews + sends
                _push(f"[{_ts()}] OK -- Outlook draft opened. To: {to_addr}. "
                      f"Attachments: {[Path(a).name for a in attachments]}")
                _push(f"[{_ts()}]      User reviews + clicks Send in Outlook to deliver.")
            except Exception as e:
                _push(f"[{_ts()}] ERROR: Outlook COM error: {type(e).__name__}: {e}")
                rc = 1
            finally:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        finally:
            # Outlook holds file handles on attachments while the draft is open.
            # We let Windows clean up after reboot rather than racing the user.
            # If you want explicit cleanup, close the Outlook draft first.
            pass

    except Exception as e:
        _push(f"[{_ts()}] ERROR: unhandled in email-pm thread: {type(e).__name__}: {e}")
        rc = 1
    finally:
        _release_job(rc)


# ----------------------------------------------------------------------
# Helpers — read disk artifacts
# ----------------------------------------------------------------------
_OFFICE_RE = re.compile(r"\boffice\b", re.IGNORECASE)
_SITE_RE   = re.compile(r"\bsite\b", re.IGNORECASE)
_PM_FIRST_NAMES = ("nelson", "bob", "lee", "martin", "jason", "jeff")


def _detect_type(fname: str) -> str:
    if _OFFICE_RE.search(fname):
        return "OFFICE"
    if _SITE_RE.search(fname):
        return "SITE"
    return "?"


def _detect_pm(fname: str) -> str:
    low = fname.lower()
    for n in _PM_FIRST_NAMES:
        if n in low:
            return n.capitalize()
    return ""


def _list_inbox() -> list[dict]:
    items = []
    if INBOX.exists():
        for p in sorted(INBOX.glob("*.txt")):
            try:
                stat = p.stat()
            except OSError:
                continue
            items.append({
                "filename": p.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "type": _detect_type(p.name),
                "pm": _detect_pm(p.name),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })
    return items


def _read_status() -> dict:
    """Parse state/LAST_RUN_STATUS.txt key=value lines."""
    if not STATUS_FILE.exists():
        return {"present": False}
    out: dict = {"present": True}
    try:
        for line in STATUS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    except OSError:
        return {"present": False}
    return out


def _iso_week(d: date) -> str:
    iy, iw, _ = d.isocalendar()
    return f"{iy}-W{iw:02d}"


def _pdf_meta(p: Path) -> tuple[int, str]:
    if not p.exists():
        return (0, "—")
    raw = p.read_bytes()
    pages = raw.count(b"/Type /Page") - raw.count(b"/Type /Pages")
    sz = p.stat().st_size
    return (max(0, pages), f"{sz // 1024} KB")


def _load_excluded() -> set:
    if not EXCLUDED_YAML.exists():
        return set()
    cfg = yaml.safe_load(EXCLUDED_YAML.read_text(encoding="utf-8")) or {}
    return {e["job"] for e in cfg.get("excluded", []) if e.get("job")}


def _binder_cards() -> dict:
    """Compute the 8-card payload (5 PMs + 3 leadership).

    Phase 11 — pages render LIVE from /meeting-prep/* on this server. No
    pre-generated HTML or PDF is read from disk. PDFs only generate on
    demand when the user clicks the download URL.
    """
    excluded = _load_excluded()
    BINDERS_DIR = PROJECT_ROOT / "binders"

    # PM aggregates from insights.json
    agg = defaultdict(lambda: {"asks": 0, "critical": 0, "missed": 0})
    if INSIGHTS_JSON.exists():
        try:
            ins_doc = json.loads(INSIGHTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            ins_doc = {"insights": []}
        for i in ins_doc.get("insights", []):
            if i.get("bucket", "field") == "data_quality":
                continue
            pm = i.get("related_pm")
            job = i.get("related_job")
            if not pm or job in excluded:
                continue
            agg[pm]["asks"] += 1
            if i.get("severity") == "critical":
                agg[pm]["critical"] += 1
            if i.get("type") == "missed_commitment":
                agg[pm]["missed"] += 1

    # Build PM cards — alphabetical by first name
    pm_cards = []
    for pm in sorted(PM_BINDER, key=lambda x: x.split()[0]):
        bp = BINDERS_DIR / f"{PM_BINDER[pm]}.json"
        jobs: list[dict] = []
        if bp.exists():
            try:
                for j in json.loads(bp.read_text(encoding="utf-8")).get("jobs", []):
                    jname = j.get("name")
                    if not jname or jname in excluded:
                        continue
                    jobs.append({
                        "name": jname,
                        "slug": re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", jname.lower())).strip("-"),
                    })
            except Exception:
                jobs = []
        slug = PM_SLUGS[pm]
        a = agg.get(pm, {"asks": 0, "critical": 0, "missed": 0})
        pm_cards.append({
            "pm": pm,
            "first": pm.split()[0],
            "slug": slug,
            # Phase 13 — jobs becomes a list of dicts {name, slug} for the
            # "Jobs:" chip row. Backwards-compat: keep a flat names list too.
            "jobs": jobs,
            "job_names": [j["name"] for j in jobs],
            "job_count": len(jobs),
            "asks": a["asks"],
            "critical": a["critical"],
            "packet_html": f"meeting-prep/pm/{slug}",
            "packet_pdf":  f"meeting-prep/pm/{slug}.pdf?download=1",
        })

    # Leadership cards
    total_critical = sum(p["critical"] for p in pm_cards)
    total_asks = sum(p["asks"] for p in pm_cards)

    upcoming_count = 0
    if JOB_STAGES_JSON.exists():
        try:
            js = json.loads(JOB_STAGES_JSON.read_text(encoding="utf-8"))
            for short, j in js.get("jobs", {}).items():
                if short in excluded:
                    continue
                cs = j.get("current_stage")
                if cs is not None and cs <= 1:
                    upcoming_count += 1
        except Exception:
            pass

    def _leader(audience, title, blurb, basename, stat):
        return {
            "audience": audience,
            "title": title,
            "blurb": blurb,
            "html": f"meeting-prep/{basename}.html",
            "pdf":  f"meeting-prep/{basename}.pdf?download=1",
            "stat": stat,
        }

    leadership = [
        _leader("Jake",   "Master",
                "Cross-PM rollup · top red flags · week-over-week accountability",
                "master",
                f"{total_asks} ASKs · {total_critical} critical"),
        _leader("Lee",    "Executive",
                "Exception-only summary · red this week · decisions needed",
                "executive",
                f"{total_critical} jobs flagged red"),
        _leader("Andrew", "Pre-Construction",
                "Forward-looking · upcoming jobs · sub readiness gaps",
                "preconstruction",
                f"{upcoming_count} upcoming job{'' if upcoming_count == 1 else 's'} in 60d"),
    ]

    archive_dir = PROJECT_ROOT / "monday-binder-v1-archive"
    archive_files = []
    if archive_dir.exists():
        for p in sorted(archive_dir.glob("*.html")):
            archive_files.append({"name": p.name, "size": _pdf_meta(p)[1]})

    return {
        "pms": pm_cards,
        "leadership": leadership,
        "archive_files": archive_files,
    }


# ----------------------------------------------------------------------
# Subs / jobs aggregation (Phase 10)
# ----------------------------------------------------------------------
def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower())
    return re.sub(r"-+", "-", s).strip("-")


def _load_sub_overrides() -> dict:
    p = PROJECT_ROOT / "config" / "sub_name_overrides.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _canonicalize_sub(name: str, overrides: dict) -> str:
    if not name:
        return name or ""
    key = name.strip().lower()
    if key in overrides and isinstance(overrides[key], str):
        return overrides[key]
    return name.strip()


def _load_rollups() -> list[dict]:
    p = PROJECT_ROOT / "data" / "sub-phase-rollups.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("rollups", [])
    except Exception:
        return []


def _load_phase_instances() -> list[dict]:
    p = PROJECT_ROOT / "data" / "phase-instances-v2.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("instances", [])
    except Exception:
        return []


def _load_insights_list() -> list[dict]:
    p = PROJECT_ROOT / "data" / "insights.json"
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("insights", [])
    except Exception:
        return []


def _load_job_stages_doc() -> dict:
    p = PROJECT_ROOT / "data" / "job-stages.json"
    if not p.exists():
        return {"jobs": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": {}}


def _load_enriched_items_by_sub() -> dict:
    """Returns {sub_canonical: [item, ...]} from binders/enriched/*.enriched.json."""
    enr_dir = PROJECT_ROOT / "binders" / "enriched"
    out: dict = defaultdict(list)
    overrides = _load_sub_overrides()
    if not enr_dir.exists():
        return out
    for p in sorted(enr_dir.glob("*.enriched.json")):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        pm = doc.get("meta", {}).get("pm", "")
        for it in doc.get("items", []):
            sub = it.get("related_sub")
            if not sub:
                continue
            canon = _canonicalize_sub(sub, overrides)
            out[canon].append({**it, "_pm": pm})
    return out


def _get_subs_aggregate() -> dict:
    overrides = _load_sub_overrides()
    excluded = _load_excluded()
    rollups = _load_rollups()
    instances = _load_phase_instances()
    insights = _load_insights_list()
    js = _load_job_stages_doc()

    subs: dict = {}

    def _ensure(slug: str, sub: str) -> dict:
        if slug not in subs:
            subs[slug] = {
                "sub": sub, "slug": slug,
                "rollup_count": 0, "flag_score": 0, "flagged_count": 0,
                "phase_codes": set(), "density_dist": defaultdict(int),
                "jobs": set(), "drift_count": 0,
            }
        return subs[slug]

    for r in rollups:
        sub = _canonicalize_sub(r.get("sub", ""), overrides)
        if not sub:
            continue
        slug = _slugify(sub)
        d = _ensure(slug, sub)
        d["rollup_count"] += 1
        d["flag_score"] += r.get("flag_score", 0) or 0
        if r.get("flag_for_pm_binder"):
            d["flagged_count"] += 1
        if r.get("phase_code"):
            d["phase_codes"].add(r["phase_code"])
        tier = r.get("primary_density_label") or "unknown"
        d["density_dist"][tier] += 1

    for ins in instances:
        if ins.get("job") in excluded:
            continue
        for s in ins.get("subs_involved", []) or []:
            sub = _canonicalize_sub(s.get("sub", ""), overrides)
            if not sub:
                continue
            slug = _slugify(sub)
            d = _ensure(slug, sub)
            d["jobs"].add(ins["job"])

    for i in insights:
        if i.get("type") != "sub_drift":
            continue
        if i.get("bucket", "field") == "data_quality":
            continue
        sub_raw = i.get("related_sub")
        if not sub_raw:
            continue
        sub = _canonicalize_sub(sub_raw, overrides)
        slug = _slugify(sub)
        if slug in subs:
            subs[slug]["drift_count"] += 1

    active_phase_codes: set = set()
    for short, j in (js.get("jobs") or {}).items():
        if short in excluded:
            continue
        for op in j.get("ongoing_phases", []) or []:
            if op.get("phase_code"):
                active_phase_codes.add(op["phase_code"])

    out = []
    for slug, d in subs.items():
        d["job_count"] = len(d["jobs"])
        d["jobs"] = sorted(d["jobs"])
        d["phase_count"] = len(d["phase_codes"])
        d["active_phase_count"] = len(d["phase_codes"] & active_phase_codes)
        d["density_dist"] = dict(d["density_dist"])
        d["phase_codes"] = sorted(d["phase_codes"])
        out.append(d)

    out.sort(key=lambda x: (-x["flag_score"], -x["flagged_count"], x["sub"].lower()))

    return {
        "subs": out,
        "totals": {
            "total_subs": len(out),
            "rollup_count": sum(s["rollup_count"] for s in out),
            "flagged_count": sum(s["flagged_count"] for s in out),
            "with_drift": sum(1 for s in out if s["drift_count"] > 0),
        },
    }


def _get_sub_detail(slug: str) -> dict | None:
    overrides = _load_sub_overrides()
    excluded = _load_excluded()
    rollups = _load_rollups()
    instances = _load_phase_instances()
    insights = _load_insights_list()
    enriched_by_sub = _load_enriched_items_by_sub()

    target_sub = None
    for r in rollups:
        c = _canonicalize_sub(r.get("sub", ""), overrides)
        if c and _slugify(c) == slug:
            target_sub = c
            break
    if target_sub is None:
        for ins in instances:
            for s in ins.get("subs_involved", []) or []:
                c = _canonicalize_sub(s.get("sub", ""), overrides)
                if c and _slugify(c) == slug:
                    target_sub = c
                    break
            if target_sub:
                break
    if target_sub is None:
        return None

    sub_rollups = [
        {**r, "sub": target_sub}
        for r in rollups
        if _canonicalize_sub(r.get("sub", ""), overrides) == target_sub
    ]
    sub_rollups.sort(key=lambda r: (-(r.get("flag_score") or 0), r.get("phase_code") or ""))

    sub_instances = []
    for ins in instances:
        if ins.get("job") in excluded:
            continue
        for s in ins.get("subs_involved", []) or []:
            if _canonicalize_sub(s.get("sub", ""), overrides) == target_sub:
                sub_instances.append({
                    "job": ins["job"],
                    "job_slug": _slugify(ins["job"]),
                    "phase_code": ins["phase_code"],
                    "phase_name": ins["phase_name"],
                    "status": ins["status"],
                    "sub_active_days": s.get("active_days"),
                    "sub_density": s.get("density"),
                    "sub_density_tier": s.get("density_tier"),
                    "first_log_date": ins.get("first_log_date"),
                    "last_log_date": ins.get("last_log_date"),
                })
                break

    sub_drifts = []
    for i in insights:
        if i.get("type") != "sub_drift":
            continue
        if _canonicalize_sub(i.get("related_sub") or "", overrides) == target_sub:
            sub_drifts.append({
                "job": i.get("related_job"),
                "job_slug": _slugify(i.get("related_job") or ""),
                "phase": i.get("related_phase"),
                "phase_name": i.get("related_phase_name"),
                "summary": i.get("summary_line") or i.get("message"),
                "ask": i.get("ask"),
                "severity": i.get("severity"),
            })

    items = enriched_by_sub.get(target_sub, [])

    distinct_jobs = sorted({i["job"] for i in sub_instances})
    job_links = [{"name": j, "slug": _slugify(j)} for j in distinct_jobs]

    return {
        "sub": target_sub,
        "slug": slug,
        "status": "active",
        "rollups": sub_rollups,
        "instances": sub_instances,
        "drifts": sub_drifts,
        "items": items,
        "jobs": job_links,
        "totals": {
            "rollup_count": len(sub_rollups),
            "instance_count": len(sub_instances),
            "drift_count": len(sub_drifts),
            "item_count": len(items),
            "job_count": len(distinct_jobs),
            "flagged_count": sum(1 for r in sub_rollups if r.get("flag_for_pm_binder")),
            "flag_score_total": sum((r.get("flag_score") or 0) for r in sub_rollups),
        },
    }


def _get_jobs_aggregate() -> dict:
    overrides = _load_sub_overrides()
    excluded = _load_excluded()
    instances = _load_phase_instances()
    rollups = _load_rollups()
    js = _load_job_stages_doc()

    pm_by_job: dict = {}
    job_meta: dict = {}
    for pm, stem in PM_BINDER.items():
        bp = PROJECT_ROOT / "binders" / f"{stem}.json"
        if not bp.exists():
            continue
        try:
            b = json.loads(bp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for j in b.get("jobs", []) or []:
            n = j.get("name")
            if not n or n in excluded:
                continue
            pm_by_job[n] = pm
            job_meta[n] = j

    job_subs: dict = defaultdict(set)
    job_phase_codes: dict = defaultdict(set)
    for ins in instances:
        job = ins.get("job")
        if not job or job in excluded:
            continue
        job_phase_codes[job].add(ins["phase_code"])
        for s in ins.get("subs_involved", []) or []:
            sub = _canonicalize_sub(s.get("sub", ""), overrides)
            if sub:
                job_subs[job].add(sub)

    sub_flagged_phases: dict = defaultdict(set)
    for r in rollups:
        if r.get("flag_for_pm_binder"):
            sub = _canonicalize_sub(r.get("sub", ""), overrides)
            sub_flagged_phases[sub].add(r.get("phase_code"))

    rows = []
    for job, pm in sorted(pm_by_job.items(), key=lambda x: x[0].lower()):
        slug = _slugify(job)
        stage = (js.get("jobs") or {}).get(job, {})
        subs_for_job = job_subs.get(job, set())
        flagged_count = sum(
            1 for sub in subs_for_job
            if sub_flagged_phases.get(sub, set()) & job_phase_codes.get(job, set())
        )
        rows.append({
            "job": job, "slug": slug, "pm": pm,
            "current_stage": stage.get("current_stage"),
            "current_stage_name": stage.get("current_stage_name", ""),
            "ongoing_count": stage.get("ongoing_count", 0),
            "complete_count": stage.get("complete_count", 0),
            "co_target": (job_meta.get(job, {}).get("targetCO") or stage.get("co_target") or "—"),
            "status": job_meta.get(job, {}).get("status", ""),
            "phase_string": job_meta.get(job, {}).get("phase", ""),
            "address": job_meta.get(job, {}).get("address", ""),
            "sub_count": len(subs_for_job),
            "flagged_sub_count": flagged_count,
        })

    return {
        "jobs": rows,
        "totals": {
            "total_jobs": len(rows),
            "with_flagged_subs": sum(1 for j in rows if j["flagged_sub_count"] > 0),
        },
    }


def _get_job_detail(slug: str) -> dict | None:
    overrides = _load_sub_overrides()
    excluded = _load_excluded()
    instances = _load_phase_instances()
    rollups = _load_rollups()
    js = _load_job_stages_doc()

    target_job = None
    target_pm = None
    target_meta: dict | None = None
    target_items: list = []
    for pm, stem in PM_BINDER.items():
        bp = PROJECT_ROOT / "binders" / f"{stem}.json"
        if not bp.exists():
            continue
        try:
            b = json.loads(bp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for j in b.get("jobs", []) or []:
            n = j.get("name")
            if not n or n in excluded:
                continue
            if _slugify(n) == slug:
                target_job = n
                target_pm = pm
                target_meta = j
                target_items = [it for it in (b.get("items") or []) if it.get("job") == n]
                break
        if target_job:
            break
    if target_job is None:
        return None

    stage = (js.get("jobs") or {}).get(target_job, {})

    sub_data: dict = defaultdict(lambda: {"phases": [], "total_active_days": 0})
    job_phase_codes: set = set()
    job_instances = []
    for ins in instances:
        if ins.get("job") != target_job:
            continue
        job_phase_codes.add(ins["phase_code"])
        job_instances.append({
            "phase_code": ins["phase_code"],
            "phase_name": ins["phase_name"],
            "stage": ins.get("stage"),
            "stage_name": ins.get("stage_name"),
            "status": ins.get("status"),
            "primary_density": ins.get("primary_density"),
            "primary_density_tier": ins.get("primary_density_tier"),
            "primary_active_days": ins.get("primary_active_days"),
            "first_log_date": ins.get("first_log_date"),
            "last_log_date": ins.get("last_log_date"),
        })
        for s in ins.get("subs_involved", []) or []:
            sub = _canonicalize_sub(s.get("sub", ""), overrides)
            if not sub:
                continue
            sub_data[sub]["phases"].append({
                "phase_code": ins["phase_code"],
                "phase_name": ins["phase_name"],
                "active_days": s.get("active_days"),
                "density": s.get("density"),
                "density_tier": s.get("density_tier"),
                "phase_status": ins.get("status"),
            })
            sub_data[sub]["total_active_days"] += (s.get("active_days") or 0)

    sub_flagged_phases: dict = defaultdict(set)
    for r in rollups:
        if r.get("flag_for_pm_binder"):
            sub = _canonicalize_sub(r.get("sub", ""), overrides)
            sub_flagged_phases[sub].add(r.get("phase_code"))

    subs_list = []
    for sub, d in sub_data.items():
        flagged_phases_for_this_job = sub_flagged_phases.get(sub, set()) & job_phase_codes
        subs_list.append({
            "sub": sub,
            "slug": _slugify(sub),
            "phases": d["phases"],
            "phase_count": len(d["phases"]),
            "total_active_days": d["total_active_days"],
            "is_flagged": bool(flagged_phases_for_this_job),
            "flagged_phases": sorted(flagged_phases_for_this_job),
        })
    subs_list.sort(key=lambda s: (not s["is_flagged"], -s["total_active_days"]))

    def _phase_key(p):
        try:
            parts = p["phase_code"].split(".")
            return tuple(int(x) for x in parts)
        except Exception:
            return (99, 99)
    job_instances.sort(key=_phase_key)

    return {
        "job": target_job, "slug": slug, "pm": target_pm,
        "address": (target_meta or {}).get("address") or "—",
        "phase_string": (target_meta or {}).get("phase") or "",
        "status": (target_meta or {}).get("status") or "",
        "target_co": (target_meta or {}).get("targetCO") or stage.get("co_target") or "—",
        "current_stage": stage.get("current_stage"),
        "current_stage_name": stage.get("current_stage_name", ""),
        "ongoing_count": stage.get("ongoing_count", 0),
        "complete_count": stage.get("complete_count", 0),
        "subs": subs_list,
        "instances": job_instances,
        "items": target_items,
        "totals": {
            "sub_count": len(subs_list),
            "flagged_sub_count": sum(1 for s in subs_list if s["is_flagged"]),
            "instance_count": len(job_instances),
            "item_count": len(target_items),
        },
    }


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return INDEX_HTML


@app.route("/assets/<path:fname>")
def assets(fname: str):
    if not ASSETS_DIR.exists():
        abort(404)
    safe = (ASSETS_DIR / fname).resolve()
    try:
        safe.relative_to(ASSETS_DIR)
    except ValueError:
        abort(404)
    if not safe.exists() or not safe.is_file():
        abort(404)
    return send_from_directory(str(ASSETS_DIR), fname)


# ----------------------------------------------------------------------
# Meeting-prep live routes (Phase 11)
# Pages render fresh on every request from current binder + insights data.
# PDFs generate on-demand at click time; never stored on disk.
# ----------------------------------------------------------------------
def _no_store_html(html: str) -> Response:
    """Wrap rendered HTML with no-store cache headers so browsers always
    re-fetch — required by spec: live views must reflect current data."""
    resp = Response(html, mimetype="text/html")
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


def _build_render_state():
    """Load context, compute top-5, compute readonly tracking. Used by
    every live HTML and on-demand PDF route. Reads everything fresh."""
    ctx = render_helpers.load_context()
    top_5 = render_helpers.compute_top_5_by_pm(ctx)
    tracking = render_helpers.compute_tracking(ctx, top_5, persist=False)
    return ctx, tracking


def _pdf_response(html: str, filename: str, download: bool) -> Response:
    """Render HTML to PDF via Edge headless and return as attachment
    (download=True) or inline."""
    edge = render_helpers.find_edge()
    if edge is None:
        return Response(
            "Edge not found at standard install paths. "
            "Set EDGE_BINARY env var to msedge.exe.\n",
            status=503,
            mimetype="text/plain",
        )
    try:
        pdf_bytes = render_helpers.html_to_pdf_bytes(html, edge_path=edge, timeout=60)
    except Exception as e:
        return Response(
            f"PDF generation failed: {type(e).__name__}: {e}\n",
            status=500,
            mimetype="text/plain",
        )
    disposition = "attachment" if download else "inline"
    return Response(pdf_bytes, mimetype="application/pdf", headers={
        "Cache-Control": "no-store",
        "Content-Disposition": f'{disposition}; filename="{filename}"',
    })


@app.route("/meeting-prep/master.html")
def mp_master_html():
    ctx, tracking = _build_render_state()
    return _no_store_html(render_helpers.render_master(ctx, tracking))


@app.route("/meeting-prep/executive.html")
def mp_executive_html():
    ctx, tracking = _build_render_state()
    return _no_store_html(render_helpers.render_executive(ctx, tracking))


@app.route("/meeting-prep/preconstruction.html")
def mp_precon_html():
    ctx, _tracking = _build_render_state()
    return _no_store_html(render_helpers.render_preconstruction(ctx))


@app.route("/meeting-prep/pm/<pm_slug>.html")
@app.route("/meeting-prep/pm/<pm_slug>")
def mp_pm_packet_html(pm_slug: str):
    """Phase 13 — unified PM packet (no office/site mode). Aggregates the
    PM's jobs into one document, each rendered as a job-document section."""
    ctx, tracking = _build_render_state()
    try:
        return _no_store_html(render_helpers.render_pm_packet(ctx, pm_slug, tracking))
    except KeyError:
        abort(404)


@app.route("/meeting-prep/job/<job_slug>.html")
@app.route("/meeting-prep/job/<job_slug>")
def mp_job_html(job_slug: str):
    """Phase 13 — single-job living document."""
    ctx, tracking = _build_render_state()
    try:
        return _no_store_html(render_helpers.render_job_document(ctx, job_slug, tracking))
    except KeyError:
        abort(404)


@app.route("/meeting-prep/master.pdf")
def mp_master_pdf():
    download = request.args.get("download") == "1"
    ctx, tracking = _build_render_state()
    html = render_helpers.render_master(ctx, tracking)
    return _pdf_response(html, "master.pdf", download)


@app.route("/meeting-prep/executive.pdf")
def mp_executive_pdf():
    download = request.args.get("download") == "1"
    ctx, tracking = _build_render_state()
    html = render_helpers.render_executive(ctx, tracking)
    return _pdf_response(html, "executive.pdf", download)


@app.route("/meeting-prep/preconstruction.pdf")
def mp_precon_pdf():
    download = request.args.get("download") == "1"
    ctx, _tracking = _build_render_state()
    html = render_helpers.render_preconstruction(ctx)
    return _pdf_response(html, "preconstruction.pdf", download)


@app.route("/meeting-prep/pm/<pm_slug>.pdf")
def mp_pm_packet_pdf(pm_slug: str):
    """Phase 13 — single PDF for the unified PM packet."""
    download = request.args.get("download") == "1"
    ctx, tracking = _build_render_state()
    try:
        html = render_helpers.render_pm_packet(ctx, pm_slug, tracking)
    except KeyError:
        abort(404)
    return _pdf_response(html, f"{pm_slug}.pdf", download)


@app.route("/meeting-prep/job/<job_slug>.pdf")
def mp_job_pdf(job_slug: str):
    """Phase 13 — on-demand single-job PDF."""
    download = request.args.get("download") == "1"
    ctx, tracking = _build_render_state()
    try:
        html = render_helpers.render_job_document(ctx, job_slug, tracking)
    except KeyError:
        abort(404)
    return _pdf_response(html, f"{job_slug}.pdf", download)


@app.route("/archive/<path:rest>")
def serve_archive(rest: str):
    base = PROJECT_ROOT / "monday-binder-v1-archive"
    safe = (base / rest).resolve()
    try:
        safe.relative_to(base)
    except ValueError:
        abort(404)
    if not safe.exists() or not safe.is_file():
        abort(404)
    return send_from_directory(str(base), rest)


@app.route("/api/inbox")
def api_inbox():
    return jsonify({"inbox": _list_inbox()})


@app.route("/api/binder-status")
def api_binder_status():
    s = _read_status()
    today = date.today()
    s["iso_week_today"] = _iso_week(today)
    s["today"] = today.isoformat()
    return jsonify(s)


@app.route("/api/binder-cards")
def api_binder_cards():
    return jsonify(_binder_cards())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "no files in request"}), 400
    saved = []
    for f in files:
        if not f or not f.filename:
            continue
        name = Path(f.filename).name
        if not name.lower().endswith(".txt"):
            continue
        target = INBOX / name
        if target.exists():
            stem, suffix = target.stem, target.suffix
            n = 2
            while (INBOX / f"{stem} ({n}){suffix}").exists():
                n += 1
            target = INBOX / f"{stem} ({n}){suffix}"
        f.save(str(target))
        saved.append(target.name)
    return jsonify({"saved": saved, "inbox": _list_inbox()})


@app.route("/api/process", methods=["POST"])
def api_process():
    if not _claim_job("process"):
        return jsonify({"error": f"another job is running ({_state['action']})"}), 409
    threading.Thread(target=_run_process_thread, daemon=True).start()
    return jsonify({"started": True, "action": "process"})


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    if not _claim_job("scrape"):
        return jsonify({"error": f"another job is running ({_state['action']})"}), 409
    threading.Thread(target=_run_scrape_thread, daemon=True).start()
    return jsonify({"started": True, "action": "scrape"})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    if not _claim_job("refresh"):
        return jsonify({"error": f"another job is running ({_state['action']})"}), 409
    threading.Thread(target=_run_refresh_thread, daemon=True).start()
    return jsonify({"started": True, "action": "refresh"})


@app.route("/api/email-pm", methods=["POST"])
def api_email_pm():
    """Phase 13 — render the unified PM packet, generate ONE PDF, open an
    Outlook draft. Body shape simplified to {"pm_slug": "..."} only —
    "include" parameter removed (was office/site mode toggle).
    Concurrency-locked with the existing subprocess gate."""
    body = request.get_json(silent=True) or {}
    pm_slug = (body.get("pm_slug") or "").strip()
    if not pm_slug:
        return jsonify({"error": "pm_slug required"}), 400
    if pm_slug not in render_helpers.SLUG_TO_PM:
        return jsonify({"error": f"unknown pm_slug '{pm_slug}'"}), 404

    if not _claim_job(f"email:{pm_slug}"):
        return jsonify({"error": f"another job is running ({_state['action']})"}), 409
    threading.Thread(
        target=_run_email_pm_thread,
        args=(pm_slug,),
        daemon=True,
    ).start()
    pm_name = render_helpers.SLUG_TO_PM[pm_slug]
    dist_path = PROJECT_ROOT / "config" / "distribution.json"
    to_addr = ""
    if dist_path.exists():
        try:
            to_addr = (json.loads(dist_path.read_text(encoding="utf-8")).get("pm_emails") or {}).get(pm_name, "")
        except Exception:
            pass
    return jsonify({
        "started": True,
        "action": f"email:{pm_slug}",
        "pm": pm_name,
        "to": to_addr,
        "note": "Outlook draft opens via .Display() -- user reviews + clicks Send.",
    })


@app.route("/api/status")
def api_status():
    since = int(request.args.get("since", "0"))
    with _state_lock:
        total = len(_state["lines"])
        new_lines = _state["lines"][since:]
        return jsonify({
            "running": _state["running"],
            "action": _state["action"],
            "started_at": _state["started_at"],
            "finished_at": _state["finished_at"],
            "exit_code": _state["exit_code"],
            "total_lines": total,
            "new_lines": new_lines,
        })


# ----------------------------------------------------------------------
# Phase 10 — sub/job routes
# ----------------------------------------------------------------------
@app.route("/api/subs")
def api_subs():
    return jsonify(_get_subs_aggregate())


@app.route("/api/subs/<slug>")
def api_sub_detail(slug):
    d = _get_sub_detail(slug)
    if d is None:
        return jsonify({"error": "sub not found"}), 404
    return jsonify(d)


@app.route("/api/jobs")
def api_jobs():
    return jsonify(_get_jobs_aggregate())


@app.route("/api/jobs/<slug>")
def api_job_detail(slug):
    d = _get_job_detail(slug)
    if d is None:
        return jsonify({"error": "job not found"}), 404
    return jsonify(d)


@app.route("/subs")
def page_subs():
    return SUBS_HTML


@app.route("/subs/<slug>")
def page_sub_detail(slug):
    return SUB_DETAIL_HTML


@app.route("/jobs")
def page_jobs():
    return JOBS_HTML


@app.route("/jobs/<slug>")
def page_job_detail(slug):
    return JOB_DETAIL_HTML


# ----------------------------------------------------------------------
# Inline HTML
# ----------------------------------------------------------------------
INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Ross Built Monday Ops</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<link rel="stylesheet" href="/assets/nightwork-tokens.css">
<style>
  body { padding: 0; }
  *, *::before, *::after { font-variant-numeric: tabular-nums; }
  .ops { max-width: 9.5in; margin: 0 auto; padding: 0 36px 80px; font-family: var(--font-body); color: var(--ink); }

  /* ---------- Sticky status bar ---------- */
  .status-bar {
    position: sticky; top: 0; z-index: 50;
    background: var(--bg);
    padding: 12px 0 10px;
    border-bottom: 1.5px solid var(--ink);
    margin-bottom: 28px;
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 18px;
  }
  .status-bar .brand {
    font-family: var(--font-head);
    font-weight: 700;
    font-size: 16px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--ink);
  }
  .status-bar .meta-line {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-2);
    margin-top: 4px;
    display: flex; gap: 16px; flex-wrap: wrap;
  }
  .status-bar .meta-line .lbl {
    color: var(--ink-3); text-transform: uppercase;
    font-size: 9.5px; letter-spacing: 0.7px; margin-right: 4px;
  }
  .status-bar .meta-line .pass { color: var(--success); font-weight: 600; }
  .status-bar .meta-line .fail { color: var(--nw-danger); font-weight: 600; }
  .status-bar .right {
    text-align: right;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--ink-2);
  }
  .status-bar .right .now {
    font-size: 14px; color: var(--ink); margin-bottom: 2px;
  }

  /* ---------- Section labels ---------- */
  .sec-label {
    font-family: var(--font-head);
    font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: var(--ink); margin: 32px 0 12px;
    padding-bottom: 7px;
    border-bottom: 1px solid var(--accent);
    display: flex; justify-content: space-between; align-items: baseline;
  }
  .sec-label:first-of-type { margin-top: 0; }
  .sec-label .badge {
    font-family: var(--font-mono);
    font-size: 10.5px; text-transform: none; letter-spacing: 0.4px;
    color: var(--ink-3); font-weight: 500;
  }

  /* ---------- 8-card binder grid ---------- */
  .card-grid { display: grid; grid-template-columns: 1fr; gap: 8px; }
  .primary-card {
    background: var(--bg-card);
    border: 1px solid var(--line);
    padding: 12px 18px;
    transition: background-color 0.12s ease, border-color 0.12s ease;
  }
  .primary-card:hover {
    background: var(--bg-soft);
    border-color: var(--ink-2);
  }
  .pm-card    { border-left: 4px solid var(--ink); }
  .leader-card {
    border-left: 4px solid var(--accent);
    background: rgba(91, 134, 153, 0.04);
  }
  .leader-card:hover { background: rgba(91, 134, 153, 0.08); }
  .card-head {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 18px;
  }
  .card-title h2 {
    font-family: var(--font-head);
    font-size: 17px; font-weight: 700;
    letter-spacing: 1px; text-transform: uppercase;
    color: var(--ink); margin: 0 0 3px;
  }
  .card-title .card-sub {
    font-family: var(--font-mono);
    font-size: 11.5px; color: var(--ink-2); line-height: 1.4;
  }
  .card-stat {
    display: flex; align-items: baseline; gap: 5px;
    font-family: var(--font-mono); white-space: nowrap;
  }
  .card-stat .stat-num {
    font-family: var(--font-head);
    font-size: 20px; font-weight: 700;
    color: var(--ink); line-height: 1;
  }
  .card-stat .stat-num.alert { color: var(--nw-danger); }
  .card-stat .stat-lbl {
    font-size: 9.5px; text-transform: uppercase;
    letter-spacing: 0.7px; color: var(--ink-3); margin-right: 4px;
  }
  .card-stat .stat-lbl.alert { color: var(--nw-danger); font-weight: 600; }
  .card-stat .stat-divider { color: var(--ink-3); margin: 0 3px; }
  .card-stat .stat-text { font-size: 11px; color: var(--ink-2); }
  .card-actions { display: flex; gap: 8px; margin-top: 10px; }
  .btn-card {
    flex: 1; border: 1px solid var(--ink);
    padding: 8px 14px;
    font-family: var(--font-mono);
    font-size: 11.5px;
    color: var(--ink); text-decoration: none;
    background: var(--bg-card);
    display: flex; align-items: baseline; justify-content: space-between; gap: 10px;
    transition: background-color 0.12s ease, color 0.12s ease;
  }
  .btn-card:hover { background: var(--ink); color: var(--bg); }
  .btn-card:hover .btn-meta { color: rgba(247, 245, 236, 0.7); }
  .btn-card.primary { background: var(--ink); color: var(--bg); }
  .btn-card.primary:hover { background: var(--accent); border-color: var(--accent); }
  .btn-card .btn-label {
    font-size: 12px; font-weight: 600;
    letter-spacing: 0.5px; text-transform: uppercase;
  }
  .btn-card .btn-meta {
    font-size: 10px; color: var(--ink-3); letter-spacing: 0.3px;
  }
  .btn-card.primary .btn-meta { color: rgba(247, 245, 236, 0.6); }
  .leader-card .btn-card.primary { background: var(--accent); border-color: var(--accent); }
  .leader-card .btn-card.primary:hover { background: var(--ink); border-color: var(--ink); }

  /* ---------- Pipeline section ---------- */
  .dropzone {
    border: 1.5px dashed var(--ink-3);
    background: var(--bg-soft);
    padding: 36px 28px;
    text-align: center;
    color: var(--ink-2);
    font-family: var(--font-mono);
    font-size: 12px;
    cursor: pointer;
    transition: background-color 0.12s ease, border-color 0.12s ease, color 0.12s ease;
  }
  .dropzone:hover, .dropzone.drag {
    background: rgba(91, 134, 153, 0.08);
    border-color: var(--accent);
    color: var(--ink);
  }
  .dropzone .glyph {
    font-family: var(--font-head);
    font-size: 28px; font-weight: 700;
    color: var(--accent);
    display: block;
    margin-bottom: 10px;
    line-height: 1;
  }
  .dropzone .primary-text {
    font-family: var(--font-head);
    font-size: 14px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 1.5px;
    color: var(--ink);
    margin-bottom: 4px;
  }
  .dropzone .secondary-text {
    font-size: 11px; color: var(--ink-3); letter-spacing: 0.3px;
  }
  .dropzone input[type=file] { display: none; }

  /* Inbox table */
  .inbox-wrap { margin-top: 14px; }
  .inbox-table { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 11.5px; }
  .inbox-table th {
    text-align: left; padding: 5px 10px;
    border-bottom: 1px solid var(--line);
    color: var(--ink-3);
    font-size: 9.5px; text-transform: uppercase;
    letter-spacing: 0.7px; font-weight: 500;
  }
  .inbox-table td {
    padding: 6px 10px;
    border-bottom: 1px dotted var(--line-2);
    color: var(--ink); vertical-align: top;
  }
  .pill {
    display: inline-block; padding: 1px 7px;
    font-size: 9.5px; letter-spacing: 0.5px;
    text-transform: uppercase; font-weight: 600;
    border: 1px solid;
  }
  .pill.OFFICE { color: var(--accent); border-color: var(--accent); }
  .pill.SITE { color: var(--success); border-color: var(--success); }
  .pill.unknown { color: var(--ink-muted); border-color: var(--line); }
  .inbox-empty {
    color: var(--ink-muted); font-style: italic;
    padding: 8px 0; font-family: var(--font-mono); font-size: 11px;
  }

  /* Action row */
  .actions-row {
    margin-top: 16px;
    display: flex; gap: 10px; align-items: stretch; flex-wrap: wrap;
  }
  .btn-action {
    flex: 1 1 0;
    min-width: 200px;
    border: 1.5px solid;
    padding: 12px 18px;
    font-family: var(--font-mono);
    font-size: 11px; font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    cursor: pointer;
    transition: background-color 0.12s ease, color 0.12s ease, border-color 0.12s ease, opacity 0.12s ease;
    text-align: center;
  }
  .btn-action.primary {
    background: var(--ink); border-color: var(--ink); color: var(--bg);
  }
  .btn-action.primary:hover:not(:disabled) {
    background: var(--accent); border-color: var(--accent);
  }
  .btn-action.outline {
    background: transparent; border-color: var(--accent); color: var(--accent);
  }
  .btn-action.outline:hover:not(:disabled) {
    background: var(--accent); color: var(--bg);
  }
  .btn-action:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  /* Run header + log */
  .run-header {
    margin-top: 22px;
    padding: 8px 14px;
    background: var(--ink);
    color: var(--bg);
    font-family: var(--font-mono);
    font-size: 11px;
    letter-spacing: 0.5px;
    display: flex; justify-content: space-between; align-items: baseline;
  }
  .run-header .lhs {
    text-transform: uppercase; font-weight: 600; letter-spacing: 1.5px;
  }
  .run-header .status-pill {
    font-size: 10.5px;
    padding: 2px 8px;
    background: rgba(247, 245, 236, 0.15);
  }
  .run-header.running .status-pill { background: var(--warn); color: var(--ink); }
  .run-header.ok .status-pill { background: var(--success); color: var(--bg); }
  .run-header.err .status-pill { background: var(--nw-danger); color: var(--bg); }

  .log {
    background: var(--ink);
    color: var(--bg);
    font-family: var(--font-mono);
    font-size: 11px; line-height: 1.55;
    padding: 14px 18px;
    height: 360px;
    overflow-y: auto;
    white-space: pre-wrap;
    word-break: break-word;
  }
  .log:empty::before {
    content: '(no output yet — start a job above)';
    color: rgba(247, 245, 236, 0.45);
    font-style: italic;
  }

  /* Sub-performance totals (dashboard inline) */
  #subperf-totals .key { color: var(--ink-3); text-transform: uppercase; font-size: 9.5px; letter-spacing: 0.7px; margin-right: 4px; }
  #subperf-totals strong { font-family: var(--font-head); font-size: 17px; font-weight: 700; color: var(--ink); }
  #subperf-totals strong.alert { color: var(--nw-danger); }
  #subperf-totals span span.key + strong { margin-left: 4px; }

  /* Dev details */
  details.dev {
    margin-top: 36px;
    border-top: 1px solid var(--line);
    padding-top: 14px;
  }
  details.dev summary {
    cursor: pointer;
    font-family: var(--font-mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: var(--ink-3);
    list-style: none;
    padding: 4px 0;
  }
  details.dev summary::-webkit-details-marker { display: none; }
  details.dev summary::before { content: "▸ "; }
  details.dev[open] summary::before { content: "▾ "; }
  details.dev summary:hover { color: var(--ink); }
  details.dev .blurb {
    font-family: var(--font-body); font-size: 11.5px;
    color: var(--ink-3); margin: 8px 0 12px; line-height: 1.55;
  }
  details.dev ul {
    list-style: none; padding: 0; margin: 0;
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3px 18px;
    font-family: var(--font-mono); font-size: 11px;
  }
  details.dev a {
    color: var(--ink-2); text-decoration: none; font-size: 10.5px;
  }
  details.dev a:hover {
    color: var(--accent); text-decoration: underline;
  }
  details.dev .dim {
    color: var(--ink-muted); font-size: 9.5px; margin-left: 4px;
  }
  details.dev li.divider {
    grid-column: 1 / -1;
    margin-top: 10px; padding-bottom: 4px;
    border-bottom: 1px solid var(--line-2);
    color: var(--ink-3); text-transform: uppercase;
    font-size: 9.5px; letter-spacing: 0.8px;
  }
</style>
</head>
<body>
<div class="ops">

  <header class="status-bar">
    <div>
      <div class="brand">ROSS BUILT · MONDAY OPS</div>
      <div class="meta-line" id="status-meta"><span class="lbl">loading…</span></div>
    </div>
    <div class="right">
      <div class="now" id="now"></div>
      <div>localhost:8765</div>
    </div>
  </header>

  <h3 class="sec-label">Monday Binder <span class="badge" id="binder-badge">5 PMs · 3 leadership · live render</span></h3>
  <div class="card-grid" id="pm-grid"></div>
  <h3 class="sec-label">Leadership Views <span class="badge">cross-PM rollups</span></h3>
  <div class="card-grid" id="leader-grid"></div>

  <h3 class="sec-label">Transcript Pipeline <span class="badge" id="pipeline-badge"></span></h3>
  <label class="dropzone" id="dropzone" for="file-input">
    <span class="glyph">+</span>
    <div class="primary-text">Drop transcripts</div>
    <div class="secondary-text">drag .txt files here · or click to browse</div>
    <input type="file" id="file-input" multiple accept=".txt">
  </label>

  <div class="inbox-wrap" id="inbox-wrap"></div>

  <div class="actions-row">
    <button id="btn-process" class="btn-action primary" data-action="process">Process All Transcripts</button>
    <button id="btn-scrape" class="btn-action outline" data-action="scrape">Scrape Daily Logs</button>
    <button id="btn-refresh" class="btn-action outline" data-action="refresh">Refresh Binders</button>
  </div>

  <div class="run-header" id="run-header">
    <span class="lhs">RUN · <span id="run-action">idle</span></span>
    <span class="status-pill" id="run-status">idle</span>
  </div>
  <pre class="log" id="log"></pre>

  <h3 class="sec-label">Sub Performance <span class="badge" id="subperf-badge">…</span></h3>
  <div class="totals" id="subperf-totals" style="display:flex;gap:28px;flex-wrap:wrap;background:var(--bg-soft);border-left:3px solid var(--accent);padding:10px 18px;font-family:var(--font-mono);font-size:12px;color:var(--ink);"><span style="color:var(--ink-3);text-transform:uppercase;font-size:9.5px;letter-spacing:0.7px;">loading…</span></div>
  <div class="actions-row">
    <a class="btn-action primary" href="/subs">Open Sub Roster</a>
    <a class="btn-action outline" href="/jobs">Open Job Breakdown</a>
  </div>

  <details class="dev">
    <summary>Developer artifacts (HTML sources, v1 archive)</summary>
    <p class="blurb">
      Browser-only HTML sources for the v2 PDFs (show the data-quality bucket that print mode hides) and the v1 archive
      (legacy single-page binder + per-PM packets, retained for rollback only — do not modify). Not for daily Monday use.
    </p>
    <ul id="dev-list"></ul>
  </details>

</div>

<script>
(function () {
  const $ = id => document.getElementById(id);

  // ---------- Status bar ----------
  function renderStatusBar() {
    fetch('/api/binder-status').then(r => r.json()).then(s => {
      const meta = $('status-meta');
      const parts = [];
      if (s.present && s.last_run_at) {
        const overall = (s.overall || '').toUpperCase();
        const cls = overall === 'PASS' ? 'pass' : 'fail';
        parts.push('<span><span class="lbl">Last auto-run</span>' + escapeHtml(s.last_run_at) + '</span>');
        parts.push('<span><span class="lbl">overall</span><span class="' + cls + '">' + escapeHtml(overall || '—') + '</span></span>');
        if (s.banner) {
          parts.push('<span><span class="lbl">banner</span>' + escapeHtml(s.banner.slice(0, 80)) + (s.banner.length > 80 ? '…' : '') + '</span>');
        }
      } else {
        parts.push('<span><span class="lbl">Last auto-run</span>none recorded</span>');
      }
      parts.push('<span><span class="lbl">iso week</span>' + escapeHtml(s.iso_week_today || '—') + '</span>');
      meta.innerHTML = parts.join('');
    }).catch(() => {
      $('status-meta').innerHTML = '<span class="lbl">status unavailable</span>';
    });
  }

  function tickClock() {
    const d = new Date();
    const dow = ['SUN','MON','TUE','WED','THU','FRI','SAT'][d.getDay()];
    const md = d.toLocaleString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
    const hm = d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
    $('now').textContent = dow + ' · ' + md + ' · ' + hm;
  }
  tickClock();
  setInterval(tickClock, 30000);

  // ---------- Binder cards ----------
  function escapeHtml(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, c =>
      ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])
    );
  }

  function renderPMCard(p) {
    const job_label = p.job_count === 1 ? 'job' : 'jobs';
    const critPart = p.critical > 0
      ? '<span class="stat-divider">·</span><span class="stat-num alert">' + p.critical + '</span><span class="stat-lbl alert">crit</span>'
      : '';
    const askCls = p.critical > 0 ? 'alert' : '';
    // Phase 13 — Jobs: chips linking directly to /meeting-prep/job/<slug>
    const jobChips = (p.jobs || []).length
      ? '<div class="job-chips" style="margin-top:6px;font-family:var(--font-mono);font-size:10.5px;color:var(--ink-3);"><span style="text-transform:uppercase;letter-spacing:0.6px;color:var(--ink-3);">Jobs:</span> ' +
        p.jobs.map(j =>
          `<a href="meeting-prep/job/${escapeHtml(j.slug)}" target="_blank" rel="noopener" style="color:var(--accent);text-decoration:none;background:var(--bg-soft);padding:1px 6px;margin:0 2px;border:1px solid var(--line);">${escapeHtml(j.name)}</a>`
        ).join(' ') +
        '</div>'
      : '<div class="card-sub"><em>no jobs</em></div>';
    return `
      <article class="primary-card pm-card">
        <div class="card-head">
          <div class="card-title">
            <h2>${escapeHtml(p.pm.toUpperCase())}</h2>
            ${jobChips}
          </div>
          <div class="card-stat">
            <span class="stat-num">${p.job_count}</span><span class="stat-lbl">${job_label}</span>
            <span class="stat-divider">·</span>
            <span class="stat-num ${askCls}">${p.asks}</span><span class="stat-lbl">asks</span>
            ${critPart}
          </div>
        </div>
        <div class="card-actions">
          <a class="btn-card primary" href="${escapeHtml(p.packet_html)}" target="_blank" rel="noopener">
            <span class="btn-label">Open Packet</span>
          </a>
          <a class="btn-card outline" href="${escapeHtml(p.packet_pdf)}">
            <span class="btn-label">Download PDF</span>
          </a>
          <button class="btn-card outline" data-email-pm="${escapeHtml(p.slug)}">
            <span class="btn-label">Email</span>
          </button>
        </div>
      </article>`;
  }

  function renderLeaderCard(r) {
    return `
      <article class="primary-card leader-card">
        <div class="card-head">
          <div class="card-title">
            <h2>${escapeHtml(r.audience.toUpperCase())} · ${escapeHtml(r.title)}</h2>
            <div class="card-sub">${escapeHtml(r.blurb)}</div>
          </div>
          <div class="card-stat">
            <span class="stat-text">${escapeHtml(r.stat)}</span>
          </div>
        </div>
        <div class="card-actions">
          <a class="btn-card primary" href="${escapeHtml(r.html)}" target="_blank" rel="noopener">
            <span class="btn-label">Open ${escapeHtml(r.title)}</span>
          </a>
          <a class="btn-card outline" href="${escapeHtml(r.pdf)}">
            <span class="btn-label">Download PDF</span>
          </a>
        </div>
      </article>`;
  }

  function renderDevList(archive) {
    const html = [];
    html.push(
      '<li class="note">Live-rendered routes — see <code>/meeting-prep/*</code> in the address bar. ' +
      'No static HTML files exist; views render on demand from current binder data.</li>'
    );
    if (archive.length) {
      html.push('<li class="divider">v1 archive (rollback only · do not modify)</li>');
      for (const f of archive) {
        html.push('<li><a href="/archive/' + escapeHtml(f.name) + '">' + escapeHtml(f.name) + '</a><span class="dim">' + escapeHtml(f.size) + '</span></li>');
      }
    }
    $('dev-list').innerHTML = html.join('');
  }

  function renderBinderCards() {
    fetch('/api/binder-cards').then(r => r.json()).then(j => {
      $('pm-grid').innerHTML = (j.pms || []).map(renderPMCard).join('');
      $('leader-grid').innerHTML = (j.leadership || []).map(renderLeaderCard).join('');
      renderDevList(j.archive_files || []);
      // Wire EMAIL buttons (delegated handler is below in main script)
    });
  }

  // Delegated click handler for "Email" buttons on PM cards
  document.addEventListener('click', async function(ev) {
    const btn = ev.target.closest('button[data-email-pm]');
    if (!btn) return;
    ev.preventDefault();
    const slug = btn.getAttribute('data-email-pm');
    if (!slug) return;
    btn.disabled = true;
    btn.querySelector('.btn-label').textContent = 'Sending…';
    try {
      const r = await fetch('/api/email-pm', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pm_slug: slug})
      });
      const j = await r.json();
      if (!r.ok) {
        btn.querySelector('.btn-label').textContent = 'Failed';
        alert('Email failed: ' + (j.error || r.status));
      } else {
        btn.querySelector('.btn-label').textContent = 'Outlook Draft';
        // Live log will show progress
      }
    } catch (e) {
      btn.querySelector('.btn-label').textContent = 'Error';
      alert('Email error: ' + e.message);
    } finally {
      setTimeout(() => {
        btn.disabled = false;
        btn.querySelector('.btn-label').textContent = 'Email';
      }, 4000);
    }
  });

  // ---------- Inbox / pipeline ----------
  function renderInbox(items) {
    $('pipeline-badge').textContent = items.length + ' file' + (items.length === 1 ? '' : 's') + ' pending';
    if (!items.length) {
      $('inbox-wrap').innerHTML = '<div class="inbox-empty">no transcripts pending — drop .txt files above</div>';
      $('btn-process').disabled = true;
      return;
    }
    $('btn-process').disabled = false;
    let html = '<table class="inbox-table"><thead><tr>' +
      '<th>Filename</th><th>PM</th><th>Type</th><th style="text-align:right">Size</th><th>Modified</th>' +
      '</tr></thead><tbody>';
    for (const it of items) {
      const typeCls = (it.type === 'OFFICE' || it.type === 'SITE') ? it.type : 'unknown';
      html += '<tr>' +
        '<td>' + escapeHtml(it.filename) + '</td>' +
        '<td>' + escapeHtml(it.pm || '—') + '</td>' +
        '<td><span class="pill ' + typeCls + '">' + escapeHtml(it.type) + '</span></td>' +
        '<td style="text-align:right">' + it.size_kb + ' KB</td>' +
        '<td>' + escapeHtml(it.modified) + '</td>' +
        '</tr>';
    }
    html += '</tbody></table>';
    $('inbox-wrap').innerHTML = html;
  }

  async function refreshInbox() {
    const r = await fetch('/api/inbox');
    const j = await r.json();
    renderInbox(j.inbox || []);
  }

  async function uploadFiles(files) {
    const fd = new FormData();
    for (const f of files) {
      if (f.name.toLowerCase().endsWith('.txt')) fd.append('files', f);
    }
    if (!fd.has('files')) return;
    const r = await fetch('/api/upload', { method: 'POST', body: fd });
    const j = await r.json();
    if (j.inbox) renderInbox(j.inbox);
  }

  $('file-input').addEventListener('change', e => {
    if (e.target.files && e.target.files.length) uploadFiles(e.target.files);
    e.target.value = '';
  });
  ['dragenter', 'dragover'].forEach(ev =>
    $('dropzone').addEventListener(ev, e => {
      e.preventDefault(); e.stopPropagation();
      $('dropzone').classList.add('drag');
    })
  );
  ['dragleave', 'drop'].forEach(ev =>
    $('dropzone').addEventListener(ev, e => {
      e.preventDefault(); e.stopPropagation();
      $('dropzone').classList.remove('drag');
    })
  );
  $('dropzone').addEventListener('drop', e => {
    if (e.dataTransfer && e.dataTransfer.files) uploadFiles(e.dataTransfer.files);
  });

  // ---------- Subprocess actions ----------
  let pollTimer = null;
  let lineCursor = 0;
  let userScrolledUp = false;

  const logEl = $('log');
  logEl.addEventListener('scroll', () => {
    const atBottom = (logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight) < 12;
    userScrolledUp = !atBottom;
  });

  function setRunHeader(action, status, kind) {
    $('run-action').textContent = action || 'idle';
    const pill = $('run-status');
    pill.textContent = status;
    const hdr = $('run-header');
    hdr.classList.remove('running', 'ok', 'err');
    if (kind) hdr.classList.add(kind);
  }

  function setBtnState(disabled) {
    ['btn-process', 'btn-scrape', 'btn-refresh'].forEach(id => $(id).disabled = disabled);
    if (!disabled) {
      // Re-enable process only if inbox has files
      refreshInbox();
    }
  }

  async function startAction(action) {
    setBtnState(true);
    setRunHeader(action, 'starting…', 'running');
    logEl.textContent = '';
    lineCursor = 0;
    userScrolledUp = false;
    const r = await fetch('/api/' + action, { method: 'POST' });
    const j = await r.json();
    if (j.error) {
      setRunHeader(action, 'error: ' + j.error, 'err');
      setBtnState(false);
      return;
    }
    setRunHeader(action, 'running', 'running');
    pollTimer = setInterval(pollStatus, 1000);
  }

  async function pollStatus() {
    const r = await fetch('/api/status?since=' + lineCursor);
    const j = await r.json();
    if (j.new_lines && j.new_lines.length) {
      logEl.textContent += j.new_lines.join('\\n') + '\\n';
      lineCursor = j.total_lines;
      if (!userScrolledUp) logEl.scrollTop = logEl.scrollHeight;
    }
    if (!j.running) {
      clearInterval(pollTimer); pollTimer = null;
      const ok = j.exit_code === 0;
      setRunHeader(j.action || 'idle', 'done · exit ' + j.exit_code, ok ? 'ok' : 'err');
      setBtnState(false);
      // Refresh side data
      renderBinderCards();
      renderStatusBar();
    }
  }

  document.querySelectorAll('.btn-action').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.action;
      if (action) startAction(action);
    });
  });

  // ---------- Sub performance summary ----------
  function renderSubPerf() {
    fetch('/api/subs').then(r => r.json()).then(d => {
      const t = d.totals || {};
      $('subperf-badge').textContent = `${t.total_subs || 0} subs · ${t.rollup_count || 0} (sub × phase) rollups`;
      const flagCls = (t.flagged_count || 0) > 0 ? 'alert' : '';
      $('subperf-totals').innerHTML =
        `<span><span class="key">total subs tracked</span><strong>${t.total_subs || 0}</strong></span>` +
        `<span><span class="key">flagged for binder</span><strong class="${flagCls}">${t.flagged_count || 0}</strong></span>` +
        `<span><span class="key">sub × phase rollups</span><strong>${t.rollup_count || 0}</strong></span>` +
        `<span><span class="key">subs with drift signal</span><strong>${t.with_drift || 0}</strong></span>`;
    }).catch(() => {
      $('subperf-badge').textContent = '—';
      $('subperf-totals').innerHTML = '<span style="color:var(--ink-muted);font-style:italic;">/api/subs unavailable</span>';
    });
  }

  // ---------- Initial load ----------
  renderStatusBar();
  renderBinderCards();
  refreshInbox();
  renderSubPerf();
})();
</script>
</body>
</html>
"""


# ----------------------------------------------------------------------
# Phase 10 — shared page CSS (sub/job pages)
# ----------------------------------------------------------------------
_PAGE_CSS = """
  body { padding: 0; }
  *, *::before, *::after { font-variant-numeric: tabular-nums; }
  .pg { max-width: 10in; margin: 0 auto; padding: 24px 36px 80px; font-family: var(--font-body); color: var(--ink); }
  .pg-band {
    border: 1.5px solid var(--ink);
    padding: 12px 22px;
    display: flex; align-items: flex-end; justify-content: space-between;
    margin-bottom: 22px;
    background: var(--bg-card);
  }
  .pg-band h1 {
    font-family: var(--font-head);
    font-size: 20px; font-weight: 700; letter-spacing: 0.5px;
    color: var(--ink); margin: 0;
  }
  .pg-band .sub {
    font-family: var(--font-mono); font-size: 11px;
    color: var(--ink-2); margin-top: 4px; letter-spacing: 0.3px;
  }
  .pg-band .right { text-align: right; font-family: var(--font-mono); font-size: 11px; color: var(--ink-2); }
  .pg-band .right a {
    color: var(--accent); text-decoration: none;
    font-size: 11px; letter-spacing: 0.5px;
    display: inline-block; padding: 3px 0;
  }
  .pg-band .right a:hover { color: var(--ink); text-decoration: underline; }

  .totals {
    background: var(--bg-soft);
    border-left: 3px solid var(--accent);
    padding: 10px 18px; margin-bottom: 24px;
    font-family: var(--font-mono); font-size: 12px; color: var(--ink);
    display: flex; gap: 28px; flex-wrap: wrap;
  }
  .totals span { display: flex; align-items: baseline; gap: 6px; }
  .totals .key { color: var(--ink-3); text-transform: uppercase; font-size: 9.5px; letter-spacing: 0.7px; }
  .totals strong { font-family: var(--font-head); font-size: 17px; font-weight: 700; color: var(--ink); }
  .totals strong.alert { color: var(--nw-danger); }

  .sec-label {
    font-family: var(--font-head);
    font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 2px;
    color: var(--ink); margin: 28px 0 10px;
    padding-bottom: 6px; border-bottom: 1px solid var(--accent);
    display: flex; justify-content: space-between; align-items: baseline;
  }
  .sec-label .badge {
    font-family: var(--font-mono);
    font-size: 10.5px; text-transform: none; letter-spacing: 0.4px;
    color: var(--ink-3); font-weight: 500;
  }

  table.t {
    width: 100%; border-collapse: collapse;
    font-family: var(--font-mono); font-size: 11.5px;
  }
  table.t th {
    text-align: left; padding: 7px 10px;
    border-bottom: 1.5px solid var(--ink);
    color: var(--ink-3); font-size: 9.5px;
    text-transform: uppercase; letter-spacing: 0.8px;
    font-weight: 600; cursor: pointer; user-select: none;
  }
  table.t th.num { text-align: right; }
  table.t th:hover { color: var(--ink); }
  table.t th.sort-asc::after { content: " ↑"; color: var(--accent); }
  table.t th.sort-desc::after { content: " ↓"; color: var(--accent); }
  table.t td {
    padding: 7px 10px;
    border-bottom: 1px dotted var(--line-2);
    color: var(--ink); vertical-align: top;
  }
  table.t td.num { text-align: right; font-variant-numeric: tabular-nums; }
  table.t tr.row-clickable { cursor: pointer; }
  table.t tr.row-clickable:hover td { background: var(--bg-soft); }
  table.t .name {
    font-family: var(--font-head);
    font-weight: 600; font-size: 12px;
    color: var(--ink); letter-spacing: 0.4px;
  }
  table.t .pm { color: var(--accent); }
  table.t a {
    color: var(--accent); text-decoration: none;
  }
  table.t a:hover { text-decoration: underline; color: var(--ink); }

  .density-tier { display: inline-block; padding: 1px 7px; border: 1px solid; font-size: 10px; letter-spacing: 0.4px; text-transform: uppercase; }
  .density-tier.dragging   { color: var(--nw-danger); border-color: var(--nw-danger); }
  .density-tier.scattered  { color: var(--warn);      border-color: var(--warn); }
  .density-tier.steady     { color: var(--ink-2);     border-color: var(--ink-2); }
  .density-tier.continuous { color: var(--accent);    border-color: var(--accent); }
  .density-tier.empty      { color: var(--ink-muted); border-color: var(--line); }

  .flag-badge {
    display: inline-block;
    padding: 1px 7px;
    font-family: var(--font-mono); font-size: 10.5px;
    border: 1px solid;
    font-weight: 600;
  }
  .flag-badge.zero { color: var(--accent); border-color: var(--accent); }
  .flag-badge.hot  { color: var(--bg); background: var(--nw-danger); border-color: var(--nw-danger); }

  .status-pill {
    display: inline-block;
    padding: 1px 8px;
    font-family: var(--font-mono); font-size: 10px;
    text-transform: uppercase; letter-spacing: 0.6px;
    border: 1px solid var(--accent);
    color: var(--accent);
  }
  .chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 4px; }
  .chip {
    display: inline-block;
    padding: 3px 10px;
    font-family: var(--font-mono); font-size: 11px;
    border: 1px solid var(--line);
    color: var(--ink);
    text-decoration: none;
    transition: background-color 0.12s ease;
  }
  .chip:hover { background: var(--ink); color: var(--bg); border-color: var(--ink); }
  .chip.flagged { border-color: var(--nw-danger); color: var(--nw-danger); }
  .chip.flagged:hover { background: var(--nw-danger); color: var(--bg); }

  .empty-line {
    color: var(--ink-muted); font-style: italic;
    font-family: var(--font-mono); font-size: 11px;
    padding: 6px 0;
  }
  .inferred-mark {
    color: var(--ink-3); font-size: 9.5px; letter-spacing: 0.4px;
    margin-left: 6px; text-transform: uppercase;
  }
"""


# ----------------------------------------------------------------------
# Phase 10 — /subs (sub roster)
# ----------------------------------------------------------------------
SUBS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sub Roster · Ross Built Monday Ops</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<link rel="stylesheet" href="/assets/nightwork-tokens.css">
<style>__PAGE_CSS__</style>
</head>
<body>
<div class="pg">

  <header class="pg-band">
    <div>
      <h1>SUB ROSTER</h1>
      <div class="sub">All subs ranked by aggregate flag score</div>
    </div>
    <div class="right">
      <a href="/">← back to Monday Ops</a>
      <div style="margin-top:4px">/subs</div>
    </div>
  </header>

  <div class="totals" id="totals"><span class="key">loading…</span></div>

  <h3 class="sec-label">Subs <span class="badge" id="row-count"></span></h3>
  <div id="table-wrap"></div>

</div>

<script>
(function () {
  const $ = id => document.getElementById(id);
  const escapeHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let rows = [];
  let sortField = 'flag_score';
  let sortDir = 'desc';

  fetch('/api/subs').then(r => r.json()).then(d => {
    rows = d.subs || [];
    const t = d.totals || {};
    $('totals').innerHTML =
      `<span><span class="key">total subs</span><strong>${t.total_subs || 0}</strong></span>` +
      `<span><span class="key">sub × phase rollups</span><strong>${t.rollup_count || 0}</strong></span>` +
      `<span><span class="key">flagged for binder</span><strong class="alert">${t.flagged_count || 0}</strong></span>` +
      `<span><span class="key">with drift signals</span><strong>${t.with_drift || 0}</strong></span>`;
    render();
  });

  function densityChips(dist) {
    const order = ['continuous','steady','scattered','dragging','empty','unknown'];
    const out = [];
    for (const tier of order) {
      const n = dist[tier] || 0;
      if (n) out.push(`<span class="density-tier ${tier}">${n} ${tier}</span>`);
    }
    return out.join(' ');
  }

  function render() {
    rows.sort((a, b) => {
      let av = a[sortField], bv = b[sortField];
      if (sortField === 'sub') { av = av.toLowerCase(); bv = bv.toLowerCase(); }
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === 'asc' ? cmp : -cmp;
    });
    $('row-count').textContent = `${rows.length} subs`;
    const headers = [
      ['sub','Sub'],
      ['job_count','Jobs', 'num'],
      ['rollup_count','Rollups', 'num'],
      ['active_phase_count','Active phases', 'num'],
      ['flag_score','Flag score', 'num'],
      ['flagged_count','Flagged rollups', 'num'],
      ['drift_count','Drift signals', 'num'],
      ['density_dist','Density mix'],
    ];
    const thHtml = headers.map(([k, label, cls]) => {
      const sortCls = (k === sortField) ? (sortDir === 'asc' ? 'sort-asc' : 'sort-desc') : '';
      return `<th class="${cls || ''} ${sortCls}" data-k="${k}">${label}</th>`;
    }).join('');
    const trHtml = rows.map(r => {
      const flagBadge = r.flag_score > 0
        ? `<span class="flag-badge hot">${r.flag_score}</span>`
        : `<span class="flag-badge zero">0</span>`;
      return `
        <tr class="row-clickable" data-slug="${escapeHtml(r.slug)}">
          <td><span class="name">${escapeHtml(r.sub)}</span></td>
          <td class="num">${r.job_count}</td>
          <td class="num">${r.rollup_count}</td>
          <td class="num">${r.active_phase_count}</td>
          <td class="num">${flagBadge}</td>
          <td class="num">${r.flagged_count}</td>
          <td class="num">${r.drift_count}</td>
          <td>${densityChips(r.density_dist || {})}</td>
        </tr>`;
    }).join('');
    $('table-wrap').innerHTML = `<table class="t"><thead><tr>${thHtml}</tr></thead><tbody>${trHtml}</tbody></table>`;
    $('table-wrap').querySelectorAll('th').forEach(th => {
      th.addEventListener('click', () => {
        const k = th.dataset.k;
        if (!k) return;
        if (k === sortField) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        else { sortField = k; sortDir = (k === 'sub') ? 'asc' : 'desc'; }
        render();
      });
    });
    $('table-wrap').querySelectorAll('tr.row-clickable').forEach(tr => {
      tr.addEventListener('click', () => { window.location.href = '/subs/' + tr.dataset.slug; });
    });
  }
})();
</script>
</body>
</html>
""".replace("__PAGE_CSS__", _PAGE_CSS)


# ----------------------------------------------------------------------
# Phase 10 — /subs/<slug> (sub detail)
# ----------------------------------------------------------------------
SUB_DETAIL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Sub Detail · Ross Built Monday Ops</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<link rel="stylesheet" href="/assets/nightwork-tokens.css">
<style>__PAGE_CSS__</style>
</head>
<body>
<div class="pg">

  <header class="pg-band">
    <div>
      <h1 id="sub-name">…</h1>
      <div class="sub" id="sub-meta"></div>
    </div>
    <div class="right">
      <a href="/subs">← back to roster</a>
      <div style="margin-top:4px"><a href="/">Monday Ops</a></div>
    </div>
  </header>

  <div class="totals" id="totals"></div>

  <h3 class="sec-label">Jobs worked <span class="badge" id="jobs-badge"></span></h3>
  <div class="chip-row" id="jobs"></div>

  <h3 class="sec-label">Drift insights <span class="badge" id="drifts-badge"></span></h3>
  <div id="drifts"></div>

  <h3 class="sec-label">Phase rollups <span class="badge" id="rollups-badge"></span></h3>
  <div id="rollups"></div>

  <h3 class="sec-label">Phase instances <span class="badge" id="instances-badge"></span></h3>
  <div id="instances"></div>

  <h3 class="sec-label">Action items mentioning this sub <span class="badge">heuristic — not source-of-truth</span></h3>
  <div id="items"></div>

</div>

<script>
(function () {
  const $ = id => document.getElementById(id);
  const escapeHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const slug = window.location.pathname.split('/').filter(Boolean)[1] || '';
  const fmtPct = d => (d == null ? '—' : Math.round(d * 100) + '%');

  fetch('/api/subs/' + encodeURIComponent(slug)).then(r => {
    if (!r.ok) throw new Error('sub not found');
    return r.json();
  }).then(d => render(d)).catch(e => {
    $('sub-name').textContent = 'Sub not found';
    $('sub-meta').textContent = String(e);
  });

  function render(d) {
    document.title = 'Sub · ' + d.sub;
    $('sub-name').textContent = d.sub.toUpperCase();
    $('sub-meta').innerHTML = `<span class="status-pill">${escapeHtml(d.status)}</span>`;
    const t = d.totals;
    $('totals').innerHTML =
      `<span><span class="key">jobs</span><strong>${t.job_count}</strong></span>` +
      `<span><span class="key">rollups</span><strong>${t.rollup_count}</strong></span>` +
      `<span><span class="key">flagged rollups</span><strong class="${t.flagged_count > 0 ? 'alert' : ''}">${t.flagged_count}</strong></span>` +
      `<span><span class="key">flag score</span><strong class="${t.flag_score_total > 0 ? 'alert' : ''}">${t.flag_score_total}</strong></span>` +
      `<span><span class="key">drift signals</span><strong>${t.drift_count}</strong></span>` +
      `<span><span class="key">action items</span><strong>${t.item_count}</strong></span>`;

    /* Jobs */
    $('jobs-badge').textContent = `${d.jobs.length} jobs`;
    if (!d.jobs.length) {
      $('jobs').innerHTML = '<div class="empty-line">no jobs</div>';
    } else {
      $('jobs').innerHTML = d.jobs.map(j =>
        `<a class="chip" href="/jobs/${escapeHtml(j.slug)}">${escapeHtml(j.name)}</a>`
      ).join('');
    }

    /* Drift insights */
    $('drifts-badge').textContent = `${d.drifts.length} signal${d.drifts.length === 1 ? '' : 's'}`;
    if (!d.drifts.length) {
      $('drifts').innerHTML = '<div class="empty-line">no drift signals firing</div>';
    } else {
      const tr = d.drifts.map(s => {
        const phaseDisp = s.phase_name
          ? `${escapeHtml(s.phase_name)} <span style="color:var(--ink-3);font-size:10.5px;">(${escapeHtml(s.phase || '')})</span>`
          : escapeHtml(s.phase || '');
        return `<tr>
          <td><a href="/jobs/${escapeHtml(s.job_slug)}">${escapeHtml(s.job)}</a></td>
          <td>${phaseDisp}</td>
          <td>${escapeHtml(s.summary || '')}</td>
          <td><em>${escapeHtml(s.ask || '')}</em></td>
        </tr>`;
      }).join('');
      $('drifts').innerHTML = `<table class="t">
        <thead><tr><th>Job</th><th>Phase</th><th>Summary</th><th>Ask</th></tr></thead>
        <tbody>${tr}</tbody></table>`;
    }

    /* Rollups */
    $('rollups-badge').textContent = `${d.rollups.length} (sub × phase)`;
    if (!d.rollups.length) {
      $('rollups').innerHTML = '<div class="empty-line">no rollups</div>';
    } else {
      const tr = d.rollups.map(r => {
        const tier = r.primary_density_label || 'empty';
        const flag = r.flag_for_pm_binder
          ? `<span class="flag-badge hot">${r.flag_score}</span>`
          : `<span class="flag-badge zero">0</span>`;
        return `<tr>
          <td>${escapeHtml(r.phase_code)} <span style="color:var(--ink-2)">${escapeHtml(r.phase_name)}</span></td>
          <td class="num">${r.jobs_performed}</td>
          <td><span class="density-tier ${tier}">${escapeHtml(tier)}</span> ${fmtPct(r.primary_density)}</td>
          <td class="num">${r.primary_active_days_median} d</td>
          <td class="num">${fmtPct(r.return_burst_rate)}</td>
          <td class="num">${fmtPct(r.punch_burst_rate)}</td>
          <td class="num">${flag}</td>
          <td>${(r.flag_reasons || []).map(escapeHtml).join(', ')}</td>
        </tr>`;
      }).join('');
      $('rollups').innerHTML = `<table class="t">
        <thead><tr>
          <th>Phase</th>
          <th class="num">Jobs</th>
          <th>Density</th>
          <th class="num">Median active</th>
          <th class="num">Return rate</th>
          <th class="num">Punch rate</th>
          <th class="num">Flag</th>
          <th>Flag reasons</th>
        </tr></thead>
        <tbody>${tr}</tbody></table>`;
    }

    /* Instances */
    $('instances-badge').textContent = `${d.instances.length} (job × phase)`;
    if (!d.instances.length) {
      $('instances').innerHTML = '<div class="empty-line">no instance-level activity</div>';
    } else {
      const tr = d.instances.map(i => {
        const tier = i.sub_density_tier || 'empty';
        return `<tr>
          <td><a href="/jobs/${escapeHtml(i.job_slug)}">${escapeHtml(i.job)}</a></td>
          <td>${escapeHtml(i.phase_code)} <span style="color:var(--ink-2)">${escapeHtml(i.phase_name)}</span></td>
          <td>${escapeHtml(i.status)}</td>
          <td><span class="density-tier ${tier}">${escapeHtml(tier)}</span> ${fmtPct(i.sub_density)}</td>
          <td class="num">${i.sub_active_days || 0} d</td>
          <td>${escapeHtml(i.first_log_date || '—')}</td>
          <td>${escapeHtml(i.last_log_date || '—')}</td>
        </tr>`;
      }).join('');
      $('instances').innerHTML = `<table class="t">
        <thead><tr>
          <th>Job</th><th>Phase</th><th>Status</th><th>Density</th>
          <th class="num">Active days</th><th>First log</th><th>Last log</th>
        </tr></thead>
        <tbody>${tr}</tbody></table>`;
    }

    /* Items */
    if (!d.items.length) {
      $('items').innerHTML = '<div class="empty-line">no action items mention this sub</div>';
    } else {
      const tr = d.items.map(it => {
        const conf = it.related_sub_confidence;
        const confMark = it.related_sub_inferred
          ? `<span class="inferred-mark" title="heuristic match · confidence ${conf || '?'}">inferred${conf ? ' ' + conf : ''}</span>`
          : '';
        return `<tr>
          <td>${escapeHtml(it.id || '')}</td>
          <td>${escapeHtml(it.job || '')}</td>
          <td>${escapeHtml(it._pm || '')}</td>
          <td>${escapeHtml((it.action || '').slice(0, 110))}${confMark}</td>
          <td>${escapeHtml(it.status || '')}</td>
          <td class="num">${it.days_open != null ? it.days_open + 'd' : '—'}</td>
        </tr>`;
      }).join('');
      $('items').innerHTML = `<table class="t">
        <thead><tr>
          <th>ID</th><th>Job</th><th>PM</th><th>Action</th><th>Status</th><th class="num">Age</th>
        </tr></thead>
        <tbody>${tr}</tbody></table>`;
    }
  }
})();
</script>
</body>
</html>
""".replace("__PAGE_CSS__", _PAGE_CSS)


# ----------------------------------------------------------------------
# Phase 10 — /jobs (job roster)
# ----------------------------------------------------------------------
JOBS_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Jobs · Ross Built Monday Ops</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<link rel="stylesheet" href="/assets/nightwork-tokens.css">
<style>__PAGE_CSS__</style>
</head>
<body>
<div class="pg">

  <header class="pg-band">
    <div>
      <h1>JOBS · BREAKDOWN</h1>
      <div class="sub">All active jobs · sub-focused</div>
    </div>
    <div class="right">
      <a href="/">← back to Monday Ops</a>
      <div style="margin-top:4px">/jobs</div>
    </div>
  </header>

  <div class="totals" id="totals"><span class="key">loading…</span></div>

  <h3 class="sec-label">Active jobs <span class="badge" id="row-count"></span></h3>
  <div id="table-wrap"></div>

</div>

<script>
(function () {
  const $ = id => document.getElementById(id);
  const escapeHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let rows = [];
  let sortField = 'flagged_sub_count';
  let sortDir = 'desc';

  fetch('/api/jobs').then(r => r.json()).then(d => {
    rows = d.jobs || [];
    const t = d.totals || {};
    $('totals').innerHTML =
      `<span><span class="key">total jobs</span><strong>${t.total_jobs || 0}</strong></span>` +
      `<span><span class="key">with flagged subs</span><strong class="${t.with_flagged_subs ? 'alert' : ''}">${t.with_flagged_subs || 0}</strong></span>`;
    render();
  });

  function render() {
    rows.sort((a, b) => {
      let av = a[sortField], bv = b[sortField];
      if (typeof av === 'string') { av = av.toLowerCase(); bv = (bv || '').toLowerCase(); }
      if (av == null) av = '';
      if (bv == null) bv = '';
      if (av === bv) return 0;
      const cmp = av < bv ? -1 : 1;
      return sortDir === 'asc' ? cmp : -cmp;
    });
    $('row-count').textContent = `${rows.length} jobs`;
    const headers = [
      ['job','Job'],
      ['pm','PM'],
      ['current_stage_name','Stage'],
      ['ongoing_count','Ongoing', 'num'],
      ['complete_count','Complete', 'num'],
      ['sub_count','Subs', 'num'],
      ['flagged_sub_count','Flagged subs', 'num'],
      ['co_target','Target CO'],
    ];
    const thHtml = headers.map(([k, label, cls]) => {
      const sortCls = (k === sortField) ? (sortDir === 'asc' ? 'sort-asc' : 'sort-desc') : '';
      return `<th class="${cls || ''} ${sortCls}" data-k="${k}">${label}</th>`;
    }).join('');
    const trHtml = rows.map(j => {
      const flagBadge = j.flagged_sub_count > 0
        ? `<span class="flag-badge hot">${j.flagged_sub_count}</span>`
        : `<span class="flag-badge zero">0</span>`;
      return `
        <tr class="row-clickable" data-slug="${escapeHtml(j.slug)}">
          <td><span class="name">${escapeHtml(j.job)}</span></td>
          <td><span class="pm">${escapeHtml(j.pm)}</span></td>
          <td>${escapeHtml(j.current_stage_name || '—')}</td>
          <td class="num">${j.ongoing_count}</td>
          <td class="num">${j.complete_count}</td>
          <td class="num">${j.sub_count}</td>
          <td class="num">${flagBadge}</td>
          <td>${escapeHtml(j.co_target)}</td>
        </tr>`;
    }).join('');
    $('table-wrap').innerHTML = `<table class="t"><thead><tr>${thHtml}</tr></thead><tbody>${trHtml}</tbody></table>`;
    $('table-wrap').querySelectorAll('th').forEach(th => {
      th.addEventListener('click', () => {
        const k = th.dataset.k;
        if (!k) return;
        if (k === sortField) sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        else { sortField = k; sortDir = (k === 'job' || k === 'pm') ? 'asc' : 'desc'; }
        render();
      });
    });
    $('table-wrap').querySelectorAll('tr.row-clickable').forEach(tr => {
      tr.addEventListener('click', () => { window.location.href = '/jobs/' + tr.dataset.slug; });
    });
  }
})();
</script>
</body>
</html>
""".replace("__PAGE_CSS__", _PAGE_CSS)


# ----------------------------------------------------------------------
# Phase 10 — /jobs/<slug> (job detail)
# ----------------------------------------------------------------------
JOB_DETAIL_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Job Detail · Ross Built Monday Ops</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Space+Grotesk:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/assets/styles.css">
<link rel="stylesheet" href="/assets/nightwork-tokens.css">
<style>__PAGE_CSS__</style>
</head>
<body>
<div class="pg">

  <header class="pg-band">
    <div>
      <h1 id="job-name">…</h1>
      <div class="sub" id="job-meta"></div>
    </div>
    <div class="right">
      <a href="/jobs">← back to roster</a>
      <div style="margin-top:4px"><a href="/">Monday Ops</a></div>
    </div>
  </header>

  <div class="totals" id="totals"></div>

  <h3 class="sec-label">Subs working this job <span class="badge" id="subs-badge"></span></h3>
  <div id="subs"></div>

  <h3 class="sec-label">Phase activity <span class="badge" id="phases-badge"></span></h3>
  <div class="sub" style="font-family:var(--font-mono);font-size:10.5px;color:var(--ink-3);margin-bottom:6px;">
    Read-only timeline of what's been worked. Not a forward schedule (Phase 11).
  </div>
  <div id="phases"></div>

  <h3 class="sec-label">Action items <span class="badge" id="items-badge"></span></h3>
  <div id="items"></div>

</div>

<script>
(function () {
  const $ = id => document.getElementById(id);
  const escapeHtml = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const slug = window.location.pathname.split('/').filter(Boolean)[1] || '';
  const fmtPct = d => (d == null ? '—' : Math.round(d * 100) + '%');

  fetch('/api/jobs/' + encodeURIComponent(slug)).then(r => {
    if (!r.ok) throw new Error('job not found');
    return r.json();
  }).then(d => render(d)).catch(e => {
    $('job-name').textContent = 'Job not found';
    $('job-meta').textContent = String(e);
  });

  function render(d) {
    document.title = 'Job · ' + d.job;
    $('job-name').textContent = d.job.toUpperCase();
    $('job-meta').innerHTML = [
      `<strong style="color:var(--accent)">${escapeHtml(d.pm || '—')}</strong>`,
      `stage ${escapeHtml(d.current_stage || '—')} ${escapeHtml(d.current_stage_name || '')}`,
      `target CO: ${escapeHtml(d.target_co)}`,
      escapeHtml(d.address || ''),
    ].filter(Boolean).join(' · ');
    const t = d.totals;
    $('totals').innerHTML =
      `<span><span class="key">subs working</span><strong>${t.sub_count}</strong></span>` +
      `<span><span class="key">flagged subs</span><strong class="${t.flagged_sub_count > 0 ? 'alert' : ''}">${t.flagged_sub_count}</strong></span>` +
      `<span><span class="key">phase instances</span><strong>${t.instance_count}</strong></span>` +
      `<span><span class="key">action items</span><strong>${t.item_count}</strong></span>` +
      `<span><span class="key">job phase string</span><span style="color:var(--ink)">${escapeHtml(d.phase_string || '—')}</span></span>`;

    /* Subs */
    $('subs-badge').textContent = `${d.subs.length} subs`;
    if (!d.subs.length) {
      $('subs').innerHTML = '<div class="empty-line">no subs logged on this job</div>';
    } else {
      const tr = d.subs.map(s => {
        const flagPill = s.is_flagged
          ? `<span class="flag-badge hot">${s.flagged_phases.length}</span>`
          : `<span class="flag-badge zero">0</span>`;
        const phaseList = s.phases.map(p => {
          const tier = p.density_tier || 'empty';
          return `<div style="font-size:10.5px;color:var(--ink-2)">${escapeHtml(p.phase_code)} <span style="color:var(--ink)">${escapeHtml(p.phase_name)}</span> · <span class="density-tier ${tier}">${escapeHtml(tier)}</span> ${fmtPct(p.density)} · ${p.active_days || 0}d</div>`;
        }).join('');
        return `<tr>
          <td><a href="/subs/${escapeHtml(s.slug)}"><span class="name">${escapeHtml(s.sub)}</span></a></td>
          <td class="num">${s.phase_count}</td>
          <td class="num">${s.total_active_days}d</td>
          <td class="num">${flagPill}</td>
          <td>${phaseList}</td>
        </tr>`;
      }).join('');
      $('subs').innerHTML = `<table class="t">
        <thead><tr>
          <th>Sub</th><th class="num">Phases</th><th class="num">Active days</th><th class="num">Flagged</th><th>Phases worked</th>
        </tr></thead>
        <tbody>${tr}</tbody></table>`;
    }

    /* Phase activity */
    $('phases-badge').textContent = `${d.instances.length} phase instances`;
    if (!d.instances.length) {
      $('phases').innerHTML = '<div class="empty-line">no phase activity recorded</div>';
    } else {
      const tr = d.instances.map(p => {
        const tier = p.primary_density_tier || 'empty';
        return `<tr>
          <td>${escapeHtml(p.phase_code)} <span style="color:var(--ink-2)">${escapeHtml(p.phase_name)}</span></td>
          <td>${escapeHtml(p.stage_name || '')}</td>
          <td>${escapeHtml(p.status)}</td>
          <td><span class="density-tier ${tier}">${escapeHtml(tier)}</span> ${fmtPct(p.primary_density)}</td>
          <td class="num">${p.primary_active_days || 0}d</td>
          <td>${escapeHtml(p.first_log_date || '—')}</td>
          <td>${escapeHtml(p.last_log_date || '—')}</td>
        </tr>`;
      }).join('');
      $('phases').innerHTML = `<table class="t">
        <thead><tr>
          <th>Phase</th><th>Stage</th><th>Status</th><th>Density</th>
          <th class="num">Active days</th><th>First log</th><th>Last log</th>
        </tr></thead>
        <tbody>${tr}</tbody></table>`;
    }

    /* Items */
    $('items-badge').textContent = `${d.items.length} items`;
    if (!d.items.length) {
      $('items').innerHTML = '<div class="empty-line">no action items</div>';
    } else {
      const tr = d.items.map(it =>
        `<tr>
          <td>${escapeHtml(it.id || '')}</td>
          <td>${escapeHtml((it.action || '').slice(0, 110))}</td>
          <td>${escapeHtml(it.owner || '')}</td>
          <td>${escapeHtml(it.status || '')}</td>
          <td>${escapeHtml(it.priority || '')}</td>
          <td class="num">${it.days_open != null ? it.days_open + 'd' : '—'}</td>
        </tr>`).join('');
      $('items').innerHTML = `<table class="t">
        <thead><tr>
          <th>ID</th><th>Action</th><th>Owner</th><th>Status</th><th>Priority</th><th class="num">Age</th>
        </tr></thead>
        <tbody>${tr}</tbody></table>`;
    }
  }
})();
</script>
</body>
</html>
""".replace("__PAGE_CSS__", _PAGE_CSS)


def main() -> None:
    print(f"Ross Built Monday Ops dashboard starting on http://localhost:{PORT}")
    print(f"  Project root  : {PROJECT_ROOT}")
    print(f"  Inbox dir     : {INBOX}")
    print(f"  process.py    : {PROCESS_PY}{'' if PROCESS_PY.exists() else '  (NOT FOUND)'}")
    print(f"  scraper       : {SCRAPER_JS}{'' if SCRAPER_JS.exists() else '  (NOT FOUND)'}")
    print(f"  build_pages   : {BUILD_PAGES_PY}{'' if BUILD_PAGES_PY.exists() else '  (NOT FOUND)'}")
    print(f"  build_meeting : {BUILD_MEETING_PREP_PY}{'' if BUILD_MEETING_PREP_PY.exists() else '  (NOT FOUND)'}")
    app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
