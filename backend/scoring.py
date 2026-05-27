"""
scoring.py — ML output + materiality → final_tier + PCAOB labels + supporting columns.

This is the audit-logic layer that distinguishes App 3 from a generic ML
anomaly detector. It takes model.py's output (statistical + supervised) and
applies materiality + qualitative override, producing what users see:

  * final_tier            — audit-adjusted tier after all rules
  * pcaob_label           — PCAOB-style label (Potential Material Weakness
                            Indicator / Potential Significant Deficiency /
                            Monitor — Below Escalation Threshold)
  * materiality_annotation — short human-readable explanation
  * active_flags          — semicolon-joined human-readable list of which
                            features fired for this row
  * flagged_status        — "Flagged" if final_tier in {High, Medium}, else
                            "Monitor"
  * is_qualitative_override — 1 if Phase 3 override fired, 0 otherwise
  * qualitative_override_note — human-readable explanation when it fires

Scoring stages (in order):
  1. apply_materiality_filter   — quantitative materiality (dollar amount)
  2. apply_qualitative_override — co-occurrence of 2+ fraud indicators
                                  (PCAOB AS 2401 / AS 5 qualitative materiality)
  3. apply_supervised_escalation — hybrid ML: high fraud_probability nudges
                                   tier up by one (caps at High)

Language rule: labels use "Potential," "Indicator," "Monitor" throughout.
The app identifies risk indicators — it never issues audit conclusions.
"""
from __future__ import annotations

import pandas as pd

# Tier ordering for downgrade arithmetic. Higher index = more severe.
TIER_ORDER: list[str] = ["Monitor", "Low", "Medium", "High"]

# PCAOB-style label mapping. Note: "Low" and "Monitor" share a label —
# both mean below escalation threshold.
PCAOB_LABELS: dict[str, str] = {
    "High":    "Potential Material Weakness Indicator",
    "Medium":  "Potential Significant Deficiency",
    "Low":     "Monitor — Below Escalation Threshold",
    "Monitor": "Monitor — Below Escalation Threshold",
}

# Translate binary feature columns to human-readable labels for active_flags.
FLAG_LABELS: dict[str, str] = {
    "is_round_number":            "Round number amount",
    "is_weekend_posting":         "Weekend posting",
    "missing_description":        "Missing description",
    "is_new_vendor":              "New vendor",
    "is_near_approval_threshold": "Near approval threshold",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def downgrade_tier(tier: str, steps: int = 1) -> str:
    """Move down `steps` positions in TIER_ORDER, clamped to Monitor."""
    if tier not in TIER_ORDER:
        return "Monitor"
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[max(0, idx - steps)]


def upgrade_tier(tier: str, steps: int = 1) -> str:
    """Move UP `steps` positions in TIER_ORDER, clamped to High.
    Mirror of downgrade_tier — used by qualitative override and supervised
    escalation in Phase 3."""
    if tier not in TIER_ORDER:
        return tier
    idx = TIER_ORDER.index(tier)
    return TIER_ORDER[min(len(TIER_ORDER) - 1, idx + steps)]


def apply_materiality_filter(
    row: pd.Series,
    performance_materiality: float,
    transaction_materiality: float,
) -> str:
    """Apply the materiality filter to one row's raw_tier.

    Logic per blueprint:
      amount >= transaction_materiality  → keep raw_tier
      amount >= performance_materiality  → downgrade one tier
      amount <  performance_materiality  → force Monitor
    """
    raw_tier = str(row.get("raw_tier", "Low"))
    amount = row.get("abs_amount", 0) or 0

    if amount >= transaction_materiality:
        return raw_tier
    if amount >= performance_materiality:
        return downgrade_tier(raw_tier, steps=1)
    return "Monitor"


def get_materiality_annotation(
    amount: float,
    performance_materiality: float,
    transaction_materiality: float,
) -> str:
    """One-line explanation of where this amount sits relative to thresholds."""
    if pd.isna(amount):
        amount = 0
    if amount >= transaction_materiality:
        return "Exceeds Transaction Materiality"
    if amount >= performance_materiality:
        return "Below Transaction Materiality"
    return "Below Performance Materiality"


def get_active_flags(row: pd.Series) -> str:
    """Build a semicolon-joined human-readable string of which features
    fired for this row. Used in the results table so users can see WHY
    a transaction was flagged, not just THAT it was."""
    flags: list[str] = []

    # Z-score: |z| >= 2.0 is the conventional "unusual" threshold.
    z = row.get("amount_zscore_by_account", 0)
    try:
        if abs(float(z)) >= 2.0:
            flags.append("Unusual amount for account")
    except (TypeError, ValueError):
        pass

    for col, label in FLAG_LABELS.items():
        try:
            if int(row.get(col, 0) or 0) == 1:
                flags.append(label)
        except (TypeError, ValueError):
            continue

    return "; ".join(flags) if flags else "Statistical anomaly only"


# ---------------------------------------------------------------------------
# Phase 3 — Qualitative override + supervised escalation
# ---------------------------------------------------------------------------

# Threshold for the supervised layer's fraud_probability to be considered
# strong enough to nudge the tier up by one. 0.50 is a reasonable starting
# value for a calibrated classifier; can be tuned per detection sensitivity.
SUPERVISED_ESCALATION_THRESHOLD: float = 0.50


def apply_qualitative_override(row: pd.Series) -> tuple[str, int, str]:
    """Qualitative materiality override (PCAOB AS 2401 / AS 5 severity).

    When >= 2 fraud indicators fire on a single transaction (fraud_risk_flag),
    the co-occurrence signals possible deliberate concealment / control
    breakdown. Per qualitative materiality, such items matter regardless of
    dollar amount, so we cancel the materiality discount and escalate one
    tier ABOVE the raw ML tier.

    Returns (resolved_final_tier, is_override, override_note):
      * If override does not fire → existing final_tier unchanged, 0, "".
      * If it fires AND raises the tier → escalated tier, 1, explanation.
      * If it would fire but the tier was already >= the escalation → no
        annotation, 0, "" (avoids misleading badges).

    Escalation rule: one tier UP from raw_tier, NOT from final_tier — this
    restores the ML's severity assessment and undoes any materiality
    downgrade. For high-raw-tier items already at the ceiling, holds at High.
    """
    final_tier = str(row.get("final_tier", "Monitor"))
    fraud_risk = int(row.get("fraud_risk_flag", 0) or 0)
    if fraud_risk != 1:
        return final_tier, 0, ""

    raw_tier = str(row.get("raw_tier", "Low"))
    escalated = upgrade_tier(raw_tier, steps=1)

    # Only count as override if it actually raises the tier above what
    # the materiality filter decided.
    if TIER_ORDER.index(escalated) <= TIER_ORDER.index(final_tier):
        return final_tier, 0, ""

    fraud_count = int(row.get("fraud_flag_count", 0) or 0)
    note = (
        f"Escalated to {escalated}: {fraud_count} fraud indicators co-occur "
        f"(qualitative materiality, PCAOB AS 2401). Raw ML tier {raw_tier}; "
        f"materiality alone would assign {final_tier}."
    )
    return escalated, 1, note


def apply_supervised_escalation(
    row: pd.Series,
    threshold: float = SUPERVISED_ESCALATION_THRESHOLD,
) -> tuple[str, int, str]:
    """Phase 3 supervised hybrid escalation.

    The supervised classifier (model.train_supervised_layer) emits a
    fraud_probability per row. When it exceeds `threshold` AND the current
    tier doesn't already reflect that risk, escalate one tier up.

    This is intentionally GENTLER than the qualitative override:
      * Qualitative override: rule co-occurrence → strong, multi-tier-restoring escalation
      * Supervised escalation: ML similarity to flagged rows → one-tier nudge

    Returns (resolved_final_tier, is_supervised_escalation, note).
    """
    final_tier = str(row.get("final_tier", "Monitor"))
    try:
        fp = float(row.get("fraud_probability", 0.0) or 0.0)
    except (TypeError, ValueError):
        fp = 0.0

    if fp < threshold:
        return final_tier, 0, ""

    # Don't compound on top of an already-fired qualitative override.
    if int(row.get("is_qualitative_override", 0) or 0) == 1:
        return final_tier, 0, ""

    escalated = upgrade_tier(final_tier, steps=1)
    if TIER_ORDER.index(escalated) <= TIER_ORDER.index(final_tier):
        return final_tier, 0, ""

    note = (
        f"Escalated to {escalated}: supervised classifier P(fraud)={fp:.2f} "
        f">= {threshold:.2f}. Pattern resembles rule-flagged transactions "
        f"in continuous features."
    )
    return escalated, 1, note


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_scoring(
    df: pd.DataFrame,
    fs_materiality: float,
    performance_materiality: float,
    transaction_materiality: float,
) -> pd.DataFrame:
    """Apply the audit-logic layer to a dataframe that has model.py output
    (anomaly_score, raw_tier, and optionally fraud_probability).

    Adds the columns the API/UI consume:
      final_tier, pcaob_label, materiality_annotation, active_flags,
      flagged_status, is_qualitative_override, qualitative_override_note,
      is_supervised_escalation, supervised_escalation_note.

    `fs_materiality` is accepted for API symmetry / future use; the filter
    logic uses performance + transaction thresholds.
    """
    del fs_materiality
    df = df.copy()

    # Step 1: quantitative materiality filter
    df["final_tier"] = df.apply(
        lambda row: apply_materiality_filter(
            row, performance_materiality, transaction_materiality
        ),
        axis=1,
    )

    # Step 2: qualitative override (Phase 3) — may escalate final_tier
    qual_results = df.apply(apply_qualitative_override, axis=1)
    df["final_tier"]                = qual_results.apply(lambda t: t[0])
    df["is_qualitative_override"]   = qual_results.apply(lambda t: t[1])
    df["qualitative_override_note"] = qual_results.apply(lambda t: t[2])

    # Step 3: supervised hybrid escalation (Phase 3) — gentler ML-based nudge
    if "fraud_probability" in df.columns:
        sup_results = df.apply(apply_supervised_escalation, axis=1)
        df["final_tier"]                  = sup_results.apply(lambda t: t[0])
        df["is_supervised_escalation"]    = sup_results.apply(lambda t: t[1])
        df["supervised_escalation_note"]  = sup_results.apply(lambda t: t[2])
    else:
        df["is_supervised_escalation"]   = 0
        df["supervised_escalation_note"] = ""

    # Step 4: derived columns reflect the post-all-escalation tier
    df["pcaob_label"] = df["final_tier"].map(PCAOB_LABELS).fillna(
        "Monitor — Below Escalation Threshold"
    )
    df["materiality_annotation"] = df["abs_amount"].apply(
        lambda amt: get_materiality_annotation(
            amt, performance_materiality, transaction_materiality
        )
    )
    df["active_flags"] = df.apply(get_active_flags, axis=1)
    df["flagged_status"] = df["final_tier"].apply(
        lambda x: "Flagged" if x in ("High", "Medium") else "Monitor"
    )

    return df
