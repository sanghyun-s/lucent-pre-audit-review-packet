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

import { analyze, fetchOptions } from "@/lib/api";

const DEFAULT_FORM = {
  entityType: "Private for-profit",
  benchmarkFigure: 150000,
  detectionSensitivity: "Balanced (0.05)",
  periodStart: "2024-01-01",
  periodEnd: "2024-12-31",
};

/**
 * Phase 4c — explicit 4-section workflow.
 *
 * Section 1 — Engagement Setup
 *   Sidebar form (always visible while scrolling) + materiality preview
 *   + CSV upload + Run button. Pre-analysis area.
 *
 * Section 2 — Data Quality & Risk Signals
 *   Integrity panel (collapsible) + Feature firing panel (collapsible).
 *   Compacted to 1-line summaries by default so the user can skim past
 *   on a quick demo and expand for diagnostic depth.
 *
 * Section 3 — Risk Overview
 *   Summary cards + tier distribution chart + top accounts chart.
 *   The "is anything actually wrong, and where?" zone.
 *
 * Section 4 — Flagged Transaction Review
 *   The flagged transactions table with per-row expanders that include
 *   the full 7-field AI audit memo (when generated). The AI Narrative
 *   is part of Section 4, not a separate Section 5.
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
          Audit Risk Guidance · Unified System
        </p>
        <p className="text-sm text-muted-foreground">
          ML anomaly detection + materiality-calibrated risk scoring + PCAOB-aligned
          labels for QuickBooks general ledgers.
        </p>
      </header>

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* Section 1 — Engagement Setup                                    */}
      {/* ─────────────────────────────────────────────────────────────── */}
      <section id="section-1" className="space-y-4">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight">
            Section 1 — Engagement Setup
          </h2>
          <p className="text-sm text-muted-foreground">
            Client profile, materiality benchmark, and the GL CSV to analyze.
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
          {/* Section 2 — Data Quality & Risk Signals                     */}
          {/* ─────────────────────────────────────────────────────────── */}
          <section id="section-2" className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">
                Section 2 — Data Quality & Risk Signals
              </h2>
              <p className="text-sm text-muted-foreground">
                Pre-ML integrity checks and feature-firing counts. Click a panel
                header to expand for full detail.
              </p>
            </div>

            <div className="space-y-3">
              <IntegrityPanel integrity={result.integrity} />
              <FeatureFiringPanel featureFiring={result.feature_firing} />
            </div>
          </section>

          {/* ─────────────────────────────────────────────────────────── */}
          {/* Section 3 — Risk Overview                                   */}
          {/* ─────────────────────────────────────────────────────────── */}
          <section id="section-3" className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">
                Section 3 — Risk Overview
              </h2>
              <p className="text-sm text-muted-foreground">
                Isolation Forest + materiality filter results, tier distribution,
                and the accounts carrying the most flagged amount.
              </p>
            </div>

            <SummaryCards summary={result.summary} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <RiskDistributionChart data={result.chart_data?.tier_distribution} />
              <TopAccountsChart data={result.chart_data?.top_accounts} />
            </div>
          </section>

          {/* ─────────────────────────────────────────────────────────── */}
          {/* Section 4 — Flagged Transaction Review                      */}
          {/* ─────────────────────────────────────────────────────────── */}
          <section id="section-4" className="space-y-4">
            <div className="space-y-1">
              <h2 className="text-xl font-semibold tracking-tight">
                Section 4 — Flagged Transaction Review
              </h2>
              <p className="text-sm text-muted-foreground">
                Each flagged transaction with its active flags. Expand a row to
                see the full AI audit memo (assertion, magnitude, likelihood,
                control / COSO, and recommended procedures) once narratives are
                generated.
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
    </main>
  );
}
