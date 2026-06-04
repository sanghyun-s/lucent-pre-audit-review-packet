"use client";

import * as React from "react";
import { Search } from "lucide-react";

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
      // Scroll to the integrity section once results land
      setTimeout(() => {
        document.getElementById("results")?.scrollIntoView({ behavior: "smooth" });
      }, 100);
    } catch (e) {
      setError(e.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="container py-8 space-y-6">
      <header className="space-y-1">
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-2">
          <Search className="h-7 w-7" />
          AI Audit Risk Analyzer
        </h1>
        <p className="text-sm text-muted-foreground">
          ML anomaly detection + materiality-calibrated risk scoring + PCAOB-aligned
          labels for QuickBooks GL exports.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr] gap-6">
        {/* Sidebar */}
        <aside className="space-y-4">
          <ClientProfileForm value={form} onChange={setForm} options={options} />
          <div className="text-xs text-muted-foreground px-2">
            Phases 1–3 + hybrid ML shipped. Phase 4a: GPT narrative layer (in progress).
          </div>
        </aside>

        {/* Main panel */}
        <section className="space-y-6">
          <div className="space-y-2">
            <h2 className="text-lg font-semibold">Materiality Thresholds</h2>
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

          {result && (
            <div id="results" className="space-y-6">
              <IntegrityPanel integrity={result.integrity} />

              <FeatureFiringPanel featureFiring={result.feature_firing} />

              <div className="space-y-3">
                <h2 className="text-lg font-semibold">4. Isolation Forest + Materiality Filter</h2>
                <SummaryCards summary={result.summary} />
              </div>

              <div className="space-y-3">
                <h2 className="text-lg font-semibold">5. Risk Distribution</h2>
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  <RiskDistributionChart data={result.chart_data?.tier_distribution} />
                  <TopAccountsChart data={result.chart_data?.top_accounts} />
                </div>
              </div>

              <div className="space-y-3">
                <h2 className="text-lg font-semibold">6. Flagged Transactions</h2>
                <FlaggedTable
                  rows={result.flagged_rows}
                  entityContext={{
                    entity_type: result.request?.entity_type,
                    period_start: result.request?.period_start,
                    period_end: result.request?.period_end,
                  }}
                />
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
