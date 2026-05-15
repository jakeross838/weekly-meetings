"""Database-driven entity normalizer.

Reads aliases from internal_people, pms, subs (NO hardcoded names) and
resolves alias mentions to canonical IDs and names. New aliases added to
the DB are picked up on next process boot or force_refresh call.

Public functions:
    load_entity_index(force_refresh=False) -> dict
    normalize_entity(text, context='', entity_index=None) -> dict
        {"canonical": str, "ambiguous": bool, "matched_via": str,
         "canonical_id": str | None}

Bare-name ambiguity: "Lee" and "Terry" alone are ambiguous on this team
(Lee Ross vs Lee Worthy; multiple "Terry" subs). normalize returns
"Lee?" with ambiguous=True; downstream Reconciler resolves from context.
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()


_CACHE: dict | None = None

# Bare first-name aliases that hit multiple entities — not safe to auto-resolve.
_BARE_AMBIGUOUS: set[str] = {"lee", "terry"}


def _supabase():
    from supabase import create_client
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


def load_entity_index(force_refresh: bool = False) -> dict:
    """Build a case-insensitive alias index from internal_people, pms, subs.

    Priority on alias collision: person > pm > sub. First-write-wins.
    Returned shape: {alias_lower: {type, canonical_id, canonical_name}}."""
    global _CACHE
    if _CACHE is not None and not force_refresh:
        return _CACHE

    client = _supabase()
    index: dict[str, dict[str, str]] = {}

    def _add(alias: str, type_: str, canonical_id: str, canonical_name: str) -> None:
        a = alias.lower().strip() if alias else ""
        if not a:
            return
        if a in index:
            return  # higher-priority entry already present
        index[a] = {
            "type": type_,
            "canonical_id": canonical_id,
            "canonical_name": canonical_name,
        }

    rp = (
        client.table("internal_people")
        .select("id, full_name, aliases")
        .eq("active", True)
        .execute()
    )
    for row in (rp.data or []):
        _add(row["full_name"], "person", row["id"], row["full_name"])
        for alias in (row.get("aliases") or []):
            _add(alias, "person", row["id"], row["full_name"])

    rpms = (
        client.table("pms")
        .select("id, full_name, aliases, active")
        .eq("active", True)
        .execute()
    )
    for row in (rpms.data or []):
        _add(row["full_name"], "pm", row["id"], row["full_name"])
        for alias in (row.get("aliases") or []):
            _add(alias, "pm", row["id"], row["full_name"])

    rs = client.table("subs").select("id, name, aliases").execute()
    for row in (rs.data or []):
        _add(row["name"], "sub", row["id"], row["name"])
        for alias in (row.get("aliases") or []):
            _add(alias, "sub", row["id"], row["name"])

    _CACHE = index
    return index


def normalize_entity(
    text: Optional[str],
    context: str = "",
    entity_index: Optional[dict] = None,
) -> dict:
    """Resolve `text` to a canonical entity.

    Lookup order:
    1. Bare-ambiguous (e.g. "Lee" alone) → return "{text}?" with ambiguous=True.
    2. Exact match on full name or alias → canonical_name.
    3. Word-boundary substring (longest alias wins) → substitute alias with
       canonical name in the text.
    4. No match → return original text.

    Returns:
        {"canonical": str, "ambiguous": bool, "matched_via": str, "canonical_id": str|None}
    """
    if not text:
        return {"canonical": text or "", "ambiguous": False, "matched_via": "none", "canonical_id": None}

    if entity_index is None:
        entity_index = load_entity_index()

    text_stripped = text.strip()
    text_lo = text_stripped.lower()

    if text_lo in _BARE_AMBIGUOUS:
        return {
            "canonical": f"{text_stripped}?",
            "ambiguous": True,
            "matched_via": "none",
            "canonical_id": None,
        }

    if text_lo in entity_index:
        match = entity_index[text_lo]
        return {
            "canonical": match["canonical_name"],
            "ambiguous": False,
            "matched_via": "exact",
            "canonical_id": match["canonical_id"],
        }

    best = None
    best_alias_lo: str | None = None
    best_len = 0
    for alias_lo, entry in entity_index.items():
        if len(alias_lo) < 3:
            continue
        if alias_lo in _BARE_AMBIGUOUS:
            continue  # don't auto-substitute bare names inside compound text
        if re.search(rf"\b{re.escape(alias_lo)}\b", text_lo) and len(alias_lo) > best_len:
            best = entry
            best_alias_lo = alias_lo
            best_len = len(alias_lo)

    if best is not None and best_alias_lo is not None:
        m = re.search(rf"\b{re.escape(best_alias_lo)}\b", text_lo)
        if m:
            start, end = m.span()
            canonical_text = (
                text_stripped[:start]
                + best["canonical_name"]
                + text_stripped[end:]
            )
        else:
            canonical_text = text_stripped
        return {
            "canonical": canonical_text,
            "ambiguous": False,
            "matched_via": "substring",
            "canonical_id": best["canonical_id"],
        }

    return {
        "canonical": text_stripped,
        "ambiguous": False,
        "matched_via": "none",
        "canonical_id": None,
    }
