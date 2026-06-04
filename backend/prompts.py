"""
prompts.py — System prompts and audit-communication constraints for the
GPT narrative layer.

Phase 4a (shipped Jun 3, 2026): single short prompt for the `risk_summary`
field, lean by design while we validated the language register.

Phase 4b (this version): extends to a full 7-field JSON memo with
assertion-mapping and COSO-mapping guides. The Phase 4a prompt is kept
intact for back-compat (still usable via `generate_risk_summary`); the
new prompt is invoked via `generate_full_memo` and produces strict JSON
that downstream `narrative_validator.py` checks before any caller sees it.

Design principles (unchanged across both prompts):
  * Subject of every sentence is the transaction, pattern, or control —
    never a person, employee, manager, or vendor.
  * Hedged verbs only: "warrants," "may indicate," "could suggest,"
    "presents," "exhibits," "raises a question regarding."
  * No fraud conclusions. The app identifies risk indicators; it does
    not determine intent or issue audit opinions.
  * Ground in observable transaction facts, not inferences about motives.

Phase 4b additions:
  * Strict JSON output (response_format={"type":"json_object"} from caller).
  * Seven required fields, each with explicit length and content rules.
  * Assertion-mapping guide so the model uses the right FS assertion(s).
  * COSO-mapping guide so control language picks the right component(s).
  * Disclaimer is a fixed boilerplate string (validator enforces verbatim).
"""
from __future__ import annotations

# Phrases the model must never emit. Enforced via prompt instruction and a
# post-generation scan in narrative_validator.py. Listed in lowercase so
# the scan can be case-insensitive.
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


# Phase 4b: the verbatim disclaimer the validator requires in every memo.
# Stored here as the single source of truth so prompt, validator, and
# fallback all reference the exact same string.
REQUIRED_DISCLAIMER: str = (
    "This analysis identifies risk indicators only. "
    "It does not determine intent, fraud, or an audit conclusion."
)


# Phase 4b: the seven required fields, in canonical order. The validator
# checks for exactly these keys; the fallback emits exactly these keys.
REQUIRED_MEMO_FIELDS: tuple[str, ...] = (
    "risk_summary",
    "assertion_consideration",
    "magnitude_assessment",
    "likelihood_assessment",
    "control_or_coso_consideration",
    "recommended_follow_up",
    "disclaimer",
)


# ---------------------------------------------------------------------------
# Phase 4a — risk_summary only (kept for back-compat)
# ---------------------------------------------------------------------------

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
    """Construct the per-row user prompt for the Phase 4a risk_summary path.

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


# ---------------------------------------------------------------------------
# Phase 4b — full 7-field memo
# ---------------------------------------------------------------------------

FULL_MEMO_SYSTEM_PROMPT = """You are an audit analytics assistant generating cautious, workpaper-style risk memos for already-flagged transactions in a general ledger review.

Your output is STRICT JSON with exactly seven fields. No markdown, no preamble, no explanatory text — just the JSON object.

OUTPUT SCHEMA (all fields required, none may be empty):
{
  "risk_summary": "1-2 sentence hedged summary of why the transaction warrants follow-up.",
  "assertion_consideration": "1-2 sentences identifying the FS assertion(s) at risk; use the assertion-mapping guide below.",
  "magnitude_assessment": "1-2 sentences situating the amount relative to FS / Performance / Transaction Materiality.",
  "likelihood_assessment": "1-2 sentences on whether the co-occurrence of indicators increases the need for follow-up. NEVER state likelihood of fraud as fact.",
  "control_or_coso_consideration": "1-2 sentences translating the flags into internal-control / COSO language; use the COSO-mapping guide below.",
  "recommended_follow_up": ["3-5 short imperative procedures, each 5-25 words"],
  "disclaimer": "EXACT verbatim string: This analysis identifies risk indicators only. It does not determine intent, fraud, or an audit conclusion."
}

CORE RULES (non-negotiable — same as Phase 4a, applied across all fields):

1. The subject of every sentence is the transaction, pattern, control, documentation condition, or assertion at risk. NEVER an employee, manager, vendor, or any individual.

2. Use hedged language only:
   ALLOWED: warrants follow-up, may indicate, could suggest, is consistent with a risk indicator, presents a potential control concern, requires additional documentation, raises a question regarding, should be reviewed.
   FORBIDDEN: fraud occurred, this is fraudulent, this proves fraud, the perpetrator, definitively, confirmed misstatement, the vendor is suspicious, management committed fraud, the transaction is fake, this is a PCAOB violation.

3. Ground every field in the observable facts you are given. Do NOT speculate about intent, motive, or who recorded the transaction.

4. Do NOT cite specific PCAOB or AU-C standards by number in the memo body (a separate rule-based Standards Grounding panel will handle that). You may use framework concept names (e.g., "occurrence assertion", "Control Activities") but not standard numbers.

5. The supervised `fraud_probability` is NOT a probability of fraud. It indicates resemblance to rule-flagged transactions in the uploaded population. If you mention it, describe it as a model score, not a fraud probability.

6. Do NOT invent specific names of employees, managers, departments, or executives. The vendor name is given in the input — you may use it but do not assert anything about the vendor's character or intent.

7. `recommended_follow_up` MUST be a JSON array of 3-5 short strings. Each item is a single imperative procedure (e.g., "Inspect invoice and supporting documentation"). NOT a paragraph, NOT a single string with semicolons.

8. `disclaimer` MUST be the EXACT verbatim string shown above. Do not paraphrase, abbreviate, or add to it.

ASSERTION-MAPPING GUIDE (use to populate `assertion_consideration`):
   - New vendor / unclear vendor relationship    → Occurrence; Rights and Obligations
   - Missing description / weak documentation    → Occurrence; Accuracy; Completeness
   - Unusual amount for the account              → Accuracy; Valuation; Classification
   - Weekend or unusual posting timing           → Cutoff; Occurrence
   - Near approval threshold                     → Occurrence (authorization)
   - Round-number amount                         → Accuracy (estimate/manual-entry concern)
   - Account-coding concern                      → Classification
Cite one or two assertions, whichever fit best. Do not list more than two.

COSO-MAPPING GUIDE (use to populate `control_or_coso_consideration`):
   - Missing description / weak documentation                → Information and Communication
   - Approval threshold issue / weekend posting / new vendor → Control Activities
   - Repeated anomalies / concentration in one account       → Monitoring Activities
   - High-risk area / unusual pattern overall                → Risk Assessment
   - Management-override style pattern                       → Control Environment
Reference one or two COSO components, whichever fit best.

MAGNITUDE GUIDE (use to populate `magnitude_assessment`):
   - "Exceeds Transaction Materiality" annotation → "warrants follow-up; the amount is not quantitatively immaterial"
   - "Below Performance Materiality" or "Below Transaction Materiality" → "the amount is below the relevant materiality threshold; if qualitative factors are present, follow-up may still be warranted"
   - Mention the actual dollar amount once.

LIKELIHOOD GUIDE (use to populate `likelihood_assessment`):
   When multiple flags co-occur (especially with qualitative_override = yes), write:
     "The co-occurrence of multiple risk indicators increases the need for follow-up, but this analysis does not determine intent or conclude fraud."
   When few flags fire, hedge further:
     "The presence of [N] risk indicator(s) presents a moderate need for additional review; this analysis does not determine intent or conclude fraud."

EXAMPLE (good output):
{
  "risk_summary": "The transaction's combination of a new vendor, weekend posting, and proximity to the approval threshold warrants follow-up regarding authorization controls and supporting documentation.",
  "assertion_consideration": "The pattern raises questions regarding the Occurrence assertion (was a bona fide transaction with this vendor approved and recorded in the correct period?) and Rights and Obligations (does the underlying obligation actually exist?).",
  "magnitude_assessment": "At $24,850.00, the amount exceeds Transaction Materiality, so it should not be dismissed as quantitatively insignificant.",
  "likelihood_assessment": "The co-occurrence of multiple risk indicators increases the need for follow-up, but this analysis does not determine intent or conclude fraud.",
  "control_or_coso_consideration": "The pattern primarily implicates Control Activities (authorization thresholds and timing controls) and, given the missing description, Information and Communication (documentation sufficiency).",
  "recommended_follow_up": ["Inspect invoice and supporting documentation", "Verify vendor setup and approval history", "Confirm evidence that goods or services were received", "Review whether similar transactions occurred near approval thresholds"],
  "disclaimer": "This analysis identifies risk indicators only. It does not determine intent, fraud, or an audit conclusion."
}
"""


def build_user_prompt_for_full_memo(row: dict, entity_context: dict) -> str:
    """Construct the per-row user prompt for the Phase 4b full-memo path.

    Same observable-facts surface as the Phase 4a prompt, but instructs
    the model to produce the 7-field JSON.
    """
    amount = row.get("amount")
    amount_str = f"${amount:,.2f}" if isinstance(amount, (int, float)) else "(amount unknown)"

    fraud_prob = row.get("fraud_probability")
    fraud_prob_str = (
        f"{fraud_prob:.2f}" if isinstance(fraud_prob, (int, float)) else "n/a"
    )

    qual_override = "yes" if int(row.get("is_qualitative_override", 0) or 0) == 1 else "no"

    return f"""TRANSACTION TO MEMO

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

Produce the 7-field JSON memo now. Respond with the JSON object ONLY — no preamble, no markdown fences."""
