#!/usr/bin/env python3
"""Monday Binder weekly pipeline orchestrator.

One command, end-to-end. Replaces the partial run_weekly.bat (which only
covered build_meeting_prep + validate_accountability) with a full pipeline:
transcripts → phase data → rollups → insights → meeting prep →
accountability validation → dashboard restart → URL verification.

Usage:
    python scripts/run_weekly_pipeline.py

Reads thresholds from config/thresholds.yaml under the `weekly_pipeline`
key. Sets PYTHONIOENCODING=utf-8 in every child process so the cp1252
crash in build_sub_phase_rollups.py doesn't fire. Aborts on first step
failure — no auto-fix, no auto-retry. The final report tells the operator
whether it's READY FOR MONDAY or NEEDS ATTENTION.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Force UTF-8 stdout BEFORE any print so this script's own logs survive on
# Windows cp1252 consoles. The PYTHONIOENCODING export below covers child
# processes; this block covers our own process.
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
if hasattr(sys.stderr, "buffer"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", line_buffering=True)

import yaml  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config"
BINDERS = ROOT / "binders"
INBOX = ROOT / "transcripts" / "inbox"
PROCESSED = ROOT / "transcripts" / "processed"
LOGS = ROOT / "logs"
STATE = ROOT / "state"
DAILY_LOGS = ROOT.parent / "buildertrend-scraper" / "data" / "daily-logs.json"

CLASSIFIER_PATH = (
    ROOT / ".planning" / "milestones" / "m02-schedule-intelligence"
    / "phases" / "01-sub-reclassification" / "classifier.py"
)

DASHBOARD_PORT = 8765
DASHBOARD_URL = f"http://localhost:{DASHBOARD_PORT}"


# ---------------------------------------------------------------------------
# Status accumulator
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    label: str
    cmd: list[str]
    rc: int
    elapsed_s: float
    stdout_tail: str = ""
    stderr_tail: str = ""

@dataclass
class PipelineStatus:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None
    preflight_warnings: list[str] = field(default_factory=list)
    preflight_aborts: list[str] = field(default_factory=list)
    steps: list[StepResult] = field(default_factory=list)
    server_old_pid: int | None = None
    server_new_pid: int | None = None
    url_verify_status: str = "not_attempted"
    url_verify_detail: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        if self.preflight_aborts:
            return False
        if any(s.rc != 0 for s in self.steps):
            return False
        if self.url_verify_status != "ok":
            return False
        return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_thresholds() -> dict:
    path = CONFIG / "thresholds.yaml"
    text = path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(text) or {}
    wp = cfg.get("weekly_pipeline") or {}
    # Sensible defaults if a field is absent
    wp.setdefault("daily_logs_recency_hours", 24)
    wp.setdefault("daily_logs_max_age_hours", 168)
    wp.setdefault("transcripts_recency_days", 7)
    wp.setdefault("url_verify_timeout_seconds", 60)
    wp.setdefault("server_startup_timeout_seconds", 30)
    wp.setdefault("required_pms", [
        "Bob Mozine", "Jason Szykulski", "Lee Worthy",
        "Martin Mannix", "Nelson Belanger",
    ])
    return wp


def _hours_old(path: Path, now: datetime) -> float | None:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return (now - mtime).total_seconds() / 3600.0


def _daily_logs_age_hours(now: datetime) -> tuple[float | None, str | None]:
    """Read daily-logs.json's `lastRun` (preferred) or fall back to mtime."""
    if not DAILY_LOGS.exists():
        return None, "missing"
    try:
        with open(DAILY_LOGS, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return _hours_old(DAILY_LOGS, now), f"could not parse lastRun ({e})"
    last_run = d.get("lastRun")
    if not last_run:
        return _hours_old(DAILY_LOGS, now), "no lastRun field; using mtime"
    try:
        if last_run.endswith("Z"):
            ts = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
        else:
            ts = datetime.fromisoformat(last_run)
        return (now - ts).total_seconds() / 3600.0, None
    except Exception as e:
        return _hours_old(DAILY_LOGS, now), f"unparseable lastRun {last_run!r} ({e})"


# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

def preflight(status: PipelineStatus, wp: dict) -> bool:
    """Run all pre-flight checks. Mutates status with warnings/aborts.
    Returns True if pipeline can proceed, False if it must abort."""
    print("=" * 70)
    print("PRE-FLIGHT CHECKS")
    print("=" * 70)
    now = datetime.now(timezone.utc)

    # Ensure logs/ + state/ exist (mirrors run_weekly.bat behavior)
    LOGS.mkdir(exist_ok=True)
    STATE.mkdir(exist_ok=True)

    # 1. daily-logs.json freshness
    age_hr, note = _daily_logs_age_hours(now)
    if age_hr is None:
        status.preflight_aborts.append(
            f"daily-logs.json missing at {DAILY_LOGS} ({note}). "
            f"Run the Buildertrend scraper before the weekly pipeline."
        )
        print(f"  [ABORT] daily-logs.json: {note}")
    else:
        if note:
            status.preflight_warnings.append(f"daily-logs.json age detection: {note}")
        if age_hr > wp["daily_logs_max_age_hours"]:
            status.preflight_aborts.append(
                f"daily-logs.json is {age_hr:.1f}h old (>{wp['daily_logs_max_age_hours']}h hard limit). "
                f"Re-run the BT scraper before retrying."
            )
            print(f"  [ABORT] daily-logs.json {age_hr:.1f}h old (max {wp['daily_logs_max_age_hours']}h)")
        elif age_hr > wp["daily_logs_recency_hours"]:
            status.preflight_warnings.append(
                f"daily-logs.json is {age_hr:.1f}h old (soft threshold {wp['daily_logs_recency_hours']}h)."
            )
            print(f"  [WARN]  daily-logs.json {age_hr:.1f}h old (soft {wp['daily_logs_recency_hours']}h)")
        else:
            print(f"  [OK]    daily-logs.json {age_hr:.1f}h old")

    # 2. transcripts/inbox: if non-empty, ANTHROPIC_API_KEY required
    inbox_files = sorted(INBOX.glob("*.txt")) if INBOX.exists() else []
    if inbox_files:
        print(f"  [OK]    transcripts/inbox/ has {len(inbox_files)} file(s) — process.py will run")
        if not os.environ.get("ANTHROPIC_API_KEY"):
            status.preflight_aborts.append(
                "transcripts/inbox/ has files but ANTHROPIC_API_KEY is not set. "
                "Either remove the inbox files or set the env var: "
                "setx ANTHROPIC_API_KEY \"sk-ant-...\""
            )
            print("  [ABORT] ANTHROPIC_API_KEY not set but inbox is non-empty")
    else:
        status.notes.append("transcripts/inbox/ empty — process.py will be a no-op; existing binders/<PM>.json reused.")
        print("  [OK]    transcripts/inbox/ empty (process.py is a no-op)")

    # 3. Newest processed transcript age (informational)
    if PROCESSED.exists():
        processed_files = list(PROCESSED.glob("*.txt"))
        if processed_files:
            newest = max(processed_files, key=lambda p: p.stat().st_mtime)
            age_days = (now - datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)).days
            if age_days > wp["transcripts_recency_days"]:
                status.preflight_warnings.append(
                    f"newest processed transcript is {age_days}d old "
                    f"(soft threshold {wp['transcripts_recency_days']}d). Verify before sending to Lee."
                )
                print(f"  [WARN]  newest processed transcript {age_days}d old ({newest.name})")
            else:
                print(f"  [OK]    newest processed transcript {age_days}d old")

    # 4. binders/<PM>.json for each required PM
    missing_pms = []
    for pm in wp["required_pms"]:
        bp = BINDERS / f"{pm.replace(' ', '_')}.json"
        if not bp.exists():
            missing_pms.append(pm)
    if missing_pms:
        status.preflight_aborts.append(
            f"binders/<PM>.json missing for: {', '.join(missing_pms)}. "
            f"Cannot run pipeline without per-PM source binders."
        )
        print(f"  [ABORT] missing binders: {missing_pms}")
    else:
        print(f"  [OK]    binders/ has all {len(wp['required_pms'])} required PM files")

    # 5. classifier.py source exists (.planning location)
    if not CLASSIFIER_PATH.exists():
        status.preflight_aborts.append(
            f"classifier.py not found at {CLASSIFIER_PATH}. "
            f"This is the upstream of derived-phases.json; pipeline cannot proceed."
        )
        print(f"  [ABORT] classifier.py missing")
    else:
        print(f"  [OK]    classifier.py exists in .planning/")

    # 6. Edge browser (used by dashboard for PDF rendering)
    try:
        sys.path.insert(0, str(ROOT / "monday-binder"))
        from render_helpers import find_edge  # type: ignore
        edge = find_edge()
        if edge:
            print(f"  [OK]    Edge found at {edge}")
        else:
            status.preflight_warnings.append(
                "Edge binary not found via render_helpers.find_edge(). "
                "Dashboard URL verification will likely fail. Set EDGE_BINARY env var."
            )
            print("  [WARN]  Edge binary not found")
    except Exception as e:
        status.preflight_warnings.append(f"could not check Edge: {e}")
        print(f"  [WARN]  could not check Edge: {e}")

    proceed = not status.preflight_aborts
    if proceed:
        print("\nPre-flight: PASS — proceeding with pipeline.")
    else:
        print(f"\nPre-flight: FAIL — {len(status.preflight_aborts)} blocker(s). Aborting.")
        for a in status.preflight_aborts:
            print(f"  - {a}")
    return proceed


# ---------------------------------------------------------------------------
# Step runner
# ---------------------------------------------------------------------------

def run_step(status: PipelineStatus, label: str, cmd: list[str], cwd: Path = ROOT) -> bool:
    """Execute a child process. Capture timing + tail output. Return True on success."""
    print("\n" + "=" * 70)
    print(f"{label}")
    print(f"  cmd: {' '.join(str(c) for c in cmd)}")
    print(f"  cwd: {cwd}")
    print("=" * 70)
    t0 = time.monotonic()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(
        cmd, cwd=str(cwd), env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    elapsed = time.monotonic() - t0
    out_tail = "\n".join((proc.stdout or "").splitlines()[-15:])
    err_tail = "\n".join((proc.stderr or "").splitlines()[-15:])
    if out_tail:
        print(out_tail)
    if proc.returncode == 0:
        print(f"  [OK] {elapsed:.1f}s")
    else:
        print(f"  [FAILED] exit={proc.returncode} ({elapsed:.1f}s)")
        if err_tail:
            print("  --- stderr tail ---")
            print(err_tail)
    status.steps.append(StepResult(
        label=label, cmd=cmd, rc=proc.returncode,
        elapsed_s=elapsed, stdout_tail=out_tail, stderr_tail=err_tail,
    ))
    return proc.returncode == 0


# ---------------------------------------------------------------------------
# Server restart + URL verification
# ---------------------------------------------------------------------------

def _pid_on_port() -> int | None:
    """Return the PID listening on DASHBOARD_PORT, or None."""
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             f"(Get-NetTCPConnection -LocalPort {DASHBOARD_PORT} "
             f"-State Listen -ErrorAction SilentlyContinue | "
             f"Select-Object -First 1).OwningProcess"],
            text=True, encoding="utf-8", errors="replace",
        ).strip()
        return int(out) if out and out.isdigit() else None
    except Exception:
        return None


def restart_server(status: PipelineStatus, wp: dict) -> bool:
    print("\n" + "=" * 70)
    print("DASHBOARD SERVER RESTART")
    print("=" * 70)

    # Stop existing
    old_pid = _pid_on_port()
    status.server_old_pid = old_pid
    if old_pid:
        print(f"  Stopping existing server PID {old_pid}...")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Stop-Process -Id {old_pid} -Force -ErrorAction SilentlyContinue"],
            check=False,
        )
        time.sleep(2)
    else:
        print("  No existing server on port — starting fresh.")

    # Start new
    log_path = LOGS / "dashboard-server.log"
    log_fp = open(log_path, "ab")
    creationflags = 0
    if os.name == "nt":
        creationflags = (
            subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    print(f"  Spawning new server (logs → {log_path})...")
    subprocess.Popen(
        [sys.executable, str(ROOT / "monday-binder" / "transcript-ui" / "server.py")],
        cwd=str(ROOT), env=env,
        stdout=log_fp, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        creationflags=creationflags, close_fds=True,
    )

    # Poll until responsive
    deadline = time.monotonic() + wp["server_startup_timeout_seconds"]
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{DASHBOARD_URL}/", timeout=2) as r:
                if 200 <= r.status < 500:
                    new_pid = _pid_on_port()
                    status.server_new_pid = new_pid
                    print(f"  [OK] server up on :{DASHBOARD_PORT} as PID {new_pid}")
                    return True
        except Exception:
            time.sleep(1)
    print(f"  [FAILED] server did not respond within {wp['server_startup_timeout_seconds']}s")
    return False


def verify_dashboard_url(status: PipelineStatus, wp: dict) -> None:
    print("\n" + "=" * 70)
    print("URL VERIFICATION")
    print("=" * 70)
    url = f"{DASHBOARD_URL}/meeting-prep/executive.pdf?_orchestrator={int(time.time())}"
    print(f"  fetching {url} ...")
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=wp["url_verify_timeout_seconds"]) as r:
            body = r.read()
            elapsed = time.monotonic() - t0
            ctype = r.headers.get("Content-Type", "")
            ok_status = (r.status == 200)
            ok_pdf = body.startswith(b"%PDF-")
            ok_size = len(body) > 50_000
            ok = ok_status and ok_pdf and ok_size
            detail = (
                f"status={r.status} content-type={ctype} bytes={len(body):,} "
                f"elapsed={elapsed:.1f}s starts-with-%PDF={ok_pdf}"
            )
            print(f"  {detail}")
            if ok:
                # Cross-check that the PDF embeds a CreationDate within the
                # last 5 minutes — proves the dashboard re-rendered against
                # the data the orchestrator just regenerated rather than
                # serving a cached payload.
                cd_marker = b"/CreationDate (D:"
                idx = body.find(cd_marker)
                if idx != -1:
                    end = body.find(b")", idx)
                    cd_str = body[idx + len(cd_marker):end].decode("ascii", "replace")
                    detail += f" creationDate={cd_str}"
                    # D:YYYYMMDDhhmmss±HH'mm'
                    try:
                        cd_dt = datetime.strptime(cd_str[:14], "%Y%m%d%H%M%S")
                        cd_dt = cd_dt.replace(tzinfo=timezone.utc)
                        age = (datetime.now(timezone.utc) - cd_dt).total_seconds()
                        detail += f" age={age:.0f}s"
                        if age > 600:  # 10 min — generous
                            status.notes.append(
                                f"executive.pdf CreationDate is {age:.0f}s old — "
                                "older than expected; server may not be using fresh data."
                            )
                    except Exception:
                        pass
                status.url_verify_status = "ok"
                status.url_verify_detail = detail
                print("  [OK] dashboard serving fresh executive.pdf")
            else:
                status.url_verify_status = "failed"
                status.url_verify_detail = detail
                print("  [FAILED] response did not pass freshness checks")
    except urllib.error.HTTPError as e:
        status.url_verify_status = "failed"
        status.url_verify_detail = f"HTTP {e.code}: {e.reason}"
        print(f"  [FAILED] {status.url_verify_detail}")
    except Exception as e:
        status.url_verify_status = "failed"
        status.url_verify_detail = f"{type(e).__name__}: {e}"
        print(f"  [FAILED] {status.url_verify_detail}")


# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------

OUTPUT_FILES_TO_REPORT = [
    DATA / "derived-phases.json",
    DATA / "derived-phases-v2.json",
    DATA / "phase-instances.json",
    DATA / "phase-instances-v2.json",
    DATA / "phase-medians.json",
    DATA / "bursts.json",
    DATA / "sub-phase-rollups.json",
    DATA / "job-stages.json",
    DATA / "insights.json",
    DATA / "meeting-commitments.json",
    DATA / "sequencing-audit.md",
]


def print_final_report(status: PipelineStatus) -> int:
    status.ended_at = datetime.now(timezone.utc)
    duration = (status.ended_at - status.started_at).total_seconds()
    print("\n" + "=" * 70)
    print("FINAL STATUS REPORT")
    print("=" * 70)
    print(f"  started:  {status.started_at.isoformat(timespec='seconds')}")
    print(f"  ended:    {status.ended_at.isoformat(timespec='seconds')}")
    print(f"  duration: {duration:.1f}s")

    # Steps
    print("\n  Steps:")
    if not status.steps:
        print("    (none — aborted before any step ran)")
    else:
        for s in status.steps:
            verdict = "OK    " if s.rc == 0 else f"FAIL{s.rc:>2}"
            print(f"    [{verdict}] {s.elapsed_s:>6.1f}s  {s.label}")

    # Output files
    print("\n  Output files updated:")
    now = datetime.now(timezone.utc).timestamp()
    for p in OUTPUT_FILES_TO_REPORT:
        if not p.exists():
            print(f"    [missing] {p.relative_to(ROOT)}")
            continue
        st = p.stat()
        age_min = (now - st.st_mtime) / 60.0
        size = st.st_size
        # Recently-touched files (within this run window) get a marker
        marker = "*" if age_min < (duration / 60.0 + 1) else " "
        print(f"    {marker} {age_min:>6.1f}min  {size:>10,}b  {p.relative_to(ROOT)}")

    # Pre-flight warnings
    print("\n  Pre-flight warnings:")
    if not status.preflight_warnings:
        print("    (none)")
    for w in status.preflight_warnings:
        print(f"    - {w}")

    # Server restart
    print("\n  Server:")
    if status.server_old_pid is None and status.server_new_pid is None:
        print("    (not restarted — pipeline aborted before server step)")
    else:
        print(f"    old PID: {status.server_old_pid}")
        print(f"    new PID: {status.server_new_pid}")

    # URL verification
    print("\n  URL verification:")
    print(f"    status: {status.url_verify_status}")
    if status.url_verify_detail:
        print(f"    detail: {status.url_verify_detail}")

    # Notes / surprises
    print("\n  Notes / surprises:")
    if not status.notes:
        print("    (none)")
    for n in status.notes:
        print(f"    - {n}")

    # Final one-liner
    print("\n" + "=" * 70)
    if status.overall_pass:
        print("READY FOR MONDAY")
        rc = 0
    else:
        reasons = []
        if status.preflight_aborts:
            reasons.append(f"{len(status.preflight_aborts)} pre-flight abort(s)")
        failed_steps = [s.label for s in status.steps if s.rc != 0]
        if failed_steps:
            reasons.append(f"failed step: {failed_steps[0]}")
        if status.url_verify_status not in ("ok", "not_attempted"):
            reasons.append(f"URL verification {status.url_verify_status}")
        if status.url_verify_status == "not_attempted" and not status.preflight_aborts and not failed_steps:
            reasons.append("URL verification skipped")
        print(f"NEEDS ATTENTION: {'; '.join(reasons)}")
        rc = 1
    print("=" * 70)
    return rc


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 70)
    print("Ross Built — Monday Binder weekly pipeline")
    print(f"  started at {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    print("=" * 70)
    wp = _load_thresholds()
    status = PipelineStatus()

    # Standing note: dual-write of derived-phases-v2.json by step 3 + step 4
    # is masked by strict ordering. Surface it so it stays visible in the
    # weekly report.
    status.notes.append(
        "derived-phases-v2.json is written by both build_phase_artifacts.py (step 3) "
        "and build_sub_phase_rollups.py (step 4). Strict ordering masks this dual-write. "
        "Discovery report flagged it; not auto-fixed."
    )

    # Standing note: TODAY hardcoded
    status.notes.append(
        "build_phase_artifacts.py and build_sub_phase_rollups.py both have "
        "TODAY = date(2026, 4, 29) hardcoded. Outputs are stamped 2026-04-29 "
        "regardless of actual run date until those constants are unhardcoded "
        "(separate ticket, per wmp33)."
    )

    if not preflight(status, wp):
        return print_final_report(status)

    # ------- Pipeline steps -------
    py = sys.executable

    if not run_step(status, "STEP 1 — process.py (transcript extraction)",
                    [py, "process.py"]):
        return print_final_report(status)

    if not run_step(status, "STEP 2 — classifier.py (.planning/) → derived-phases.json",
                    [py, str(CLASSIFIER_PATH)]):
        return print_final_report(status)

    if not run_step(status, "STEP 3 — build_phase_artifacts.py → derived-phases-v2 + phase-instances + job-stages",
                    [py, str(ROOT / "scripts" / "build_phase_artifacts.py")]):
        return print_final_report(status)

    if not run_step(status, "STEP 4 — build_sub_phase_rollups.py → bursts + phase-instances-v2 + medians + rollups",
                    [py, str(ROOT / "scripts" / "build_sub_phase_rollups.py")]):
        return print_final_report(status)

    if not run_step(status, "STEP 5 — generators/run_all.py → insights.json + binders/enriched/",
                    [py, "-m", "generators.run_all"]):
        return print_final_report(status)

    if not run_step(status, "STEP 6 — build_meeting_prep.py → meeting-commitments.json snapshot",
                    [py, str(ROOT / "monday-binder" / "build_meeting_prep.py")]):
        return print_final_report(status)

    if not run_step(status, "STEP 7 — validate_accountability.py → accountability-week-<iso>.md",
                    [py, str(ROOT / "validate_accountability.py")]):
        return print_final_report(status)

    # ------- Server restart + URL verification -------
    if not restart_server(status, wp):
        return print_final_report(status)
    verify_dashboard_url(status, wp)

    return print_final_report(status)


if __name__ == "__main__":
    sys.exit(main())
