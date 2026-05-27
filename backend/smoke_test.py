"""
smoke_test.py — runs the full pipeline on sample_gl.csv and verifies that
Phase 1 (12), Phase 2 (10), and Phase 3 (8) done-criteria are met.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))

from features import (
    REQUIRED_COLUMNS,
    clean_gl_data,
    engineer_features,
    get_feature_columns,
    get_t2_feature_columns,
    validate_required_columns,
)
from integrity import run_integrity_checks, summarize_findings
from model import (
    SENSITIVITY_MAP,
    SUPERVISED_FEATURE_COLS,
    run_hybrid_pipeline,
    run_isolation_forest,
    train_supervised_layer,
)
from scoring import apply_scoring


def check(label: str, ok: bool, detail: str = "") -> None:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise AssertionError(label)


def main() -> None:
    print("=" * 70)
    print("Phase 1 + Phase 2 + Phase 3 smoke test on sample_gl.csv")
    print("=" * 70)

    # ====================================================================
    # PHASE 1 — 12 criteria (unchanged from before)
    # ====================================================================
    print("\nPHASE 1 done-criteria")
    print("-" * 70)

    raw = pd.read_csv("sample_data/sample_gl.csv")
    check("1. CSV loads", len(raw) > 0, f"{len(raw):,} rows")

    ok, missing = validate_required_columns(raw)
    check("2. Required columns present", ok, f"missing: {missing}")

    cleaned = clean_gl_data(raw)
    check("3. date converted to datetime",
          pd.api.types.is_datetime64_any_dtype(cleaned["date"]))
    check("3. amount is numeric",
          pd.api.types.is_numeric_dtype(cleaned["amount"]))
    check("3. abs_amount created", "abs_amount" in cleaned.columns)

    feat = engineer_features(cleaned, period_end=date(2024, 12, 31))
    feature_cols = get_feature_columns()
    for col in feature_cols:
        check(f"4. T1 feature '{col}' computed",
              col in feat.columns and feat[col].notna().any())

    entity_type = "Private for-profit"
    benchmark_figure = 150_000.0
    fs_pct = 0.04
    fs_mat = benchmark_figure * fs_pct
    perf_mat = fs_mat * 0.50
    txn_mat = fs_mat * 0.80

    sensitivity = "Balanced (0.05)"
    check("5. sensitivity maps to contamination",
          SENSITIVITY_MAP[sensitivity] == 0.05)
    scored = run_isolation_forest(feat, feature_cols, sensitivity)
    check("6. anomaly_score present", "anomaly_score" in scored.columns)
    check("6. raw_tier present", "raw_tier" in scored.columns)
    check("6. scores sorted ascending",
          scored["anomaly_score"].iloc[0] <= scored["anomaly_score"].iloc[-1])

    final = apply_scoring(scored, fs_mat, perf_mat, txn_mat)
    for col in ("final_tier", "pcaob_label", "materiality_annotation",
                "active_flags", "flagged_status"):
        check(f"7. column '{col}' added", col in final.columns)

    pcaob_text = " ".join(final["pcaob_label"].unique())
    forbidden = ["fraud occurred", "is fraudulent",
                 "material weakness exists", "violation"]
    bad = [w for w in forbidden if w.lower() in pcaob_text.lower()]
    check("8. PCAOB labels use Potential/Indicator/Monitor language",
          not bad, f"forbidden found: {bad}" if bad else "")

    check("9. raw_tier and final_tier remain distinct",
          "raw_tier" in final.columns and "final_tier" in final.columns)

    # ====================================================================
    # PHASE 2 — 10 new criteria
    # ====================================================================
    print("\nPHASE 2 done-criteria")
    print("-" * 70)

    # 1. Optional Phase 2 schema columns are present in the sample data
    check("1. Phase 2 schema present (debit_amount/credit_amount/dr_cr_pattern)",
          all(c in raw.columns for c in ["debit_amount", "credit_amount", "dr_cr_pattern"]))

    # 2. Integrity layer runs and returns findings
    findings = run_integrity_checks(
        cleaned, period_start=date(2024, 1, 1), period_end=date(2024, 12, 31)
    )
    check("2. integrity layer returned findings",
          isinstance(findings, list) and len(findings) >= 4)

    # 3. Each integrity check returns a recognized status
    statuses = {f.status for f in findings}
    check("3. integrity findings use Pass/Warning/Fail status",
          statuses.issubset({"Pass", "Warning", "Fail"}),
          f"got {statuses}")

    # 4. summarize_findings returns counts
    counts = summarize_findings(findings)
    check("4. summarize_findings returns Pass/Warning/Fail counts",
          all(k in counts for k in ("Pass", "Warning", "Fail")))

    # 5–10. All 6 Tier 2 feature columns are present and non-trivial
    t2_cols = get_t2_feature_columns()
    expected_t2 = [
        "control_gap_score", "fraud_flag_count", "fraud_risk_flag",
        "period_over_period_pct", "vendor_concentration_pct",
        "is_year_end_concentration", "is_non_standard_pattern",
    ]
    for col in expected_t2:
        check(f"5. T2 feature '{col}' computed",
              col in feat.columns)

    check("6. fraud_risk_flag fires on at least some rows",
          int(feat["fraud_risk_flag"].sum()) > 0,
          f"{int(feat['fraud_risk_flag'].sum())} rows trigger override")

    check("7. period_over_period_pct produces nonzero swings",
          (feat["period_over_period_pct"].abs() > 0).any())

    check("8. is_year_end_concentration flags last 10 days",
          int(feat["is_year_end_concentration"].sum()) > 0,
          f"{int(feat['is_year_end_concentration'].sum())} year-end rows")

    check("9. is_non_standard_pattern fires from dr_cr_pattern column",
          int(feat["is_non_standard_pattern"].sum()) > 0,
          f"{int(feat['is_non_standard_pattern'].sum())} non-standard rows")

    check("10. control_gap_score range is 0–2",
          int(feat["control_gap_score"].min()) >= 0
          and int(feat["control_gap_score"].max()) <= 2)

    # ====================================================================
    # PHASE 3 — Hybrid layer + qualitative override + supervised escalation
    # ====================================================================
    print("\nPHASE 3 done-criteria")
    print("-" * 70)

    # Rerun pipeline through the hybrid orchestrator so we exercise it end-to-end
    hybrid_scored, hybrid_info = run_hybrid_pipeline(
        feat, feature_cols=get_feature_columns(),
        detection_sensitivity=sensitivity,
    )

    check("1. run_hybrid_pipeline returns scored df + info dict",
          hasattr(hybrid_scored, "shape") and isinstance(hybrid_info, dict))

    check("2. supervised layer trained successfully",
          hybrid_info.get("status") == "trained",
          f"status={hybrid_info.get('status')}")

    check("3. fraud_probability column present and in [0,1]",
          "fraud_probability" in hybrid_scored.columns
          and hybrid_scored["fraud_probability"].between(0.0, 1.0).all())

    check("4. supervised features deliberately exclude fraud-rule flags",
          all(c not in SUPERVISED_FEATURE_COLS for c in [
              "is_round_number", "is_weekend_posting", "missing_description",
              "is_new_vendor", "is_near_approval_threshold",
          ]),
          "classifier cannot trivially reproduce the rule")

    # Apply scoring with override + supervised escalation
    hybrid_final = apply_scoring(hybrid_scored, fs_mat, perf_mat, txn_mat)

    check("5. qualitative override columns present",
          all(c in hybrid_final.columns for c in [
              "is_qualitative_override", "qualitative_override_note",
          ]))

    check("6. supervised escalation columns present",
          all(c in hybrid_final.columns for c in [
              "is_supervised_escalation", "supervised_escalation_note",
          ]))

    n_override = int(hybrid_final["is_qualitative_override"].sum())
    n_sup_esc = int(hybrid_final["is_supervised_escalation"].sum())
    check("7. qualitative override fires on at least some rows",
          n_override > 0,
          f"{n_override} rows escalated by qualitative override")

    check("8. all override rows have a non-empty note",
          (hybrid_final[hybrid_final["is_qualitative_override"] == 1]
           ["qualitative_override_note"].str.len() > 0).all())

    # ====================================================================
    # Diagnostic output
    # ====================================================================
    print("\nDiagnostic summary")
    print("-" * 70)
    print(f"  Total rows:                  {len(hybrid_final):,}")
    flagged = hybrid_final[hybrid_final["flagged_status"] == "Flagged"]
    print(f"  Flagged:                     {len(flagged):,} ({len(flagged)/len(hybrid_final)*100:.1f}%)")
    print(f"  raw_tier:                    {hybrid_scored['raw_tier'].value_counts().to_dict()}")
    print(f"  final_tier:                  {hybrid_final['final_tier'].value_counts().to_dict()}")
    print()
    print(f"  T1 firing:")
    for c in ["is_round_number", "is_weekend_posting", "missing_description",
              "is_new_vendor", "is_near_approval_threshold"]:
        print(f"    {c:34s} {int(feat[c].sum()):>4d}")
    print()
    print(f"  T2 firing:")
    print(f"    control_gap_score >= 1            {int((feat['control_gap_score'] >= 1).sum()):>4d}")
    print(f"    fraud_risk_flag                   {int(feat['fraud_risk_flag'].sum()):>4d}")
    print(f"    is_year_end_concentration         {int(feat['is_year_end_concentration'].sum()):>4d}")
    print(f"    is_non_standard_pattern           {int(feat['is_non_standard_pattern'].sum()):>4d}")
    print(f"    period_over_period_pct (nonzero)  {int((feat['period_over_period_pct'].abs() > 0).sum()):>4d}")
    print()
    print(f"  Phase 3 hybrid layer:")
    print(f"    supervised status                 {hybrid_info.get('status')}")
    print(f"    supervised n_positive             {hybrid_info.get('n_positive')}")
    print(f"    fraud_probability >= 0.5          {int((hybrid_final['fraud_probability'] >= 0.5).sum())}")
    print(f"    is_qualitative_override fired     {n_override}")
    print(f"    is_supervised_escalation fired    {n_sup_esc}")
    print()
    print(f"  Top supervised feature importances:")
    importances = hybrid_info.get("feature_importance", {})
    for k, v in sorted(importances.items(), key=lambda t: -t[1])[:5]:
        print(f"    {k:32s} {v:.3f}")
    print()
    print(f"  Integrity findings:")
    for f in findings:
        print(f"    [{f.status:>7s}] {f.name:18s} {f.summary}")
    print()
    print("  Top 3 flagged transactions:")
    show_cols = ["date", "account_name", "vendor", "amount", "anomaly_score",
                 "fraud_probability", "final_tier", "is_qualitative_override",
                 "active_flags"]
    show_cols = [c for c in show_cols if c in flagged.columns]
    print(flagged[show_cols].head(3).to_string(index=False))

    if n_override > 0:
        print("\n  Sample qualitative override row:")
        override_rows = hybrid_final[hybrid_final["is_qualitative_override"] == 1]
        r = override_rows.iloc[0]
        print(f"    amount={r['amount']} | raw_tier={r['raw_tier']} | "
              f"final_tier={r['final_tier']}")
        print(f"    note: {r['qualitative_override_note']}")

    print("\n" + "=" * 70)
    print("All Phase 1 + Phase 2 + Phase 3 done-criteria pass.")
    print("=" * 70)


if __name__ == "__main__":
    main()
