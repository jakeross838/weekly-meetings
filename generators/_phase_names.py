"""Phase code → human name lookup.

Single source of truth: ``config/phase-taxonomy.yaml``. Loaded once at first
call, cached at module level. Use ``phase_name(code)`` for the bare name and
``phase_label(code)`` for the prose-friendly "Name (code)" form.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

import yaml


_TAXONOMY_PATH: Final[Path] = (
    Path(__file__).resolve().parent.parent / "config" / "phase-taxonomy.yaml"
)
_CACHE: dict[str, str] | None = None


def _load() -> dict[str, str]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    out: dict[str, str] = {}
    try:
        doc = yaml.safe_load(_TAXONOMY_PATH.read_text(encoding="utf-8")) or {}
        for p in doc.get("phases", []) or []:
            code = p.get("code")
            name = p.get("name")
            if code and name:
                out[str(code)] = str(name)
    except Exception as e:
        print(f"WARN: _phase_names._load() failed: {e}", file=sys.stderr)
    _CACHE = out
    return _CACHE


def phase_name(code: str | None) -> str:
    """Return the canonical phase name for ``code``, or a "(unknown phase)"
    fallback. Empty/None returns empty string."""
    if not code:
        return ""
    name = _load().get(str(code))
    if name:
        return name
    print(f"WARN: phase_name({code!r}) — code not in taxonomy", file=sys.stderr)
    return f"{code} (unknown phase)"


def phase_label(code: str | None, name: str | None = None) -> str:
    """Prose-friendly form: ``Drywall Hang (8.2)``.

    Pass ``name`` when it's already in scope (e.g., inside a generator that
    iterates over phase instances) to skip the cache lookup. Otherwise the
    name is resolved from the taxonomy. If the code is missing from the
    taxonomy, returns the code itself so the sentence still makes sense.
    """
    if not code:
        return name or ""
    if name is None:
        name = _load().get(str(code))
    if name:
        return f"{name} ({code})"
    print(f"WARN: phase_label({code!r}) — code not in taxonomy", file=sys.stderr)
    return str(code)


def reset_cache_for_tests() -> None:
    """Clear the module-level cache. Tests only — don't call in production."""
    global _CACHE
    _CACHE = None
