"""
Local Flask server for the Monday binder workflow.

Entry point: `python server.py` (usually launched by start-monday.bat).
Runs on http://localhost:8765 only — never binds to 0.0.0.0.

Routes:
  GET  /                        → serves monday-binder.html (read fresh per request)
  GET  /binders/<PM_Name>.json  → serves an individual binder JSON
  GET  /status                  → current pipeline state
  POST /refresh                 → kick off the full pipeline (scrape → process → regen)
  POST /scrape                  → scrape only
  POST /process                 → processor only
  POST /upload                  → drag-drop transcript files into transcripts/inbox/
  POST /email/<PM Name>         → generate per-PM PDF + open Outlook draft (never sends)

The pipeline runs on a background thread so /status can poll progress. CAPTCHA
detection in the scraper flips STATE.captcha_needed so the browser can surface
a modal telling the user to complete the login in the open browser window.
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from flask import Flask, jsonify, request, send_file, abort, Response
    from flask_cors import CORS
except ImportError as e:
    sys.stderr.write(
        "ERROR: Flask is not installed. Run: pip install flask flask-cors\n"
        f"Import error was: {e}\n"
    )
    sys.exit(1)


# =========================================================================
# Config
# =========================================================================

from constants import DAILY_LOGS_PATH

SCRIPT_DIR   = Path(__file__).parent.resolve()
SCRAPER_DIR  = Path(r"C:\Users\Jake\buildertrend-scraper")
DAILY_LOGS   = DAILY_LOGS_PATH  # canonical scraper output path (constants.py)
MONDAY_HTML  = SCRIPT_DIR / "monday-binder.html"
BINDERS_DIR  = SCRIPT_DIR / "binders"
INBOX        = SCRIPT_DIR / "transcripts" / "inbox"
LEDGER_FILE  = SCRIPT_DIR / "state" / "processing-ledger.jsonl"
CHAT_COST_LOG = SCRIPT_DIR / "state" / "chat-cost.jsonl"

HOST = "127.0.0.1"
PORT = 8765

# /chat rate limit: 10 requests / 60s, keyed by request.remote_addr
_CHAT_RATE_LIMIT = 10
_CHAT_RATE_WINDOW_SEC = 60
_chat_rate_lock = threading.Lock()
_chat_request_log: dict[str, list[float]] = defaultdict(list)

# Sonnet 4.6 published rates (USD per 1M tokens)
_SONNET_INPUT_PER_MTOK     = 3.00
_SONNET_OUTPUT_PER_MTOK    = 15.00
_SONNET_CACHE_READ_PER_MTOK  = 0.30
_SONNET_CACHE_CREATE_PER_MTOK = 3.75


# =========================================================================
# Shared pipeline state
# =========================================================================

_state_lock = threading.Lock()
_worker_thread: threading.Thread | None = None

STATE = {
    "phase": "idle",                # idle | scraping | processing | regenerating | done | error
    "started_at": None,
    "finished_at": None,
    "actions_taken": [],
    "errors": [],
    "captcha_needed": False,
    "captcha_cleared_at": None,
    "progress_message": "",
    "duration_sec": 0,
    "cost_estimate": "$0.00",
    "last_refresh": None,
    "transcripts_pending": 0,
    "daily_logs_age_hours": None,
    "daily_logs_freshness": None,
}


def _set(**kw):
    with _state_lock:
        STATE.update(kw)


def _append(key, msg):
    with _state_lock:
        STATE[key].append(msg)


def _log(prefix: str, msg: str):
    print(f"[{prefix}] {msg}", flush=True)


# =========================================================================
# Freshness + queue helpers
# =========================================================================

def scrape_freshness() -> tuple[str, float | None]:
    """Return (bucket, age_hours). Bucket is one of fresh/stale/very_stale/missing."""
    if not DAILY_LOGS.exists():
        return ("missing", None)
    try:
        d = json.loads(DAILY_LOGS.read_text(encoding="utf-8"))
        lr = d.get("lastRun", "")
        if not lr:
            return ("missing", None)
        last = datetime.fromisoformat(lr.replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if age_h < 6:
            return ("fresh", age_h)
        if age_h < 48:
            return ("stale", age_h)
        return ("very_stale", age_h)
    except Exception as e:
        _log("STATUS", f"freshness check failed: {e}")
        return ("missing", None)


def count_transcripts() -> int:
    if not INBOX.exists():
        return 0
    return len(list(INBOX.glob("*.txt")))


def refresh_snapshot():
    """Recompute derived state (transcript count, freshness) in STATE."""
    freshness, age = scrape_freshness()
    with _state_lock:
        STATE["daily_logs_freshness"] = freshness
        STATE["daily_logs_age_hours"] = round(age, 1) if age is not None else None
        STATE["transcripts_pending"] = count_transcripts()


# =========================================================================
# Subprocess runner with streaming + CAPTCHA detection
# =========================================================================

def _read_user_env_var(name: str) -> str | None:
    """Pull a Windows *user* env var via PowerShell. start-monday.bat's
    `python server.py` inherits the parent shell's env, which may not include
    ANTHROPIC_API_KEY (set via setx). Read it from the registry on demand."""
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"[Environment]::GetEnvironmentVariable('{name}','User')"],
            capture_output=True, text=True, timeout=10,
        )
        v = (r.stdout or "").strip()
        return v or None
    except Exception:
        return None


def run_subprocess(cmd, cwd, prefix, env_extra=None, scan_captcha=False, timeout_sec: int | None = None) -> int:
    """Run a subprocess, stream stdout with [prefix] lines.
    If scan_captcha is True, flip STATE.captcha_needed on detection / clear
    when the scraper appears to have moved past the login.

    Timeout is enforced by a dedicated watchdog thread so a hung process that
    produces no stdout is still killed at timeout_sec."""
    env_full = os.environ.copy()
    env_full["PYTHONUTF8"] = "1"
    env_full["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env_full.update(env_extra)

    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=env_full,
        )
    except FileNotFoundError as e:
        _log(prefix, f"command not found: {cmd[0]} ({e})")
        return 127

    start = time.time()
    CAPTCHA_TRIGGERS = ("CAPTCHA detected", "Please complete the CAPTCHA", "waiting for manual completion")
    CAPTCHA_CLEARED = ("Authenticated", "Session valid", "CAPTCHA no longer detected", "Login completed")

    # Watchdog: independent thread polls proc + wall clock so a process that
    # blocks without emitting stdout still dies on time. It also poll-interrupts
    # the stdout reader by killing the process, which closes the pipe.
    timed_out = {"flag": False}

    def _watchdog():
        while proc.poll() is None:
            if timeout_sec and (time.time() - start) > timeout_sec:
                _log(prefix, f"timeout after {timeout_sec}s — killing (watchdog)")
                timed_out["flag"] = True
                try:
                    proc.kill()
                except Exception:
                    pass
                return
            time.sleep(1.0)

    wd_thread = None
    if timeout_sec:
        wd_thread = threading.Thread(target=_watchdog, daemon=True)
        wd_thread.start()

    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip()
        _log(prefix, line)

        if scan_captcha:
            if any(t in line for t in CAPTCHA_TRIGGERS):
                _set(captcha_needed=True,
                     progress_message="BT login required — complete the CAPTCHA in the open browser window")
            elif STATE.get("captcha_needed") and any(t in line for t in CAPTCHA_CLEARED):
                _set(captcha_needed=False,
                     captcha_cleared_at=datetime.now().isoformat())

        # Belt-and-suspenders: also check timeout from this thread when stdout
        # is flowing, so we don't wait up to 1s after the watchdog tick.
        if timeout_sec and (time.time() - start) > timeout_sec:
            _log(prefix, f"timeout after {timeout_sec}s — killing")
            timed_out["flag"] = True
            try:
                proc.kill()
            except Exception:
                pass
            break

    proc.wait()
    if wd_thread is not None:
        wd_thread.join(timeout=2.0)
    if timed_out["flag"]:
        return 124
    return proc.returncode


# =========================================================================
# Pipeline worker
# =========================================================================

def pipeline_worker(force_scrape: bool = False, only: str | None = None):
    """Run the requested pipeline stages on a background thread.
    `only` restricts execution to a single stage ('scrape' or 'process')."""
    t0 = time.time()
    _set(
        phase="starting",
        started_at=datetime.now().isoformat(),
        finished_at=None,
        actions_taken=[],
        errors=[],
        captcha_needed=False,
        progress_message="Starting pipeline...",
        duration_sec=0,
    )
    refresh_snapshot()

    ran_scraper = False
    ran_processor = False

    # ----- Scrape -----
    if only in (None, "scrape"):
        freshness, age = scrape_freshness()
        age_str = f"{age:.1f}h" if age is not None else "unknown"
        if freshness == "fresh" and not force_scrape:
            _log("PIPELINE", f"Data fresh ({age_str}), skipping scrape")
            _append("actions_taken", f"Skipped scrape (data fresh, {age_str} old)")
        else:
            _set(phase="scraping",
                 progress_message=f"Scraping Buildertrend (last run {age_str} ago)...")
            _log("PIPELINE", f"Running scraper (freshness={freshness}, age={age_str})")
            rc = run_subprocess(
                cmd=["node", "scrape-daily-logs.js", "--incremental"],
                cwd=str(SCRAPER_DIR), prefix="SCRAPER", scan_captcha=True,
                timeout_sec=600,
            )
            ran_scraper = True
            if rc == 0:
                _append("actions_taken", "Scraper completed")
                if freshness == "very_stale":
                    _append("actions_taken", f"WARNING: data was >48h old ({age_str})")
            elif rc == 124:
                _append("errors", "Scraper timed out after 600s")
            else:
                _append("errors", f"Scraper exited with code {rc}")

    # ----- Process transcripts -----
    if only in (None, "process"):
        n = count_transcripts()
        if n == 0:
            _log("PIPELINE", "No transcripts in inbox — skipping process.py")
            _append("actions_taken", "Skipped process (no transcripts in inbox)")
        else:
            _set(phase="processing",
                 progress_message=f"Processing {n} transcript(s)...")
            _log("PIPELINE", f"Processing {n} transcript(s)")
            api_key = os.environ.get("ANTHROPIC_API_KEY") or _read_user_env_var("ANTHROPIC_API_KEY")
            env_extra = {"ANTHROPIC_API_KEY": api_key} if api_key else None
            if not api_key:
                _append("errors", "ANTHROPIC_API_KEY not set — process.py will abort")
            rc = run_subprocess(
                cmd=[sys.executable, "process.py"],
                cwd=str(SCRIPT_DIR), prefix="PROCESS", env_extra=env_extra,
                timeout_sec=600,
            )
            ran_processor = True
            if rc == 0:
                _append("actions_taken", f"Processed {n} transcript(s)")
            elif rc == 124:
                _append("errors", "process.py timed out after 600s")
            else:
                _append("errors", f"process.py exited with code {rc}")

    # ----- Regenerate monday-binder.html (always) -----
    _set(phase="regenerating", progress_message="Regenerating monday-binder.html...")
    rc = run_subprocess(
        cmd=[sys.executable, "generate_monday_binder.py"],
        cwd=str(SCRIPT_DIR), prefix="REGEN",
        timeout_sec=180,
    )
    if rc == 0:
        _append("actions_taken", "Regenerated monday-binder.html")
    elif rc == 124:
        _append("errors", "generate_monday_binder.py timed out after 180s")
    else:
        _append("errors", f"generate_monday_binder.py exited with code {rc}")

    # ----- Done -----
    errs = STATE["errors"]
    _set(
        phase="error" if errs else "done",
        finished_at=datetime.now().isoformat(),
        duration_sec=round(time.time() - t0, 1),
        progress_message=("Done." if not errs else f"Finished with errors: {', '.join(errs)}"),
        last_refresh=datetime.now().isoformat() if not errs else STATE.get("last_refresh"),
    )
    refresh_snapshot()
    _log("PIPELINE", f"Finished in {STATE['duration_sec']}s (errors: {len(errs)})")


def _start_worker(force_scrape=False, only=None) -> tuple[bool, str]:
    """Return (started, reason). Reason is populated only when NOT started.

    Atomicity: claim the slot by reading phase AND setting phase='starting'
    inside the same lock acquire. Two concurrent /refresh callers can no
    longer both pass the check and spawn duplicate workers."""
    global _worker_thread
    with _state_lock:
        phase = STATE["phase"]
        if phase in ("starting", "scraping", "processing", "regenerating"):
            return (False, f"pipeline already running (phase={phase})")
        # Atomic claim: stamp phase='starting' before releasing the lock so a
        # second caller arriving here sees the busy state.
        STATE["phase"] = "starting"
        STATE["progress_message"] = "Starting pipeline..."
        _worker_thread = threading.Thread(
            target=pipeline_worker,
            kwargs={"force_scrape": force_scrape, "only": only},
            daemon=True,
        )
    # start() is safe to call outside the lock.
    _worker_thread.start()
    return (True, "")


# =========================================================================
# Flask app
# =========================================================================

app = Flask(__name__)
# Only allow our own origin — localhost on the configured port.
CORS(app, resources={r"/*": {"origins": [f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"]}})


@app.route("/")
def serve_index():
    if not MONDAY_HTML.exists():
        return ("monday-binder.html does not exist yet. Run: python generate_monday_binder.py", 404)
    # Always read fresh from disk.
    return send_file(str(MONDAY_HTML), mimetype="text/html", max_age=0)


@app.route("/binders/<path:pm_name>")
def serve_binder(pm_name):
    # Accept either "Martin_Mannix.json" or "Martin Mannix.json"
    safe = pm_name.replace(" ", "_")
    if not safe.endswith(".json"):
        safe += ".json"
    p = BINDERS_DIR / safe
    # Prevent directory traversal
    try:
        p.relative_to(BINDERS_DIR)
    except ValueError:
        abort(400)
    if not p.exists():
        abort(404)
    return send_file(str(p), mimetype="application/json", max_age=0)


@app.route("/packet/<path:slug>")
def serve_packet(slug):
    """Phase 4 — serve `pm-packet-{slug}.html` for browser preview.

    Accepts either a slug ("nelson-belanger") or a PM display name
    ("Nelson Belanger"), so a /packet/Nelson%20Belanger link from Jake's
    binder works without a separate slug lookup. The CDP print path uses
    file:// directly and does not need this route — it's purely for
    browser preview / Outlook open-from-link.
    """
    import re as _re
    canonical = _re.sub(r"[^a-z0-9]+", "-", (slug or "").lower()).strip("-")
    if not canonical:
        abort(400)
    p = SCRIPT_DIR / f"pm-packet-{canonical}.html"
    try:
        p.relative_to(SCRIPT_DIR)
    except ValueError:
        abort(400)
    if not p.exists():
        abort(404)
    return send_file(str(p), mimetype="text/html", max_age=0)


@app.route("/status")
def status():
    refresh_snapshot()
    with _state_lock:
        return jsonify(STATE)


@app.route("/refresh", methods=["POST"])
def refresh():
    body = request.get_json(silent=True) or {}
    force = request.args.get("force") == "1" or body.get("force") is True
    started, reason = _start_worker(force_scrape=force)
    if not started:
        return jsonify({"started": False, "reason": reason}), 409
    return jsonify({"started": True, "force": force})


@app.route("/scrape", methods=["POST"])
def scrape_only():
    force = request.args.get("force") == "1"
    started, reason = _start_worker(force_scrape=force, only="scrape")
    if not started:
        return jsonify({"started": False, "reason": reason}), 409
    return jsonify({"started": True, "force": force})


@app.route("/process", methods=["POST"])
def process_only():
    started, reason = _start_worker(only="process")
    if not started:
        return jsonify({"started": False, "reason": reason}), 409
    return jsonify({"started": True})


@app.route("/upload", methods=["POST"])
def upload_transcripts():
    """Accept one or more .txt transcript files, save to transcripts/inbox/.
    Does NOT auto-process — the UI offers a 'Process now' button after upload
    so the user chooses when to spend Opus tokens."""
    ALLOWED_EXT = {".txt"}
    MAX_BYTES = 5 * 1024 * 1024   # 5 MB per file

    files = request.files.getlist("files")
    if not files:
        single = request.files.get("file")
        files = [single] if single else []
    if not files:
        return jsonify({"ok": False, "message": "no files in request"}), 400

    INBOX.mkdir(parents=True, exist_ok=True)
    results = []
    for f in files:
        fname = Path(f.filename or "").name   # strip any path prefix client sent
        if not fname:
            results.append({"name": "", "ok": False, "error": "no filename"})
            continue
        if Path(fname).suffix.lower() not in ALLOWED_EXT:
            results.append({"name": fname, "ok": False,
                            "error": f"only .txt allowed (got {Path(fname).suffix or 'no extension'})"})
            continue

        target = INBOX / fname
        # Avoid clobbering: append timestamp if name collides
        if target.exists():
            stem = Path(fname).stem
            fname = f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            target = INBOX / fname

        try:
            f.save(str(target))
            size = target.stat().st_size
            if size > MAX_BYTES:
                target.unlink(missing_ok=True)
                results.append({"name": fname, "ok": False,
                                "error": f"file too large: {size} bytes (max {MAX_BYTES})"})
                continue
            if size == 0:
                target.unlink(missing_ok=True)
                results.append({"name": fname, "ok": False, "error": "empty file"})
                continue
            results.append({"name": fname, "ok": True, "size": size})
            _log("UPLOAD", f"saved {fname} ({size} bytes)")
        except Exception as e:
            results.append({"name": fname, "ok": False, "error": f"{type(e).__name__}: {e}"})

    accepted = sum(1 for r in results if r["ok"])
    refresh_snapshot()
    with _state_lock:
        inbox_pending = STATE["transcripts_pending"]

    return jsonify({
        "ok": True,
        "accepted": accepted,
        "rejected": len(results) - accepted,
        "results": results,
        "inbox_pending": inbox_pending,
    })


@app.route("/email/<path:pm_name>", methods=["POST"])
def email_pm(pm_name):
    """Generate per-PM meeting PDF and open Outlook draft.
    Never sends — user reviews the draft and hits Send themselves."""
    try:
        import email_sender  # local module, imported lazily so server boot
                             # does not fail if pywin32 isn't installed yet
    except ImportError as e:
        return jsonify({
            "success": False,
            "message": f"email_sender module not available: {e}",
        }), 500

    try:
        result = email_sender.send_for_pm(pm_name)
    except FileNotFoundError as e:
        return jsonify({"success": False, "message": str(e)}), 404
    except KeyError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"{type(e).__name__}: {e}",
        }), 500

    # draft.success is False when Outlook COM failed but PDF generated;
    # surface the PDF path + mailto fallback so the UI can react sensibly.
    status = 200 if result.get("success") else 502
    payload = {
        "success": bool(result.get("success")),
        "pdf_path": result.get("pdf_path"),
        "pdf_backend": result.get("pdf_backend"),
        "pdf_warnings": result.get("pdf_warnings") or [],
        "draft": result.get("draft") or {},
        "stats": result.get("stats") or {},
        "message": (result.get("draft") or {}).get("message", ""),
    }
    return jsonify(payload), status


def _chat_rate_limit_check(remote: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_sec). Mutates _chat_request_log under lock."""
    now = time.time()
    cutoff = now - _CHAT_RATE_WINDOW_SEC
    with _chat_rate_lock:
        bucket = _chat_request_log[remote]
        # drop expired stamps
        bucket[:] = [t for t in bucket if t >= cutoff]
        if len(bucket) >= _CHAT_RATE_LIMIT:
            oldest = bucket[0]
            retry_after = max(1, int(_CHAT_RATE_WINDOW_SEC - (now - oldest)) + 1)
            return (False, retry_after)
        bucket.append(now)
    return (True, 0)


def _log_chat_cost(usage: dict) -> None:
    """Append one JSONL line per successful chat call to state/chat-cost.jsonl."""
    in_t = int(usage.get("input_tokens", 0) or 0)
    out_t = int(usage.get("output_tokens", 0) or 0)
    cr = int(usage.get("cache_read", 0) or 0)
    cc = int(usage.get("cache_create", 0) or 0)
    cost = (
        in_t  / 1_000_000 * _SONNET_INPUT_PER_MTOK +
        out_t / 1_000_000 * _SONNET_OUTPUT_PER_MTOK +
        cr    / 1_000_000 * _SONNET_CACHE_READ_PER_MTOK +
        cc    / 1_000_000 * _SONNET_CACHE_CREATE_PER_MTOK
    )
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "input_tokens": in_t,
        "output_tokens": out_t,
        "cache_read": cr,
        "cache_create": cc,
        "cost_usd_estimate": round(cost, 6),
    }
    try:
        CHAT_COST_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(CHAT_COST_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        _log("CHAT", f"failed to write cost log: {e}")


@app.route("/chat", methods=["POST"])
def chat():
    """Q&A endpoint — sends question + binder/jobs/subs context to Claude API
    with prompt caching, returns the answer."""
    remote = request.remote_addr or "unknown"
    allowed, retry_after = _chat_rate_limit_check(remote)
    if not allowed:
        resp = jsonify({
            "error": "rate_limit_exceeded",
            "message": f"max {_CHAT_RATE_LIMIT} chat requests per {_CHAT_RATE_WINDOW_SEC}s",
            "retry_after_sec": retry_after,
        })
        resp.headers["Retry-After"] = str(retry_after)
        return resp, 429

    body = request.get_json(silent=True) or {}
    question = (body.get("question") or "").strip()
    history = body.get("history") or []
    if not question:
        return jsonify({"error": "missing question"}), 400

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        api_key = _read_user_env_var("ANTHROPIC_API_KEY")
    if not api_key:
        return jsonify({"error": "ANTHROPIC_API_KEY not set"}), 500

    try:
        import anthropic
    except ImportError:
        return jsonify({"error": "anthropic SDK missing — pip install anthropic"}), 500

    context_md = _read_chat_context()

    system = [
        {
            "type": "text",
            "text": (
                "You are a construction operations analyst for Ross Built, a residential "
                "luxury homebuilder in Florida. You have full access to per-PM meeting "
                "binders (action items, schedule lookahead, issues, financial) AND per-job "
                "daily-log analytics (workforce, deliveries, inspections, sub activity, "
                "phase durations) AND per-subcontractor performance data (lifetime + recent, "
                "absences, reliability, categories, overlap concerns).\n\n"
                "Five PMs and their jobs:\n"
                "  • Martin Mannix — Fish\n"
                "  • Jason Szykulski — Pou, Dewberry, Harllee\n"
                "  • Lee Worthy — Krauss, Ruthven\n"
                "  • Bob Mozine — Drummond, Molinari, Biales\n"
                "  • Nelson Belanger — Markgraf, Clark, Johnson\n\n"
                "Answer concisely with specific numbers and names from the data. Always "
                "cite the job/sub by name when reporting figures. If a question can't be "
                "answered from this data, say so plainly. Never invent numbers."
            ),
        },
        {
            "type": "text",
            "text": context_md,
            "cache_control": {"type": "ephemeral"},
        },
    ]

    messages = []
    for h in history[-12:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=messages,
        )
        answer = resp.content[0].text if resp.content else ""
        u = resp.usage
        usage_dict = {
            "input_tokens":   getattr(u, "input_tokens", 0),
            "output_tokens":  getattr(u, "output_tokens", 0),
            "cache_read":     getattr(u, "cache_read_input_tokens", 0),
            "cache_create":   getattr(u, "cache_creation_input_tokens", 0),
        }
        _log_chat_cost(usage_dict)
        return jsonify({
            "answer": answer,
            "usage": usage_dict,
        })
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500


_chat_context_cache: dict[str, object] = {"text": None, "ts": 0.0}
_CHAT_CONTEXT_TTL_SEC = 60


def _extract_html_const(html: str, name: str) -> str:
    """Extract `const NAME = <json>;` value with proper bracket matching.
    Returns the JSON literal text, or '{}' if not found / unparseable.

    Walks forward from the assignment, counting {/[ vs }/], skipping strings
    (with backslash escape handling). Robust to whitespace before the trailing
    `;` and to other `const`/`let`/`}` patterns appearing inside the value."""
    needle = f"const {name} = "
    i = html.find(needle)
    if i < 0:
        return "{}"
    p = i + len(needle)
    n = len(html)
    if p >= n:
        return "{}"
    open_ch = html[p]
    if open_ch == "{":
        close_ch = "}"
    elif open_ch == "[":
        close_ch = "]"
    else:
        return "{}"

    depth = 0
    in_str = False
    str_quote = ""
    j = p
    while j < n:
        ch = html[j]
        if in_str:
            if ch == "\\" and j + 1 < n:
                j += 2
                continue
            if ch == str_quote:
                in_str = False
        else:
            if ch == '"' or ch == "'":
                in_str = True
                str_quote = ch
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    return html[p:j + 1]
        j += 1
    return "{}"


def _read_chat_context() -> str:
    """Build chat context from authoritative sources, cached for 60s.

    Reads binders/*.json directly (cheap, single source of truth). For jobs &
    subs analytics, prefers calling compute_* directly from generate_monday_binder
    so no HTML parsing is required. Falls back to robust bracket-matched
    extraction from monday-binder.html if the import fails."""
    now = time.time()
    cached = _chat_context_cache.get("text")
    if cached and (now - float(_chat_context_cache.get("ts") or 0)) < _CHAT_CONTEXT_TTL_SEC:
        return cached  # type: ignore[return-value]

    # 1. Binders — read JSON files directly.
    all_binders: dict[str, dict] = {}
    if BINDERS_DIR.exists():
        for p in sorted(BINDERS_DIR.glob("*.json")):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                _log("CHAT", f"failed to parse {p.name}: {e}")
                continue
            # Key by PM display name from filename (Martin_Mannix.json -> "Martin Mannix")
            pm_name = p.stem.replace("_", " ")
            all_binders[pm_name] = obj
    binders_json = json.dumps(all_binders, separators=(",", ":"), default=str) if all_binders else "{}"

    # 2. Jobs + subs — try compute_* path first.
    jobs_json = "{}"
    subs_json = "{}"
    try:
        from datetime import date as _date
        import generate_monday_binder as _gmb
        today = _date.today()
        jobs_data = _gmb.compute_jobs_lifetime_data(all_binders, today)
        subs_data = _gmb.compute_subs_performance_data(today)
        jobs_json = json.dumps(jobs_data, separators=(",", ":"), default=str)
        subs_json = json.dumps(subs_data, separators=(",", ":"), default=str)
    except Exception as e:
        _log("CHAT", f"compute_* path failed ({type(e).__name__}: {e}); falling back to HTML extraction")
        if MONDAY_HTML.exists():
            try:
                html = MONDAY_HTML.read_text(encoding="utf-8")
                jobs_json = _extract_html_const(html, "JOBS_DATA")
                subs_json = _extract_html_const(html, "SUBS_DATA")
                if not all_binders:
                    binders_json = _extract_html_const(html, "ALL_BINDERS")
            except Exception as e2:
                _log("CHAT", f"HTML fallback also failed: {e2}")

    text = (
        "## Per-PM Binders (action items, lookahead, issues, financial)\n"
        "Each PM key holds: meta, jobs (phase/status/address), items[] with "
        "owner/due/priority/status/aging, lookAhead.w2/w4/w8, lookBehind.per_job, "
        "headsUp, issues, financial.\n"
        "```json\n" + binders_json + "\n```\n\n"
        "## Jobs analytics (lifetime per-job, derived from BT daily logs)\n"
        "Keyed by canonical short name. Each job: lifetime totals (days, "
        "person-days, peak workforce, unique subs, deliveries, inspections), "
        "13-month monthly trend, top crews, top activities, phase_durations[] "
        "with substantial-burst classification (longest focused work period).\n"
        "```json\n" + jobs_json + "\n```\n\n"
        "## Subs performance + categories\n"
        "Per-subcontractor: lifetime + recent (last 30d) days/jobs/absences, "
        "reliability % (days_on / days_on + days_absent), trade category "
        "(Plumbing, Electrical, etc.), monthly history. Plus overlap_concerns "
        "(subs on 3+ jobs in last 7 days) and category aggregates.\n"
        "```json\n" + subs_json + "\n```\n"
    )
    _chat_context_cache["text"] = text
    _chat_context_cache["ts"] = now
    return text


@app.route("/ledger")
def ledger():
    """Return processing-ledger contents + aggregate stats. Used to inspect
    which transcript SHAs have been processed (success, duplicate, or
    previously-failed). Read-only — to retry a failed SHA, delete its line
    from state/processing-ledger.jsonl manually."""
    if not LEDGER_FILE.exists():
        return jsonify({
            "exists": False,
            "path": str(LEDGER_FILE),
            "records": [],
            "stats": {"total": 0, "success": 0, "backfilled": 0, "failure": 0},
        })
    records = []
    parse_errors = 0
    with open(LEDGER_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                parse_errors += 1
    success = sum(1 for r in records
                  if r.get("outcome") == "success" and r.get("reason") != "backfilled_from_processed")
    backfilled = sum(1 for r in records if r.get("reason") == "backfilled_from_processed")
    failure = sum(1 for r in records if r.get("outcome") == "failure")
    return jsonify({
        "exists": True,
        "path": str(LEDGER_FILE),
        "records": records,
        "stats": {
            "total": len(records),
            "success": success,
            "backfilled": backfilled,
            "failure": failure,
            "parse_errors": parse_errors,
        },
    })


@app.route("/favicon.ico")
def favicon():
    return ("", 204)


# =========================================================================
# Entry point
# =========================================================================

def main():
    refresh_snapshot()
    print("=" * 60)
    print(f"Monday Binder server")
    print(f"  URL:            http://localhost:{PORT}")
    print(f"  Monday HTML:    {MONDAY_HTML}")
    print(f"  Scraper data:   {DAILY_LOGS}")
    print(f"  Binders dir:    {BINDERS_DIR}")
    print(f"  Inbox pending:  {STATE['transcripts_pending']}")
    print(f"  Data freshness: {STATE['daily_logs_freshness']} "
          f"({STATE['daily_logs_age_hours']}h old)" if STATE['daily_logs_age_hours'] is not None
          else f"  Data freshness: {STATE['daily_logs_freshness']}")
    print("=" * 60)
    print("Close this window to stop the server.")
    print()
    # Flask's built-in werkzeug dev server is fine for localhost-only usage.
    # use_reloader=True so .py edits don't require a manual restart — the
    # Phase 4 incident showed how easy it is to land changes that aren't
    # actually loaded. Audit confirmed no module-level file writes / thread
    # spawns / socket binds, so the parent monitor + child worker can both
    # run main() safely; only the child actually binds the port.
    app.run(host=HOST, port=PORT, debug=False, use_reloader=True)


if __name__ == "__main__":
    main()
