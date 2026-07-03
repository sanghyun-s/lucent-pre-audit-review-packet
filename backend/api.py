"""
api.py — FastAPI server for the AI Audit Risk Analyzer.

Wraps the existing Phase 2 pipeline (features.py, model.py, scoring.py,
integrity.py) as a single HTTP endpoint that a Next.js (or any) frontend
can POST against.

Endpoint:
  POST /api/analyze   (multipart/form-data)
    Form fields:
      csv: UploadFile          — the GL CSV
      entity_type: str         — Private for-profit | Public company | Non-profit | Fund
      benchmark_figure: float  — FS materiality base
      detection_sensitivity: str — Conservative (0.03) | Balanced (0.05) | Aggressive (0.10)
      period_start: str (YYYY-MM-DD)
      period_end:   str (YYYY-MM-DD)
    Returns:
      AnalyzeResponse JSON

  POST /api/narratives  (application/json)  — Phase 4a + 4b
    Body:
      rows: list of flagged-row dicts (from a prior /api/analyze response)
      entity_context: {entity_type, period_start, period_end}
      top_n: int (1-20, default 10)
    Returns (Phase 4b shape):
      {narratives: {position: {
          risk_summary,
          assertion_consideration,
          magnitude_assessment,
          likelihood_assessment,
          control_or_coso_consideration,
          recommended_follow_up,  (list of 3-5 strings)
          disclaimer,
          narrative_status,       ("GPT" | "Fallback")
        }},
       selected_row_keys: [...], top_n_used, n_gpt, n_fallback}

  GET /api/healthz  — liveness probe

Run locally:  uvicorn api:app --reload --port 8000
"""
from __future__ import annotations

import io
import math
import os
from datetime import date, datetime
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Load .env early so any module that reads OPENAI_API_KEY (or other env
# vars) sees them. dotenv is silent if .env is missing — appropriate for
# production where env vars come from the host.
load_dotenv()

from features import (
    REQUIRED_COLUMNS,
    clean_gl_data,
    engineer_features,
    get_feature_columns,
    get_t2_feature_columns,
    validate_required_columns,
)
from integrity import run_integrity_checks, summarize_findings
from model import SENSITIVITY_MAP, run_hybrid_pipeline
from narrative import (
    DEFAULT_TOP_N,
    MAX_TOP_N,
    generate_narratives_for_rows,
)
from scoring import apply_scoring


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AI Audit Risk Analyzer API",
    version="0.4.1",
    description="ML anomaly detection + materiality-calibrated risk scoring "
                "+ PCAOB-aligned labels for QuickBooks GL exports. Phase 4b "
                "extends the GPT narrative endpoint to a full 7-field audit "
                "memo (risk summary, assertion consideration, magnitude, "
                "likelihood, COSO consideration, follow-up procedures, "
                "disclaimer) with strict validation and deterministic fallback.",
)

# In production the Next.js frontend proxies /api/* server-side (see
# next.config.js rewrites), so the browser never calls this API cross-origin
# and CORS isn't exercised. ALLOWED_ORIGINS (comma-separated) lets a deployment
# add its public frontend URL for the case where the browser calls the backend
# directly (NEXT_PUBLIC_API_BASE_URL). Defaults to the local dev origins.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_allowed_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fs_pct_for_entity(entity_type: str) -> float:
    return 0.05 if entity_type == "Public company" else 0.04


def _clean_for_json(value: Any) -> Any:
    """Convert pandas / numpy scalars to JSON-safe primitives, replacing
    NaN / Inf with None so the response is always valid JSON."""
    if value is None:
        return None
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat() if value is not pd.NaT else None
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    # numpy scalar types fall through to native via item()
    if hasattr(value, "item"):
        try:
            return _clean_for_json(value.item())
        except (ValueError, AttributeError):
            return str(value)
    return value


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a dataframe to a list of JSON-safe dicts."""
    records = []
    for _, row in df.iterrows():
        records.append({k: _clean_for_json(v) for k, v in row.items()})
    return records


def _parse_date(s: str, field: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}: expected YYYY-MM-DD, got {s!r}",
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok", "version": app.version}


@app.get("/api/options")
def options() -> dict[str, Any]:
    """Static options the frontend uses to populate dropdowns."""
    return {
        "entity_types": [
            "Private for-profit", "Public company", "Non-profit", "Fund",
        ],
        "benchmark_labels": {
            "Private for-profit": "EBT (Earnings Before Tax)",
            "Public company":     "Net Income",
            "Non-profit":         "Total Expenses",
            "Fund":               "Net Asset Value (NAV)",
        },
        "detection_sensitivities": list(SENSITIVITY_MAP.keys()),
        "required_columns": REQUIRED_COLUMNS,
        "narrative": {
            "default_top_n": DEFAULT_TOP_N,
            "max_top_n": MAX_TOP_N,
        },
    }


@app.post("/api/analyze")
async def analyze(
    csv: UploadFile = File(...),
    entity_type: str = Form(...),
    benchmark_figure: float = Form(...),
    detection_sensitivity: str = Form(...),
    period_start: str = Form(...),
    period_end: str = Form(...),
) -> dict[str, Any]:
    # ---- 0. Validate inputs ----
    if detection_sensitivity not in SENSITIVITY_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown detection_sensitivity {detection_sensitivity!r}. "
                   f"Expected one of {list(SENSITIVITY_MAP)}.",
        )

    period_start_d = _parse_date(period_start, "period_start")
    period_end_d = _parse_date(period_end, "period_end")
    if period_end_d < period_start_d:
        raise HTTPException(
            status_code=400,
            detail="period_end must be on or after period_start.",
        )

    # ---- 1. Read CSV ----
    raw_bytes = await csv.read()
    try:
        raw_df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read CSV: {e}")

    ok, missing = validate_required_columns(raw_df)
    if not ok:
        raise HTTPException(
            status_code=400,
            detail=f"Uploaded CSV is missing required columns: {missing}",
        )

    # ---- 2. Materiality ----
    fs_pct = fs_pct_for_entity(entity_type)
    fs_mat = benchmark_figure * fs_pct
    perf_mat = fs_mat * 0.50
    txn_mat = fs_mat * 0.80

    # ---- 3. Cleaning + integrity ----
    cleaned_df = clean_gl_data(raw_df)
    findings = run_integrity_checks(
        cleaned_df, period_start=period_start_d, period_end=period_end_d
    )
    integrity_counts = summarize_findings(findings)

    # ---- 4. Feature engineering (T1 + T2) ----
    feat_df = engineer_features(cleaned_df, period_end=period_end_d)
    feature_cols = get_feature_columns()
    t2_feature_cols = get_t2_feature_columns()

    feature_firing_t1 = {
        "is_round_number":             int(feat_df["is_round_number"].sum()),
        "is_weekend_posting":          int(feat_df["is_weekend_posting"].sum()),
        "missing_description":         int(feat_df["missing_description"].sum()),
        "is_new_vendor":               int(feat_df["is_new_vendor"].sum()),
        "is_near_approval_threshold":  int(feat_df["is_near_approval_threshold"].sum()),
    }
    feature_firing_t2 = {
        "control_gap_ge_1":            int((feat_df["control_gap_score"] >= 1).sum()),
        "fraud_risk_flag":             int(feat_df["fraud_risk_flag"].sum()),
        "is_year_end_concentration":   int(feat_df["is_year_end_concentration"].sum()),
        "is_non_standard_pattern":     int(feat_df["is_non_standard_pattern"].sum()),
    }

    # ---- 5. ML + scoring (Phase 3: hybrid two-track) ----
    scored_df, hybrid_info = run_hybrid_pipeline(
        feat_df,
        feature_cols=feature_cols,
        detection_sensitivity=detection_sensitivity,
    )
    scored_df = apply_scoring(
        scored_df,
        fs_materiality=fs_mat,
        performance_materiality=perf_mat,
        transaction_materiality=txn_mat,
    )

    total = len(scored_df)
    flagged_df = scored_df[scored_df["flagged_status"] == "Flagged"].copy()
    n_flagged = len(flagged_df)
    pct_flagged = (n_flagged / total * 100) if total else 0.0
    risk_rating = (
        "Elevated" if pct_flagged > 5 else
        "Moderate" if pct_flagged > 2 else
        "Low"
    )

    # ---- 6. Chart data ----
    pcaob_label_order = [
        "Potential Material Weakness Indicator",
        "Potential Significant Deficiency",
        "Monitor — Below Escalation Threshold",
    ]
    tier_distribution = []
    counts = scored_df["pcaob_label"].value_counts().to_dict()
    for label in pcaob_label_order:
        tier_distribution.append({
            "label": label,
            "count": int(counts.get(label, 0)),
        })

    if n_flagged > 0:
        top_accounts = (
            flagged_df.groupby("account_name")["abs_amount"]
            .sum().sort_values(ascending=False).head(10)
            .reset_index()
        )
        top_accounts_data = [
            {"account_name": str(r["account_name"]),
             "flagged_amount": float(r["abs_amount"])}
            for _, r in top_accounts.iterrows()
        ]
    else:
        top_accounts_data = []

    # ---- 7. Flagged rows for the table ----
    display_cols = [
        "date", "account_name", "vendor", "amount",
        "anomaly_score", "raw_tier", "final_tier", "pcaob_label",
        "materiality_annotation", "active_flags",
        "control_gap_score", "fraud_risk_flag",
        "period_over_period_pct", "vendor_concentration_pct",
        "is_year_end_concentration", "is_non_standard_pattern",
        # Phase 3 hybrid columns
        "fraud_probability",
        "is_qualitative_override", "qualitative_override_note",
        "is_supervised_escalation", "supervised_escalation_note",
    ]
    display_cols = [c for c in display_cols if c in flagged_df.columns]
    flagged_rows = _df_to_records(flagged_df[display_cols])

    # Phase 3 hybrid layer metadata for the response
    n_qual_override = int(scored_df.get("is_qualitative_override",
                                        pd.Series([0]*len(scored_df))).sum())
    n_sup_escalation = int(scored_df.get("is_supervised_escalation",
                                         pd.Series([0]*len(scored_df))).sum())

    # ---- 8. Response ----
    return {
        "ok": True,
        "request": {
            "entity_type": entity_type,
            "benchmark_figure": benchmark_figure,
            "detection_sensitivity": detection_sensitivity,
            "period_start": period_start,
            "period_end": period_end,
            "row_count": len(raw_df),
        },
        "materiality": {
            "fs_pct": fs_pct,
            "fs": fs_mat,
            "performance": perf_mat,
            "transaction": txn_mat,
        },
        "integrity": {
            "counts": integrity_counts,
            "findings": [
                {"name": f.name, "status": f.status,
                 "summary": f.summary, "detail": f.detail}
                for f in findings
            ],
        },
        "feature_firing": {
            "t1": feature_firing_t1,
            "t2": feature_firing_t2,
        },
        "summary": {
            "total": total,
            "flagged": n_flagged,
            "flagged_pct": round(pct_flagged, 2),
            "risk_rating": risk_rating,
        },
        "hybrid_layer": {
            "status": hybrid_info.get("status"),
            "n_qualitative_override": n_qual_override,
            "n_supervised_escalation": n_sup_escalation,
            "supervised_n_positive": hybrid_info.get("n_positive"),
            "supervised_n_negative": hybrid_info.get("n_negative"),
            "supervised_feature_importance": hybrid_info.get("feature_importance", {}),
        },
        "chart_data": {
            "tier_distribution": tier_distribution,
            "top_accounts": top_accounts_data,
        },
        "flagged_rows": flagged_rows,
    }


# ---------------------------------------------------------------------------
# Phase 4a + 4b — narrative endpoint
# ---------------------------------------------------------------------------

class _EntityContext(BaseModel):
    entity_type: str | None = None
    period_start: str | None = None
    period_end: str | None = None


class _NarrativesRequest(BaseModel):
    """Body schema for POST /api/narratives.

    `rows` is the same shape as the `flagged_rows` array in /api/analyze's
    response. The frontend just forwards them.
    """
    rows: list[dict[str, Any]] = Field(default_factory=list)
    entity_context: _EntityContext = Field(default_factory=_EntityContext)
    top_n: int = Field(default=DEFAULT_TOP_N, ge=1, le=MAX_TOP_N)


@app.post("/api/narratives")
def narratives(req: _NarrativesRequest) -> dict[str, Any]:
    """Generate full audit memos for the top-N flagged transactions.

    Phase 4b: each narrative now contains all 7 audit-memo fields plus
    `narrative_status` ("GPT" or "Fallback"). The endpoint never raises
    on OpenAI errors or validator rejection — both paths route through a
    deterministic fallback that is itself guaranteed to pass validation.
    """
    if not req.rows:
        raise HTTPException(
            status_code=400,
            detail="No rows provided. Call /api/analyze first and forward "
                   "the flagged_rows array to this endpoint.",
        )

    result = generate_narratives_for_rows(
        rows=req.rows,
        entity_context=req.entity_context.model_dump(),
        top_n=req.top_n,
    )
    return {"ok": True, **result}
