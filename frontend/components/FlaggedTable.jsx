"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Download, Sparkles, ChevronRight, ChevronDown, Loader2 } from "lucide-react";
import { generateNarratives as requestNarratives } from "@/lib/api";

const PAGE_SIZE = 25;
const NARRATIVE_DEFAULT_TOP_N = 10;
const NARRATIVE_MAX_TOP_N = 20;

function tierVariant(tier) {
  if (tier === "High") return "danger";
  if (tier === "Medium") return "warning";
  if (tier === "Low") return "secondary";
  return "outline";
}

function fmtAmount(n) {
  if (n == null) return "";
  return `$${Number(n).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2,
  })}`;
}

function fmtDate(s) {
  if (!s) return "";
  return s.split("T")[0];
}

function toCsv(rows, cols) {
  const escape = (v) => {
    if (v == null) return "";
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = cols.join(",");
  const body = rows.map((r) => cols.map((c) => escape(r[c])).join(",")).join("\n");
  return header + "\n" + body;
}

// Build a stable row key the backend can match against. Mirrors what
// generate_narratives_for_rows returns in selected_row_keys.
function rowKey(r) {
  return `${r?.date || ""}|${r?.account_name || ""}|${r?.vendor || ""}|${r?.amount || ""}`;
}

/**
 * The four "context" rows (materiality / anomaly / similarity / override)
 * that sit at the bottom of every expanded row — same content in both
 * with-narrative and without-narrative cases. Extracted as a sub-component
 * since the JSX was identical in both branches and the duplication added
 * noise to the expander logic.
 *
 * Note: the underlying field is still `fraud_probability` (internal name),
 * but it is a risk-pattern similarity score — how closely a row resembles
 * the rule-flagged population in feature space — NOT a probability of fraud.
 * The user-facing label reflects that.
 */
function ContextFields({ row }) {
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground">
      <div>Materiality: {row.materiality_annotation || "—"}</div>
      <div>Anomaly score: {row.anomaly_score?.toFixed(3) ?? "—"}</div>
      <div>
        Risk-Pattern Similarity:{" "}
        {row.fraud_probability != null ? row.fraud_probability.toFixed(2) : "—"}
      </div>
      <div>Qualitative override: {row.is_qualitative_override ? "Yes" : "No"}</div>
      {row.qualitative_override_note && (
        <div className="col-span-2 italic">{row.qualitative_override_note}</div>
      )}
    </div>
  );
}

/**
 * Phase 4c — card-with-hierarchy display of the full 7-field audit memo.
 *
 * Visual hierarchy (top to bottom):
 *   1. Header strip: AI Risk Summary label + GPT/Fallback badge
 *   2. Large risk_summary paragraph (the headline finding)
 *   3. 2x2 grid of structured fields (assertion / magnitude / likelihood / COSO)
 *   4. Recommended follow-up: bulleted list of audit procedures
 *   5. Muted small disclaimer
 *
 * Field presence is defensive: any field can be absent (e.g., a stale
 * Phase 4a-shape narrative) and the corresponding block is omitted
 * gracefully rather than crashing.
 */
function NarrativeCard({ narrative }) {
  const {
    risk_summary,
    assertion_consideration,
    magnitude_assessment,
    likelihood_assessment,
    control_or_coso_consideration,
    recommended_follow_up,
    disclaimer,
    narrative_status,
  } = narrative;

  const structuredFields = [
    { label: "Assertion Consideration",  value: assertion_consideration },
    { label: "Magnitude Assessment",     value: magnitude_assessment },
    { label: "Likelihood Assessment",    value: likelihood_assessment },
    { label: "Control / COSO Consideration", value: control_or_coso_consideration },
  ].filter((f) => !!f.value);

  return (
    <div className="rounded-lg border bg-background p-4 space-y-4">
      {/* Header strip */}
      <div className="flex items-center gap-2 text-xs">
        <Sparkles className="h-3.5 w-3.5 text-blue-500" />
        <span className="font-medium">AI Risk Summary</span>
        <Badge
          variant={narrative_status === "GPT" ? "secondary" : "outline"}
          className="text-[10px]"
        >
          {narrative_status}
        </Badge>
      </div>

      {/* Headline finding — risk_summary in larger text */}
      {risk_summary && (
        <p className="text-sm leading-relaxed text-foreground">{risk_summary}</p>
      )}

      {/* 2x2 structured fields grid */}
      {structuredFields.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2 border-t">
          {structuredFields.map((f) => (
            <div key={f.label} className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {f.label}
              </p>
              <p className="text-xs leading-relaxed text-foreground">{f.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Evidence to Request — the reviewer's next action, emphasized */}
      {Array.isArray(recommended_follow_up) && recommended_follow_up.length > 0 && (
        <div className="space-y-1.5 mt-1 rounded-md border border-blue-200 bg-blue-50/40 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground">
            Evidence to Request
          </p>
          <ul className="text-xs leading-relaxed text-foreground list-disc pl-5 space-y-0.5">
            {recommended_follow_up.map((item, j) => (
              <li key={j}>{item}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Muted disclaimer */}
      {disclaimer && (
        <p className="text-[10px] italic text-muted-foreground/80 pt-2 border-t">
          {disclaimer}
        </p>
      )}
    </div>
  );
}

export default function FlaggedTable({ rows, entityContext }) {
  const [page, setPage] = React.useState(0);
  const [expanded, setExpanded] = React.useState(() => new Set());
  const [narrativesByKey, setNarrativesByKey] = React.useState({});
  const [topN, setTopN] = React.useState(NARRATIVE_DEFAULT_TOP_N);
  const [narrativeLoading, setNarrativeLoading] = React.useState(false);
  const [narrativeError, setNarrativeError] = React.useState(null);
  const [narrativeMeta, setNarrativeMeta] = React.useState(null); // {n_gpt, n_fallback, top_n_used}

  if (!rows?.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Flagged Transactions</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">No flagged transactions.</p>
        </CardContent>
      </Card>
    );
  }

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  const toggleExpanded = (idx) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
  };

  // Transport now lives in lib/api.js (generateNarratives), matching how
  // analyze() is structured. This handler owns only the UI state: loading,
  // key-mapping, meta, and auto-expand.
  const generateNarratives = async () => {
    setNarrativeLoading(true);
    setNarrativeError(null);
    try {
      const data = await requestNarratives({
        rows,
        entityContext,
        topN,
      });
      // Map narratives back to row keys so we can look them up per-row
      const byKey = {};
      (data.selected_row_keys || []).forEach((k) => {
        const key = `${k.date || ""}|${k.account_name || ""}|${k.vendor || ""}|${k.amount || ""}`;
        const n = data.narratives?.[String(k.position)];
        if (n) byKey[key] = n;
      });
      setNarrativesByKey(byKey);
      setNarrativeMeta({
        n_gpt: data.n_gpt,
        n_fallback: data.n_fallback,
        top_n_used: data.top_n_used,
      });
      // Auto-expand the rows that just got narratives, so the user sees
      // them immediately without hunting.
      setExpanded((prev) => {
        const next = new Set(prev);
        rows.forEach((r, i) => {
          if (byKey[rowKey(r)]) next.add(i);
        });
        return next;
      });
    } catch (e) {
      setNarrativeError(e.message || "Failed to generate narratives.");
    } finally {
      setNarrativeLoading(false);
    }
  };

  const downloadCsv = () => {
    const baseCols = [
      "date", "account_name", "vendor", "amount",
      "anomaly_score", "raw_tier", "final_tier", "pcaob_label",
      "materiality_annotation", "active_flags",
      "control_gap_score", "fraud_risk_flag",
      "period_over_period_pct", "vendor_concentration_pct",
      "is_year_end_concentration", "is_non_standard_pattern",
    ].filter((c) => rows[0] && c in rows[0]);

    // When narratives exist, append narrative_status + all 7 memo fields
    // so the full audit reasoning travels into the user's workpapers.
    // recommended_follow_up is a list — joined with "; " for a single CSV cell.
    const narrativeCols = [
      "narrative_status",
      "risk_summary",
      "assertion_consideration",
      "magnitude_assessment",
      "likelihood_assessment",
      "control_or_coso_consideration",
      "recommended_follow_up",
      "disclaimer",
    ];
    const hasAnyNarrative = Object.keys(narrativesByKey).length > 0;
    const cols = hasAnyNarrative ? [...baseCols, ...narrativeCols] : baseCols;

    const enriched = rows.map((r) => {
      if (!hasAnyNarrative) return r;
      const n = narrativesByKey[rowKey(r)];
      return {
        ...r,
        narrative_status: n ? n.narrative_status : "Not generated",
        risk_summary: n ? n.risk_summary : "",
        assertion_consideration: n ? n.assertion_consideration : "",
        magnitude_assessment: n ? n.magnitude_assessment : "",
        likelihood_assessment: n ? n.likelihood_assessment : "",
        control_or_coso_consideration: n ? n.control_or_coso_consideration : "",
        recommended_follow_up:
          n && Array.isArray(n.recommended_follow_up)
            ? n.recommended_follow_up.join("; ")
            : "",
        disclaimer: n ? n.disclaimer : "",
      };
    });

    const csv = toCsv(enriched, cols);
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "flagged_transactions.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const narrativeCount = Object.keys(narrativesByKey).length;

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-lg">Flagged Transactions ({rows.length})</CardTitle>
        <Button variant="outline" size="sm" onClick={downloadCsv} className="gap-2">
          <Download className="h-4 w-4" /> Download CSV
        </Button>
      </CardHeader>
      <CardContent>
        {/* Narrative controls — Phase 4a (unchanged in 4c) */}
        <div className="flex flex-wrap items-center gap-3 mb-3 p-3 rounded-md border bg-muted/30">
          <div className="flex items-center gap-2">
            <label htmlFor="topN" className="text-xs font-medium text-muted-foreground">
              Top
            </label>
            <input
              id="topN"
              type="number"
              min={1}
              max={NARRATIVE_MAX_TOP_N}
              value={topN}
              onChange={(e) => {
                const v = parseInt(e.target.value, 10);
                if (!Number.isNaN(v)) setTopN(Math.max(1, Math.min(NARRATIVE_MAX_TOP_N, v)));
              }}
              className="w-16 h-8 px-2 text-xs rounded border bg-background"
              disabled={narrativeLoading}
            />
            <span className="text-xs text-muted-foreground">
              rows (1–{NARRATIVE_MAX_TOP_N})
            </span>
          </div>
          <Button
            size="sm"
            onClick={generateNarratives}
            disabled={narrativeLoading}
            className="gap-2"
          >
            {narrativeLoading ? (
              <><Loader2 className="h-4 w-4 animate-spin" /> Generating…</>
            ) : (
              <><Sparkles className="h-4 w-4" /> Generate AI Narrative</>
            )}
          </Button>
          {narrativeMeta && !narrativeLoading && (
            <span className="text-xs text-muted-foreground">
              {narrativeCount} narrative{narrativeCount === 1 ? "" : "s"} ready ·
              {" "}{narrativeMeta.n_gpt} GPT / {narrativeMeta.n_fallback} fallback
            </span>
          )}
          {narrativeError && (
            <span className="text-xs text-red-600">Error: {narrativeError}</span>
          )}
        </div>

        <div className="rounded-md border overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="bg-muted/50">
              <tr className="text-left">
                <th className="px-2 py-2 font-medium w-6"></th>
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Account</th>
                <th className="px-3 py-2 font-medium">Vendor</th>
                <th className="px-3 py-2 font-medium text-right">Amount</th>
                <th className="px-3 py-2 font-medium">Final Tier</th>
                <th className="px-3 py-2 font-medium">Audit Review Label</th>
                <th className="px-3 py-2 font-medium text-center">Control Signal</th>
                <th className="px-3 py-2 font-medium text-center">Co-occurrence</th>
                <th className="px-3 py-2 font-medium text-center">Override</th>
                <th className="px-3 py-2 font-medium text-right">Similarity</th>
                <th className="px-3 py-2 font-medium">Active Flags</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((r, i) => {
                // The expanded-set tracks indices into the FULL `rows` list,
                // not the paginated slice, so it survives page changes.
                const globalIdx = page * PAGE_SIZE + i;
                const isExpanded = expanded.has(globalIdx);
                const narrative = narrativesByKey[rowKey(r)];
                const hasNarrative = !!narrative;

                return (
                  <React.Fragment key={globalIdx}>
                    <tr
                      className={`border-t hover:bg-muted/30 cursor-pointer ${hasNarrative ? "bg-blue-50/30" : ""}`}
                      onClick={() => toggleExpanded(globalIdx)}
                    >
                      <td className="px-2 py-2 text-muted-foreground">
                        {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{fmtDate(r.date)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{r.account_name}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {r.vendor}
                        {hasNarrative && (
                          <Sparkles
                            className="inline-block h-3 w-3 ml-1 text-blue-500"
                            aria-label="AI narrative available"
                          />
                        )}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap text-right">{fmtAmount(r.amount)}</td>
                      <td className="px-3 py-2">
                        <Badge variant={tierVariant(r.final_tier)}>{r.final_tier}</Badge>
                      </td>
                      <td className="px-3 py-2">{r.pcaob_label}</td>
                      <td className="px-3 py-2 text-center">{r.control_gap_score}</td>
                      <td className="px-3 py-2 text-center">
                        {r.fraud_risk_flag ? <Badge variant="warning">Yes</Badge> : "—"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {r.is_qualitative_override ? <Badge variant="warning">Override</Badge> : "—"}
                      </td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {r.fraud_probability != null ? r.fraud_probability.toFixed(2) : "—"}
                      </td>
                      <td className="px-3 py-2 text-muted-foreground">{r.active_flags}</td>
                    </tr>
                    {isExpanded && (
                      <tr className="border-t bg-muted/20">
                        <td></td>
                        <td colSpan={11} className="px-3 py-3">
                          {hasNarrative ? (
                            <div className="space-y-3">
                              {/* Phase 4c: card-with-hierarchy 7-field memo */}
                              <NarrativeCard narrative={narrative} />

                              {/* Context fields stay at the bottom (decision a) */}
                              <div className="pt-2 border-t border-muted">
                                <ContextFields row={r} />
                              </div>
                            </div>
                          ) : (
                            <div className="text-xs text-muted-foreground">
                              No AI narrative yet for this row. Click{" "}
                              <span className="font-medium">Generate AI Narrative</span> above
                              to produce risk summaries for the top {topN} most demo-relevant
                              flagged transactions.
                              <div className="mt-2 pt-2 border-t border-muted">
                                <ContextFields row={r} />
                              </div>
                            </div>
                          )}
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-3 text-xs">
            <span className="text-muted-foreground">
              Page {page + 1} of {totalPages} · showing {pageRows.length} of {rows.length}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page === 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>
                Next
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
