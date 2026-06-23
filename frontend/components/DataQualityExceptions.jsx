"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { AlertTriangle } from "lucide-react";

/**
 * DataQualityExceptions — extracts the integrity checks that did NOT pass and
 * presents them as action items, answering "if totals don't tie, surface the
 * exception."
 *
 * Frontend-only: reads the existing integrity findings from the analyze
 * response. It surfaces exceptions at the CHECK level (which check, what it
 * reports). Listing the specific offending rows / journal references behind a
 * warning needs the backend integrity layer to return those identifiers — a
 * Phase 6 additive change, intentionally not done here.
 *
 * Renders nothing when every check passes, so it never shows an empty card.
 *
 * Usage (Section 2):
 *   <DataQualityExceptions integrity={result.integrity} />
 */
// Integrity findings carry a string `summary` plus a sometimes-STRUCTURED
// `detail` (e.g., cross-footing returns {sum_d, sum_c, diff, pct}). Rendering an
// object directly as a React child throws, so coerce anything non-string to
// readable text and never hand React a raw object.
const DETAIL_LABELS = {
  sum_d: "Total debits",
  sum_c: "Total credits",
  diff: "Difference",
  pct: "Difference (%)",
};

function asText(v) {
  if (v == null) return null;
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  if (typeof v === "object") {
    const parts = Object.entries(v).map(
      ([k, val]) => `${DETAIL_LABELS[k] || k}: ${val}`
    );
    return parts.length ? parts.join(" · ") : null;
  }
  return String(v);
}

export default function DataQualityExceptions({ integrity }) {
  const findings = integrity?.findings || [];
  const exceptions = findings.filter((f) => f.status && f.status !== "Pass");

  if (exceptions.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          Data Quality Exceptions ({exceptions.length})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Data-quality checks that did not pass. Resolve or explain these before
          relying on the review queue — a warning is advisory, a failure should be
          cleared first.
        </p>
        {exceptions.map((f, i) => {
          const summaryText = asText(f.summary);
          const detailText = typeof f.detail === "string" ? f.detail : null;
          return (
            <div key={i} className="rounded-md border p-3 space-y-1">
              <div className="flex items-center gap-2">
                <Badge variant={f.status === "Fail" ? "danger" : "warning"}>
                  {f.status}
                </Badge>
                <span className="text-sm font-medium">{f.name}</span>
              </div>
              {summaryText && (
                <p className="text-xs text-foreground">{summaryText}</p>
              )}
              {detailText && (
                <p className="text-xs text-muted-foreground">{detailText}</p>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
