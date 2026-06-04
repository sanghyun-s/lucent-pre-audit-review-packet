"""
narrative.py — GPT narrative generation orchestrator.

Phase 4a (shipped Jun 3, 2026): single risk_summary per row.

Phase 4b (this version): extends to a full 7-field JSON memo per row
(`generate_full_memo`) with strict validator gating and deterministic
fallback. The orchestrator-level helper `generate_narratives_for_rows`
now returns 7 fields per narrative instead of 1, but otherwise preserves
the Phase 4a response shape (same dict keys, same status semantics).

Phase 4b fix (this revision): the orchestrator now runs per-row LLM calls
concurrently via ThreadPoolExecutor instead of sequentially. Top-N
generation goes from ~4 seconds × N (serial) to ~max(per-call latency)
(parallel) — roughly 4-5 seconds total regardless of N, well under the
default Next.js dev proxy timeout.

Public surface:
  * sort_rows_for_narrative(rows) -> list[dict]
      Demo-relevance sort (unchanged from Phase 4a).

  * generate_risk_summary(row, entity_context) -> dict          [Phase 4a]
      Returns {"risk_summary", "narrative_status"}. Back-compat only.

  * generate_full_memo(row, entity_context) -> dict             [Phase 4b]
      Returns the 7 memo fields plus "narrative_status". Always returns
      a validator-passing memo (LLM if it passes validation, fallback
      otherwise). Never raises.

  * generate_narratives_for_rows(rows, entity_context, top_n) -> dict
      Endpoint-level helper. Phase 4b: each narrative entry now contains
      the full memo (7 fields + status), not just a summary. Calls run
      concurrently (see "Phase 4b fix" note above).

Cost discipline: gpt-4o-mini in JSON mode, temperature 0.3, max_tokens
700 (full memo needs more output than the 1-2 sentence summary). Top-N
generation costs the same whether serial or concurrent — concurrency
only reduces wall-clock time, not API spend. Top-10 ≈ $0.003.

Failure handling: validator rejection, network errors, empty responses,
banned-phrase trips, and name-leakage all route through the deterministic
fallback. The fallback is provably validator-passing. Each row's failure
is isolated — one row falling back never affects another row.
"""
from __future__ import annotations

import json
import logging
import os
import concurrent.futures
from typing import Any

from prompts import (
    BANNED_PHRASES,
    FULL_MEMO_SYSTEM_PROMPT,
    REQUIRED_MEMO_FIELDS,
    RISK_SUMMARY_SYSTEM_PROMPT,
    build_user_prompt,
    build_user_prompt_for_full_memo,
)
from narrative_fallback import (
    build_fallback_full_memo,
    build_fallback_risk_summary,
)
from narrative_validator import validate_memo

logger = logging.getLogger("app3.narrative")

# Maximum top_n cap. Phase 4 spec sets this at 20.
MAX_TOP_N: int = 20
DEFAULT_TOP_N: int = 5

# OpenAI call settings.
OPENAI_MODEL: str = "gpt-4o-mini"
OPENAI_TEMPERATURE: float = 0.3

# Phase 4a path (summary only): kept lean.
OPENAI_MAX_TOKENS_SUMMARY: int = 120

# Phase 4b path (full memo): 7 fields with 1-2 sentences each plus the
# follow-up list. ~700 tokens is comfortable headroom; observed actual
# usage during testing is ~350-450 output tokens.
OPENAI_MAX_TOKENS_MEMO: int = 700

# Concurrency pool size for orchestrator. Set to MAX_TOP_N so even a
# slider-maxed request runs every row in parallel. OpenAI's gpt-4o-mini
# rate limit is 500+ rpm on most tiers; 20 concurrent requests is far
# below that ceiling.
_NARRATIVE_POOL_SIZE: int = MAX_TOP_N

_TIER_RANK = {"High": 0, "Medium": 1, "Low": 2, "Monitor": 3}


# ---------------------------------------------------------------------------
# Sort + helpers (unchanged from Phase 4a)
# ---------------------------------------------------------------------------

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
    in environments without the openai SDK."""
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


# ---------------------------------------------------------------------------
# Phase 4a — risk_summary path (kept for back-compat)
# ---------------------------------------------------------------------------

def _call_openai_risk_summary(row: dict, entity_context: dict) -> str:
    """Phase 4a OpenAI call — returns plain-text 1-2 sentence summary."""
    client = _get_openai_client()
    user_prompt = build_user_prompt(row, entity_context)

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": RISK_SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=OPENAI_MAX_TOKENS_SUMMARY,
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
    """Phase 4a: generate one risk_summary for one row.

    Returns:
      {"risk_summary": "...", "narrative_status": "GPT" | "Fallback"}

    Kept for back-compat with Phase 4a callers (tests, CLI tools). The
    HTTP endpoint now calls `generate_full_memo` instead.
    """
    try:
        text = _call_openai_risk_summary(row, entity_context)
        return {"risk_summary": text, "narrative_status": "GPT"}
    except Exception as e:
        logger.warning(
            "risk_summary generation fell back for row vendor=%r: %s",
            row.get("vendor"), type(e).__name__,
        )
        return {
            "risk_summary": build_fallback_risk_summary(row),
            "narrative_status": "Fallback",
        }


# ---------------------------------------------------------------------------
# Phase 4b — full 7-field memo path
# ---------------------------------------------------------------------------

def _call_openai_full_memo(row: dict, entity_context: dict) -> dict:
    """Phase 4b OpenAI call — returns a parsed JSON dict.

    The response_format={"type": "json_object"} hint instructs the model
    to emit syntactically valid JSON. We still parse defensively and let
    parse errors / validator errors propagate to the orchestrator's
    except block.
    """
    client = _get_openai_client()
    user_prompt = build_user_prompt_for_full_memo(row, entity_context)

    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": FULL_MEMO_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=OPENAI_MAX_TOKENS_MEMO,
        temperature=OPENAI_TEMPERATURE,
        response_format={"type": "json_object"},
    )

    text = (resp.choices[0].message.content or "").strip()
    if not text:
        raise ValueError("OpenAI returned an empty response")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"OpenAI output is not valid JSON: {e}") from e

    # The validator does the heavy lifting (schema, fields, lengths,
    # banned-phrase scan, name-leakage scan, verbatim disclaimer). Any
    # rejection becomes an exception so the caller falls back.
    is_valid, reason = validate_memo(parsed)
    if not is_valid:
        raise ValueError(f"validator rejected memo: {reason}")

    return parsed


def generate_full_memo(row: dict, entity_context: dict) -> dict[str, Any]:
    """Phase 4b: generate a full 7-field memo for one row.

    Returns a dict with the 7 memo fields plus "narrative_status" set to
    either "GPT" (LLM output passed validation) or "Fallback" (any error,
    including validator rejection — used the deterministic fallback).

    Never raises. The returned dict is guaranteed to have all 7 fields
    plus narrative_status. The 7 fields themselves are guaranteed to pass
    `validate_memo` (because either the LLM passed it directly, or the
    fallback is constructed to pass it).
    """
    try:
        memo = _call_openai_full_memo(row, entity_context)
        memo["narrative_status"] = "GPT"
        return memo
    except Exception as e:
        logger.warning(
            "full_memo generation fell back for row vendor=%r: %s: %s",
            row.get("vendor"), type(e).__name__, str(e)[:120],
        )
        memo = build_fallback_full_memo(row)
        memo["narrative_status"] = "Fallback"
        return memo


# ---------------------------------------------------------------------------
# Endpoint-level orchestrator — concurrent
# ---------------------------------------------------------------------------

def generate_narratives_for_rows(
    rows: list[dict],
    entity_context: dict,
    top_n: int = DEFAULT_TOP_N,
) -> dict[str, Any]:
    """Sort, clip to top_n, and generate a full 7-field memo per selected row.

    Returns:
      {
        "narratives":         {position: {7 memo fields + narrative_status}},
        "selected_row_keys":  [{position, date, account_name, vendor, amount}, ...],
        "top_n_used":         int,
        "n_gpt":              int,
        "n_fallback":         int,
      }

    Implementation note: per-row LLM calls execute in parallel via a
    ThreadPoolExecutor. Each call is I/O-bound (waiting on OpenAI's
    network response), so threads work efficiently despite Python's GIL.
    Wall-clock time for top-N ≈ max single-call latency, not sum.

    The `narratives` dict and `selected_row_keys` list are keyed/indexed
    by the row's position in the demo-relevance sort, NOT by the order
    LLM calls complete. This keeps the frontend's row-key matching stable
    regardless of which call finishes first.
    """
    top_n = max(1, min(int(top_n), MAX_TOP_N))
    sorted_rows = sort_rows_for_narrative(rows)
    selected = sorted_rows[:top_n]

    # Build selected_row_keys up-front in sorted order — these don't need
    # the LLM call to happen first, so we can construct them deterministically
    # while the concurrent calls are in flight.
    selected_keys: list[dict[str, Any]] = [
        {
            "position": i,
            "date": row.get("date"),
            "account_name": row.get("account_name"),
            "vendor": row.get("vendor"),
            "amount": row.get("amount"),
        }
        for i, row in enumerate(selected)
    ]

    narratives: dict[str, dict[str, Any]] = {}

    # Submit all LLM calls concurrently. ThreadPoolExecutor handles the
    # parallelism; generate_full_memo's internal try/except still catches
    # all errors per row so one row's failure never affects another.
    with concurrent.futures.ThreadPoolExecutor(max_workers=_NARRATIVE_POOL_SIZE) as pool:
        future_to_position: dict[concurrent.futures.Future, int] = {
            pool.submit(generate_full_memo, row, entity_context): i
            for i, row in enumerate(selected)
        }
        for future in concurrent.futures.as_completed(future_to_position):
            i = future_to_position[future]
            # future.result() re-raises only if generate_full_memo itself
            # raised, which it never does (it always returns a memo dict
            # via its own try/except). Belt-and-suspenders: if some future
            # bug changes that, we catch it here and emit a fallback so
            # the endpoint still returns a complete response.
            try:
                memo = future.result()
            except Exception as e:
                logger.error(
                    "unexpected exception escaped generate_full_memo for position %d: %s",
                    i, type(e).__name__,
                )
                memo = build_fallback_full_memo(selected[i])
                memo["narrative_status"] = "Fallback"
            narratives[str(i)] = memo

    # Tally after all results land. Walking the narratives dict in
    # position order keeps the final summary deterministic.
    n_gpt = sum(
        1 for k in sorted(narratives, key=int)
        if narratives[k].get("narrative_status") == "GPT"
    )
    n_fallback = len(narratives) - n_gpt

    return {
        "narratives": narratives,
        "selected_row_keys": selected_keys,
        "top_n_used": top_n,
        "n_gpt": n_gpt,
        "n_fallback": n_fallback,
    }
