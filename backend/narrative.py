"""
narrative.py — GPT narrative generation orchestrator (Phase 4a).

Public surface:
  * sort_rows_for_narrative(rows) -> list[dict]
      Apply the demo-relevance sort (final_tier=High first, qualitative
      override first, fraud_risk_flag first, anomaly_score ascending,
      amount descending) so the user's top-N narratives are the most
      audit-meaningful, not random.

  * generate_risk_summary(row, entity_context) -> dict
      Single-row narrative call. Always returns
      {"risk_summary": str, "narrative_status": "GPT" | "Fallback"}.
      Never raises — any error (API down, timeout, banned-phrase output,
      empty completion) is caught and converted to fallback.

  * generate_narratives_for_rows(rows, entity_context, top_n) -> dict
      The endpoint-level helper. Sorts, clips to top_n (max 20), generates
      a risk_summary per selected row, returns a dict keyed by the row's
      position in the sorted output.

Cost discipline: the OpenAI call is configured for ~80 tokens max output
with temperature 0.3. Each call costs roughly $0.0001 on gpt-4o-mini.
Top-10 generation = roughly $0.001.

Failure handling: a failed call is logged to stderr (without leaking the
API key) and the row falls back to narrative_fallback. The app never
crashes because of LLM availability.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from prompts import (
    BANNED_PHRASES,
    RISK_SUMMARY_SYSTEM_PROMPT,
    build_user_prompt,
)
from narrative_fallback import build_fallback_risk_summary

logger = logging.getLogger("app3.narrative")

# Maximum top_n cap. Phase 4 spec sets this at 20.
MAX_TOP_N: int = 20
DEFAULT_TOP_N: int = 10

# OpenAI call settings — kept here so they're easy to tune without
# digging through the function body.
OPENAI_MODEL: str = "gpt-4o-mini"
OPENAI_MAX_TOKENS: int = 120     # 1-2 sentences fits comfortably under 80; 120 is headroom
OPENAI_TEMPERATURE: float = 0.3  # low but non-zero — some natural variation, mostly steered

_TIER_RANK = {"High": 0, "Medium": 1, "Low": 2, "Monitor": 3}


def sort_rows_for_narrative(rows: list[dict]) -> list[dict]:
    """Sort rows in demo-relevance order:
      1. final_tier ranked High > Medium > Low > Monitor
      2. is_qualitative_override == 1 first
      3. fraud_risk_flag == 1 first
      4. anomaly_score ascending (more anomalous first; IF scores are negative)
      5. amount descending (larger first)
    """
    def key(r: dict) -> tuple:
        return (
            _TIER_RANK.get(str(r.get("final_tier", "")), 99),
            0 if int(r.get("is_qualitative_override", 0) or 0) == 1 else 1,
            0 if int(r.get("fraud_risk_flag", 0) or 0) == 1 else 1,
            float(r.get("anomaly_score", 0.0) or 0.0),
            -float(r.get("amount", 0.0) or 0.0),
        )
    return sorted(rows, key=key)


def _contains_banned_phrase(text: str) -> tuple[bool, str]:
    """Return (True, matched_phrase) if text contains a banned phrase."""
    lower = text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower:
            return True, phrase
    return False, ""


def _get_openai_client():
    """Lazy import + construct so the rest of the module imports cleanly
    in environments without the openai SDK (smoke tests, doc builds)."""
    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(
            "openai package not installed — install with `pip install openai`"
        ) from e

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set — narrative endpoint requires it"
        )
    return OpenAI(api_key=api_key)


def _call_openai_risk_summary(row: dict, entity_context: dict) -> str:
    """Make the actual OpenAI call. Returns the model's text, or raises.

    All exceptions propagate to generate_risk_summary which converts them
    to a fallback narrative.
    """
    client = _get_openai_client()
    user_prompt = build_user_prompt(row, entity_context)

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": RISK_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=OPENAI_MAX_TOKENS,
        temperature=OPENAI_TEMPERATURE,
    )

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("OpenAI returned an empty response")

    bad, matched = _contains_banned_phrase(text)
    if bad:
        raise ValueError(f"OpenAI output contained banned phrase: {matched!r}")

    return text


def generate_risk_summary(row: dict, entity_context: dict) -> dict[str, str]:
    """Generate one risk_summary for one row.

    Returns:
      {"risk_summary": "...", "narrative_status": "GPT" | "Fallback"}

    Never raises. Any exception from the OpenAI call (network, auth,
    rate limit, validation) is caught and converted to a fallback summary.
    """
    try:
        text = _call_openai_risk_summary(row, entity_context)
        return {"risk_summary": text, "narrative_status": "GPT"}
    except Exception as e:
        # Log but do not surface the API key or full exception chain to the
        # caller. The user sees only that the fallback was used.
        logger.warning(
            "narrative generation fell back for row vendor=%r: %s",
            row.get("vendor"), type(e).__name__,
        )
        return {
            "risk_summary": build_fallback_risk_summary(row),
            "narrative_status": "Fallback",
        }


def generate_narratives_for_rows(
    rows: list[dict],
    entity_context: dict,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Sort, clip to top_n, and generate narratives for each selected row.

    Returns:
      {
        "narratives":         {position: {"risk_summary": ..., "narrative_status": ...}},
        "selected_row_keys":  [list of (date, vendor, amount) tuples to help
                              the frontend identify which rows to expand],
        "top_n_used":         int,
        "n_gpt":              int,
        "n_fallback":         int,
      }

    The frontend uses `selected_row_keys` to map narratives back to the
    correct table rows (since the backend re-sorts the input).
    """
    top_n = max(1, min(int(top_n), MAX_TOP_N))
    sorted_rows = sort_rows_for_narrative(rows)
    selected = sorted_rows[:top_n]

    narratives: dict[str, dict[str, str]] = {}
    selected_keys: list[dict[str, Any]] = []
    n_gpt = 0
    n_fallback = 0

    for i, row in enumerate(selected):
        result = generate_risk_summary(row, entity_context)
        narratives[str(i)] = result
        if result["narrative_status"] == "GPT":
            n_gpt += 1
        else:
            n_fallback += 1
        # Keys the frontend can match against to find the right table row
        selected_keys.append({
            "position": i,
            "date": row.get("date"),
            "account_name": row.get("account_name"),
            "vendor": row.get("vendor"),
            "amount": row.get("amount"),
        })

    return {
        "narratives": narratives,
        "selected_row_keys": selected_keys,
        "top_n_used": top_n,
        "n_gpt": n_gpt,
        "n_fallback": n_fallback,
    }
