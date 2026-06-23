"use client";

import * as React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { BookOpen, ChevronDown, ChevronRight } from "lucide-react";
import SignalCard from "./SignalCard";

/**
 * DataDictionary — Section 5, "How to Read LUCENT Signals."
 *
 * Collapsible by default (matches the Section 2 panel pattern) so it doesn't
 * push the workflow down. Has id="signal-guide" so a "View Signal Guide" link
 * elsewhere can scroll to it.
 *
 * Static reference content — no props required, no backend dependency.
 */
const GROUPS = [
  {
    title: "Transaction Review Signals",
    cards: [
      {
        indicator: "Unusual amount for account",
        aka: "account-level amount z-score",
        whatItMeans:
          "The amount is far from the typical size of entries in this same account, measured against that account's own history in the file.",
        whyItMatters:
          "An entry that's unusually large or small for its account can signal a misclassification, a one-off error, or an item worth understanding.",
        whatToRequest:
          "The supporting document for the amount and a short explanation of what drove it.",
        whatItDoesNotMean:
          "An unusual size is not an error by itself — many large entries are perfectly legitimate.",
      },
      {
        indicator: "Round-number amount",
        whatItMeans:
          "The amount is a clean round figure (e.g., $5,000.00, $10,000.00) with no cents or odd remainder.",
        whyItMatters:
          "Round numbers more often reflect estimates, manual journal entries, or placeholders than precise invoice-driven amounts.",
        whatToRequest:
          "The invoice or calculation behind the figure to confirm it's a real, supported amount rather than an estimate left in.",
        whatItDoesNotMean:
          "Round amounts are common and usually fine; this is a prompt to confirm, not a finding.",
      },
      {
        indicator: "Weekend posting",
        whatItMeans: "The transaction was dated on a Saturday or Sunday.",
        whyItMatters:
          "Most routine business postings happen on weekdays, so weekend entries can indicate manual adjustments or timing worth a quick look.",
        whatToRequest:
          "Confirmation of who recorded it and why it posted outside normal processing days.",
        whatItDoesNotMean:
          "Plenty of businesses legitimately post on weekends; this is timing context, not a problem.",
      },
      {
        indicator: "Missing description",
        whatItMeans: "The transaction has no description or memo text.",
        whyItMatters:
          "A missing description is a documentation gap — it's harder to tell what the entry was for, which weakens the audit trail.",
        whatToRequest:
          "The business purpose and supporting documentation for the entry.",
        whatItDoesNotMean:
          "A blank description is a record-keeping gap, not evidence that anything is wrong with the transaction itself.",
      },
      {
        indicator: "New vendor",
        whatItMeans:
          "This vendor appears only a few times in the uploaded file, suggesting it's new or rarely used.",
        whyItMatters:
          "New or infrequent vendors are where setup and approval controls matter most, so they're worth confirming.",
        whatToRequest:
          "Vendor setup documentation and evidence the goods or services were actually received.",
        whatItDoesNotMean:
          "New vendors are a normal part of business; this flags them for a setup check, nothing more.",
      },
      {
        indicator: "Near approval threshold",
        whatItMeans:
          "The amount sits just under a common approval limit such as $5,000, $10,000, or $25,000.",
        whyItMatters:
          "Amounts clustered just below a limit can indicate approval avoidance or splitting a larger purchase into smaller pieces.",
        whatToRequest:
          "The invoice, the approval record, and the business purpose for the amount.",
        whatItDoesNotMean:
          "Being near a threshold is not proof of anything — many legitimate amounts land there by coincidence.",
      },
    ],
  },
  {
    title: "Data Integrity Checks",
    cards: [
      {
        indicator: "Hash total",
        whatItMeans:
          "A check that the sum of all transaction amounts ties to the sum of the debit and credit columns.",
        whyItMatters:
          "If the totals don't tie, the file may be incomplete or altered, and the whole population should be trusted less until it's resolved.",
        whatToRequest: "A re-export of the GL or an explanation of the difference.",
        whatItDoesNotMean:
          "A pass confirms the file totals are internally consistent — it does not verify the underlying transactions are correct.",
      },
      {
        indicator: "Cross-footing",
        whatItMeans: "A check that total debits equal total credits across the file.",
        whyItMatters:
          "Balanced debits and credits are the foundation of double-entry bookkeeping; an imbalance points to an export or data issue. (QuickBooks-style \"one row per leg\" exports often raise this as a warning — expected, not a defect.)",
        whatToRequest:
          "The journal references behind the imbalance, or a clean re-export.",
        whatItDoesNotMean:
          "A warning here is usually a data-format artifact, not a sign of wrongdoing.",
      },
      {
        indicator: "Date-in-period",
        whatItMeans:
          "A check that every transaction date falls inside the review period you selected.",
        whyItMatters:
          "Entries dated outside the period can indicate cutoff issues — items recorded in the wrong window.",
        whatToRequest:
          "Support for any out-of-period item and confirmation of the correct posting date.",
        whatItDoesNotMean:
          "An out-of-period date can be a simple entry error, not necessarily a cutoff manipulation.",
      },
      {
        indicator: "Account mapping",
        whatItMeans:
          "A check that each account code maps consistently to one account name throughout the file.",
        whyItMatters:
          "If one code points to several names (or vice versa), the chart of accounts may be inconsistent, which muddies any account-level analysis.",
        whatToRequest: "The current chart of accounts to reconcile the mismatches.",
        whatItDoesNotMean:
          "Mapping inconsistencies are usually housekeeping issues, not indicators of misstatement.",
      },
    ],
  },
  {
    title: "Scoring Logic & Review Labels",
    cards: [
      {
        indicator: "Risk Indicator Co-occurrence",
        aka: "shown as the \"Co-occurrence\" column",
        whatItMeans:
          "Two or more review indicators appear on the same transaction.",
        whyItMatters:
          "Co-occurrence is what can support qualitative review escalation — a cluster of indicators is more notable than any single one.",
        whatToRequest:
          "Evidence covering each indicator present on the row.",
        whatItDoesNotMean:
          "It does not mean fraud occurred. It is an input signal; the escalation decision is a separate scoring step.",
      },
      {
        indicator: "Materiality filter",
        whatItMeans:
          "LUCENT compares each amount to materiality thresholds derived from your benchmark and lowers the priority of small-dollar items.",
        whyItMatters:
          "It keeps attention on amounts large enough to matter and prevents tiny statistical oddities from crowding the queue. It is the only step that can lower a row's priority.",
        whatToRequest:
          "Nothing directly — this is a prioritization rule, not a signal about a transaction.",
        whatItDoesNotMean:
          "A lowered priority does not mean an item is fine; it means it's below the dollar threshold set for this review.",
      },
      {
        indicator: "Qualitative override",
        whatItMeans:
          "When two or more review indicators appear on the same transaction, LUCENT raises its priority above what the dollar amount alone would assign.",
        whyItMatters:
          "It encodes the audit principle that a pattern of red flags can matter regardless of size — a small transaction with several indicators can deserve more attention than a large clean one.",
        whatToRequest:
          "The combined evidence for the indicators that co-occurred (invoice, approval, vendor file, timing explanation).",
        whatItDoesNotMean:
          "Escalation is a reason to look, not a conclusion that anything is wrong.",
      },
      {
        indicator: "Supervised escalation",
        whatItMeans:
          "A secondary model gently nudges a row's priority up when it statistically resembles the rule-flagged population.",
        whyItMatters:
          "It catches subtler items that don't trip an explicit rule but pattern-match to ones that do.",
        whatToRequest:
          "The same supporting evidence as for the row's active indicators.",
        whatItDoesNotMean:
          "Resemblance is a similarity score, not a probability of fraud or error.",
      },
      {
        indicator: "Audit Review Label",
        aka: "PCAOB-aligned, non-conclusive review label",
        whatItMeans:
          "The review label LUCENT assigns — Potential Material Weakness Indicator, Potential Significant Deficiency, or Monitor — Below Escalation Threshold.",
        whyItMatters:
          "It communicates review priority in PCAOB-aligned, deliberately hedged language an audit-literate reader recognizes.",
        whatToRequest:
          "Drive evidence requests from the row's specific indicators, not the label alone.",
        whatItDoesNotMean:
          "These are review labels, not audit conclusions or opinions — the words \"Potential,\" \"Indicator,\" and \"Monitor\" are intentional.",
      },
      {
        indicator: "Risk-Pattern Similarity",
        aka: "internally fraud_probability",
        whatItMeans:
          "A 0–1 score for how closely a transaction resembles the rule-flagged population in its measurable features.",
        whyItMatters:
          "It's a relative \"looks like the flagged ones\" indicator that helps rank the queue.",
        whatToRequest:
          "Nothing on its own — use it to prioritize, then request evidence based on the row's indicators.",
        whatItDoesNotMean:
          "It is not a probability that fraud occurred; the file has no fraud labels, so no such probability can exist.",
      },
      {
        indicator: "Anomaly score",
        whatItMeans:
          "The unsupervised model's measure of how statistically unusual a row is across all its features (more negative = more unusual).",
        whyItMatters:
          "It's the original \"this stands out\" signal before any audit logic is applied.",
        whatToRequest: "Nothing directly; it's an input to prioritization.",
        whatItDoesNotMean:
          "Statistically unusual is not the same as wrong — context and evidence decide that.",
      },
    ],
  },
];

export default function DataDictionary({ defaultOpen = false }) {
  const [open, setOpen] = React.useState(defaultOpen);

  return (
    <Card id="signal-guide">
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle className="text-lg flex items-center gap-2">
          <BookOpen className="h-4 w-4" />
          Section 5 — How to Read LUCENT Signals
        </CardTitle>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setOpen((v) => !v)}
          className="gap-2"
        >
          {open ? (
            <>
              <ChevronDown className="h-4 w-4" /> Hide signal guide
            </>
          ) : (
            <>
              <ChevronRight className="h-4 w-4" /> Show signal guide
            </>
          )}
        </Button>
      </CardHeader>

      {open && (
        <CardContent className="space-y-6">
          <p className="text-sm text-muted-foreground">
            Each signal below explains what it means, why it matters, what evidence to
            request, and — importantly — what it does not mean. LUCENT indicates review
            priority; it never concludes fraud.
          </p>
          {GROUPS.map((group) => (
            <div key={group.title} className="space-y-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground border-b pb-1">
                {group.title}
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {group.cards.map((c) => (
                  <SignalCard key={c.indicator} {...c} />
                ))}
              </div>
            </div>
          ))}
        </CardContent>
      )}
    </Card>
  );
}
