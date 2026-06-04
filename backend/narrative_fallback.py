"""
narrative_fallback.py — deterministic rule-based fallback narrative.

When the LLM call fails (API down, timeout, banned-phrase trip, empty
response), we still want the user to see *something* hedged and audit-safe
in place of an error. This module produces that fallback.

It does NOT use any LLM. It is pure template logic over the same observable
fields the LLM would have used, so the fallback narrative is grounded in
the same facts — just less stylistically polished.

The output of `build_fallback_risk_summary` is guaranteed to:
  * Be 1-2 sentences
  * Use hedged audit language
  * Never accuse a person, vendor, employee, or manager
  * Never conclude fraud
  * Always produce a string, even with minimal row data
"""
from __future__ import annotations


def _amount_str(row: dict) -> str:
    amt = row.get("amount")
    if isinstance(amt, (int, float)):
        return f"${amt:,.2f}"
    return "the transaction amount"


def _flags_clause(row: dict) -> str:
    """Turn the active_flags string into a natural-language clause."""
    flags = (row.get("active_flags") or "").strip()
    if not flags:
        return "the flagged indicators on this transaction"
    # active_flags is already a semicolon-separated list of human-readable
    # phrases like "Weekend posting; Missing description; New vendor".
    parts = [p.strip() for p in flags.split(";") if p.strip()]
    if not parts:
        return "the flagged indicators on this transaction"
    if len(parts) == 1:
        return parts[0].lower()
    if len(parts) == 2:
        return f"{parts[0].lower()} and {parts[1].lower()}"
    return ", ".join(p.lower() for p in parts[:-1]) + f", and {parts[-1].lower()}"


def build_fallback_risk_summary(row: dict) -> str:
    """Generate a deterministic 1-2 sentence risk summary from row facts.

    This is the safety net behind the LLM call. Always returns a non-empty
    string. Never accuses a person. Never concludes fraud.
    """
    flags_clause = _flags_clause(row)
    amount_str = _amount_str(row)
    materiality = (row.get("materiality_annotation") or "").strip()
    qual_override = int(row.get("is_qualitative_override", 0) or 0) == 1
    fraud_risk = int(row.get("fraud_risk_flag", 0) or 0) == 1
    final_tier = (row.get("final_tier") or "").strip()

    # Sentence 1: the observable pattern + a hedged claim about what
    # warrants follow-up.
    sentence_1 = (
        f"This {amount_str} transaction exhibits {flags_clause}, "
        f"which warrants follow-up regarding authorization, "
        f"supporting documentation, and the surrounding control activities."
    )

    # Sentence 2: optional context, only when something audit-meaningful
    # holds. Skip the second sentence if nothing additional is informative.
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

    # Materiality clause uses "and"/"but" conjunctions only if there's
    # already a preceding clause. If it's the only clause, drop the conjunction.
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
        # Always close with the disclaimer so even the minimal fallback
        # is audit-safe.
        sentence_2 = (
            "This analysis identifies risk indicators only and does not "
            "determine intent or fraud."
        )

    return f"{sentence_1} {sentence_2}"
