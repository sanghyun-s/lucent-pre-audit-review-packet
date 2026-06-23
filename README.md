# LUCENT — Ledger Understanding, Control Evidence & Narrative Triage

> *See what to check, why it matters, and what evidence to request before the handoff.*

> **Status:** Phases 1–5 shipped (incl. 5A/5B business-context refactor) · **Phase 6 planned**
> **Stack:** FastAPI · Next.js 14 · scikit-learn · OpenAI · Tailwind · shadcn/ui · Plotly

**A pre-audit review packet for general-ledger exports.** Upload a company-level QuickBooks-style GL, and LUCENT narrows a large transaction population into a prioritized review queue, explains the risk indicators in plain language, and shows what evidence to request — before close, CPA handoff, audit readiness, or investor diligence.

Under the hood it pairs ML anomaly detection with materiality-calibrated risk scoring, PCAOB-aligned review labels, and a live LLM narrative layer that translates findings into hedged, framework-grounded review memos. Built as a portfolio piece exploring the intersection of accounting standards, machine learning, and LLM-driven narrative generation.

**The framing is deliberate: risk indication, not fraud detection.** A real client GL never arrives with confirmed fraud labels, so LUCENT treats machine-learning output as a triage signal, then layers audit logic and cautious narrative language on top. It narrows the review population and explains why selected rows deserve a closer look — it supports professional judgment, it does not replace it. LUCENT reviews the general ledger *before* financial statements are finalized; it does not prepare financial statements, perform an audit, or issue an opinion.

---

## Who it's for, and when

- **Who** — SMBs, startups, and boutique accounting teams that can't afford enterprise audit tooling or heavy outside consulting.
- **When** — before a close, a year-end review, a CPA handoff, audit readiness, or investor diligence.
- **Input** — a company-level QuickBooks-style general-ledger export (CSV).
- **Output** — a prioritized transaction review queue, plain-English risk indicators, evidence-request memos, and a signal guide that explains every label.
- **Not for** — fraud conclusions, audit opinions, preparing or reviewing full financial statements, or replacing professional judgment.

---

## Build progress

A journal-referenced timeline. Phase 4 shipped in three sub-phases (4a → 4b → 4c); Phase 5 includes the 5A/5B business-context refactor and the LUCENT rebrand.

| Phase | Status | Date | Summary |
|---|---|---|---|
| **Phase 1 — MVP pipeline** | ✅ Shipped | May 17, 2026 | Streamlit prototype proving the full loop end-to-end: GL CSV upload, 7 required columns, six Tier 1 features, StandardScaler + Isolation Forest, materiality filter, review labels, table + two charts. Outcome: a raw GL can become a review queue. |
| **Phase 2 — Audit depth + full-stack migration** | ✅ Shipped | May 18, 2026 | Added six Tier 2 mechanisms and four data-integrity checks; migrated off Streamlit to a **FastAPI** backend and a **Next.js / shadcn** frontend. From prototype script to full-stack application. |
| **Phase 3 — Hybrid scoring + qualitative judgment** | ✅ Shipped | May 27, 2026 | The audit-logic core. Evidence-based hybrid ML: Isolation Forest (primary) + weak-label Random Forest (secondary similarity); the PCAOB AS 2401 qualitative override; supervised escalation; and explicit `raw_tier` vs `final_tier` separation. |
| **Phase 4a — Narrative integration** | ✅ Shipped | Jun 2026 | Button-triggered, top-N narrative generation wired end-to-end (frontend → backend → OpenAI → row display). A single `risk_summary` field to prove the path. Narratives bound to flagged rows, not a page-bottom block. |
| **Phase 4b — 7-field memo + validator + fallback** | ✅ Shipped | Jun 2026 | Expanded to the full seven-field review memo; added the strict validator (schema, length, banned phrases, name-leakage, verbatim disclaimer) and the deterministic rule-based fallback (valid by construction); concurrent generation via `ThreadPoolExecutor` (~80s → ~5s for top-N=20). |
| **Phase 4c — 4-section workflow UI** | ✅ Shipped | Jun 9, 2026 (`42fb5a7`) | Frontend restructured into four numbered sections; Section 2 panels collapse to one-line summaries; flagged-row expander renders the 7-field memo as a card-with-hierarchy. Backend untouched. From scoring dashboard to review workflow. |
| **Phase 5 — Testing, polish, pre-deploy bundle** | ✅ Shipped | Jun 2026 | Three profiled sample ledgers + a four-scenario validation matrix; the pre-deploy bundle (Risk-Pattern Similarity relabel, 7-field CSV export, Override/Similarity columns, centralized narrative transport, Top-N reconciliation). Verified end-to-end on a Jun 14 live run with all-GPT narratives. |
| **Phase 5A — Business-context & signal-dictionary refactor** | ✅ Shipped | Jun 22, 2026 (`09c45f1`) | Frontend-only. Business Use Case card, softened subtitle, data-provenance note, review-packet section renames, a collapsible Data Dictionary (17 signal cards), and softer table column labels (Audit Review Label, Co-occurrence, Control Signal). Engine untouched. |
| **Phase 5B — Review-packet UX & evidence-request layer** | ✅ Shipped | Jun 22, 2026 (`5fb0bb8`, fix `d4015db`) | Frontend-only. Review Packet Summary (suggested next action + top review drivers), an emphasized "Evidence to Request" block in each memo, and a Data Quality Exceptions panel. Includes a safe-render fix for structured integrity detail. Engine untouched. |
| **LUCENT rebrand** | ✅ Shipped | Jun 23, 2026 | Final identity pass: ARGUS → LUCENT across the frontend and README, business-readable header and metadata, and the "PCAOB Risk Tier" chart title softened to "Review Tier." Public-facing only — internal logic and variable names unchanged. |
| **Phase 6 — Deployment & extensions** | ⬜ Planned | — | Deployment (Vercel + Render/Fly.io), repository rename, Standards Grounding panel, Excel workbook export, CI/CD, API observability, period-over-period fluctuation table, multi-period comparison, row-level data-quality exception drill-down. |

---

## What it does

Upload a GL CSV, configure the review context (entity type, materiality benchmark, detection sensitivity, review period), and the app runs the following pipeline in under a second:

1. **Validates** the file structure and required columns
2. **Cleans** and coerces dtypes (date → datetime, amount → numeric, derives `abs_amount`)
3. **Engineers 12 audit-domain features** — 6 Tier 1 features that feed the ML model (account-level magnitude z-score, round number, weekend posting, missing description, new vendor, near approval threshold) plus 6 Tier 2 mechanisms — 7 output columns — for display and override logic (control gap score, fraud-flag count + risk-indicator co-occurrence flag, period-over-period %, vendor concentration %, year-end concentration, non-standard DR/CR pattern)
4. **Runs 4 data integrity checks** — hash total, cross-footing, date-in-period, account mapping
5. **Scores anomalies** with a hybrid ML layer: unsupervised Isolation Forest (200 trees, sensitivity-controlled contamination) for label-free anomaly detection, plus a weak-label supervised layer that adds a **risk-pattern similarity** signal for subtle cases the unsupervised layer may not prioritize (see *Model design*)
6. **Applies the materiality filter** — the only step that can *lower* a tier: it keeps the raw ML tier at or above Transaction materiality, downgrades one tier between Performance and Transaction materiality, and sends anything below Performance materiality to *Monitor*
7. **Applies the qualitative override** — when ≥ 2 fraud-related indicators co-occur on a single transaction, escalates **one tier above the raw ML tier** (not the materiality-adjusted tier), so a small-dollar row that materiality pushed down can be restored (PCAOB AS 2401 qualitative materiality; AS 2201, legacy AS 5)
8. **Labels** findings with PCAOB-aligned review language: *Potential Material Weakness Indicator*, *Potential Significant Deficiency*, *Monitor — Below Escalation Threshold*
9. **Returns** a sortable, exportable table of flagged transactions with the specific risk indicators that fired on each row, a **risk-pattern similarity score** (internally `fraud_probability` — a resemblance score, **not** a probability that fraud occurred), and qualitative override annotations
10. **On user request**, generates 7-field review memos via `gpt-4o-mini` for the top-N most demo-relevant flagged transactions — each memo covers risk summary, assertion consideration, magnitude assessment, likelihood assessment, control/COSO consideration, evidence to request, and a verbatim disclaimer. Output passes a strict validator (schema, length, banned-phrase, name-leakage, verbatim disclaimer) before display, with a deterministic rule-based fallback that satisfies the same validator by construction.

The core thesis: a generic ML anomaly detector finds statistically unusual transactions. An audit-aware tool also asks whether the dollar amount matters, recognizes that some patterns are material regardless of amount, and translates findings into the cautious, hedged language standards require.

---

## The frontend as a review packet

The interface is organized so a non-technical reviewer can answer "what is this, what do I upload, what do I get, what do I do next" without reading the code:

- **Header + business use-case card** — what it's for, input, output, and an explicit "not for," before any workflow.
- **Section 1 — Review Context & Input File** — client profile, materiality preview, CSV upload, and a data-provenance note disclosing that demo datasets are seeded synthetic ledgers (no real client data).
- **Section 2 — Data Quality Check** — a Data Quality Exceptions panel surfacing any non-passing integrity check, plus collapsible integrity and feature-firing panels.
- **Section 3 — Review Queue Summary** — a Review Packet Summary card (input file, period, population, queue size, data-quality line, *suggested next action*, *top review drivers*), then the metric cards and charts.
- **Section 4 — Flagged Transactions & Evidence Requests** — the flagged table with per-row expanders; each memo emphasizes an **Evidence to Request** block as the reviewer's next action.
- **Section 5 — How to Read LUCENT Signals** — a collapsible Data Dictionary with 17 plain-English signal cards (what it means / why it matters / what to request / what it does not mean).

The 5A/5B refactor and the LUCENT rebrand that produced this layer were **frontend-only** — the scoring, model, integrity, validator, and narrative logic were not touched.

---

## Skills demonstrated

This project exercises a deliberate breadth across full-stack engineering, applied ML, and domain modeling.

### Applied machine learning
- **Unsupervised anomaly detection** — Isolation Forest with engineered audit features, contamination sweep, and sensitivity-controlled tuning
- **Weak-label supervised learning** — bootstrapping training labels from rule-derived indicators to add a risk-pattern similarity signal for an evidence-identified subtle-pattern gap (67% subtle-archetype recall in a controlled simulation), while keeping the model honest by excluding the rule's own flag columns from the training feature set
- **Evidence-based model selection** — a controlled simulation with three fraud archetypes (obvious, structured, subtle) and per-archetype recall measurement to justify a hybrid approach rather than committing to either pure paradigm
- **Feature engineering for a regulated domain** — translating audit standards into 12 numeric features, each traceable to a specific source (AU-C 315, PCAOB AS 2401, COSO components)

### Domain modeling — accounting & audit
- **Quantitative materiality** — FS / Performance / Transaction thresholds with entity-type calibration (Public company 5%; Private for-profit, Non-profit, and Fund all 4% — entity type changes only the benchmark label, not the percentage)
- **Qualitative materiality override** — PCAOB AS 2401-aligned escalation rule encoding the audit principle that pattern co-occurrence is material regardless of dollar amount
- **PCAOB-aligned labeling** — never-conclusive language ("Potential Material Weakness Indicator", "Monitor — Below Escalation Threshold") instead of definitive findings
- **Data integrity layer** — hash total, cross-footing, date-in-period, and account-mapping checks running as a separate concern before ML scoring
- **Review-memo discipline** — 7-field structured output mapped to FS assertions (Occurrence, Accuracy, Cutoff, Classification, Rights & Obligations, Valuation, Completeness) and COSO components (Control Environment, Risk Assessment, Control Activities, Information & Communication, Monitoring Activities)

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
- **Business-readable review-packet layer** — a use-case card, data-provenance note, review-packet summary with suggested next action and top review drivers, an evidence-request emphasis in each memo, a data-quality exceptions panel, and a 17-card signal dictionary — all built on top of an unchanged engine
- **Row-level expanders + conditional rendering** — clicking a flagged row reveals the full 7-field memo in a card-with-hierarchy layout (large risk_summary headline, 2x2 grid of structured fields, bulleted evidence-to-request, muted disclaimer); CSV export conditionally includes narrative columns when narratives have been generated

### LLM integration
- **Cost-aware design** — Top-N capped at 20 (default 10), button-triggered generation rather than automatic, model choice (`gpt-4o-mini`) sized to task complexity; observed cost ~$0.003 per Top-10 7-field memo generation
- **Prompt engineering for a high-stakes domain** — banned-phrase enforcement, sentence-subject discipline (transaction not person), hedged-verb requirements, explicit framing that `fraud_probability` is a resemblance score not a fraud probability, assertion-mapping guide and COSO-mapping guide embedded in the system prompt for structured field generation
- **JSON-mode structured output** — `response_format={"type": "json_object"}` ensures the model emits parseable JSON; downstream validator enforces the strict 7-field schema before any output reaches the user
- **Demo-relevance sort** — backend re-sorts incoming rows by final_tier → qualitative override → risk-indicator co-occurrence → anomaly score → amount so Top-N narratives are the most audit-meaningful items, not random
- **Post-generation validation** — JSON parse + schema check + banned-phrase scan + name-leakage detection + verbatim-disclaimer check on every memo; any failure routes through fallback so no fraud-conclusion language or hallucinated names ever reach the user
- **Field-level differentiation verified empirically** — diagnostic curl across 3 distinct flagged rows confirmed that 5 of 6 hidden memo fields show meaningful row-to-row variation (assertion mapping, COSO mapping, follow-up procedures vary by flag pattern), with `likelihood_assessment` deliberately consistent as the most rigid hedging claim

### Software engineering practice
- **Git hygiene** — meaningful commit messages, staged commits per phase, logical commits across the build to date
- **Pre-deployment verification** — diff-based comparison between staging files and live files before each major drop, backup snapshots, `git status` surface-area checks confirming only intended files modified, never committing untested code
- **Reproducibility** — `requirements.txt` pinned, seeded sample-data generators (`generate_sample_gl.py`, `generate_sample_variants.py`) for deterministic test runs
- **Documented decisions** — model comparison findings, phase plan, and design rationales preserved in commit messages and `docs/`

---

## Architecture

```
┌─────────────────────────────┐         ┌────────────────────────────────────┐
│  Next.js frontend           │  HTTP   │  FastAPI backend                   │
│  (React 18, shadcn/ui,      │ ──────► │  (Python 3.13)                     │
│   Tailwind, plotly.js)      │  multi- │                                    │
│  1 Review Context & Input   │  part   │  features.py    cleaning + 12 feats│
│  2 Data Quality Check       │ ◄────── │  integrity.py   4 audit checks     │
│  3 Review Queue Summary     │  JSON   │  model.py       hybrid ML layer:   │
│  4 Flagged Transactions &   │         │                  · Isolation Forest│
│    Evidence Requests        │         │                  · weak-label RF   │
│  5 How to Read LUCENT       │         │  scoring.py     materiality +      │
│    Signals (dictionary)     │         │                  qualitative       │
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

The frontend and backend are independently deployable, and the two HTTP endpoints are independent — if OpenAI is unavailable, GL upload, scoring, the flagged table, and charts all still work. The same Python pipeline is reachable via:
- `POST /api/analyze` over HTTP — GL validation, feature engineering, anomaly scoring, audit scoring, table/chart output (used by the Next.js UI)
- `POST /api/narratives` over HTTP — on-demand AI memo generation on the top-N flagged rows (returns 7 fields per row)
- Direct import (`from features import engineer_features`) — used by `smoke_test.py` for regression testing

---

## Project structure

```
app3/
├── backend/
│   ├── api.py                     FastAPI app — /api/analyze, /api/narratives, /api/options, /api/healthz
│   ├── api_test.py                End-to-end tests using TestClient (~145 assertions)
│   ├── features.py                Cleaning + 12 engineered features (6 T1 for ML, 6 T2 / 7 cols for display)
│   ├── integrity.py               4 pre-analysis data integrity checks
│   ├── model.py                   Hybrid ML layer: IsolationForest + weak-label RandomForest
│   ├── scoring.py                 Materiality filter + qualitative override + supervised escalation
│   ├── prompts.py                 System prompts (risk_summary + full 7-field memo) + 18 banned phrases
│   ├── narrative.py               GPT orchestrator, demo-relevance sort, concurrent ThreadPoolExecutor
│   ├── narrative_validator.py     7-field schema + banned-phrase + length + name-leakage validator
│   ├── narrative_fallback.py      Deterministic fallback memo (validator-passing by construction)
│   ├── generate_sample_gl.py      2,000-row simulated reference GL with planted anomalies (seeded)
│   ├── generate_sample_variants.py  Three profiled ledgers: clean / high-risk / non-profit (seeded)
│   ├── smoke_test.py              Asserts 30 Phase 1 + Phase 2 + Phase 3 done-criteria
│   ├── requirements.txt
│   ├── .env                       Local secrets (gitignored)
│   └── sample_data/
│       ├── sample_gl.csv          2,000-row reference ledger (≈ Moderate at Balanced)
│       ├── sample_gl_clean.csv    450-row low-anomaly ledger (Low — credibility case)
│       ├── sample_gl_high_risk.csv  800-row dense-anomaly ledger (Elevated — override showcase)
│       └── sample_gl_nonprofit.csv  550-row non-profit chart of accounts (pair with entity = Non-profit)
│
├── frontend/
│   ├── app/
│   │   ├── layout.jsx
│   │   ├── page.jsx               Main analyzer page — Sections 1–5, review-packet framing
│   │   └── globals.css
│   ├── components/
│   │   ├── ClientProfileForm.jsx
│   │   ├── CsvUpload.jsx
│   │   ├── BusinessContextCard.jsx   Use case / input / output / not-for
│   │   ├── DataProvenanceNote.jsx     Synthetic-data disclosure at upload
│   │   ├── IntegrityPanel.jsx         Collapsible 1-line summary by default
│   │   ├── FeatureFiringPanel.jsx     Collapsible 1-line summary by default
│   │   ├── DataQualityExceptions.jsx  Surfaces non-passing integrity checks
│   │   ├── ReviewPacketSummary.jsx    Suggested next action + top review drivers
│   │   ├── SummaryCards.jsx
│   │   ├── MaterialityBanner.jsx
│   │   ├── RiskDistributionChart.jsx
│   │   ├── TopAccountsChart.jsx
│   │   ├── FlaggedTable.jsx           Table + Top-N controls + 7-field memo (Evidence to Request emphasized)
│   │   ├── DataDictionary.jsx         Collapsible Section 5 — 17 signal cards
│   │   ├── SignalCard.jsx             One dictionary entry (means / matters / request / does-not-mean)
│   │   └── ui/                        shadcn primitives + custom Collapsible
│   │       ├── badge.jsx
│   │       ├── button.jsx
│   │       ├── card.jsx
│   │       ├── collapsible.jsx        Pure-React disclosure, no Radix dependency
│   │       ├── input.jsx
│   │       ├── label.jsx
│   │       └── select.jsx
│   ├── lib/
│   │   ├── api.js                 Thin fetch wrapper for the FastAPI endpoints
│   │   └── utils.js               shadcn cn() helper
│   ├── .env.local.example         Documents optional NEXT_PUBLIC_API_BASE_URL override
│   ├── next.config.js             Proxies /api/* to FastAPI (localhost:8000) in dev
│   ├── jsconfig.json              Path alias (@/* → ./*)
│   ├── tailwind.config.js
│   └── package.json
│
└── docs/
    └── COMPARISON_FINDINGS.md     Hybrid model-selection simulation results
                                   (planning docs — blueprint, phase plan, design brief — live alongside)
```

Planned additions in Phase 6: `backend/standards_grounding.py` (rule-based mapping from row attributes to AS 2401 / AS 2201 / AS 1215 / COSO 2013 citations) + corresponding `frontend/components/StandardsGrounding.jsx` rendering the citations inline at the bottom of each row expander.

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

### LLM specific
- OpenAI API key with chat completions permission, stored in `backend/.env` (gitignored)
- Recommended spend limit: ≤ $10 hard cap (observed cost: under $1 across all dev iterations)

---

## Model design — why hybrid

The natural ML question for LUCENT is "supervised or unsupervised?" Both approaches have a literature in fraud detection, and they make different demands. To decide deliberately, I built a controlled simulation: a 2,000-row synthetic GL with hidden ground-truth labels across three archetypes (statistically obvious, threshold-evading "structured", and quiet "subtle"), then ran both approaches on identical data and compared.

The findings:

- **Pure unsupervised (Isolation Forest)** caught 100% of obvious, 100% of structured, and 67% of subtle archetypes — with no labels required. This is the only mode that works on a real client's GL upload, where no labels exist.
- **Pure supervised (Random Forest)** scored higher overall, but cannot train on real GL data because it requires labels that aren't there. Its high score on the simulation was partly a synthetic-data artifact.
- **The 67% subtle gap** is the real, evidence-based case for adding a supervised layer.

The implementation is a hybrid:

1. **Track 1 — Unsupervised Isolation Forest** stays as the primary detector. It produces `anomaly_score` and `raw_tier`, runs on any GL upload, and doesn't depend on labels.
2. **Track 2 — Weak-label Random Forest** trains in-process on each upload, using the rule-based risk-indicator co-occurrence flag as a weak label. Its training features deliberately exclude the five fraud-indicator flags themselves, so the classifier cannot trivially reproduce the rule — it must learn from continuous and structural features (amount, account z-score, period-over-period change, vendor concentration, etc.). This is how it adds genuine signal for subtle risk patterns rather than restating what the rule already says. Because it trains and predicts on the same upload, its output is honestly a **risk-pattern similarity score**, not a validated fraud probability.
3. **The qualitative override** fires when ≥ 2 fraud-related indicators co-occur on a single transaction, escalating the tier *one step above the raw ML tier*. This encodes PCAOB AS 2401 qualitative materiality: the co-occurrence of red flags is material regardless of dollar amount because it suggests a control breakdown whose potential magnitude exceeds the individual transaction.
4. **Supervised escalation** acts as a gentler secondary signal — when the similarity score ≥ 0.50 and the qualitative override hasn't already fired, the tier nudges up by one level.

The result is a layered detection system where each layer has a defined role: anomaly detection finds statistical outliers, the materiality filter applies quantitative judgment, the qualitative override applies pattern-based judgment, and the supervised layer adds a smoothed second opinion for subtle cases.

---

## Scoring logic

The scoring layer runs in a fixed order. **Materiality is the only step that can lower a tier; the two escalation steps only raise it**, so the conservative materiality output is the floor.

**1. Materiality filter** (uses Performance and Transaction materiality):

| raw tier | amount ≥ Transaction | Performance ≤ amount < Transaction | amount < Performance |
|---|---|---|---|
| High | High | Medium | Monitor |
| Medium | Medium | Low | Monitor |
| Low | Low | Monitor | Monitor |

**2. Qualitative override** — if the risk-indicator co-occurrence flag is active (≥ 2 of the five fraud-related binary flags: round number, weekend posting, missing description, new vendor, near approval threshold), escalate to `raw_tier + 1`, applied only if strictly higher than the current tier. Because it references the *raw* tier, it can restore a row that materiality pushed to Monitor. (The account-level z-score appears in active flags but is **not** part of the co-occurrence count.)

**3. Supervised escalation** — if the similarity score ≥ 0.50 and the override has not already fired, nudge the final tier up one level (capped at High). Never compounds with the override.

**4. Review labels** — High → *Potential Material Weakness Indicator*; Medium → *Potential Significant Deficiency*; Low/Monitor → *Monitor — Below Escalation Threshold*. These are PCAOB-aligned, severity-style triage labels, not audit conclusions.

---

## Narrative design — why the 7-field memo, validated, and fallback-protected

The LLM layer translates already-scored findings into a structured review memo. Each memo has seven required fields that mirror the structure of a workpaper review note:

| Field | Purpose |
|---|---|
| `risk_summary` | 1-2 sentence hedged summary of why the transaction warrants follow-up |
| `assertion_consideration` | Which FS assertion(s) at risk (Occurrence, Accuracy, Cutoff, Classification, etc.), with parenthetical reasoning |
| `magnitude_assessment` | Dollar amount situated relative to materiality threshold |
| `likelihood_assessment` | Co-occurrence reasoning — always hedged, never concludes fraud |
| `control_or_coso_consideration` | COSO component mapping (Control Activities, Information & Communication, Risk Assessment, etc.) |
| `recommended_follow_up` | List of 3-5 short imperative audit procedures (shown as "Evidence to Request") |
| `disclaimer` | Verbatim "This analysis identifies risk indicators only..." |

Several design choices reflect the constraints of using LLMs in a regulated domain:

1. **Button-triggered, not automatic.** Generation runs only when the user clicks **Generate AI Narrative**, with a Top-N selector (default 10, max 20). This caps cost, lets the user inspect the flagged table first, and keeps the core scoring functional even if OpenAI is unavailable.
2. **Concurrent generation.** Per-row calls execute in parallel via `ThreadPoolExecutor`. Top-N=20 finishes in ~5 seconds instead of ~80, with deterministic ordering preserved regardless of completion order.
3. **Backend re-sorts for demo relevance.** Incoming rows are sorted by final_tier → qualitative override → risk-indicator co-occurrence → anomaly_score → amount, then the top N go to the model — so the narratives shown are the most audit-meaningful items.
4. **Audit-language discipline is enforced at three layers.**
   - **System prompt** — hedged verbs only, transaction (not a person) as the subject of every sentence, summaries grounded in observable facts, `fraud_probability` framed as a resemblance score, strict 7-field JSON, with embedded assertion- and COSO-mapping guides.
   - **Validator** (`narrative_validator.py`) — schema, per-field length bounds, follow-up shape (3-5 items), verbatim disclaimer, an 18-phrase banned-phrase scan, and name-leakage patterns. Any failure routes the row to the fallback.
   - **Deterministic fallback** (`narrative_fallback.py`) — rule-based 7-field memo built from the row's own flags, valid by construction. A `GPT` or `Fallback` badge makes provenance visible.

The validator guarantees the memo is **safe and well-formed — not that GPT picked the correct assertion or COSO component**. The fallback is the only path provably correct by construction. The layer translates already-scored results; it does not extend the scoring and cannot conclude fraud.

---

## Workflow UI design — why the section structure

The section flow reflects how an auditor moves through a review, not how the engine computes:

1. **Section 1 — Review Context & Input File**: client profile, materiality benchmark, review period, CSV upload, and the data-provenance note.
2. **Section 2 — Data Quality Check**: a Data Quality Exceptions panel for any non-passing check, plus integrity and feature-firing panels collapsed to 1-line summaries by default (e.g., "Data Integrity Checks · 3 Pass · 1 Warning · 0 Fail"), detail one click away.
3. **Section 3 — Review Queue Summary**: the Review Packet Summary card (population, queue size, data quality, suggested next action, top review drivers), then summary cards, tier-distribution chart, and top accounts by flagged amount.
4. **Section 4 — Flagged Transactions & Evidence Requests**: the flagged table with per-row expanders containing the full 7-field memo (large `risk_summary` headline, 2×2 grid of structured fields, an emphasized **Evidence to Request** block, muted disclaimer; context fields — materiality annotation, anomaly score, similarity score, override note — beneath).
5. **Section 5 — How to Read LUCENT Signals**: the collapsible Data Dictionary, available even before an upload.

The hierarchy makes the 60-second demo journey legible: open the app, read the use case, define the engagement, scan the data-quality signals, read the review summary, drill into a flagged row, read the memo and the evidence to request.

---

## Validation — controlled test runs

LUCENT was run across four scenarios on generated ledgers built to exercise specific behavior:

| Scenario | Flagged | Flagged % | Rating | What it confirms |
|---|---:|---:|---|---|
| Clean · Conservative | 2 | 0.4% | Low | No over-flagging — only genuine outliers survive |
| Clean · Balanced | 12 | 2.7% | Moderate | Sensitivity widens the net; zero overrides fire |
| Non-profit · Balanced | 17 | 3.1% | Moderate | Entity adaptation (Total Expenses benchmark, 4%); all 17 override-driven |
| High-risk · Aggressive | 100 | 12.5% | Elevated | Override at full tilt — 92 escalations, 82 from a raw *Low* tier |

The most important result is not the flagged counts. It is that **the feature-firing counts the app reported matched the planted patterns in the generated ledgers exactly** (e.g., 101 round-number, 76 weekend, 94 missing-description, 95 new-vendor rows on the high-risk file), and that **the qualitative override surfaced rows the raw Isolation Forest tier alone would have left low** (82 of 100 flagged rows on the high-risk run had a raw tier of Low). The three profiled ledgers (`sample_gl_clean.csv`, `sample_gl_high_risk.csv`, `sample_gl_nonprofit.csv`) are reproducible via `generate_sample_variants.py`.

---

## Running locally

### Backend (terminal 1)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python generate_sample_gl.py        # creates sample_data/sample_gl.csv
python generate_sample_variants.py  # creates the clean / high-risk / non-profit ledgers
python smoke_test.py                # verifies 30 acceptance criteria pass
uvicorn api:app --reload --port 8000
```

The FastAPI server is now serving on `http://localhost:8000`. Hit `/api/healthz` to verify — should return `{"status":"ok","version":"0.4.1"}`.

### Frontend (terminal 2)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Upload any ledger from `backend/sample_data/` (start with `sample_gl.csv`, or `sample_gl_high_risk.csv` on **Aggressive** to see the override fire), click **Run Analysis**, and the full pipeline runs end-to-end. To see the AI narrative layer, click **Generate AI Narrative** above the flagged table — the top-N memos (default 10, max 20) generate concurrently in roughly 5 seconds and render inside row expanders as you click them.

### LLM prerequisites

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

The 12 features, the materiality filter, the qualitative override, and the narrative prompts are anchored to specific audit-standard sources. PCAOB references use the current reorganized numbering, with legacy numbers in parentheses:

| Feature / mechanism | Source | What it captures |
|---|---|---|
| `amount_zscore_by_account` | AU-C 315, ARP | Account-level magnitude deviation |
| `is_round_number` | PCAOB AS 2401 | Manual entry / estimate red flag |
| `is_weekend_posting` | Control activities | Unusual posting timing |
| `missing_description` | Information & Communication (COSO) | Documentation control gap |
| `is_new_vendor` | Fraud risk factors | Misappropriation opportunity |
| `is_near_approval_threshold` | IT controls / limit tests | Invoice splitting / approval avoidance |
| Materiality filter | PCAOB AS 2201 (legacy AS 5) | Quantitative severity-of-deficiency framework |
| Qualitative override | PCAOB AS 2401; AS 2201 (legacy AS 5) | Co-occurrence of fraud indicators is material regardless of amount because it signals a control breakdown |
| Review labels | PCAOB AS 2201 (legacy AS 5) | "Potential Material Weakness Indicator", etc. |
| Narrative — hedged language | AU-C 315, PCAOB AS 2401 | Risk-indicator framing, never fraud conclusions |
| Narrative — subject discipline | Audit professional standards | Transaction/control as subject, not the person who recorded it |
| Memo — `assertion_consideration` | AU-C 315, FS assertions framework | Occurrence, Accuracy, Cutoff, Classification, Rights & Obligations, Valuation, Completeness |
| Memo — `control_or_coso_consideration` | COSO 2013 framework | Control Environment, Risk Assessment, Control Activities, Information & Communication, Monitoring Activities |

Phase 6 will add a structured Standards Grounding panel below each memo that surfaces explicit AS 2401 / AS 2201 (legacy AS 5) / AS 1215 (legacy AS 3) / COSO 2013 citations via a rule-based mapping rather than free-form LLM citation, to keep regulatory references deterministic and auditable.

---

## Phase 6 — deployment and extensions

The roadmap from here. Deployment is the immediate next step; the rest are post-deploy extensions, roughly in priority order.

- **Deployment** — Vercel (frontend) + Render or Fly.io (backend), server-side `OPENAI_API_KEY` as secret, CORS for the frontend domain, `NEXT_PUBLIC_API_BASE_URL` pointed at the backend (budget for free-tier cold start). LUCENT is stateless — upload → analyze → return, no persistence — which makes it a low-risk first deploy.
- **Repository rename** — rename the GitHub repo `ai-audit-risk-analyzer` → `lucent-pre-audit-review-packet` to match the product (GitHub redirects the old URL)
- **Standards Grounding panel** — backend-derived rule-based mapping from row attributes to four fixed framework categories (AS 2401, AS 2201 (legacy AS 5), AS 1215 (legacy AS 3), COSO 2013), rendered inline at the bottom of each row expander; deterministic lookup, not LLM-generated, so citations can't be hallucinated
- **CI/CD** — GitHub Actions running `smoke_test.py` and `api_test.py` on every push
- **Excel workbook export** — multi-sheet `.xlsx` via `openpyxl`: summary, flagged transactions, integrity findings, narrative memos
- **API observability** — structured logging for narrative-layer GPT-vs-fallback rate, latency, and cost
- **Row-level data-quality exceptions** — drill-down from a non-passing integrity check to the specific journal references behind it (requires an additive integrity-layer return field)
- **Period-over-period fluctuation table** — account-level variance analysis as a separate analytical procedure (depends on multi-period support)
- **Multi-period support** — comparison mode across two uploaded GL periods (the foundation the fluctuation table builds on)

---

## Methodology and limitations

This tool identifies *risk indicators* using statistical anomaly detection, weak-label supervised classification, and materiality thresholds. It does not determine intent, conclude fraud, or issue audit opinions. The PCAOB-aligned labels use "Potential", "Indicator", and "Monitor" throughout — never definitive language.

The supervised layer is trained on weak labels derived from rule-based fraud indicators, then applied in-process to the same upload. The honest interpretation of its score is "this transaction resembles the rule-flagged transactions in continuous-feature space" — a smoothing of the rule rather than an independent validator. The qualitative override and supervised escalation are designed to never lower a tier, only raise it, so the materiality filter's conservative output remains the floor.

The GPT narrative layer is constrained to risk-indication language with explicit banned phrases ("fraud occurred," "the perpetrator," "this proves," etc.) enforced both in the system prompt and in a post-generation validator. Any banned-phrase trip, schema violation, length-bound violation, name-leakage pattern, or non-verbatim disclaimer routes the row through a deterministic fallback memo that satisfies the same validator by construction. The layer translates already-scored results into hedged review memos; it does not extend the scoring logic itself, and it cannot conclude fraud or issue an audit opinion regardless of how the underlying ML output is interpreted.

Findings should be corroborated with documentary evidence and discussions with management consistent with AU-C 315 (Understanding the Entity and Its Environment) and PCAOB AS 2401 (Consideration of Fraud in a Financial Statement Audit). LUCENT reviews the general ledger before financial statements are finalized; it does not prepare or review full financial statements.

Sample data is simulated. The cross-footing integrity check often produces a warning on QuickBooks-style "one row per leg" GL exports — this is expected and demonstrates the integrity layer working on realistic input rather than indicating a tool defect.

This project is a portfolio piece, not production audit software. It is not affiliated with any audit firm, and its outputs are not a substitute for professional auditor judgment.
