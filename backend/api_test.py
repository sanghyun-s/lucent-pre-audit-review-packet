"""api_test.py — verify the FastAPI /api/analyze + /api/narratives endpoints.

Phase 4a tested /api/narratives end-to-end against the fallback path
(no real LLM calls). Phase 4b extends those tests to the full 7-field
memo shape: every memo must have exactly 7 fields, recommended_follow_up
must be a list of 3-5 strings, the disclaimer must be verbatim, and no
banned phrases may appear in any field.

Real end-to-end LLM testing is still done in the browser against a
running server with a valid OPENAI_API_KEY.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Force fallback path for narrative tests so they run without a real API
# key (and without making real billed calls during smoke tests).
os.environ["OPENAI_API_KEY"] = ""

from fastapi.testclient import TestClient

from api import app
from prompts import BANNED_PHRASES, REQUIRED_DISCLAIMER, REQUIRED_MEMO_FIELDS

client = TestClient(app)


def check(label, ok, detail=""):
    mark = "✓" if ok else "✗"
    print(f"  {mark} {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise AssertionError(label)


def main():
    print("FastAPI endpoint smoke test")
    print("-" * 70)

    # Health check
    r = client.get("/api/healthz")
    check("GET /api/healthz returns 200", r.status_code == 200)
    check("healthz returns ok status", r.json().get("status") == "ok")
    check("healthz reports Phase 4 version",
          r.json().get("version", "").startswith("0.4"),
          f"got {r.json().get('version')}")

    # Options endpoint
    r = client.get("/api/options")
    check("GET /api/options returns 200", r.status_code == 200)
    opts = r.json()
    check("options has entity_types", "entity_types" in opts)
    check("options has detection_sensitivities",
          "Balanced (0.05)" in opts["detection_sensitivities"])
    check("options exposes narrative.default_top_n",
          opts.get("narrative", {}).get("default_top_n") == 5)
    check("options exposes narrative.max_top_n",
          opts.get("narrative", {}).get("max_top_n") == 20)

    # The main analyze endpoint
    csv_path = Path(__file__).parent / "sample_data" / "sample_gl.csv"
    check("sample CSV exists", csv_path.exists())

    with open(csv_path, "rb") as f:
        r = client.post(
            "/api/analyze",
            files={"csv": ("sample_gl.csv", f, "text/csv")},
            data={
                "entity_type": "Private for-profit",
                "benchmark_figure": "150000",
                "detection_sensitivity": "Balanced (0.05)",
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
        )
    check("POST /api/analyze returns 200", r.status_code == 200,
          f"status={r.status_code}, body={r.text[:200]}")

    body = r.json()
    check("response has ok=True", body.get("ok") is True)

    # Structural checks
    for section in ("request", "materiality", "integrity", "feature_firing",
                    "summary", "chart_data", "flagged_rows"):
        check(f"response has '{section}'", section in body)

    # Materiality math
    m = body["materiality"]
    check("FS materiality = $6000", m["fs"] == 6000.0,
          f"got {m['fs']}")
    check("Performance = $3000", m["performance"] == 3000.0)
    check("Transaction = $4800", m["transaction"] == 4800.0)

    # Integrity findings present
    fi = body["integrity"]
    check("integrity has counts", "counts" in fi)
    check("integrity has findings list", isinstance(fi["findings"], list))
    check("at least 4 integrity checks ran", len(fi["findings"]) >= 4)

    # Feature firing
    ff = body["feature_firing"]
    check("feature_firing has t1", "t1" in ff)
    check("feature_firing has t2", "t2" in ff)
    check("t2.fraud_risk_flag > 0", ff["t2"]["fraud_risk_flag"] > 0,
          f"got {ff['t2']['fraud_risk_flag']}")

    # Summary numbers
    s = body["summary"]
    check("total = 2000", s["total"] == 2000)
    check("flagged > 0", s["flagged"] > 0)
    check("flagged_pct present", "flagged_pct" in s)
    check("risk_rating present", s["risk_rating"] in ("Low", "Moderate", "Elevated"))

    # Chart data
    cd = body["chart_data"]
    check("tier_distribution has 3 entries", len(cd["tier_distribution"]) == 3)
    check("top_accounts is a list", isinstance(cd["top_accounts"], list))

    # Flagged rows
    rows = body["flagged_rows"]
    check("flagged_rows is a list", isinstance(rows, list))
    check("flagged_rows count matches summary",
          len(rows) == s["flagged"])
    if rows:
        r0 = rows[0]
        for col in ("date", "account_name", "vendor", "amount",
                    "anomaly_score", "final_tier", "pcaob_label",
                    "active_flags", "control_gap_score", "fraud_risk_flag",
                    # Phase 3 additions
                    "fraud_probability",
                    "is_qualitative_override", "qualitative_override_note",
                    "is_supervised_escalation", "supervised_escalation_note"):
            check(f"row[0] has '{col}'", col in r0)

        # Phase 3 sanity: fraud_probability between 0 and 1
        check("fraud_probability is between 0 and 1",
              0.0 <= r0["fraud_probability"] <= 1.0,
              f"got {r0['fraud_probability']}")

    # Phase 3: hybrid_layer metadata
    check("response has 'hybrid_layer' section", "hybrid_layer" in body)
    hl = body["hybrid_layer"]
    check("hybrid_layer status == 'trained'", hl.get("status") == "trained",
          f"got {hl.get('status')}")
    check("hybrid_layer reports n_qualitative_override",
          isinstance(hl.get("n_qualitative_override"), int))
    check("hybrid_layer reports supervised_feature_importance",
          isinstance(hl.get("supervised_feature_importance"), dict)
          and len(hl["supervised_feature_importance"]) > 0)

    # Sample of top flagged row
    print("\nTop flagged row from /api/analyze:")
    print(f"  date          : {rows[0]['date']}")
    print(f"  account       : {rows[0]['account_name']}")
    print(f"  vendor        : {rows[0]['vendor']}")
    print(f"  amount        : ${rows[0]['amount']:,.2f}")
    print(f"  pcaob_label   : {rows[0]['pcaob_label']}")
    print(f"  active_flags  : {rows[0]['active_flags']}")
    print(f"  fraud_risk    : {rows[0]['fraud_risk_flag']}")

    # Error path: bad sensitivity
    with open(csv_path, "rb") as f:
        r = client.post(
            "/api/analyze",
            files={"csv": ("sample_gl.csv", f, "text/csv")},
            data={
                "entity_type": "Private for-profit",
                "benchmark_figure": "150000",
                "detection_sensitivity": "BogusValue",
                "period_start": "2024-01-01",
                "period_end": "2024-12-31",
            },
        )
    check("bad sensitivity → 400", r.status_code == 400,
          f"got {r.status_code}")

    # Error path: bad date order
    with open(csv_path, "rb") as f:
        r = client.post(
            "/api/analyze",
            files={"csv": ("sample_gl.csv", f, "text/csv")},
            data={
                "entity_type": "Private for-profit",
                "benchmark_figure": "150000",
                "detection_sensitivity": "Balanced (0.05)",
                "period_start": "2024-12-31",
                "period_end": "2024-01-01",
            },
        )
    check("inverted date range → 400", r.status_code == 400)

    # ============================================================
    # Phase 4a + 4b — /api/narratives
    # ============================================================
    print("\nPHASE 4a + 4b narrative endpoint")
    print("-" * 70)

    # Empty rows → 400
    r = client.post("/api/narratives", json={
        "rows": [],
        "entity_context": {"entity_type": "Private for-profit",
                            "period_start": "2024-01-01",
                            "period_end": "2024-12-31"},
        "top_n": 10,
    })
    check("POST /api/narratives with empty rows → 400",
          r.status_code == 400, f"got {r.status_code}")

    # Real call with the flagged rows. Test runs with OPENAI_API_KEY=""
    # cleared at module load, so every row takes the fallback path.
    narrative_req = {
        "rows": rows,
        "entity_context": {"entity_type": "Private for-profit",
                            "period_start": "2024-01-01",
                            "period_end": "2024-12-31"},
        "top_n": 5,
    }
    r = client.post("/api/narratives", json=narrative_req)
    check("POST /api/narratives returns 200", r.status_code == 200,
          f"status={r.status_code}, body={r.text[:200]}")

    nbody = r.json()
    check("response has ok=True", nbody.get("ok") is True)
    check("response has 'narratives'", "narratives" in nbody)
    check("response has 'selected_row_keys'", "selected_row_keys" in nbody)
    check("response reports top_n_used = 5", nbody.get("top_n_used") == 5)
    check("response reports n_gpt + n_fallback = 5",
          nbody.get("n_gpt", 0) + nbody.get("n_fallback", 0) == 5)
    check("with no API key, all 5 are Fallback",
          nbody.get("n_fallback") == 5,
          f"got n_gpt={nbody.get('n_gpt')}, n_fallback={nbody.get('n_fallback')}")

    # ---- Phase 4b: validate full memo shape on each narrative ----
    narr = nbody["narratives"]
    check("narratives has 5 entries", len(narr) == 5)

    for pos in ("0", "1", "2", "3", "4"):
        check(f"narratives['{pos}'] exists", pos in narr)
        entry = narr[pos]

        # All 7 memo fields plus narrative_status
        for field in REQUIRED_MEMO_FIELDS:
            check(f"narratives['{pos}'].{field} present",
                  field in entry,
                  f"got keys: {sorted(entry.keys())}")
        check(f"narratives['{pos}'].narrative_status present",
              "narrative_status" in entry)
        check(f"narratives['{pos}'].narrative_status valid",
              entry.get("narrative_status") in ("GPT", "Fallback"))

        # Type checks
        check(f"narratives['{pos}'].risk_summary is non-empty str",
              isinstance(entry["risk_summary"], str) and len(entry["risk_summary"]) > 20)
        check(f"narratives['{pos}'].recommended_follow_up is list of 3-5",
              isinstance(entry["recommended_follow_up"], list)
              and 3 <= len(entry["recommended_follow_up"]) <= 5,
              f"got len={len(entry.get('recommended_follow_up', []))}")
        for j, item in enumerate(entry["recommended_follow_up"]):
            check(f"narratives['{pos}'].recommended_follow_up[{j}] is non-empty str",
                  isinstance(item, str) and len(item.strip()) > 5)

        # Disclaimer must be verbatim
        check(f"narratives['{pos}'].disclaimer is verbatim",
              entry["disclaimer"].strip() == REQUIRED_DISCLAIMER,
              f"got: {entry['disclaimer'][:80]!r}")

        # No banned phrases in any text field
        text_parts = []
        for f in REQUIRED_MEMO_FIELDS:
            v = entry[f]
            if isinstance(v, str):
                text_parts.append(v)
            elif isinstance(v, list):
                text_parts.extend(item for item in v if isinstance(item, str))
        combined = "\n".join(text_parts).lower()
        for phrase in BANNED_PHRASES:
            if phrase in combined:
                raise AssertionError(
                    f"BANNED PHRASE LEAKED in position {pos}: {phrase!r}"
                )
    check("no banned phrases in any narrative output", True)

    # Show one full memo for visual confirmation
    print("\nSample fallback memo (position 0):")
    print(f"  status: {narr['0']['narrative_status']}")
    print(f"  risk_summary:                  {narr['0']['risk_summary'][:120]}...")
    print(f"  assertion_consideration:       {narr['0']['assertion_consideration'][:120]}...")
    print(f"  magnitude_assessment:          {narr['0']['magnitude_assessment'][:120]}...")
    print(f"  likelihood_assessment:         {narr['0']['likelihood_assessment'][:120]}...")
    print(f"  control_or_coso_consideration: {narr['0']['control_or_coso_consideration'][:120]}...")
    print(f"  recommended_follow_up:         ({len(narr['0']['recommended_follow_up'])} items)")
    for item in narr['0']['recommended_follow_up']:
        print(f"    - {item}")
    print(f"  disclaimer:                    {narr['0']['disclaimer']}")

    # top_n bounds checks
    r = client.post("/api/narratives", json={
        "rows": rows[:3],
        "entity_context": {},
        "top_n": 999,  # over MAX_TOP_N
    })
    check("top_n > 20 → 422 (pydantic validation)",
          r.status_code == 422, f"got {r.status_code}")

    r = client.post("/api/narratives", json={
        "rows": rows[:3],
        "entity_context": {},
        "top_n": 0,  # under min
    })
    check("top_n < 1 → 422 (pydantic validation)",
          r.status_code == 422, f"got {r.status_code}")

    # ============================================================
    # Phase 4b — validator unit tests (direct, no HTTP)
    # ============================================================
    print("\nPHASE 4b validator unit tests")
    print("-" * 70)

    from narrative_validator import validate_memo
    from narrative_fallback import build_fallback_full_memo

    # The fallback for any flagged row must always pass validation
    sample_row = rows[0] if rows else {"amount": 1000.0, "active_flags": "Round number amount"}
    fallback_memo = build_fallback_full_memo(sample_row)
    ok, reason = validate_memo(fallback_memo)
    check("fallback memo passes validator", ok, f"reason: {reason!r}")

    # Validator catches missing fields
    bad1 = {k: v for k, v in fallback_memo.items() if k != "disclaimer"}
    ok, reason = validate_memo(bad1)
    check("validator rejects missing 'disclaimer'", not ok, f"reason: {reason!r}")
    check("rejection reason mentions disclaimer",
          "disclaimer" in reason, f"reason: {reason!r}")

    # Validator catches wrong follow-up type
    bad2 = dict(fallback_memo)
    bad2["recommended_follow_up"] = "not a list"
    ok, reason = validate_memo(bad2)
    check("validator rejects str recommended_follow_up", not ok)

    # Validator catches follow-up count out of bounds
    bad3 = dict(fallback_memo)
    bad3["recommended_follow_up"] = ["only one item"]
    ok, reason = validate_memo(bad3)
    check("validator rejects follow-up with < 3 items", not ok)

    # Validator catches banned phrase
    bad4 = dict(fallback_memo)
    bad4["risk_summary"] = bad4["risk_summary"] + " fraud occurred."
    ok, reason = validate_memo(bad4)
    check("validator rejects banned phrase 'fraud occurred'", not ok,
          f"reason: {reason!r}")

    # Validator catches non-verbatim disclaimer
    bad5 = dict(fallback_memo)
    bad5["disclaimer"] = "This is risk only."
    ok, reason = validate_memo(bad5)
    check("validator rejects non-verbatim disclaimer", not ok)

    # Validator catches name leakage
    bad6 = dict(fallback_memo)
    bad6["risk_summary"] = bad6["risk_summary"] + " The employee approved this."
    ok, reason = validate_memo(bad6)
    check("validator rejects 'the employee' name-leakage", not ok)

    # Validator accepts a clean memo without modification
    ok, reason = validate_memo(fallback_memo)
    check("validator still accepts clean fallback after mutation tests",
          ok, f"reason: {reason!r}")

    print("\nAll FastAPI endpoint criteria pass.")


if __name__ == "__main__":
    main()
