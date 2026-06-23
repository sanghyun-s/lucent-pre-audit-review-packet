"use client";

import * as React from "react";
import { Card, CardContent } from "@/components/ui/card";

/**
 * BusinessContextCard — answers "what is this for?" before the workflow.
 *
 * Four blocks: Use case / Input / Output / Not for. The "Not for" block is
 * styled as a guardrail (muted, bordered) so the honesty boundary reads as
 * deliberate rather than fine print. Static content only — no props, no logic.
 *
 * Mount this directly under the page header, above Section 1.
 */
const BLOCKS = [
  {
    label: "Use case",
    body:
      "Close review, year-end review, CPA handoff, audit readiness, or investor diligence.",
  },
  {
    label: "Input",
    body: "A company-level QuickBooks-style general-ledger export (CSV).",
  },
  {
    label: "Output",
    body:
      "A prioritized transaction review queue, plain-English risk indicators, and evidence-request memos. Review labels use PCAOB-aligned, non-conclusive wording (Potential Indicator, Monitor).",
  },
];

export default function BusinessContextCard() {
  return (
    <Card>
      <CardContent className="pt-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {BLOCKS.map((b) => (
            <div key={b.label} className="space-y-1">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                {b.label}
              </p>
              <p className="text-sm leading-relaxed text-foreground">{b.body}</p>
            </div>
          ))}
        </div>

        {/* Guardrail block — the honesty boundary, set apart on purpose */}
        <div className="mt-4 rounded-md border border-muted bg-muted/40 p-3">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            Not for
          </p>
          <p className="text-xs leading-relaxed text-foreground">
            Fraud conclusions, audit opinions, preparing financial statements, or
            replacing professional judgment. LUCENT reviews the general ledger{" "}
            <span className="italic">before</span> financial statements are finalized.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
