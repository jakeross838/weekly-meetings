"""
email_sender.py — generate a per-PM meeting PDF and open an Outlook draft.

Public entry points (called by server.py):
  send_for_pm(pm_name)               → dict with success + pdf_path + draft info
  generate_pdf(pm_name)              → dict with pdf_path / backend / stats
  open_outlook_draft(pm_name, pdf)   → dict with Outlook status / mailto fallback

Design (Phase 3 — single source of truth):
  - PDFs are produced by rendering the already-generated `monday-binder.html`
    in headless Edge/Chrome via the DevTools Protocol (CDP). The binder's
    tab-switch JS (`activateTab(pm_name)`) is invoked before `Page.printToPDF`,
    so the emitted PDF is a per-PM slice of the same HTML the user sees on
    screen and with Ctrl+P.
  - No HTML templating, no secondary stylesheet, no weasyprint/pdfkit path.
    If the CDP print fails, the whole flow raises a loud error — never
    silently reverts to an Emil-era pipeline.
  - Before printing, mtime(monday-binder.html) is compared to the newest
    binder JSON. If the HTML is stale, `generate_monday_binder.py` is
    invoked as a subprocess to refresh it.
  - Outlook uses `.Display()` not `.Send()` — the user reviews before sending.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path

try:
    import websocket  # type: ignore  # websocket-client package
except ImportError as _e:  # pragma: no cover
    raise ImportError(
        "email_sender requires websocket-client (pip install websocket-client)"
    ) from _e


SCRIPT_DIR   = Path(__file__).parent.resolve()
BINDERS_DIR  = SCRIPT_DIR / "binders"
CONFIG_FILE  = SCRIPT_DIR / "config" / "distribution.json"
EXPORTS_DIR  = SCRIPT_DIR / "exports"
MONDAY_HTML  = SCRIPT_DIR / "monday-binder.html"
GENERATOR    = SCRIPT_DIR / "generate_monday_binder.py"


def _pm_packet_path(pm_name: str) -> Path:
    """Mirrors generate_monday_binder._pm_slug — keep them in sync."""
    slug = re.sub(r"[^a-z0-9]+", "-", (pm_name or "").lower()).strip("-")
    return SCRIPT_DIR / f"pm-packet-{slug}.html"


# =========================================================================
# Distribution config
# =========================================================================

def _load_distribution() -> dict:
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Distribution config missing: {CONFIG_FILE}. "
            "Create it with pm_emails and always_cc keys."
        )
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"config/distribution.json is not valid JSON: {e}")


def _pm_binder_path(pm_name: str) -> Path:
    safe = pm_name.replace(" ", "_")
    return BINDERS_DIR / f"{safe}.json"


def _load_binder(pm_name: str) -> dict:
    p = _pm_binder_path(pm_name)
    if not p.exists():
        raise FileNotFoundError(f"Binder not found for {pm_name}: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


# =========================================================================
# Stats shown in email body
# =========================================================================

ACTIVE_STATUSES = {"NOT_STARTED", "IN_PROGRESS", "BLOCKED", "OPEN", "IN PROGRESS"}
COMPLETE_STATUSES = {"COMPLETE", "DONE", "KILLED"}


def _norm_status(s: str) -> str:
    return (s or "").strip().upper()


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _days_open(item: dict, today: date) -> int:
    opened = _parse_date(item.get("opened"))
    return (today - opened).days if opened else 0


def _compute_stats(binder: dict) -> dict:
    items = binder.get("items", [])
    today = date.today()
    active = [i for i in items if _norm_status(i.get("status")) in ACTIVE_STATUSES]
    completed = [i for i in items if _norm_status(i.get("status")) in COMPLETE_STATUSES]
    urgent = sum(1 for i in active if (i.get("priority") or "").upper() == "URGENT")
    stale = sum(1 for i in active if _days_open(i, today) >= 14)
    due_soon = 0
    for i in active:
        d = _parse_date(i.get("due"))
        if d and 0 <= (d - today).days <= 7:
            due_soon += 1
    total = len(active) + len(completed)
    ppc = f"{round(100 * len(completed) / total)}%" if total else "N/A"
    return {
        "urgent": urgent,
        "aging_past_14d": stale,
        "due_within_7d": due_soon,
        "ppc": ppc,
    }


# =========================================================================
# Browser discovery (Edge first on Windows, then Chrome)
# =========================================================================

def _find_browser() -> Path:
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe")),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")),
    ]
    for c in candidates:
        if c.exists():
            return c
    for name in ("msedge", "msedge.exe", "chrome", "chrome.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise RuntimeError(
        "No Edge or Chrome binary found. Install Edge (ships with Windows 10/11) "
        "or Chrome; email PDF generation requires a Chromium-based browser for CDP print."
    )


# =========================================================================
# Freshness check — regenerate monday-binder.html if any binder is newer
# =========================================================================

def _ensure_html_fresh(pm_name: str | None = None) -> None:
    """Regenerate monday-binder.html + all PM packets if any binder JSON is
    newer than the rendered output, or if any output file is missing.

    Phase 4 — both monday-binder.html (Jake's) and the per-PM packets are
    produced by a single `python generate_monday_binder.py` invocation, so
    one freshness check covers both. If pm_name is given, that packet must
    also exist; missing packet forces a regen even if monday-binder.html is
    fresh (e.g., first run after upgrade)."""
    binder_files = list(BINDERS_DIR.glob("*.json")) if BINDERS_DIR.exists() else []
    html_mtime = MONDAY_HTML.stat().st_mtime if MONDAY_HTML.exists() else 0.0
    newest_binder = max((p.stat().st_mtime for p in binder_files), default=0.0)
    needs_regen = (not MONDAY_HTML.exists()) or (newest_binder > html_mtime)
    if pm_name and not needs_regen:
        packet = _pm_packet_path(pm_name)
        if not packet.exists() or packet.stat().st_mtime < newest_binder:
            needs_regen = True
    if not needs_regen:
        return
    if not GENERATOR.exists():
        raise FileNotFoundError(
            f"generate_monday_binder.py not found at {GENERATOR}; "
            "cannot refresh monday-binder.html before printing."
        )
    rc = subprocess.run(
        [sys.executable, str(GENERATOR)],
        cwd=str(SCRIPT_DIR), capture_output=True, text=True, timeout=180,
    )
    if rc.returncode != 0:
        raise RuntimeError(
            "generate_monday_binder.py failed when refreshing outputs:\n"
            f"stdout: {rc.stdout[-500:]}\nstderr: {rc.stderr[-500:]}"
        )


# =========================================================================
# CDP print — the single PDF path
# =========================================================================

_CDP_HOST = "127.0.0.1"


def _read_cdp_port(user_data: str, timeout: float = 5.0) -> int:
    """Edge writes its actual listening port to <user-data-dir>/DevToolsActivePort
    when launched with --remote-debugging-port=0. First line is the port; second
    is the WebSocket path. Poll until the file exists + is parseable."""
    port_file = Path(user_data) / "DevToolsActivePort"
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            if port_file.exists():
                first = port_file.read_text(encoding="utf-8").splitlines()[0].strip()
                if first.isdigit():
                    return int(first)
        except Exception as e:
            last_err = e
        time.sleep(0.1)
    raise RuntimeError(
        f"Edge never wrote DevToolsActivePort in {user_data}"
        + (f" ({last_err})" if last_err else "")
    )


def _wait_for_cdp(port: int, target_url_prefix: str, timeout: float = 15.0) -> dict:
    """Poll the CDP /json endpoint until the target page is listed."""
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://{_CDP_HOST}:{port}/json", timeout=1) as r:
                pages = json.loads(r.read())
            for p in pages:
                if p.get("type") == "page" and target_url_prefix in p.get("url", ""):
                    return p
        except Exception as e:
            last_err = e
        time.sleep(0.25)
    raise RuntimeError(
        f"CDP endpoint never came up on port {port}"
        + (f" ({last_err})" if last_err else "")
    )


def _cdp_send(ws, msg_id_ref: list[int], method: str, params: dict | None = None) -> dict:
    msg_id_ref[0] += 1
    mid = msg_id_ref[0]
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    # Drain messages until our response arrives (filter out events).
    while True:
        raw = ws.recv()
        if not raw:
            raise RuntimeError(f"CDP connection closed while waiting for {method}")
        r = json.loads(raw)
        if r.get("id") == mid:
            if "error" in r:
                raise RuntimeError(f"CDP {method} failed: {r['error']}")
            return r.get("result", {})


def _print_packet_via_cdp(pm_name: str, out_pdf: Path) -> None:
    """Phase 4 — load the static pm-packet-{slug}.html file directly through
    headless Edge and Page.printToPDF. No JS activator needed because the
    packet is a fully static, self-contained HTML file (one PM only, all
    sections pre-rendered server-side). Loud failure on any error."""
    browser = _find_browser()
    packet_path = _pm_packet_path(pm_name)
    if not packet_path.exists():
        raise FileNotFoundError(
            f"PM packet missing: {packet_path}. Run generate_monday_binder.py first."
        )

    file_url = "file:///" + str(packet_path.resolve()).replace("\\", "/")
    user_data = tempfile.mkdtemp(prefix="edge_cdp_packet_")

    proc = subprocess.Popen([
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--remote-debugging-port=0",
        f"--user-data-dir={user_data}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--disable-extensions",
        file_url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ws = None
    try:
        port = _read_cdp_port(user_data, timeout=5.0)
        page = _wait_for_cdp(port, packet_path.name, timeout=20.0)
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
        msg_id = [0]

        _cdp_send(ws, msg_id, "Page.enable")
        _cdp_send(ws, msg_id, "Runtime.enable")

        # Static page — only thing we wait for is fonts, since Google Fonts
        # arrive over the network and printToPDF must not race them.
        _cdp_send(ws, msg_id, "Runtime.evaluate", {
            "expression": "document.fonts.ready.then(() => 'ready')",
            "awaitPromise": True,
            "returnByValue": True,
        })

        # Verify the packet's title contains the PM name — guards against the
        # wrong file being printed under the right slug (rename / collision).
        r = _cdp_send(ws, msg_id, "Runtime.evaluate", {
            "expression": "document.title || ''",
            "returnByValue": True,
        })
        title = (r.get("result") or {}).get("value", "")
        if pm_name not in title:
            raise RuntimeError(
                f"Packet title '{title}' does not contain '{pm_name}'. "
                f"Refusing to print — wrong PM."
            )

        pdf = _cdp_send(ws, msg_id, "Page.printToPDF", {
            "paperWidth":   8.5,
            "paperHeight": 11.0,
            "marginTop":    0.0,
            "marginBottom": 0.0,
            "marginLeft":   0.0,
            "marginRight":  0.0,
            "printBackground":   True,
            "preferCSSPageSize": True,
        })
        data = base64.b64decode(pdf["data"])
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.write_bytes(data)
        if out_pdf.stat().st_size < 200:
            raise RuntimeError(
                f"PrintToPDF produced a suspiciously small file ({out_pdf.stat().st_size} bytes)"
            )
    finally:
        try:
            if ws is not None:
                ws.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        shutil.rmtree(user_data, ignore_errors=True)


def _print_via_cdp(pm_name: str, out_pdf: Path, view: str = "pm") -> None:
    """Launch headless Edge, load monday-binder.html, render the requested
    view for pm_name, and Page.printToPDF. Writes to out_pdf. Raises on any
    failure — no silent fallback to a legacy PDF path.

    view:
      "pm"        — meeting binder (calls activateTab)
      "analytics" — Jobs + Subs filtered to this PM (calls activatePMAnalytics)
    """
    browser = _find_browser()
    if not MONDAY_HTML.exists():
        raise FileNotFoundError(
            f"{MONDAY_HTML} does not exist. Run generate_monday_binder.py first."
        )

    # file:/// URL for the local HTML
    file_url = "file:///" + str(MONDAY_HTML.resolve()).replace("\\", "/")
    user_data = tempfile.mkdtemp(prefix="edge_cdp_emailsender_")

    proc = subprocess.Popen([
        str(browser),
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--remote-debugging-port=0",
        f"--user-data-dir={user_data}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--disable-extensions",
        file_url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    ws = None
    try:
        port = _read_cdp_port(user_data, timeout=5.0)
        page = _wait_for_cdp(port, "monday-binder.html", timeout=20.0)
        ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=20)
        msg_id = [0]

        _cdp_send(ws, msg_id, "Page.enable")
        _cdp_send(ws, msg_id, "Runtime.enable")

        # Wait for app's initial render — the generator emits the HTML but the
        # actual tab content is drawn by JS into #pmView after load + tab init.
        for _ in range(80):  # ~20s budget
            r = _cdp_send(ws, msg_id, "Runtime.evaluate", {
                "expression": (
                    "(function(){"
                    "  const v = document.getElementById('pmView');"
                    "  return typeof activateTab === 'function'"
                    "    && v && v.childElementCount > 0"
                    "    && typeof ALL_BINDERS !== 'undefined';"
                    "})()"
                ),
                "returnByValue": True,
            })
            if r.get("result", {}).get("value"):
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(
                "monday-binder.html never finished its initial render "
                "(activateTab / ALL_BINDERS / #pmView not ready within 20s)"
            )

        # Activate the requested view. The binder JS defines activateTab(pm)
        # for the meeting view and activatePMAnalytics(pm) for the filtered
        # Jobs+Subs analytics view.
        if view == "analytics":
            activator_fn = "activatePMAnalytics"
            verify_expr  = "document.querySelector('.pm-analytics')?.dataset?.pm || ''"
        else:
            activator_fn = "activateTab"
            verify_expr  = "document.querySelector('.meeting-header h1')?.textContent || ''"

        r = _cdp_send(ws, msg_id, "Runtime.evaluate", {
            "expression": (
                f"(function(){{"
                f"  if (typeof {activator_fn} !== 'function') return 'no-{activator_fn}';"
                f"  {activator_fn}({json.dumps(pm_name)});"
                f"  return 'ok';"
                f"}})()"
            ),
            "returnByValue": True,
        })
        result_tag = (r.get("result") or {}).get("value")
        if result_tag != "ok":
            raise RuntimeError(
                f"{activator_fn}('{pm_name}') not invoked — result was {result_tag!r}. "
                "The binder JS may have changed name or the PM name isn't recognized."
            )

        # Let the 180ms switching transition complete, then explicitly await
        # font readiness instead of guessing with a fixed sleep. Google Fonts
        # (Inter / Space Grotesk / JetBrains Mono) must be fully loaded before
        # printToPDF or glyphs fall back to system fonts.
        time.sleep(0.2)
        _cdp_send(ws, msg_id, "Runtime.evaluate", {
            "expression": "document.fonts.ready.then(() => 'ready')",
            "awaitPromise": True,
            "returnByValue": True,
        })

        # Confirm the rendered PM matches — otherwise we'd silently email the
        # wrong person the wrong document. Loud failure instead.
        r = _cdp_send(ws, msg_id, "Runtime.evaluate", {
            "expression": verify_expr,
            "returnByValue": True,
        })
        rendered = (r.get("result") or {}).get("value", "")
        if pm_name not in rendered:
            raise RuntimeError(
                f"Expected the rendered PM to be '{pm_name}' but got '{rendered}' "
                f"(view={view!r}). Refusing to print — PDF would be for the wrong PM."
            )

        # Print. Margins mirror the binder's @page { margin: 0.55in 0.6in }.
        pdf = _cdp_send(ws, msg_id, "Page.printToPDF", {
            "paperWidth":   8.5,
            "paperHeight": 11.0,
            "marginTop":    0.55,
            "marginBottom": 0.55,
            "marginLeft":   0.60,
            "marginRight":  0.60,
            "printBackground":   True,
            "preferCSSPageSize": True,
        })
        data = base64.b64decode(pdf["data"])
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        out_pdf.write_bytes(data)
        if out_pdf.stat().st_size < 200:
            raise RuntimeError(f"PrintToPDF produced a suspiciously small file ({out_pdf.stat().st_size} bytes)")
    finally:
        try:
            if ws is not None:
                ws.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        # Cleanup user_data dir — ignore_errors guards against Edge file locks
        # that may linger briefly after process termination.
        shutil.rmtree(user_data, ignore_errors=True)


# =========================================================================
# Public: generate_pdf — single source of truth
# =========================================================================

def _slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_")


def generate_pdf(pm_name: str) -> dict:
    """Phase 4 — produce per-PM packet PDF by printing pm-packet-{slug}.html
    through CDP. Returns {pdf_path, backend, stats}."""
    # Sanity: PM must exist in binders/ before we spin up a browser.
    binder = _load_binder(pm_name)
    stats  = _compute_stats(binder)

    _ensure_html_fresh(pm_name)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out_pdf = EXPORTS_DIR / f"{_slugify(pm_name)}_{date.today().isoformat()}.pdf"

    _print_packet_via_cdp(pm_name, out_pdf)
    return {
        "pdf_path": str(out_pdf),
        "backend": "cdp-print-packet",
        "stats": stats,
    }


# Alias kept for compatibility with Phase 11 V7 validation; produces a single
# meeting PDF (no Outlook draft).
generate_pdf_for_pm = generate_pdf


# =========================================================================
# Outlook COM — draft only, never send
# =========================================================================

def _first_name(full: str) -> str:
    return (full or "").split()[0] if full else ""


def _build_email_subject(binder: dict) -> str:
    m = binder.get("meta", {})
    pm = m.get("pm", "")
    first = _first_name(pm)
    d = _parse_date(m.get("date"))
    date_str = d.strftime("%b %d").replace(" 0", " ") if d else (m.get("date") or "")
    return f"Production Meeting — {first} — Week of {date_str}"


def _build_email_body(binder: dict, stats: dict | None = None,
                      has_analytics: bool = False) -> str:
    """Phase 4 — short body. The packet itself carries the analytics; this
    note just frames how to use it during the week. `stats` is accepted for
    API compatibility but no longer surfaced in copy."""
    m = binder.get("meta", {})
    pm = m.get("pm", "")
    first = _first_name(pm)
    d = _parse_date(m.get("date"))
    meeting_date = d.strftime("%B %d, %Y").replace(" 0", " ") if d else (m.get("date") or "")
    return (
        f"Hi {first},\n\n"
        f"Attached is your production document for the week of {meeting_date}.\n\n"
        f"This is your packet only — your jobs, your open items, your look-ahead. "
        f"The full company-wide analytics live with Jake.\n\n"
        f"Please print, mark up throughout the week as items progress or complete, "
        f"and bring your marked copy to next week's meeting.\n\n"
        f"Anything urgent, text Jake directly.\n\n"
        f"— Ross Built\n"
    )


def open_outlook_draft(pm_name: str, pdf_paths: list[str] | str,
                       binder: dict | None = None, stats: dict | None = None) -> dict:
    """Create + display an Outlook draft with one or more PDFs attached.
    Never calls `.Send()` — the user reviews and sends manually."""
    # Normalize: accept single path (legacy) or list (current).
    if isinstance(pdf_paths, str):
        pdf_paths = [pdf_paths]
    pdf_paths = [p for p in pdf_paths if p]

    dist = _load_distribution()
    pm_emails = dist.get("pm_emails", {})
    always_cc = dist.get("always_cc", [])
    to_addr = pm_emails.get(pm_name)
    if not to_addr:
        raise KeyError(f"No email mapped for PM '{pm_name}' in config/distribution.json")

    binder = binder if binder is not None else _load_binder(pm_name)
    stats  = stats  if stats  is not None else _compute_stats(binder)
    subject = _build_email_subject(binder)
    body    = _build_email_body(binder, stats, has_analytics=len(pdf_paths) > 1)

    try:
        import pythoncom       # type: ignore
        import win32com.client  # type: ignore
    except ImportError as e:
        return _mailto_fallback(to_addr, always_cc, subject, body, pdf_paths[0] if pdf_paths else "",
                                reason=f"pywin32 not installed: {e}")

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = to_addr
        if always_cc:
            mail.CC = "; ".join(always_cc)
        mail.Subject = subject
        mail.Body = body
        for p in pdf_paths:
            mail.Attachments.Add(str(Path(p).resolve()))
        mail.Display()  # opens draft — user reviews and sends
        return {
            "success": True,
            "backend": "outlook-com",
            "message": f"Draft opened in Outlook. To: {to_addr}. {len(pdf_paths)} PDF(s) attached.",
            "to": to_addr,
            "cc": always_cc,
            "subject": subject,
            "attached": pdf_paths,
        }
    except Exception as e:
        return _mailto_fallback(to_addr, always_cc, subject, body,
                                pdf_paths[0] if pdf_paths else "",
                                reason=f"Outlook COM error: {type(e).__name__}: {e}")
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _mailto_fallback(to_addr: str, cc_list: list[str], subject: str, body: str,
                     pdf_path: str, reason: str) -> dict:
    """Build a mailto: URL the user can open manually; user must attach PDF manually."""
    from urllib.parse import quote
    mailto = (
        f"mailto:{to_addr}"
        f"?cc={quote('; '.join(cc_list))}"
        f"&subject={quote(subject)}"
        f"&body={quote(body)}"
    )
    return {
        "success": False,
        "backend": "mailto",
        "message": (
            f"Outlook COM unavailable ({reason}). Use mailto fallback and attach "
            f"the PDF manually.\nPDF: {pdf_path}"
        ),
        "mailto_url": mailto,
        "pdf_path": pdf_path,
        "reason": reason,
    }


# =========================================================================
# Combined entry point — called by server.py /email/<pm_name>
# =========================================================================

def send_for_pm(pm_name: str) -> dict:
    """Phase 4 — generate the per-PM packet PDF (the new lean document) and
    open an Outlook draft with it attached. The full company-wide analytics
    no longer go to PMs; that view stays with Jake on monday-binder.html."""
    binder = _load_binder(pm_name)
    stats  = _compute_stats(binder)

    _ensure_html_fresh(pm_name)

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    today_str = date.today().isoformat()
    pm_slug = _slugify(pm_name)
    packet_pdf = EXPORTS_DIR / f"{pm_slug}_{today_str}.pdf"

    _print_packet_via_cdp(pm_name, packet_pdf)

    draft = open_outlook_draft(pm_name, [str(packet_pdf)], binder=binder, stats=stats)
    return {
        "success": bool(draft.get("success")),
        "pdf_path": str(packet_pdf),
        "analytics_pdf_path": None,  # kept for response shape compatibility
        "pdf_backend": "cdp-print-packet",
        "pdf_warnings": [],
        "draft": draft,
        "stats": stats,
    }


# =========================================================================
# CLI (manual testing / regenerating a single PDF without Outlook)
# =========================================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python email_sender.py <PM Name>                # PDF + Outlook draft")
        print("       python email_sender.py --pdf-only <PM Name>     # PDF only, no Outlook")
        sys.exit(1)
    if sys.argv[1] == "--pdf-only" and len(sys.argv) >= 3:
        pm = sys.argv[2]
        result = generate_pdf(pm)
        print(json.dumps(result, indent=2))
    else:
        pm = sys.argv[1]
        result = send_for_pm(pm)
        print(json.dumps(result, indent=2, default=str))
