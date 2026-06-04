"""
prompts.py — System prompts and audit-communication constraints for the
GPT narrative layer.

Phase 4a scope: a single short prompt for the `risk_summary` field. Phase
4b will extend this to a full 7-field memo with assertion/COSO mapping
tables. Keeping the prompt lean now means lower latency, lower token cost,
and a clearer baseline to evaluate generation quality before adding more
structure.

Design principles:
  * Subject of every sentence is the transaction, pattern, or control —
    never a person, employee, manager, or vendor.
  * Hedged verbs only: "warrants," "may indicate," "could suggest,"
    "presents," "exhibits," "raises a question regarding."
  * No fraud conclusions. The app identifies risk indicators; it does
    not determine intent or issue audit opinions.
  * Ground in observable transaction facts (amount, timing, vendor
    status, documentation), not inferences about motives.
  * Stay within 1-2 sentences for risk_summary.
"""
from __future__ import annotations

# Phrases the model must never emit. Enforced via prompt instruction and a
# post-generation scan in narrative.py. Listed in lowercase so the scan can
# be case-insensitive.
BANNED_PHRASES: tuple[str, ...] = (
    "fraud occurred",
    "this is fraudulent",
    "this is fraud",
    "this proves fraud",
    "proves fraud",
    "confirms fraud",
    "confirmed misstatement",
    "confirms a material weakness",
    "confirms a significant deficiency",
    "the vendor is suspicious",
    "the perpetrator",
    "management committed fraud",
    "employee committed fraud",
    "definitively",
    "the transaction is fake",
    "this is a pcaob violation",
    "the employee stole",
    "the manager stole",
)


RISK_SUMMARY_SYSTEM_PROMPT = """You are an audit analytics assistant generating cautious, workpaper-style risk summaries for already-flagged transactions in a general ledger review.

Your output is a single 1-2 sentence risk summary explaining why the transaction warrants follow-up. Output plain text only — no JSON, no markdown, no headings.

CORE RULES (non-negotiable):

1. The subject of your sentences is the transaction, pattern, control, or documentation condition. NEVER an employee, manager, vendor, or any individual.

2. Use hedged language only:
   ALLOWED: warrants follow-up, may indicate, could suggest, is consistent with a risk indicator, presents a potential control concern, requires additional documentation, raises a question regarding, should be reviewed.
   FORBIDDEN: fraud occurred, this is fraudulent, this proves fraud, the perpetrator, definitively, confirmed misstatement, the vendor is suspicious, management committed fraud, the transaction is fake.

3. Ground your summary in the observable facts you are given (amount, active flags, materiality annotation, control gap level, fraud risk status, anomaly score, qualitative override status). Do NOT speculate about intent, motive, or who recorded the transaction.

4. Do NOT issue audit opinions. Do NOT conclude fraud. Do NOT cite specific PCAOB or AU-C standards by number in this summary (Phase 4b will add structured standards grounding separately).

5. If the row already triggered a qualitative override, briefly acknowledge that the co-occurrence of indicators is the reason for elevated concern — but still hedge.

6. The supervised classifier's `fraud_probability` is NOT a probability that fraud occurred. It indicates resemblance to other rule-flagged transactions in the uploaded population. If you mention it, describe it as a model score, not a fraud probability.

7. Output exactly 1-2 sentences. No bullet points. No preamble like "Here is a summary:". Just the summary.

EXAMPLE (good output):
"The transaction's combination of a new vendor, weekend posting, missing description, and amount just under the approval threshold warrants follow-up regarding authorization controls and supporting documentation. This pattern may indicate a control gap but does not establish intent or fraud."

EXAMPLE (bad — do NOT do this):
"The employee likely tried to bypass approval thresholds by structuring this fraudulent payment to a shell vendor."
(Reasons: subject is a person, uses "fraudulent," asserts intent.)
"""


def build_user_prompt(row: dict, entity_context: dict) -> str:
    """Construct the per-row user prompt with the observable facts the LLM
    is allowed to ground its summary in.

    Only fields the spec sanctions as narrative basis are included:
      active_flags, pcaob_label, final_tier, materiality_annotation,
      control_gap, fraud_risk_flag, qualitative_override, anomaly_score,
      amount, account, vendor.
    """
    amount = row.get("amount")
    amount_str = f"${amount:,.2f}" if isinstance(amount, (int, float)) else "(amount unknown)"

    fraud_prob = row.get("fraud_probability")
    fraud_prob_str = (
        f"{fraud_prob:.2f}" if isinstance(fraud_prob, (int, float)) else "n/a"
    )

    qual_override = "yes" if int(row.get("is_qualitative_override", 0) or 0) == 1 else "no"

    return f"""TRANSACTION TO SUMMARIZE

Entity context:
  - Entity type:        {entity_context.get('entity_type', 'n/a')}
  - Audit period:       {entity_context.get('period_start', 'n/a')} to {entity_context.get('period_end', 'n/a')}

Observable transaction facts:
  - Amount:                          {amount_str}
  - Account:                         {row.get('account_name', 'n/a')}
  - Vendor:                          {row.get('vendor', 'n/a')}
  - Active flags:                    {row.get('active_flags', '(none)')}
  - PCAOB label:                     {row.get('pcaob_label', 'n/a')}
  - Final tier:                      {row.get('final_tier', 'n/a')}
  - Materiality annotation:          {row.get('materiality_annotation', 'n/a')}
  - Control gap score (0-2):         {row.get('control_gap_score', 0)}
  - Fraud risk indicator triggered:  {"yes" if int(row.get('fraud_risk_flag', 0) or 0) == 1 else "no"}
  - Qualitative override fired:      {qual_override}
  - Supervised model score:          {fraud_prob_str} (resemblance to rule-flagged patterns, NOT P(fraud))

Write the 1-2 sentence risk summary now."""
