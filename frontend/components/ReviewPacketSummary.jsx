"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ClipboardList } from "lucide-react";

/**
 * ReviewPacketSummary — the "what to do next" card at the top of Section 3.
 *
 * Reads only fields already present in the analyze response plus the selected
 * file name. No backend dependency. Two derived values:
 *   - Suggested next action: from the High / Medium counts in the queue.
 *   - Top review drivers: the most frequent active flags across flagged rows.
 *
 * Usage:
 *   <ReviewPacketSummary result={result} fileName={file?.name} />
 */
function fmtDate(s) {
  if (!s) return "—";
  const parts = String(s).split("-");
  if (parts.length !== 3) return s;
  const [y, m, d] = parts;
  return `${m}/${d}/${y}`;
}

function topDrivers(rows, n = 3) {
  const counts = {};
  for (const r of rows || []) {
    const flags = String(r.active_flags || "")
      .split(";")
      .map((s) => s.trim())
      .filter(Boolean);
    for (const f of flags) {
      if (f === "Statistical anomaly only") continue; // not a review driver
      counts[f] = (counts[f] || 0) + 1;
    }
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([flag]) => flag);
}

function suggestedAction(high, med) {
  if (high > 0 && med > 0)
    return `Review the ${high} High-priority item${high === 1 ? "" : "s"} first, then the ${med} Medium-priority item${med === 1 ? "" : "s"}.`;
  if (high > 0)
    return `Review the ${high} High-priority item${high === 1 ? "" : "s"}.`;
  if (med > 0)
    return `Review the ${med} Medium-priority item${med === 1 ? "" : "s"}.`;
  return "No High or Medium priority items — the review queue is clear.";
}

export default function ReviewPacketSummary({ result, fileName }) {
  if (!result) return null;

  const summary = result.summary || {};
  const request = result.request || {};
  const dq = result.integrity?.counts || {};
  const rows = result.flagged_rows || [];

  const pass = dq.Pass || 0;
  const warn = dq.Warning || 0;
  const fail = dq.Fail || 0;

  const high = rows.filter((r) => r.final_tier === "High").length;
  const med = rows.filter((r) => r.final_tier === "Medium").length;
  const drivers = topDrivers(rows);

  const population = summary.total ?? request.row_count ?? rows.length;
  const flagged = summary.flagged ?? rows.length;

  const fields = [
    { label: "Input file", value: fileName || "—" },
    {
      label: "Review period",
      value: `${fmtDate(request.period_start)} – ${fmtDate(request.period_end)}`,
    },
    {
      label: "Population",
      value: `${Number(population).toLocaleString()} GL transactions`,
    },
    {
      label: "Review queue",
      value: `${Number(flagged).toLocaleString()} flagged for follow-up`,
    },
    {
      label: "Data quality",
      value: `${pass} check${pass === 1 ? "" : "s"} passed · ${warn} warning${warn === 1 ? "" : "s"} · ${fail} failure${fail === 1 ? "" : "s"}`,
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <ClipboardList className="h-4 w-4" />
          Review Packet Summary
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
          {fields.map((f) => (
            <div key={f.label} className="flex justify-between gap-4 text-sm">
              <span className="text-muted-foreground">{f.label}</span>
              <span className="text-foreground font-medium text-right">{f.value}</span>
            </div>
          ))}
        </div>

        <div className="rounded-md border border-blue-200 bg-blue-50/40 p-3 space-y-1">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-foreground">
            Suggested next action
          </p>
          <p className="text-sm text-foreground">{suggestedAction(high, med)}</p>
        </div>

        {drivers.length > 0 && (
          <div className="space-y-1">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              Top review drivers
            </p>
            <p className="text-sm text-foreground">{drivers.join(", ")}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
