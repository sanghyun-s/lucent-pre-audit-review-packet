"""
narrative_validator.py — schema and content validator for the Phase 4b
7-field GPT-generated audit memo.

Public surface:
  * validate_memo(parsed_obj) -> tuple[bool, str]
      Returns (is_valid, reason). is_valid is True only if every check
      passes. reason is "" on success or a short human-readable failure
      description on rejection. The narrative orchestrator uses this to
      decide whether to surface the GPT memo or fall back to the
      deterministic template.

Design:
  Validation is intentionally strict — if anything is even slightly off
  (banned phrase in any field, follow-up list wrong type, disclaimer not
  verbatim, field too short or too long), we reject and fall back. The
  cost of a fallback narrative is low (still hedged, still safe); the
  cost of letting bad output through is high (could undermine the audit
  positioning of the entire tool).

  This module never raises on validator input — even malformed types are
  treated as a failed-validation reason, not an exception.
"""
from __future__ import annotations

from typing import Any

from prompts import (
    BANNED_PHRASES,
    REQUIRED_DISCLAIMER,
    REQUIRED_MEMO_FIELDS,
)

# Per-field length bounds. Tuned to the prompt's "1-2 sentences" target
# with comfortable headroom on both sides. risk_summary may be shorter
# because Phase 4a kept it concise; the other narrative fields are
# slightly larger because they pack assertion / COSO / magnitude reasoning.
_LENGTH_BOUNDS: dict[str, tuple[int, int]] = {
    "risk_summary":                  (40, 600),
    "assertion_consideration":       (40, 600),
    "magnitude_assessment":          (30, 500),
    "likelihood_assessment":         (40, 600),
    "control_or_coso_consideration": (40, 600),
}

# recommended_follow_up: 3-5 items, each within these bounds.
_FOLLOWUP_MIN_ITEMS: int = 3
_FOLLOWUP_MAX_ITEMS: int = 5
_FOLLOWUP_ITEM_MIN: int = 10
_FOLLOWUP_ITEM_MAX: int = 250

# Patterns that suggest the model invented a person's name or role.
# Conservative — only flags clear personifications that would violate the
# subject-discipline rule. Vendor names from the row are NOT in this list
# because they're legitimate observable facts.
_NAME_LEAK_PATTERNS: tuple[str, ...] = (
    "the employee",
    "the manager",
    "the controller",
    "the cfo",
    "the ceo",
    "the bookkeeper",
    "the accountant who",
    "the preparer",   # vague but commonly LLM-invented
    "mr.",
    "mrs.",
    "ms. ",   # trailing space avoids matching real word fragments
)


def _contains_banned_phrase(text: str) -> tuple[bool, str]:
    """Case-insensitive scan for any phrase in BANNED_PHRASES."""
    lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            return True, phrase
    return False, ""


def _contains_name_leak(text: str) -> tuple[bool, str]:
    """Detect personifications that violate the subject-discipline rule."""
    lower = text.lower()
    for pattern in _NAME_LEAK_PATTERNS:
        if pattern in lower:
            return True, pattern
    return False, ""


def validate_memo(parsed: Any) -> tuple[bool, str]:
    """Validate a parsed JSON memo against the Phase 4b schema and content rules.

    Returns:
      (True, "") on success.
      (False, reason) on failure, where reason names the first problem found.

    Never raises. Hostile or malformed input produces a False result.
    """
    # ---- Type check ----
    if not isinstance(parsed, dict):
        return False, f"top-level value is not a JSON object (got {type(parsed).__name__})"

    # ---- Key set: exactly the 7 required, no more, no less ----
    actual_keys = set(parsed.keys())
    required_keys = set(REQUIRED_MEMO_FIELDS)
    if actual_keys != required_keys:
        missing = required_keys - actual_keys
        extra = actual_keys - required_keys
        parts = []
        if missing:
            parts.append(f"missing keys: {sorted(missing)}")
        if extra:
            parts.append(f"extra keys: {sorted(extra)}")
        return False, "; ".join(parts)

    # ---- Per-field type / non-emptiness / length ----
    for field in REQUIRED_MEMO_FIELDS:
        value = parsed[field]
        if field == "recommended_follow_up":
            # Special: must be a list of strings, 3-5 items
            if not isinstance(value, list):
                return False, f"recommended_follow_up must be a list, got {type(value).__name__}"
            if not (_FOLLOWUP_MIN_ITEMS <= len(value) <= _FOLLOWUP_MAX_ITEMS):
                return False, f"recommended_follow_up has {len(value)} items, expected {_FOLLOWUP_MIN_ITEMS}-{_FOLLOWUP_MAX_ITEMS}"
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    return False, f"recommended_follow_up[{i}] must be a string"
                stripped = item.strip()
                if not stripped:
                    return False, f"recommended_follow_up[{i}] is empty"
                if not (_FOLLOWUP_ITEM_MIN <= len(stripped) <= _FOLLOWUP_ITEM_MAX):
                    return False, f"recommended_follow_up[{i}] length {len(stripped)} out of bounds [{_FOLLOWUP_ITEM_MIN}, {_FOLLOWUP_ITEM_MAX}]"
        else:
            # Standard string field
            if not isinstance(value, str):
                return False, f"{field} must be a string, got {type(value).__name__}"
            stripped = value.strip()
            if not stripped:
                return False, f"{field} is empty"
            if field in _LENGTH_BOUNDS:
                lo, hi = _LENGTH_BOUNDS[field]
                if not (lo <= len(stripped) <= hi):
                    return False, f"{field} length {len(stripped)} out of bounds [{lo}, {hi}]"

    # ---- Disclaimer must be verbatim ----
    if parsed["disclaimer"].strip() != REQUIRED_DISCLAIMER:
        return False, "disclaimer does not match the required verbatim string"

    # ---- Banned-phrase scan across all text content ----
    all_text_parts: list[str] = []
    for field in REQUIRED_MEMO_FIELDS:
        v = parsed[field]
        if isinstance(v, str):
            all_text_parts.append(v)
        elif isinstance(v, list):
            all_text_parts.extend(item for item in v if isinstance(item, str))
    combined = "\n".join(all_text_parts)

    bad, matched = _contains_banned_phrase(combined)
    if bad:
        return False, f"banned phrase detected: {matched!r}"

    leaked, leak_pat = _contains_name_leak(combined)
    if leaked:
        return False, f"name-leakage pattern detected: {leak_pat!r}"

    return True, ""
