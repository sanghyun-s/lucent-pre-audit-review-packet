# AI Audit Risk Analyzer

> **Status:** Phase 4 shipped · Phase 5 planned · **Phase 4 shipped Jun 9, 2026**
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
| Phase 4 — GPT narrative layer + workflow UI | ✅ Shipped | Jun 9, 2026 | Live OpenAI integration producing 7-field audit memos with strict validator and deterministic fallback, concurrent generation, explicit 4-section workflow UI with card-with-hierarchy memo rendering |
| Phase 5 — Standards Grounding + deployment + polish | ⬜ Planned | — | Rule-based Standards Grounding panel (AS 5 / AS 2401 / AS 3 / COSO citations), CSV export expansion for all 7 memo fields, Vercel + Render deployment, README/branding finalization |

---

## What it does

Upload a GL CSV, configure the client profile (entity type, materiality benchmark, detection sensitivity, audit period), and the app runs the following pipeline in under a second:

1. **Validates** the file structure and required columns
2. **Cleans** and coerces dtypes (date → datetime, amount → numeric, derives `abs_amount`)
3. **Engineers 12 audit-domain features** — 6 Tier 1 features that feed the ML model (account-level magnitude z-score, round number, weekend posting, missing description, new vendor, near approval threshold) plus 6 Tier 2 mechanisms — 7 output columns — for display and override logic (control gap score, fraud-flag count + fraud risk flag, period-over-period %, vendor concentration %, year-end concentration, non-standard DR/CR pattern)
4. **Runs 4 data integrity checks** — hash total, cross-footing, date-in-period, account mapping
5. **Scores anomalies** with a hybrid ML layer: unsupervised Isolation Forest (200 trees, sensitivity-controlled contamination) for label-free anomaly detection, plus a weak-label supervised classifier that catches subtle fraud the unsupervised layer misses
6. **Applies the materiality filter** — downgrades or escalates the raw ML tier based on whether the dollar amount exceeds Performance / Transaction materiality
7. **Applies the qualitative override** — when ≥ 2 fraud indicators co-occur on a single transaction, escalates the tier *above* what materiality would assign (PCAOB AS 2401 / AS 5 qualitative materiality)
8. **Labels** findings with PCAOB-aligned language: *Potential Material Weakness Indicator*, *Potential Significant Deficiency*, *Monitor — Below Escalation Threshold*
9. **Returns** a sortable, exportable table of flagged transactions with the specific risk indicators that fired on each row, the supervised classifier's fraud probability, and qualitative override annotations
10. **On user request**, generates 7-field audit memos via `gpt-4o-mini` for the top-N most demo-relevant flagged transactions — each memo covers risk summary, assertion consideration, magnitude assessment, likelihood assessment, control/COSO consideration, recommended follow-up procedures, and a verbatim disclaimer. Output passes a strict validator (schema, length, banned-phrase, name-leakage, verbatim disclaimer) before display, with a deterministic rule-based fallback that satisfies the same validator by construction.

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
- **Quantitative materiality** — FS / Performance / Transaction thresholds with entity-type calibration (Public company 5%; Private for-profit, Non-profit, and Fund all 4% — entity type changes only the benchmark label, not the percentage)
- **Qualitative materiality override** — PCAOB AS 2401-aligned escalation rule encoding the audit principle that pattern co-occurrence is material regardless of dollar amount
- **PCAOB-aligned labeling** — never-conclusive language ("Potential Material Weakness Indicator", "Monitor — Below Escalation Threshold") instead of definitive findings
- **Data integrity layer** — hash total, cross-footing, date-in-period, and account-mapping checks running as a separate concern before ML scoring
- **Audit-memo discipline** — 7-field structured output mapped to FS assertions (Occurrence, Accuracy, Cutoff, Classification, Rights & Obligations, Valuation, Completeness) and COSO components (Control Environment, Risk Assessment, Control Activities, Information & Communication, Monitoring Activities)

### Backend engineering
- **FastAPI** — clean module separation (`features` / `model` / `scoring` / `integrity` / `narrative` / `narrative_validator` / `narrative_fallback` / `prompts` / `api`), typed responses, async-ready
- **TestClient + custom acceptance suite** — 30 done-criteria asserted across Phases 1–3, plus ~145 FastAPI endpoint contract checks including 80+ Phase 4b 7-field-shape assertions and 8 validator unit tests with deliberate mutation cases
- **Pipeline orchestration** — `run_hybrid_pipeline` ties unsupervised and supervised tracks together in a single call that's reachable both over HTTP and via direct Python import
- **Secrets hygiene** — environment-based config with `python-dotenv`, gitignored `.env`, `git check-ignore` verification, restricted-permission API keys
- **Graceful degradation** — narrative endpoint never raises on OpenAI errors, validator rejection, banned-phrase trips, or empty completions; every failure path routes through a deterministic fallback memo that satisfies the validator by construction
- **Concurrent LLM generation** — per-row OpenAI calls execute in parallel via `ThreadPoolExecutor`, reducing top-N=20 wall-clock time from ~80 seconds (sequential) to ~5 seconds while preserving deterministic ordering of results
- **Strict output validation** — independent `narrative_validator.py` checks JSON schema, per-field length bounds, follow-up list shape (3-5 items), verbatim disclaimer, banned-phrase scan, and name-leakage detection; any failure routes the row through the fallback transparently

### Frontend engineering
- **Next.js 14 (App Router)** with proxy configuration for backend interop
- **shadcn/ui + Tailwind** for composable design primitives without runtime CSS overhead, plus a custom Collapsible primitive written in pure React (no Radix dependency)
- **Interactive charting** with Plotly via `react-plotly.js`
- **Multi-state UI** — form validation, file upload, async analysis triggering, sortable/paginated/exportable result table
- **Explicit 4-section workflow** — engagement setup → data quality & risk signals → risk overview → flagged transaction review, with the data-integrity and feature-engineering panels collapsed to 1-line summaries by default to compact diagnostic content
- **Row-level expanders + conditional rendering** — clicking a flagged row reveals the full 7-field AI memo in a card-with-hierarchy layout (large risk_summary headline, 2x2 grid of structured fields, bulleted recommended procedures, muted disclaimer); CSV export conditionally includes narrative columns when narratives have been generated

### LLM integration
- **Cost-aware design** — Top-N capped at 20 (default 5), button-triggered generation rather than automatic, model choice (`gpt-4o-mini`) sized to task complexity; observed cost ~$0.003 per Top-10 7-field memo generation
- **Prompt engineering for a high-stakes domain** — banned-phrase enforcement, sentence-subject discipline (transaction not person), hedged-verb requirements, explicit framing that `fraud_probability` is a resemblance score not a fraud probability, assertion-mapping guide and COSO-mapping guide embedded in the system prompt for structured field generation
- **JSON-mode structured output** — `response_format={"type": "json_object"}` ensures the model emits parseable JSON; downstream validator enforces the strict 7-field schema before any output reaches the user
- **Demo-relevance sort** — backend re-sorts incoming rows by final_tier → qualitative override → fraud_risk_flag → anomaly score → amount so Top-N narratives are the most audit-meaningful items, not random
- **Post-generation validation** — JSON parse + schema check + banned-phrase scan + name-leakage detection + verbatim-disclaimer check on every memo; any failure routes through fallback so no fraud-conclusion language or hallucinated names ever reach the user
- **Field-level differentiation verified empirically** — diagnostic curl across 3 distinct flagged rows confirmed that 5 of 6 hidden memo fields show meaningful row-to-row variation (assertion mapping, COSO mapping, follow-up procedures vary by flag pattern), with `likelihood_assessment` deliberately consistent as the most rigid hedging claim

### Software engineering practice
- **Git hygiene** — meaningful commit messages, staged commits per phase, branch-based workflow, nine logical commits across the build to date
- **Pre-deployment verification** — diff-based comparison between staging files and live files before each major drop, backup snapshots, `git status` surface-area checks confirming only intended files modified, never committing untested code
- **Reproducibility** — `requirements.txt` pinned, sample data generator (`generate_sample_gl.py`) seeded for deterministic test runs
- **Documented decisions** — model comparison findings, phase plan, design rationales preserved in commit messages and README

---

## Architecture

```
┌─────────────────────────────┐         ┌────────────────────────────────────┐
│  Next.js frontend           │  HTTP   │  FastAPI backend                   │
│  (React 18, shadcn/ui,      │ ──────► │  (Python 3.13)                     │
│   Tailwind, plotly.js)      │  multi- │                                    │
│  Section 1 — Engagement     │  part   │  features.py    cleaning + 12 feats│
│    Setup                    │ ◄────── │  integrity.py   4 audit checks     │
│  Section 2 — Data Quality   │  JSON   │  model.py       hybrid ML layer:   │
│    & Risk Signals           │         │                  · Isolation Forest│
│  Section 3 — Risk Overview  │         │                  · weak-label RF   │
│  Section 4 — Flagged        │         │  scoring.py     materiality +      │
│    Transaction Review       │         │                  qualitative       │
│  (AI memo in row expanders) │         │                  override          │
│  Port 3000 (dev)            │         │  prompts.py     audit-language     │
│                             │         │                  system prompts    │
│                             │         │  narrative.py   GPT orchestrator   │
│                             │         │                  (concurrent)      │
│                             │         │  narrative_     7-field schema +   │
│                             │         │    validator.py  banned-phrase +   │
│                             │         │                  name-leakage      │
│                             │         │  narrative_     deterministic      │
│                             │         │    fallback.py   memo by construct │
│                             │         │  api.py         FastAPI routes     │
│                             │         │  Port 8000 (dev)                   │
└─────────────────────────────┘         └────────────────────────────────────┘
```

The frontend and backend are independently deployable. The same Python pipeline is reachable via:
- `POST /api/analyze` over HTTP — used by the Next.js UI for scoring
- `POST /api/narratives` over HTTP — used for on-demand AI memo generation on the top-N flagged rows (returns 7 fields per row)
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
- Recommended spend limit: ≤ $10 hard cap (observed Phase 4 cost: under $1 across all dev iterations)

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

## Narrative design — why the 7-field memo, validated, and fallback-protected

Phase 4 adds an LLM layer that translates already-scored findings into a structured audit memo. Each memo has seven required fields that mirror the structure of a workpaper review note:

| Field | Purpose |
|---|---|
| `risk_summary` | 1-2 sentence hedged summary of why the transaction warrants follow-up |
| `assertion_consideration` | Which FS assertion(s) at risk (Occurrence, Accuracy, Cutoff, Classification, etc.), with parenthetical reasoning |
| `magnitude_assessment` | Dollar amount situated relative to materiality threshold |
| `likelihood_assessment` | Co-occurrence reasoning — always hedged, never concludes fraud |
| `control_or_coso_consideration` | COSO component mapping (Control Activities, Information & Communication, Risk Assessment, etc.) |
| `recommended_follow_up` | List of 3-5 short imperative audit procedures |
| `disclaimer` | Verbatim "This analysis identifies risk indicators only..." |

Several design choices are worth noting because they reflect the constraints of using LLMs in a regulated domain:

1. **Button-triggered, not automatic.** Narrative generation runs only when the user explicitly clicks **Generate AI Narrative**, with a Top-N selector (default 5, max 20). This caps cost, gives the user a chance to inspect the flagged table first, and keeps the core scoring functional even if OpenAI is unavailable.

2. **Concurrent generation.** Per-row OpenAI calls execute in parallel via `ThreadPoolExecutor`. Top-N=20 finishes in ~5 seconds wall-clock instead of ~80 seconds sequential — keeping the user experience interactive while preserving deterministic ordering of results regardless of which call completes first.

3. **Backend re-sorts for demo relevance.** Incoming rows are sorted by final_tier (High first) → qualitative_override (fired first) → fraud_risk_flag (fired first) → anomaly_score (most anomalous first) → amount (largest first), then the top N are passed to the model. The narratives shown are the most audit-meaningful items, not the first N in the table's visible order.

4. **Audit-language discipline is enforced at three layers.**
   - **System prompt** instructs the model to use hedged verbs only, keep the transaction (not a person) as the subject of every sentence, ground summaries in observable facts, treat `fraud_probability` as a resemblance score, and emit strict JSON matching the 7-field schema. Embedded assertion-mapping and COSO-mapping guides constrain the model's choices to the framework vocabulary.
   - **Validator** (`narrative_validator.py`) checks every memo against the schema, per-field length bounds, follow-up list shape (3-5 items each within length bounds), verbatim disclaimer, banned-phrase scan (18 forbidden phrases), and name-leakage patterns (no "the employee", "the manager", etc.). Any failure routes the row through the fallback.
   - **Deterministic fallback** built from the row's own active flags produces an always-valid 7-field memo by construction (rule-based assertion and COSO mapping). The user sees a `GPT` or `Fallback` badge so the provenance is visible.

The result: memos that read like workpaper review notes (transaction-subject, hedged, grounded in observable facts) rather than confident accusations, with the entire chain auditable from prompt → model → validator → display.

---

## Workflow UI design — why the 4-section structure

The Phase 4c restructure of the frontend reflects how an auditor actually moves through a review, not how the engine happens to compute things. Four explicit numbered sections in order:

1. **Section 1 — Engagement Setup**: client profile, materiality benchmark, audit period, CSV upload. The sidebar form stays visible while scrolling so engagement context remains anchored.
2. **Section 2 — Data Quality & Risk Signals**: pre-ML integrity checks and feature-firing counts. Both panels collapse to 1-line summaries by default (e.g., "Data Integrity Checks · 3 Pass · 1 Warning · 0 Fail") so a quick-skim viewer doesn't get bogged down in diagnostics, but the detail is one click away.
3. **Section 3 — Risk Overview**: summary cards (total, flagged, %, risk rating), risk-tier distribution chart, top accounts by flagged amount. The "is anything actually wrong, and where?" zone.
4. **Section 4 — Flagged Transaction Review**: the flagged transactions table with per-row expanders that include the full 7-field AI audit memo when generated. The memo is rendered in a card-with-hierarchy layout — large `risk_summary` headline, 2×2 grid of structured fields, bulleted follow-up procedures, muted disclaimer. The AI memo is part of Section 4, not a separate section, because it's per-row analysis on top of the table.

The hierarchy makes the 60-second demo journey legible: open the app, see the engagement setup, get the data-quality-and-features signals at a glance, see the risk overview, drill into a flagged row, read the AI memo. No scrolling past irrelevant diagnostic detail to find the headline findings.

---

## Project structure

```
app3/
├── backend/
│   ├── api.py                     FastAPI app — /api/analyze, /api/narratives, /api/options, /api/healthz
│   ├── api_test.py                End-to-end tests using TestClient (~145 assertions)
│   ├── features.py                Cleaning + 12 engineered features (6 T1 for ML, 6 T2 for display)
│   ├── integrity.py               4 pre-analysis data integrity checks
│   ├── model.py                   Hybrid ML layer: IsolationForest + weak-label RandomForest
│   ├── scoring.py                 Materiality filter + qualitative override + supervised escalation
│   ├── prompts.py                 System prompts (risk_summary + full 7-field memo) + 18 banned phrases
│   ├── narrative.py               GPT orchestrator, demo-relevance sort, concurrent ThreadPoolExecutor
│   ├── narrative_validator.py     7-field schema + banned-phrase + length + name-leakage validator
│   ├── narrative_fallback.py      Deterministic fallback memo (validator-passing by construction)
│   ├── generate_sample_gl.py      2,000-row simulated GL with planted anomalies
│   ├── smoke_test.py              Asserts 30 Phase 1 + Phase 2 + Phase 3 done-criteria
│   ├── requirements.txt
│   ├── .env                       Local secrets (gitignored)
│   └── sample_data/
│       └── sample_gl.csv          Generated demo data
│
└── frontend/
    ├── app/
    │   ├── layout.jsx
    │   ├── page.jsx               Main analyzer page with explicit Section 1/2/3/4 structure
    │   └── globals.css
    ├── components/
    │   ├── ClientProfileForm.jsx
    │   ├── CsvUpload.jsx
    │   ├── IntegrityPanel.jsx     Collapsible 1-line summary by default
    │   ├── FeatureFiringPanel.jsx Collapsible 1-line summary by default
    │   ├── SummaryCards.jsx
    │   ├── MaterialityBanner.jsx
    │   ├── RiskDistributionChart.jsx
    │   ├── TopAccountsChart.jsx
    │   ├── FlaggedTable.jsx       Table + Top-N controls + 7-field memo card-with-hierarchy in row expanders
    │   └── ui/                    shadcn primitives + custom Collapsible
    │       ├── badge.jsx
    │       ├── button.jsx
    │       ├── card.jsx
    │       ├── collapsible.jsx    Pure-React disclosure, no Radix dependency
    │       ├── input.jsx
    │       ├── label.jsx
    │       └── select.jsx
    ├── lib/
    │   ├── api.js                 Thin fetch wrapper for the FastAPI endpoints
    │   └── utils.js               shadcn cn() helper
    ├── .env.local.example         Documents optional NEXT_PUBLIC_API_BASE_URL override
    ├── next.config.js             Proxies /api/* to FastAPI (localhost:8000) in dev
    ├── tailwind.config.js
    └── package.json
```

Planned additions in Phase 5: `backend/standards_grounding.py` (rule-based mapping from row attributes to AS 5 / AS 2401 / AS 3 / COSO citations) + corresponding `frontend/components/StandardsGrounding.jsx` rendering the citations inline at the bottom of each row expander.

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

The FastAPI server is now serving on `http://localhost:8000`. Hit `/api/healthz` to verify — should return `{"status":"ok","version":"0.4.1"}`.

### Frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Upload `backend/sample_data/sample_gl.csv`, click **Run Analysis**, and the full pipeline runs end-to-end against the FastAPI backend. To see the AI narrative layer in action, click **Generate AI Narrative** above the flagged transactions table — the top-N memos (default 5, max 20) generate concurrently in roughly 5 seconds and render inside row expanders as you click them.

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
python api_test.py               # FastAPI endpoint contract (~145 checks including Phase 4b validator tests)
```

`api_test.py` deliberately clears `OPENAI_API_KEY` so it exercises the fallback path without making real API calls. Real LLM testing is done in the browser against a running server.

---

## Audit theory references

The 12 features, the materiality filter, the qualitative override, and the narrative prompts are anchored to specific audit-standard sources:

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
| Narrative — hedged language | AU-C 315, PCAOB AS 2401 | Risk-indicator framing, never fraud conclusions |
| Narrative — subject discipline | Audit professional standards | Transaction/control as subject, not the person who recorded it |
| Memo — `assertion_consideration` | AU-C 315, FS assertions framework | Occurrence, Accuracy, Cutoff, Classification, Rights & Obligations, Valuation, Completeness |
| Memo — `control_or_coso_consideration` | COSO 2013 framework | Control Environment, Risk Assessment, Control Activities, Information & Communication, Monitoring Activities |

Phase 5 will add a structured Standards Grounding panel below each memo that surfaces explicit AS 5 / AS 2401 / AS 3 / COSO citations via a rule-based mapping rather than free-form LLM citation, to keep regulatory references deterministic and auditable.

---

## Future improvements (Phase 5)

Items planned to bring the project to demo-ready and deployable state:

- **Standards Grounding panel** — backend-derived rule-based mapping from row attributes to 4 fixed framework categories (PCAOB AS 5, AS 2401, AS 3, COSO), rendered inline at the bottom of each row expander
- **CSV export expansion** — surface all 7 memo fields in the downloaded CSV (currently only `risk_summary` + `narrative_status` are exported), so the user can take all the audit reasoning into their workpapers
- **Deployment** — Vercel (frontend) + Render or Fly.io (backend), ≈ $5-7/mo, custom subdomain, server-side `OPENAI_API_KEY` as secret
- **README finalization + product naming** — settle the product name (candidates: NEXUS, INDICIA, LUMEN, FORUM, VERITAS, AUSPEX, SAGE, PROBE, LAUREL, PARSE), update README and repository name accordingly
- **Excel workbook export** — multi-sheet `.xlsx` via `openpyxl`: summary, flagged transactions, integrity findings, narrative memos
- **Period-over-period fluctuation table** — account-level variance analysis as a separate analytical procedure
- **Frontend badge column** — visible "Override" and "Fraud Prob" cells in the flagged table (currently in the API response and the row expander, but not as visible columns)
- **`fraud_probability` relabel** — the system prompt already frames the supervised score as "not a fraud probability," but the UI still displays "Fraud probability" and `scoring.py`'s escalation note emits `P(fraud)=…`. Rename the displayed label and that note string to "Risk-Pattern Similarity" so user-facing language matches the risk-indication framing; the internal column name can stay
- **Centralize narrative transport** — move the inline `/api/narratives` fetch out of `FlaggedTable.jsx` into `lib/api.js` as `generateNarratives()`, matching how `analyze()` is structured
- **CI/CD** — GitHub Actions running `smoke_test.py` and `api_test.py` on every push
- **API observability** — structured logging for narrative-layer cost and latency tracking
- **Multi-period support** — comparison mode across two uploaded GL periods

---

## Methodology and limitations

This tool identifies *risk indicators* using statistical anomaly detection, weak-label supervised classification, and materiality thresholds. It does not determine intent, conclude fraud, or issue audit opinions. The PCAOB-aligned labels use "Potential", "Indicator", and "Monitor" throughout — never definitive language.

The supervised layer is trained on weak labels derived from rule-based fraud indicators, then applied in-process to the same upload. The honest interpretation of its `fraud_probability` is "this transaction resembles the rule-flagged transactions in continuous-feature space" — it is a smoothing of the rule rather than an independent validator. The qualitative override and supervised escalation are designed to never lower a tier, only raise it, so the materiality filter's conservative output remains the floor.

The GPT narrative layer is constrained to risk-indication language with explicit banned phrases ("fraud occurred," "the perpetrator," "this proves," etc.) enforced both in the system prompt and in a post-generation validator. Any banned-phrase trip, schema violation, length bound violation, name-leakage pattern, or non-verbatim disclaimer routes the row through a deterministic fallback memo that satisfies the same validator by construction. The layer translates already-scored results into hedged audit-review memos; it does not extend the scoring logic itself, and it cannot conclude fraud or issue an audit opinion regardless of how the underlying ML output is interpreted.

Findings should be corroborated with documentary evidence and discussions with management consistent with AU-C 315 (Understanding the Entity and Its Environment) and PCAOB AS 2401 (Consideration of Fraud in a Financial Statement Audit).

Sample data is simulated. The cross-footing integrity check often produces a warning on QuickBooks-style "one row per leg" GL exports — this is expected and demonstrates the integrity layer working on realistic input rather than indicating a tool defect.

This project is a portfolio piece, not production audit software. It is not affiliated with any audit firm, and its outputs are not a substitute for professional auditor judgment.
