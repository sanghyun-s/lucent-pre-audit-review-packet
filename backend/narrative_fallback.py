"""
narrative_fallback.py — deterministic rule-based fallback narratives.

When the LLM call fails (API down, timeout, banned-phrase trip, empty
response, validator rejection), we still want the user to see *something*
hedged and audit-safe in place of an error. This module produces that
fallback.

It does NOT use any LLM. It is pure template logic over the same observable
fields the LLM would have used, so fallback narratives are grounded in the
same facts — just less stylistically polished.

Public surface:
  * build_fallback_risk_summary(row) -> str
      Phase 4a — single 1-2 sentence summary. Kept for back-compat.

  * build_fallback_full_memo(row) -> dict
      Phase 4b — full 7-field memo with the same schema the validator
      enforces. Always passes the validator by construction.
"""
from __future__ import annotations

from prompts import REQUIRED_DISCLAIMER


# ---------------------------------------------------------------------------
# Shared helpers (used by both fallback paths)
# ---------------------------------------------------------------------------

def _amount_str(row: dict) -> str:
    amt = row.get("amount")
    if isinstance(amt, (int, float)):
        return f"${amt:,.2f}"
    return "the transaction amount"


def _flag_parts(row: dict) -> list[str]:
    """Return the active_flags as a list of phrases. Always returns at
    least one element (a placeholder) so downstream joins never fail."""
    flags = (row.get("active_flags") or "").strip()
    if not flags:
        return ["the flagged indicators on this transaction"]
    parts = [p.strip() for p in flags.split(";") if p.strip()]
    return parts or ["the flagged indicators on this transaction"]


def _flags_clause(row: dict) -> str:
    """Natural-language clause from active_flags."""
    parts = _flag_parts(row)
    if len(parts) == 1:
        return parts[0].lower()
    if len(parts) == 2:
        return f"{parts[0].lower()} and {parts[1].lower()}"
    return ", ".join(p.lower() for p in parts[:-1]) + f", and {parts[-1].lower()}"


# ---------------------------------------------------------------------------
# Phase 4a — risk_summary fallback (kept for back-compat)
# ---------------------------------------------------------------------------

def build_fallback_risk_summary(row: dict) -> str:
    """Generate a deterministic 1-2 sentence risk summary from row facts.

    This is the Phase 4a safety net. Always returns a non-empty string.
    Never accuses a person. Never concludes fraud.
    """
    flags_clause = _flags_clause(row)
    amount_str = _amount_str(row)
    materiality = (row.get("materiality_annotation") or "").strip()
    qual_override = int(row.get("is_qualitative_override", 0) or 0) == 1
    fraud_risk = int(row.get("fraud_risk_flag", 0) or 0) == 1

    sentence_1 = (
        f"This {amount_str} transaction exhibits {flags_clause}, "
        f"which warrants follow-up regarding authorization, "
        f"supporting documentation, and the surrounding control activities."
    )

    sentence_2_parts: list[str] = []
    if qual_override:
        sentence_2_parts.append(
            "the co-occurrence of multiple risk indicators is the basis "
            "for elevated concern"
        )
    elif fraud_risk:
        sentence_2_parts.append(
            "multiple fraud risk indicators are present on this row"
        )

    has_preceding = bool(sentence_2_parts)
    if materiality and "exceeds" in materiality.lower():
        if has_preceding:
            sentence_2_parts.append("and the amount is not quantitatively immaterial")
        else:
            sentence_2_parts.append("the amount is not quantitatively immaterial")
    elif materiality and "below" in materiality.lower():
        if has_preceding:
            sentence_2_parts.append("but the amount is below the relevant materiality threshold")
        else:
            sentence_2_parts.append("the amount is below the relevant materiality threshold")

    if sentence_2_parts:
        sentence_2 = (
            "Note that "
            + ", ".join(sentence_2_parts)
            + "; this analysis identifies risk indicators only and "
            "does not determine intent or fraud."
        )
    else:
        sentence_2 = (
            "This analysis identifies risk indicators only and does not "
            "determine intent or fraud."
        )

    return f"{sentence_1} {sentence_2}"


# ---------------------------------------------------------------------------
# Phase 4b — full 7-field memo fallback
# ---------------------------------------------------------------------------

# Lowercased patterns used to map active_flags into assertion and COSO
# language. Keys are substrings of typical active_flags text; values are
# the assertion / COSO components to consider.
_FLAG_TO_ASSERTIONS: dict[str, tuple[str, ...]] = {
    "new vendor":             ("Occurrence", "Rights and Obligations"),
    "missing description":    ("Occurrence", "Accuracy", "Completeness"),
    "weak documentation":     ("Occurrence", "Accuracy", "Completeness"),
    "unusual amount":         ("Accuracy", "Valuation", "Classification"),
    "weekend posting":        ("Cutoff", "Occurrence"),
    "near approval":          ("Occurrence"),
    "round number":           ("Accuracy",),
    "account coding":         ("Classification",),
}

_FLAG_TO_COSO: dict[str, tuple[str, ...]] = {
    "missing description":    ("Information and Communication",),
    "weak documentation":     ("Information and Communication",),
    "near approval":          ("Control Activities",),
    "weekend posting":        ("Control Activities",),
    "new vendor":             ("Control Activities", "Risk Assessment"),
    "year-end concentration": ("Monitoring Activities",),
    "non-standard":           ("Risk Assessment",),
    "management override":    ("Control Environment",),
}


def _derive_assertions(row: dict) -> list[str]:
    """Pick 1-2 FS assertions to cite based on the active flags."""
    flags_text = (row.get("active_flags") or "").lower()
    seen: list[str] = []
    for pattern, assertions in _FLAG_TO_ASSERTIONS.items():
        if pattern in flags_text:
            for a in assertions:
                if a not in seen:
                    seen.append(a)
                if len(seen) >= 2:
                    return seen
    # Fallback if no flag matched: a generic but safe choice
    return seen or ["Occurrence", "Accuracy"]


def _derive_coso(row: dict) -> list[str]:
    """Pick 1-2 COSO components based on the active flags."""
    flags_text = (row.get("active_flags") or "").lower()
    seen: list[str] = []
    for pattern, components in _FLAG_TO_COSO.items():
        if pattern in flags_text:
            for c in components:
                if c not in seen:
                    seen.append(c)
                if len(seen) >= 2:
                    return seen
    return seen or ["Control Activities"]


def _join_two(items: list[str]) -> str:
    """English-style join of 1-2 items."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{items[0]} and {items[1]}"


def _build_followups(row: dict) -> list[str]:
    """Build a 3-5 item recommended_follow_up list, varied by what fired.

    Guaranteed to return at least 3 items by always including a baseline
    set, then adding conditional items based on which flags fired.
    """
    # Baseline: always-applicable procedures that work for any flagged row
    items: list[str] = [
        "Inspect invoice and supporting documentation",
        "Confirm evidence that goods or services were received",
        "Corroborate evidence with management discussion consistent with audit standards",
    ]

    flags_text = (row.get("active_flags") or "").lower()
    if "new vendor" in flags_text:
        items.append("Verify vendor setup history and supporting due-diligence file")
    if "missing description" in flags_text or "weak documentation" in flags_text:
        items.append("Obtain written explanation of business purpose for this transaction")
    if "near approval" in flags_text:
        items.append("Review whether similar transactions occurred near approval thresholds")
    if "weekend posting" in flags_text:
        items.append("Confirm rationale for posting outside normal business hours")
    if "unusual amount" in flags_text:
        items.append("Compare the transaction to prior-period activity in the same account")
    if int(row.get("is_qualitative_override", 0) or 0) == 1:
        items.append("Document the co-occurrence of risk indicators in the audit workpaper")

    # De-duplicate while preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)

    # Clip to 5 (the 3 baseline + first 2 conditional)
    return deduped[:5]


def build_fallback_full_memo(row: dict) -> dict:
    """Generate a deterministic 7-field memo from row facts.

    Always passes the Phase 4b validator by construction (correct schema,
    non-empty fields, follow-up list of 3-5 items, verbatim disclaimer,
    no banned phrases by design).
    """
    amount_str = _amount_str(row)
    flags_clause = _flags_clause(row)
    flag_count = len(_flag_parts(row))
    materiality = (row.get("materiality_annotation") or "").strip()
    qual_override = int(row.get("is_qualitative_override", 0) or 0) == 1

    # ---- risk_summary ----
    risk_summary = (
        f"This {amount_str} transaction exhibits {flags_clause}, which "
        f"warrants follow-up regarding authorization, supporting "
        f"documentation, and the surrounding control activities."
    )

    # ---- assertion_consideration ----
    assertions = _derive_assertions(row)
    assertion_consideration = (
        f"The pattern raises questions regarding the "
        f"{_join_two(assertions)} assertion"
        + ("s" if len(assertions) > 1 else "")
        + ", warranting additional procedures to confirm the transaction's "
        f"validity and proper recording."
    )

    # ---- magnitude_assessment ----
    if materiality and "exceeds" in materiality.lower():
        magnitude_assessment = (
            f"At {amount_str}, the amount exceeds the applicable materiality "
            f"threshold, so this transaction should not be dismissed as "
            f"quantitatively insignificant."
        )
    elif materiality and "below" in materiality.lower():
        magnitude_assessment = (
            f"At {amount_str}, the amount is below the relevant materiality "
            f"threshold; if the qualitative factors are present, follow-up "
            f"may still be warranted on a qualitative basis."
        )
    else:
        magnitude_assessment = (
            f"At {amount_str}, the amount should be considered in light of "
            f"the engagement's materiality thresholds and the qualitative "
            f"factors present."
        )

    # ---- likelihood_assessment ----
    if qual_override or flag_count >= 3:
        likelihood_assessment = (
            "The co-occurrence of multiple risk indicators increases the "
            "need for follow-up, but this analysis does not determine "
            "intent or conclude fraud."
        )
    else:
        likelihood_assessment = (
            f"The presence of {flag_count} risk indicator"
            + ("s" if flag_count != 1 else "")
            + " presents a moderate need for additional review; this "
            "analysis does not determine intent or conclude fraud."
        )

    # ---- control_or_coso_consideration ----
    coso = _derive_coso(row)
    if len(coso) > 1:
        control_or_coso_consideration = (
            f"The pattern primarily implicates {coso[0]} and {coso[1]}, "
            f"warranting review of the related control design and operating "
            f"effectiveness."
        )
    else:
        control_or_coso_consideration = (
            f"The pattern primarily implicates {coso[0]}, warranting review "
            f"of the related control design and operating effectiveness."
        )

    # ---- recommended_follow_up ----
    recommended_follow_up = _build_followups(row)

    return {
        "risk_summary":                  risk_summary,
        "assertion_consideration":       assertion_consideration,
        "magnitude_assessment":          magnitude_assessment,
        "likelihood_assessment":         likelihood_assessment,
        "control_or_coso_consideration": control_or_coso_consideration,
        "recommended_follow_up":         recommended_follow_up,
        "disclaimer":                    REQUIRED_DISCLAIMER,
    }
