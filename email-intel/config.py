# Ross Built - Email Intel: CONFIG LOADER
#
# Reads EVERY secret and behavior knob from the ENVIRONMENT (never hardcoded).
# Loads the repo-root .env via python-dotenv so `python capture.py` "just works"
# the same way the rest of the repo does. This file contains NO secrets, so it
# is safe to commit. See config.example.py for a documented list of every var.
#
# Model selection is org-configurable: the resolved model name comes from
# Supabase app_config FIRST (keys INTEL_EXTRACT_MODEL / INTEL_ANALYZE_MODEL),
# then the env var, then the prototype default. capture.py performs the
# app_config lookup (it holds the Supabase client) and calls pick_model().

import os
import re
from pathlib import Path

# --- Load .env ------------------------------------------------------------
# This file lives at  <repo>/email-intel/config.py , so the repo root (which
# holds the shared .env with SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY /
# ANTHROPIC_API_KEY) is one level up. We also load an optional email-intel/.env
# for local overrides. dotenv is optional-at-import so pure-function unit tests
# (routing.py) never require it to be installed.
try:
    from dotenv import load_dotenv

    _HERE = Path(__file__).resolve().parent
    _ROOT = _HERE.parent
    load_dotenv(_ROOT / ".env")            # shared repo-root secrets
    load_dotenv(_HERE / ".env", override=True)  # optional local override
except Exception:
    pass


def _clean(v):
    return v.strip() if isinstance(v, str) else v


def _split_list(s):
    """Split a comma / whitespace / newline separated list into clean items."""
    if not s:
        return []
    return [x.strip() for x in re.split(r"[,\s]+", s.strip()) if x.strip()]


# --- Supabase (repo-root .env) -------------------------------------------
SUPABASE_URL = _clean(os.environ.get("SUPABASE_URL", ""))
# The repo-root .env uses SUPABASE_SERVICE_ROLE_KEY; the original prototype used
# SUPABASE_SERVICE_KEY. Accept either so this drops into the existing repo.
SUPABASE_SERVICE_KEY = _clean(
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_SERVICE_KEY", "")
)

# --- Anthropic -----------------------------------------------------------
ANTHROPIC_API_KEY = _clean(os.environ.get("ANTHROPIC_API_KEY", ""))

# --- Microsoft / Azure app registration ----------------------------------
AZURE_CLIENT_ID = _clean(os.environ.get("AZURE_CLIENT_ID", ""))
AZURE_TENANT_ID = _clean(os.environ.get("AZURE_TENANT_ID", ""))
# Only needed for AUTH_MODE=app (client-credentials). Leave unset for device mode.
AZURE_CLIENT_SECRET = _clean(os.environ.get("AZURE_CLIENT_SECRET", ""))

# --- Auth mode -----------------------------------------------------------
#   "device"  (Phase 1, default): MSAL PublicClientApplication device-code flow,
#             delegated Mail.Read, reads the signed-in user's OWN sent items.
#   "app"     (Phase 4): MSAL ConfidentialClientApplication client-credentials,
#             application Mail.Read, reads a LIST of PM mailboxes unattended.
AUTH_MODE = (os.environ.get("AUTH_MODE", "device") or "device").strip().lower()

# --- Mailboxes -----------------------------------------------------------
# device mode reads the single signed-in mailbox ("me"); MAILBOX_LABEL is just
# the key used for that mailbox's watermark row in sync_state. Default it to the
# operator's own address if you like; the value only has to be stable.
MAILBOX_LABEL = _clean(os.environ.get("MAILBOX_LABEL", "me")) or "me"

# app mode: explicit list of PM mailbox addresses to sweep. If left blank,
# capture.py derives the list from DISTINCT jobs.pm_email in Supabase.
PM_MAILBOXES = _split_list(os.environ.get("PM_MAILBOXES", ""))

# --- Behavior knobs (safe defaults) --------------------------------------
def _int_env(name, default):
    try:
        return int(str(os.environ.get(name, "")).strip() or default)
    except ValueError:
        return default


DAYS_BACK_ON_FIRST_RUN = _int_env("DAYS_BACK_ON_FIRST_RUN", 7)   # first-run history window
MAX_EMAILS_PER_RUN = _int_env("MAX_EMAILS_PER_RUN", 200)         # cost guard, per mailbox

# --- Models --------------------------------------------------------------
# Prototype defaults (last-resort fallback).
DEFAULT_EXTRACT_MODEL = "claude-haiku-4-5-20251001"   # cheap, for triage/extraction
DEFAULT_ANALYZE_MODEL = "claude-sonnet-4-6"           # smarter, for the PM review

# Env overrides for models (accept both the plain and INTEL_ prefixed names).
EXTRACT_MODEL_ENV = _clean(
    os.environ.get("EXTRACT_MODEL") or os.environ.get("INTEL_EXTRACT_MODEL") or ""
) or None
ANALYZE_MODEL_ENV = _clean(
    os.environ.get("ANALYZE_MODEL") or os.environ.get("INTEL_ANALYZE_MODEL") or ""
) or None


def pick_model(app_config_value, env_value, default):
    """Resolve a model name. Order per the Job Intelligence brief:
    Supabase app_config (org-configurable, central) -> env var -> prototype default.
    """
    return (
        (app_config_value.strip() if isinstance(app_config_value, str) else app_config_value)
        or env_value
        or default
    )
