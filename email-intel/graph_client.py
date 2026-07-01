#!/usr/bin/env python3
"""Ross Built - Email Intel: MICROSOFT GRAPH CLIENT.

Token acquisition for BOTH auth modes plus the SINGLE shared sent-mail fetch,
so the Graph query/paging logic lives in exactly one place and only the token +
the mailbox path differ between modes.

  device mode (Phase 1): MSAL PublicClientApplication, device-code / interactive
      login, DELEGATED scope Mail.Read. Reads the signed-in user's own mailbox
      via /me/mailFolders/sentitems.

  app mode (Phase 4): MSAL ConfidentialClientApplication, client-credentials,
      scope https://graph.microsoft.com/.default (APPLICATION permission
      Mail.Read + admin consent). Reads any mailbox via
      /users/{mailbox}/mailFolders/sentitems.

fetch_sent_since() is auth-agnostic: it takes a bearer token + a mailbox and
returns the sent messages after the watermark. Pass mailbox="me" for device mode.
"""

import json
import sys
import datetime as dt

import msal
import requests

GRAPH = "https://graph.microsoft.com/v1.0"

# Delegated (device mode): the user consents to us reading their own mail.
DELEGATED_SCOPES = ["Mail.Read"]
# Client-credentials (app mode): the ".default" scope tells AAD to mint a token
# carrying whatever APPLICATION permissions were admin-consented on the app reg.
APP_SCOPE = ["https://graph.microsoft.com/.default"]

TOKEN_CACHE_FILE = ".token_cache.bin"


def _authority(tenant_id):
    return f"https://login.microsoftonline.com/{tenant_id}"


# ---------------------------------------------------------------------------
# datetime helpers (Graph and Supabase format their timestamps differently)
# ---------------------------------------------------------------------------
def parse_iso(s):
    """Parse an ISO-8601 timestamp, tolerating Graph's 7-digit fractional secs."""
    s = s.strip().replace("Z", "+00:00")
    if "." in s:  # trim over-long fractional seconds (Graph gives 7 digits)
        head, rest = s.split(".", 1)
        frac, off = "", ""
        for ch in rest:
            if ch in "+-":
                off = rest[rest.index(ch):]
                break
            frac += ch
        s = f"{head}.{frac[:6]}{off}"
    return dt.datetime.fromisoformat(s)


def to_graph_z(d):
    """Format a datetime as the UTC 'Z' form Graph's $filter expects."""
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Token acquisition
# ---------------------------------------------------------------------------
def get_token_device(client_id, tenant_id, cache_file=TOKEN_CACHE_FILE):
    """Device-code / interactive delegated login. Caches the token so the user
    only sees the browser prompt on first run (and rarely thereafter)."""
    cache = msal.SerializableTokenCache()
    try:
        with open(cache_file) as f:
            cache.deserialize(f.read())
    except FileNotFoundError:
        pass

    app = msal.PublicClientApplication(
        client_id,
        authority=_authority(tenant_id),
        token_cache=cache,
    )

    result = None
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(DELEGATED_SCOPES, account=accounts[0])
    if not result:
        flow = app.initiate_device_flow(scopes=DELEGATED_SCOPES)
        if "user_code" not in flow:
            sys.exit("Could not start device login: " + json.dumps(flow))
        print("\n" + flow["message"] + "\n")  # go to the URL shown, enter the code
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        with open(cache_file, "w") as f:
            f.write(cache.serialize())
    if "access_token" not in result:
        sys.exit("Auth failed: " + json.dumps(result.get("error_description", result)))
    return result["access_token"]


def get_token_app(client_id, tenant_id, client_secret):
    """Client-credentials app token (no user). Requires an admin-consented
    APPLICATION permission (Mail.Read) on the app registration. MSAL caches the
    token internally, so calling this per run is cheap."""
    if not client_secret:
        sys.exit("AUTH_MODE=app requires AZURE_CLIENT_SECRET (see SETUP.md, Phase 4).")
    app = msal.ConfidentialClientApplication(
        client_id,
        authority=_authority(tenant_id),
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=APP_SCOPE)
    if "access_token" not in result:
        sys.exit("App auth failed: " + json.dumps(result.get("error_description", result)))
    return result["access_token"]


# ---------------------------------------------------------------------------
# Shared sent-mail fetch (both modes)
# ---------------------------------------------------------------------------
def _sentitems_url(mailbox):
    """device mode -> the signed-in user's own mailbox; app mode -> a named user."""
    if not mailbox or mailbox == "me":
        return f"{GRAPH}/me/mailFolders/sentitems/messages"
    return f"{GRAPH}/users/{mailbox}/mailFolders/sentitems/messages"


def fetch_sent_since(token, mailbox, watermark, cap):
    """Return sent messages (oldest first) with sentDateTime > watermark, up to
    `cap` (the cost guard). `mailbox` is "me" for device mode, else an address.

    We $select `from`/`toRecipients`/`ccRecipients` so routing.py has the full
    people set (sender + to + cc) for address-based job resolution.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": 'outlook.body-content-type="text"',
    }
    params = {
        "$filter": f"sentDateTime gt {watermark}",
        "$select": "id,subject,bodyPreview,body,from,toRecipients,ccRecipients,sentDateTime",
        "$orderby": "sentDateTime asc",
        "$top": "50",
    }
    url = _sentitems_url(mailbox)
    out = []
    while url and len(out) < cap:
        r = requests.get(url, headers=headers, params=params, timeout=60)
        r.raise_for_status()
        data = r.json()
        out.extend(data.get("value", []))
        url = data.get("@odata.nextLink")  # nextLink already carries the query
        params = None
    return out[:cap]
