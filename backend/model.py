"""
model.py — feature matrix → anomaly_score + raw_tier + fraud_probability.

Phase 3: hybrid two-track ML layer.

  TRACK 1 — Unsupervised (Isolation Forest):
    * anomaly_score (float) — IF decision_function. Lower = more anomalous.
    * raw_tier (High/Medium/Low) — bucketed anomaly score.
    Catches statistically loud + structured fraud without needing any labels.
    Works on a raw GL upload from any client. This is App 3's primary detector.

  TRACK 2 — Supervised (weak-label Random Forest) [Phase 3 addition]:
    * fraud_probability (float, 0–1) — classifier confidence that this
      transaction looks like the rule-based fraud pattern.
    Trained per-upload on weak labels derived from features.fraud_risk_flag.
    Importantly: the classifier's training features deliberately EXCLUDE the
    five fraud-indicator flags themselves (which define the weak label).
    Instead it trains on continuous/structural features (amount, z-score,
    period-over-period, vendor concentration, etc.) — so it can only
    *correlate* with the rule, not trivially reproduce it.
    Aimed at the "subtle fraud" gap that pure IF misses (~67% recall in the
    simulation study); model comparison findings documented separately.

Both `raw_tier` (statistical) and `final_tier` (audit-adjusted) remain
distinct columns. The qualitative override in scoring.py uses BOTH tracks'
output to decide escalation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Detection sensitivity → Isolation Forest contamination parameter.
# In audit terms, this is the auditor-controlled Detection Risk dial.
SENSITIVITY_MAP: dict[str, float] = {
    "Conservative (0.03)": 0.03,
    "Balanced (0.05)":     0.05,
    "Aggressive (0.10)":   0.10,
}

# Default starting bin edges for raw_tier. Adjust after testing with real
# sample GL data if the distribution skews too far in either direction.
RAW_TIER_BINS: list[float] = [-np.inf, -0.15, -0.05, np.inf]
RAW_TIER_LABELS: list[str] = ["High", "Medium", "Low"]


def run_isolation_forest(
    df: pd.DataFrame,
    feature_cols: list[str],
    detection_sensitivity: str,
    random_state: int = 42,
) -> pd.DataFrame:
    """Fit IsolationForest on df[feature_cols], add anomaly_score and raw_tier.

    Args:
        df: DataFrame already cleaned and feature-engineered.
        feature_cols: Column names to use as the feature matrix.
        detection_sensitivity: One of the keys in SENSITIVITY_MAP.
        random_state: For reproducible scores.

    Returns:
        DataFrame with `anomaly_score`, `anomaly_label`, and `raw_tier`
        columns added. Sorted ascending by anomaly_score so the most
        anomalous rows appear at the top.
    """
    if detection_sensitivity not in SENSITIVITY_MAP:
        raise ValueError(
            f"Unknown detection_sensitivity {detection_sensitivity!r}. "
            f"Expected one of {list(SENSITIVITY_MAP)}."
        )
    contamination = SENSITIVITY_MAP[detection_sensitivity]

    df = df.copy()

    # Feature matrix — fillna(0) is safe because all 6 features are either
    # binary flags or z-scores (where 0 = average).
    X = df[feature_cols].fillna(0).values

    # StandardScaler is non-negotiable — without it the (dollar-scale)
    # z-score feature dominates the binary flags in the tree splits.
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=random_state,
    )
    model.fit(X_scaled)

    # decision_function: continuous score. Lower = more anomalous.
    df["anomaly_score"] = model.decision_function(X_scaled)
    # predict: -1 anomaly, 1 normal. Useful for debugging and Tier-2 flags.
    df["anomaly_label"] = model.predict(X_scaled)

    # Bucket the continuous score into a coarse raw tier.
    df["raw_tier"] = pd.cut(
        df["anomaly_score"],
        bins=RAW_TIER_BINS,
        labels=RAW_TIER_LABELS,
    ).astype(str)

    # Sort ascending so the most-anomalous rows are first.
    df = df.sort_values("anomaly_score", ascending=True).reset_index(drop=True)

    return df


# ===========================================================================
# Phase 3 — Supervised hybrid layer (weak-label Random Forest)
# ===========================================================================

# Features the supervised classifier trains on. Deliberately excludes the
# 5 fraud-indicator FLAG columns (is_round_number, is_weekend_posting,
# missing_description, is_new_vendor, is_near_approval_threshold), because
# those define the weak label fraud_risk_flag — if we included them, the
# classifier would trivially reproduce the rule and add no information.
#
# Instead we use continuous + structural features that *correlate* with the
# rule firing without uniquely determining it. The classifier learns "what
# does a row that LOOKS like a flagged row look like in the continuous
# features?" and can therefore flag rows the rule itself missed.
SUPERVISED_FEATURE_COLS: list[str] = [
    "abs_amount",                # raw dollar magnitude
    "amount_zscore_by_account",  # account-level outlier signal
    "period_over_period_pct",    # T2 — temporal anomaly
    "vendor_concentration_pct",  # T2 — vendor distribution
    "is_year_end_concentration", # T2 — timing irregularity
    "is_non_standard_pattern",   # T2 — DR/CR pairing irregularity
    "vendor_txn_count",          # raw vendor history (continuous)
]

# Minimum number of positive (fraud_risk_flag=1) examples needed to train.
# Below this, the classifier can't learn anything meaningful — we abstain
# and return fraud_probability = 0 for all rows, with a status note.
MIN_POSITIVE_EXAMPLES: int = 5


def train_supervised_layer(
    df: pd.DataFrame,
    label_col: str = "fraud_risk_flag",
    feature_cols: list[str] | None = None,
    random_state: int = 42,
) -> tuple[RandomForestClassifier | None, StandardScaler | None, dict]:
    """Train a weak-label Random Forest classifier in-process on the uploaded
    dataframe. Returns (model, scaler, info_dict).

    Per the model comparison study, this layer aims at the 'subtle fraud' gap
    where pure unsupervised detection underperforms. The 'weak label' comes
    from the existing rule-based fraud_risk_flag in features.py.

    Returns (None, None, info) when the data has insufficient positive
    examples to train — caller should handle by assigning fraud_probability=0.

    Methodology note: this trains and predicts on the SAME dataframe (no
    held-out split), because at inference time there's only one client's
    upload to score. The honest interpretation is "the classifier identifies
    transactions similar to the rule-flagged ones in continuous-feature
    space" — it is a smoothing of the rule, not an independent validator.
    """
    feature_cols = feature_cols or SUPERVISED_FEATURE_COLS
    info: dict = {
        "status": "trained",
        "feature_cols": list(feature_cols),
        "label_col": label_col,
    }

    # Check label availability
    if label_col not in df.columns:
        info["status"] = "skipped_no_label_column"
        info["reason"] = f"{label_col!r} not in dataframe"
        return None, None, info

    # Check feature availability — drop any features that don't exist
    available = [c for c in feature_cols if c in df.columns]
    if not available:
        info["status"] = "skipped_no_features"
        info["reason"] = "none of the supervised feature columns are present"
        return None, None, info
    info["feature_cols"] = available

    y = df[label_col].fillna(0).astype(int).values
    n_pos = int(y.sum())
    n_neg = int((y == 0).sum())
    info["n_positive"] = n_pos
    info["n_negative"] = n_neg

    if n_pos < MIN_POSITIVE_EXAMPLES:
        info["status"] = "skipped_insufficient_positives"
        info["reason"] = (
            f"only {n_pos} positive examples (need >= {MIN_POSITIVE_EXAMPLES})"
        )
        return None, None, info

    X = df[available].fillna(0).values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = RandomForestClassifier(
        n_estimators=200,
        class_weight="balanced",   # crucial: weak-label data is highly imbalanced
        max_depth=8,               # restrain capacity to avoid memorizing the rule
        min_samples_leaf=10,       # smooth out high-variance leaves
        random_state=random_state,
        n_jobs=-1,
    )
    clf.fit(X_scaled, y)

    # Feature importances for transparency / demo narration
    info["feature_importance"] = {
        feat: float(imp)
        for feat, imp in zip(available, clf.feature_importances_)
    }
    return clf, scaler, info


def predict_fraud_probability(
    df: pd.DataFrame,
    clf: RandomForestClassifier | None,
    scaler: StandardScaler | None,
    feature_cols: list[str],
) -> np.ndarray:
    """Return per-row P(fraud) from the supervised layer. If clf is None
    (insufficient training data), returns all-zeros."""
    if clf is None or scaler is None:
        return np.zeros(len(df))
    available = [c for c in feature_cols if c in df.columns]
    X = df[available].fillna(0).values
    X_scaled = scaler.transform(X)
    return clf.predict_proba(X_scaled)[:, 1]


def run_hybrid_pipeline(
    df: pd.DataFrame,
    feature_cols: list[str],
    detection_sensitivity: str,
    random_state: int = 42,
) -> tuple[pd.DataFrame, dict]:
    """Phase 3 orchestrator: run unsupervised + supervised on the same df.

    Returns (scored_df, hybrid_info) where hybrid_info contains
    metadata about the supervised layer (status, feature importance, etc.)
    so the API can surface it.

    The returned df has:
      * anomaly_score, anomaly_label, raw_tier  ← from IF (track 1)
      * fraud_probability                       ← from RF (track 2)
    """
    # Track 1 — unsupervised (sorts the df ascending by anomaly_score)
    df_scored = run_isolation_forest(
        df, feature_cols=feature_cols,
        detection_sensitivity=detection_sensitivity,
        random_state=random_state,
    )

    # Track 2 — supervised (weak-label)
    clf, scaler, info = train_supervised_layer(
        df_scored, random_state=random_state,
    )
    df_scored["fraud_probability"] = predict_fraud_probability(
        df_scored, clf, scaler, info.get("feature_cols", SUPERVISED_FEATURE_COLS),
    )
    return df_scored, info
