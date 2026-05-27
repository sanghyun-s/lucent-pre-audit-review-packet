"""api_test.py — verify the FastAPI /api/analyze endpoint works end-to-end."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from api import app

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

    # Options endpoint
    r = client.get("/api/options")
    check("GET /api/options returns 200", r.status_code == 200)
    opts = r.json()
    check("options has entity_types", "entity_types" in opts)
    check("options has detection_sensitivities",
          "Balanced (0.05)" in opts["detection_sensitivities"])

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

    print("\nAll FastAPI endpoint criteria pass.")


if __name__ == "__main__":
    main()
