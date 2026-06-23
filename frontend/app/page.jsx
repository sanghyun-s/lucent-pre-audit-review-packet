"use client";

import * as React from "react";
import { Eye } from "lucide-react";

import ClientProfileForm   from "@/components/ClientProfileForm";
import MaterialityBanner   from "@/components/MaterialityBanner";
import CsvUpload           from "@/components/CsvUpload";
import IntegrityPanel      from "@/components/IntegrityPanel";
import FeatureFiringPanel  from "@/components/FeatureFiringPanel";
import SummaryCards        from "@/components/SummaryCards";
import RiskDistributionChart from "@/components/RiskDistributionChart";
import TopAccountsChart    from "@/components/TopAccountsChart";
import FlaggedTable        from "@/components/FlaggedTable";
import BusinessContextCard from "@/components/BusinessContextCard";
import DataProvenanceNote from "@/components/DataProvenanceNote";
import DataDictionary from "@/components/DataDictionary";
import ReviewPacketSummary from "@/components/ReviewPacketSummary";
import DataQualityExceptions from "@/components/DataQualityExceptions";

import { analyze, fetchOptions } from "@/lib/api";

const DEFAULT_FORM = {
  entityType: "Private for-profit",
  benchmarkFigure: 150000,
  detectionSensitivity: "Balanced (0.05)",
  periodStart: "2024-01-01",
  periodEnd: "2024-12-31",
};

/**
 * Phase 5A — business-context & explainability refactor over the existing
 * four-section workflow. The engine is untouched; this layer reframes the
 * page so a non-technical reviewer can tell what it's for, what each signal
 * means, and what evidence to request.
 *
 *   Header           ARGUS + business subtitle
 *   Business Context what it's for / input / output / not for
 *   Section 1        Review Context & Input File   (+ data-provenance note)
 *   Section 2        Data Quality Check
 *   Section 3        Review Queue Summary
 *   Section 4        Flagged Transactions & Evidence Requests (+ Signal Guide link)
 *   Section 5        How to Read ARGUS Signals     (collapsible data dictionary)
 *   Disclaimer       the honesty boundary
 */
export default function Page() {
  const [options, setOptions] = React.useState(null);
  const [form, setForm]       = React.useState(DEFAULT_FORM);
  const [file, setFile]       = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult]   = React.useState(null);
  const [error, setError]     = React.useState(null);

  React.useEffect(() => {
    fetchOptions().then(setOptions).catch(() => {
      // Backend may not be running yet — fall back to baked-in defaults
      setOptions(null);
    });
  }, []);

  async function handleRun() {
    setError(null);
    setLoading(true);
    try {
      const data = await analyze({
        file,
        entityType: form.entityType,
        benchmarkFigure: form.benchmarkFigure,
        detectionSensitivity: form.detectionSensitivity,
        periodStart: form.periodStart,
        periodEnd: form.periodEnd,
      });
      setResult(data);
      // Scroll to the data-quality section once results land
      setTimeout(() => {
        document.getElementById("section-2")?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch (e) {
      setError(e.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="container py-8 space-y-8">
      <header className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Eye className="h-7 w-7" />
          ARGUS
        </h1>
        <p className="text-sm font-medium text-foreground">
          Audit Review Packet
        </p>
        <p className="text-sm text-muted-foreground max-w-3xl">
          Narrow a full general-ledger export into a prioritized review queue — see
          what to check, why it matters, and what evidence to request — before close,
          CPA handoff, audit readiness, or investor diligence.
        </p>
      </header>

      {/* Business use case — answers "what is this for?" before the workflow */}
      <BusinessContextCard />

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Section 1 — Review Context & Input File                         */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <section id="section-1" className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight">
            Section 1 — Review Context & Input File
          </h2>
          <p className="text-sm text-muted-foreground">
            Define the review context — client profile, materiality benchmark, and the
            general-ledger export to review.
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
          {/* Sidebar form — stays visible while scrolling below */}
          <aside className="space-y-4">
            <ClientProfileForm value={form} onChange={setForm} options={options} />
          </aside>

          {/* Materiality preview + upload area */}
          <div className="space-y-6">
            <div className="space-y-2">
              <h3 className="text-base font-semibold">Materiality Thresholds</h3>
              <MaterialityBanner
                entityType={form.entityType}
                benchmarkFigure={form.benchmarkFigure}
              />
              <p className="text-xs text-muted-foreground">
                Methodology: FS materiality derives from the entity benchmark.
                Performance and transaction materiality are auditor-judgment haircuts.
              </p>
            </div>

            <CsvUpload
              file={file}
              onFileChange={setFile}
              onRun={handleRun}
              loading={loading}
              requiredColumns={options?.required_columns}
            />

            {/* Where did this data come from? — visible at the upload */}
            <DataProvenanceNote fileName={file?.name} />

            {error && (
              <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
                {error}
              </div>
            )}
          </div>
        </div>
      </section>

      {/* Sections 2–4 only appear once analysis has run */}
      {result && (
        <>
          {/* ─────────────────────────────────────────────────────────── */}
          {/* Section 2 — Data Quality Check                              */}
          {/* ─────────────────────────────────────────────────────────── */}
          <section id="section-2" className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">
                Section 2 — Data Quality Check
              </h2>
              <p className="text-sm text-muted-foreground">
                Pre-review data-quality checks and the review signals found in the
                file. Click a panel header to expand for full detail.
              </p>
            </div>

            <div className="space-y-3">
              <DataQualityExceptions integrity={result.integrity} />
              <IntegrityPanel integrity={result.integrity} />
              <FeatureFiringPanel featureFiring={result.feature_firing} />
            </div>
          </section>

          {/* ─────────────────────────────────────────────────────────── */}
          {/* Section 3 — Review Queue Summary                            */}
          {/* ─────────────────────────────────────────────────────────── */}
          <section id="section-3" className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">
                Section 3 — Review Queue Summary
              </h2>
              <p className="text-sm text-muted-foreground">
                What the review produced: how many transactions were flagged for
                follow-up, how they break down by priority, and where the flagged
                amounts concentrate.
              </p>
            </div>

            <ReviewPacketSummary result={result} fileName={file?.name} />

            <SummaryCards summary={result.summary} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <RiskDistributionChart data={result.chart_data?.tier_distribution} />
              <TopAccountsChart data={result.chart_data?.top_accounts} />
            </div>
          </section>

          {/* ─────────────────────────────────────────────────────────── */}
          {/* Section 4 — Flagged Transactions & Evidence Requests        */}
          {/* ─────────────────────────────────────────────────────────── */}
          <section id="section-4" className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">
                Section 4 — Flagged Transactions & Evidence Requests
              </h2>
              <p className="text-sm text-muted-foreground">
                Each flagged transaction with its review signals. Expand a row for the
                full review memo — assertion, magnitude, likelihood, control / COSO,
                and the evidence to request — once narratives are generated.
              </p>
              <p className="text-xs text-muted-foreground">
                Not sure what a signal means?{" "}
                <a
                  href="#signal-guide"
                  className="underline underline-offset-2 hover:text-foreground"
                >
                  View the Signal Guide ↓
                </a>
              </p>
            </div>

            <FlaggedTable
              rows={result.flagged_rows}
              entityContext={{
                entity_type: result.request?.entity_type,
                period_start: result.request?.period_start,
                period_end: result.request?.period_end,
              }}
            />
          </section>
        </>
      )}

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Section 5 — How to Read ARGUS Signals  (always available)       */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <DataDictionary />

      {/* Honesty boundary — what ARGUS does not do */}
      <footer className="rounded-md border border-muted bg-muted/30 p-4">
        <p className="text-xs leading-relaxed text-muted-foreground">
          ARGUS indicates review priority; it does not conclude. It does not prepare
          financial statements, perform an audit, issue an audit opinion, or detect or
          conclude fraud. It narrows a general-ledger population and explains why
          selected transactions deserve attention, leaving all judgment to the reviewer.
        </p>
      </footer>
    </main>
  );
}
