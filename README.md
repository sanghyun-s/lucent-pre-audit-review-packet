# AI Audit Risk Analyzer

> **Status:** Phase 4a shipped · 4b/4c in progress · **Last updated:** June 3, 2026
> **Stack:** FastAPI · Next.js 14 · scikit-learn · OpenAI · Tailwind · shadcn/ui · Plotly

ML anomaly detection + materiality-calibrated risk scoring + PCAOB-aligned labels for QuickBooks GL exports, with a live LLM narrative layer that translates findings into hedged, framework-grounded audit review memos.

A generalized audit software (GAS) prototype that automates transaction-level analytical review procedures (ARP) on SMB general ledger data. Built as a portfolio piece exploring the intersection of accounting standards, machine learning, and LLM-driven narrative generation.

---

## Build progress

| Phase | Status | Shipped | Summary |
|---|---|---|---|
| Phase 1 — MVP pipeline | ✅ Shipped | May 17, 2026 | CSV upload → 6-feature ML pipeline → PCAOB-labeled table + charts (Streamlit prototype, since migrated) |
| Phase 2 — Tier 2 features + integrity + stack migration | ✅ Shipped | May 18, 2026 | 6 Tier 2 features, 4 data integrity checks, FastAPI restructure, Next.js + shadcn frontend |
| Phase 3 — Hybrid fraud detection + qualitative override | ✅ Shipped | May 27, 2026 | Hybrid two-track ML (Isolation Forest + weak-label Random Forest) with PCAOB AS 2401 qualitative override |
| **Phase 4 — GPT narrative layer** | ✅ **Phase 4a shipped** | Jun 3, 2026 (4a) | Live OpenAI integration generating row-level audit risk summaries; 4b (full memo + validator) and 4c (UI refactor) remaining |
| Phase 5 — Deployment + polish | ⬜ Planned | — | Vercel + Render/Railway deployment, Excel workbook export, period-over-period table, demo polish |

### Phase 4 detail

| Sub-phase | Status | Shipped | Scope |
|---|---|---|---|
| 4 Prep | ✅ Done | Jun 1, 2026 | OpenAI account, secrets hygiene (`.env` + gitignore verified), `openai` and `python-dotenv` installed, end-to-end smoke test confirmed audit-credible output at ~$0.000024 per call |
| 4a — Risk-summary integration | ✅ Shipped | Jun 3, 2026 | `prompts.py` + `narrative.py` + `narrative_fallback.py` modules, `POST /api/narratives` endpoint (v0.4.0), frontend "Generate AI Narrative" button with Top-N selector (default 10, max 20), row-level expanders rendering audit-credible summaries, deterministic fallback when API fails, CSV export enriched with `narrative_status` + `risk_summary` columns when narratives exist |
| 4b — Full 7-field memo + validator | ⬜ Next | — | Extend to 7 audit-memo fields (risk_summary, assertion_consideration, magnitude_assessment, likelihood_assessment, control_or_coso_consideration, recommended_follow_up, disclaimer), banned-phrase validator with structured fallback per field, CSV export with all 7 narrative columns |
| 4c — Review workflow UI refactor | ⬜ Planned | — | Compact Data Integrity / Feature Engineering panels into expanders, restructure into 5-section review workflow, narrative card visual polish, rule-based Standards Grounding panel under each narrative |

---

## What it does

Upload a GL CSV, configure the client profile (entity type, materiality benchmark, detection sensitivity, audit period), and the app runs the following pipeline in under a second:

1. **Validates** the file structure and required columns
2. **Cleans** and coerces dtypes (date → datetime, amount → numeric, derives `abs_amount`)
3. **Engineers 12 audit-domain features** — 6 Tier 1 features that feed the ML model (account-level magnitude z-score, round number, weekend posting, missing description, new vendor, near approval threshold) plus 6 Tier 2 features for display and override logic (control gap score, fraud risk flag, period-over-period %, vendor concentration %, year-end concentration, non-standard DR/CR pattern)
4. **Runs 4 data integrity checks** — hash total, cross-footing, date-in-period, account mapping
5. **Scores anomalies** with a hybrid ML layer: unsupervised Isolation Forest (200 trees, sensitivity-controlled contamination) for label-free anomaly detection, plus a weak-label supervised classifier that catches subtle fraud the unsupervised layer misses
6. **Applies the materiality filter** — downgrades or escalates the raw ML tier based on whether the dollar amount exceeds Performance / Transaction materiality
7. **Applies the qualitative override** — when ≥ 2 fraud indicators co-occur on a single transaction, escalates the tier *above* what materiality would assign (PCAOB AS 2401 / AS 5 qualitative materiality)
8. **Labels** findings with PCAOB-aligned language: *Potential Material Weakness Indicator*, *Potential Significant Deficiency*, *Monitor — Below Escalation Threshold*
9. **Returns** a sortable, exportable table of flagged transactions with the specific risk indicators that fired on each row, the supervised classifier's fraud probability, and qualitative override annotations
10. **(Phase 4a) On user request**, generates audit-credible risk summaries via `gpt-4o-mini` for the top-N most demo-relevant flagged transactions — hedged language, transaction-as-subject discipline, banned-phrase enforcement, deterministic fallback on API failure

The core thesis: a generic ML anomaly detector finds statistically unusual transactions. An audit-grade tool also asks whether the dollar amount matters, recognizes that some patterns are material regardless of amount, and translates findings into the cautious, hedged language standards require.

---

## Skills demonstrated

This project exercises a deliberate breadth across full-stack engineering, applied ML, and domain modeling. What's actually been built and why each item is non-trivial:

### Applied machine learning
- **Unsupervised anomaly detection** — Isolation Forest with engineered audit features, contamination sweep, and sensitivity-controlled tuning
- **Weak-label supervised learning** — bootstrapping training labels from rule-derived indicators to address an evidence-identified subtle-fraud gap (67% recall on subtle patterns) while keeping the model honest by excluding the rule's own flag columns from the training feature set
- **Evidence-based model selection** — built a controlled simulation with three fraud archetypes (obvious, structured, subtle) and per-archetype recall measurement to justify a hybrid approach rather than committing to either pure paradigm
- **Feature engineering for a regulated domain** — translating audit standards into 12 numeric features, each traceable to a specific source (AU-C 315, PCAOB AS 2401, COSO components)

### Domain modeling — accounting & audit
- **Quantitative materiality** — FS / Performance / Transaction thresholds with entity-type calibration (Private 4%, Public 5%)
- **Qualitative materiality override** — PCAOB AS 2401-aligned escalation rule encoding the audit principle that pattern co-occurrence is material regardless of dollar amount
- **PCAOB-aligned labeling** — never-conclusive language ("Potential Material Weakness Indicator", "Monitor — Below Escalation Threshold") instead of definitive findings
- **Data integrity layer** — hash total, cross-footing, date-in-period, and account-mapping checks running as a separate concern before ML scoring

### Backend engineering
- **FastAPI** — clean module separation (`features` / `model` / `scoring` / `integrity` / `narrative` / `api`), typed responses, async-ready
- **TestClient + custom acceptance suite** — 30 done-criteria asserted across Phases 1–3, plus 70+ FastAPI endpoint contract checks including 22 new Phase 4a narrative-endpoint assertions
- **Pipeline orchestration** — `run_hybrid_pipeline` ties unsupervised and supervised tracks together in a single call that's reachable both over HTTP and via direct Python import
- **Secrets hygiene** — environment-based config with `python-dotenv`, gitignored `.env`, `git check-ignore` verification, restricted-permission API keys
- **Graceful degradation** — narrative endpoint never raises on OpenAI errors; any failure path (network, auth, rate limit, banned-phrase trip, empty completion) routes through a deterministic fallback so the app stays usable when external services fail

### Frontend engineering
- **Next.js 14 (App Router)** with proxy configuration for backend interop
- **shadcn/ui + Tailwind** for composable design primitives without runtime CSS overhead
- **Interactive charting** with Plotly via `react-plotly.js`
- **Multi-state UI** — form validation, file upload, async analysis triggering, sortable/paginated/exportable result table
- **Row-level expanders + conditional rendering** — clicking a flagged row reveals AI narrative + extended context; CSV export conditionally includes narrative columns only when narratives have been generated

### LLM integration
- **Cost-aware design** — Top-N capped at 20, button-triggered generation rather than automatic, model choice (`gpt-4o-mini`) sized to task complexity; observed cost ~$0.001 per Top-10 generation
- **Prompt engineering for a high-stakes domain** — banned-phrase enforcement, sentence-subject discipline (transaction not person), hedged-verb requirements, explicit framing that `fraud_probability` is a resemblance score not a fraud probability
- **Demo-relevance sort** — backend re-sorts incoming rows by final_tier → qualitative override → fraud_risk_flag → anomaly score → amount so Top-N narratives are the most audit-meaningful items, not random
- **Post-generation validation** — banned-phrase scan on model output; any banned phrase routes through fallback, ensuring no fraud-conclusion language ever reaches the user

### Software engineering practice
- **Git hygiene** — meaningful commit messages, staged commits per phase, branch-based workflow, six logical commits across the build to date
- **Pre-deployment verification** — diff-based comparison between staging files and live files before each major drop, backup snapshots, never committing on untested code
- **Reproducibility** — `requirements.txt` pinned, sample data generator (`generate_sample_gl.py`) seeded for deterministic test runs
- **Documented decisions** — model comparison findings, phase plan, design rationales preserved in commit messages and README

---

## Architecture

```
┌─────────────────────────────┐         ┌────────────────────────────────────┐
│  Next.js frontend           │  HTTP   │  FastAPI backend                   │
│  (React 18, shadcn/ui,      │ ──────► │  (Python 3.13)                     │
│   Tailwind, plotly.js)      │  multi- │                                    │
│  - Client profile form      │  part   │  features.py    cleaning + 12 feats│
│  - CSV upload widget        │ ◄────── │  integrity.py   4 audit checks     │
│  - Integrity panel          │  JSON   │  model.py       hybrid ML layer:   │
│  - PCAOB tier chart         │         │                  · Isolation Forest│
│  - Flagged txn table        │         │                  · weak-label RF   │
│  - AI narrative expanders   │         │  scoring.py     materiality +      │
│  Port 3000 (dev)            │         │                  qualitative       │
│                             │         │                  override          │
│                             │         │  prompts.py     audit-language     │
│                             │         │                  system prompt     │
│                             │         │  narrative.py   GPT orchestrator   │
│                             │         │  narrative_     deterministic      │
│                             │         │    fallback.py   safety net        │
│                             │         │  api.py         FastAPI routes     │
│                             │         │  Port 8000 (dev)                   │
└─────────────────────────────┘         └────────────────────────────────────┘
```

The frontend and backend are independently deployable. The same Python pipeline is reachable via:
- `POST /api/analyze` over HTTP — used by the Next.js UI for scoring
- `POST /api/narratives` over HTTP — used for on-demand AI narrative generation on the top-N flagged rows
- Direct import (`from features import engineer_features`) — used by `smoke_test.py` for regression testing

---

## Technical requirements

### Runtime
- **Python 3.11+** (tested on 3.13)
- **Node.js 18+** (tested on 22)
- **macOS, Linux, or WSL** for the dev environment

### Python dependencies (backend)
- `fastapi` + `uvicorn` — API framework and ASGI server
- `pandas` + `numpy` — tabular data processing
- `scikit-learn` — IsolationForest, RandomForestClassifier, StandardScaler
- `pydantic` — request/response validation
- `httpx` — TestClient dependency
- `openai` (≥ 2.40) + `python-dotenv` — LLM integration and environment config

### Node dependencies (frontend)
- `next` 14.x (App Router)
- `react` 18.x
- `tailwindcss` + `@radix-ui/react-*` + `class-variance-authority` (shadcn primitives)
- `plotly.js` + `react-plotly.js`
- `lucide-react` (icons)

### Phase 4 specific
- OpenAI API key with chat completions permission, stored in `backend/.env` (gitignored)
- Recommended spend limit: ≤ $10 hard cap (actual Phase 4a cost so far: well under $1)

---

## Model design — why hybrid fraud detection

The natural ML question for App 3 is "supervised or unsupervised?" Both approaches have a literature in fraud detection, and they make different demands. To decide deliberately, I built a controlled simulation: a 2,000-row synthetic GL with hidden ground-truth fraud labels across three archetypes (statistically obvious fraud, threshold-evading "structured" fraud, and quiet "subtle" fraud), then ran both approaches on identical data and compared.

The findings:

- **Pure unsupervised (Isolation Forest)** caught 100% of obvious fraud, 100% of structured fraud, and 67% of subtle fraud — with no labels required. This is the only mode that works on a real client's GL upload, where no fraud labels exist.
- **Pure supervised (Random Forest)** scored higher overall, but cannot train on real GL data because it requires labels that aren't there. Its perfect score on the simulation was partly a synthetic-data artifact.
- **The 67% subtle-fraud gap** is the real, evidence-based case for adding a supervised layer.

The implementation is a hybrid:

1. **Track 1 — Unsupervised Isolation Forest** stays as the primary detector. It produces `anomaly_score` and `raw_tier`, runs on any GL upload, and doesn't depend on labels.
2. **Track 2 — Weak-label Random Forest** trains in-process on each upload, using the rule-based `fraud_risk_flag` as a weak label. Its training features deliberately exclude the five fraud-indicator flags themselves, so the classifier cannot trivially reproduce the rule — it must learn from continuous and structural features (amount, account z-score, period-over-period change, vendor concentration, etc.). This is how it adds genuine signal for subtle fraud rather than restating what the rule already says.
3. **The qualitative override** fires when ≥ 2 fraud indicators co-occur on a single transaction, escalating the tier *above* what materiality alone would assign. This encodes PCAOB AS 2401 qualitative materiality: the co-occurrence of red flags is material regardless of dollar amount because it suggests a control breakdown whose potential magnitude exceeds the individual transaction.
4. **Supervised escalation** acts as a gentler secondary signal — when the classifier's `fraud_probability ≥ 0.50` and the qualitative override hasn't already fired, the tier nudges up by one level.

The result is a layered detection system where each layer has a defined role: anomaly detection finds statistical outliers, the materiality filter applies quantitative judgment, the qualitative override applies pattern-based judgment, and the supervised layer adds a smoothed second opinion for subtle cases.

---

## Narrative design — why button-triggered, validated, and fallback-protected

Phase 4a adds an LLM layer that translates already-scored findings into audit-credible risk summaries. Three design choices are worth noting because they reflect the constraints of using LLMs in a regulated domain:

1. **Button-triggered, not automatic.** Narrative generation runs only when the user explicitly clicks **Generate AI Narrative**, with a Top-N selector (default 10, max 20). This caps cost, gives the user a chance to inspect the flagged table first, and keeps the core scoring functional even if OpenAI is unavailable.

2. **Backend re-sorts for demo relevance.** Incoming rows are sorted by final_tier (High first) → qualitative_override (fired first) → fraud_risk_flag (fired first) → anomaly_score (most anomalous first) → amount (largest first), then the top N are passed to the model. This ensures the narratives shown are the most audit-meaningful items, not the first N in the table's visible order.

3. **Audit-language discipline is enforced at three layers.**
   - **System prompt** instructs the model to use hedged verbs only, keep the transaction (not a person) as the subject of every sentence, ground summaries in observable facts, and treat `fraud_probability` as a resemblance score not a fraud probability.
   - **Banned-phrase scan** on the model's output catches any forbidden phrase ("fraud occurred", "the perpetrator", "this proves", etc.) and routes the row through the fallback.
   - **Deterministic fallback** built from the row's own active flags produces an always-safe summary if the API is down, returns empty, or trips the banned-phrase scan. The user sees a `GPT` or `Fallback` badge so the provenance is visible.

The result: narratives that read like workpaper review notes (transaction-subject, hedged, grounded in observable facts) rather than confident accusations, with the entire chain auditable from prompt → model → validator → display.

---

## Project structure

```
app3/
├── backend/
│   ├── api.py                  FastAPI app — /api/analyze, /api/narratives, /api/options, /api/healthz
│   ├── api_test.py             End-to-end tests using TestClient (70+ assertions)
│   ├── features.py             Cleaning + 12 engineered features (6 T1 for ML, 6 T2 for display)
│   ├── integrity.py            4 pre-analysis data integrity checks
│   ├── model.py                Hybrid ML layer: IsolationForest + weak-label RandomForest
│   ├── scoring.py              Materiality filter + qualitative override + supervised escalation
│   ├── prompts.py              System prompt + 18 banned phrases for audit-grade language
│   ├── narrative.py            GPT orchestrator, demo-relevance sort, OpenAI call wrapper
│   ├── narrative_fallback.py   Deterministic fallback narrative template
│   ├── generate_sample_gl.py   2,000-row simulated GL with planted anomalies
│   ├── smoke_test.py           Asserts 30 Phase 1 + Phase 2 + Phase 3 done-criteria
│   ├── requirements.txt
│   ├── .env                    Local secrets (gitignored)
│   └── sample_data/
│       └── sample_gl.csv       Generated demo data
│
└── frontend/
    ├── app/
    │   ├── layout.jsx
    │   ├── page.jsx            Main analyzer page wiring all sections
    │   └── globals.css
    ├── components/
    │   ├── ClientProfileForm.jsx
    │   ├── CsvUpload.jsx
    │   ├── IntegrityPanel.jsx
    │   ├── FeatureFiringPanel.jsx
    │   ├── SummaryCards.jsx
    │   ├── MaterialityBanner.jsx
    │   ├── RiskDistributionChart.jsx
    │   ├── TopAccountsChart.jsx
    │   ├── FlaggedTable.jsx    Table + Top-N narrative controls + row expanders
    │   └── ui/                 shadcn primitives (button, card, input, label, select, badge)
    ├── lib/
    │   ├── api.js              Thin fetch wrapper for the FastAPI endpoints
    │   └── utils.js            shadcn cn() helper
    ├── next.config.js          Proxies /api/* to FastAPI (localhost:8000) in dev
    ├── tailwind.config.js
    └── package.json
```

Planned additions in Phase 4b: `backend/narrative_validator.py` (banned-phrase + schema validator for the full 7-field memo).

---

## Running locally

### Backend (terminal 1)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_sample_gl.py     # creates sample_data/sample_gl.csv
python smoke_test.py             # verifies 30 acceptance criteria pass
uvicorn api:app --reload --port 8000
```

The FastAPI server is now serving on `http://localhost:8000`. Hit `/api/healthz` to verify — should return `{"status":"ok","version":"0.4.0"}`.

### Frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Upload `backend/sample_data/sample_gl.csv`, click **Run Analysis**, and the full pipeline runs end-to-end against the FastAPI backend. To see the AI narrative layer in action, click **Generate AI Narrative** above the flagged transactions table.

### Phase 4 prerequisites

Create `backend/.env` containing:
```
OPENAI_API_KEY=sk-...
```
Verify it's gitignored: `git check-ignore -v backend/.env` should print a matching `.gitignore` line. The narrative endpoint falls back to deterministic templates if the key is missing or invalid — the app stays usable either way, but live AI narratives require a valid key.

### Running the test suite

```bash
cd backend
source .venv/bin/activate
python smoke_test.py             # Phase 1 + Phase 2 + Phase 3 pipeline criteria (30)
python api_test.py               # FastAPI endpoint contract (70+ checks including Phase 4a)
```

`api_test.py` deliberately clears `OPENAI_API_KEY` so it exercises the fallback path without making real API calls. Real LLM testing is done in the browser against a running server.

---

## Audit theory references

The 12 features, the materiality filter, the qualitative override, and the narrative prompt are anchored to specific audit-standard sources:

| Feature / mechanism | Source | What it captures |
|---|---|---|
| `amount_zscore_by_account` | AU-C 315, ARP | Account-level magnitude deviation |
| `is_round_number` | PCAOB AS 2401 | Manual entry / estimate red flag |
| `is_weekend_posting` | Control activities | Unusual posting timing |
| `missing_description` | Information & communication (COSO) | Documentation control gap |
| `is_new_vendor` | Fraud risk factors | Misappropriation opportunity |
| `is_near_approval_threshold` | IT controls / limit tests | Invoice splitting / approval avoidance |
| Materiality filter | PCAOB AS 5 | Quantitative severity-of-deficiency framework |
| Qualitative override | PCAOB AS 2401, AS 5 | Co-occurrence of fraud indicators is material regardless of amount because it signals a control breakdown |
| PCAOB labels | PCAOB AS 5 | "Potential Material Weakness Indicator", etc. |
| Narrative prompt — hedged language | AU-C 315, PCAOB AS 2401 | Risk-indicator framing, never fraud conclusions |
| Narrative prompt — subject discipline | Audit professional standards | Transaction/control as subject, not the person who recorded it |

Phase 4b will extend the narrative layer with structured prompts that reference AU-C 315 assertion considerations and COSO five-component framework via a rule-based mapping rather than free-form LLM citation.

---

## Future improvements (Phase 5 and beyond)

Items planned beyond Phase 4 to bring the project to demo-ready and deployable state:

- **Deployment** — Vercel (frontend) + Render or Railway (backend), ≈ $5-7/mo, custom subdomain
- **Excel workbook export** — multi-sheet `.xlsx` via `openpyxl`: summary, flagged transactions, integrity findings, narrative memos
- **Period-over-period fluctuation table** — account-level variance analysis as a separate analytical procedure
- **Demo polish** — animated transitions for state changes, loading skeletons, empty-state copy
- **Frontend badge column** — visible "Override" and "Fraud Prob" cells in the flagged table (currently in the API response but not rendered)
- **Compact review-workflow UI** — collapse Data Integrity and Feature Engineering panels into expanders, restructure into the 5-section review flow described in Phase 4c
- **Standards Grounding panel** — rule-based mapping from row attributes to AS 5 / AS 2401 / AS 3 / COSO citations, rendered beneath each AI narrative
- **Narrative card visual polish** — left-border tint, hierarchy improvements in the row-expander layout (deferred from 4a to 4c for a coherent UI restructure)
- **CI/CD** — GitHub Actions running `smoke_test.py` and `api_test.py` on every push
- **API observability** — structured logging for narrative-layer cost and latency tracking
- **Multi-period support** — comparison mode across two uploaded GL periods

---

## Methodology and limitations

This tool identifies *risk indicators* using statistical anomaly detection, weak-label supervised classification, and materiality thresholds. It does not determine intent, conclude fraud, or issue audit opinions. The PCAOB-aligned labels use "Potential", "Indicator", and "Monitor" throughout — never definitive language.

The supervised layer is trained on weak labels derived from rule-based fraud indicators, then applied in-process to the same upload. The honest interpretation of its `fraud_probability` is "this transaction resembles the rule-flagged transactions in continuous-feature space" — it is a smoothing of the rule rather than an independent validator. The qualitative override and supervised escalation are designed to never lower a tier, only raise it, so the materiality filter's conservative output remains the floor.

The GPT narrative layer (Phase 4a, shipped) is constrained to risk-indication language with explicit banned phrases ("fraud occurred," "the perpetrator," "this proves," etc.) enforced both in the system prompt and in a post-generation scan. Any banned-phrase trip routes the row through a deterministic fallback narrative built from observable transaction facts. The layer translates already-scored results into hedged audit-review memos; it does not extend the scoring logic itself, and it cannot conclude fraud or issue an audit opinion regardless of how the underlying ML output is interpreted.

Findings should be corroborated with documentary evidence and discussions with management consistent with AU-C 315 (Understanding the Entity and Its Environment) and PCAOB AS 2401 (Consideration of Fraud in a Financial Statement Audit).

Sample data is simulated. The cross-footing integrity check often produces a warning on QuickBooks-style "one row per leg" GL exports — this is expected and demonstrates the integrity layer working on realistic input rather than indicating a tool defect.

This project is a portfolio piece, not production audit software. It is not affiliated with any audit firm, and its outputs are not a substitute for professional auditor judgment.
