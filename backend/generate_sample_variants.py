"""
generate_sample_variants.py

Produces three demo general-ledger CSVs for ARGUS, each with a deliberately
different risk profile, matching the engine's exact required schema and the
feature-trigger thresholds it keys on.

Required columns: date, amount, account_code, account_name, vendor,
                  description, journal_ref

Feature triggers reproduced here:
  - round number .......... abs(amount) % 100 == 0
  - weekend posting ....... date falls on Sat/Sun
  - missing description ... blank
  - new vendor ............ vendor appears < 3 times in the file
  - near threshold ........ 95%-100% of $5,000 / $10,000 / $25,000
  - amount z-score ........ per-account statistical outlier
  - year-end concentration  posted in the last 10 days of the period
A "stacked" row trips several at once -> fraud_risk_flag = 1 -> qualitative
override -> High tier. Optional debit/credit/dr_cr_pattern columns are omitted
on purpose (hash-total and cross-footing checks then report Pass/skipped).
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

PERIOD_START = date(2024, 1, 1)
PERIOD_END = date(2024, 12, 31)
SPAN_DAYS = (PERIOD_END - PERIOD_START).days

COA_CORP = {
    "4010": "Sales Revenue", "4020": "Service Revenue",
    "5010": "Cost of Goods Sold",
    "6010": "Professional Fees", "6020": "Software Subscriptions",
    "6030": "Insurance Expense", "6040": "Rent Expense",
    "6050": "Utilities Expense", "6060": "Marketing Expense",
    "6070": "Travel & Entertainment", "6080": "Repairs & Maintenance",
    "6090": "Office Supplies", "7010": "Bank Fees",
}

COA_NONPROFIT = {
    "4010": "Donations & Contributions", "4020": "Grant Revenue",
    "4030": "Program Service Fees",
    "6010": "Program Services", "6020": "Management & General",
    "6030": "Fundraising", "6040": "Salaries & Wages",
    "6050": "Occupancy", "6060": "Office Supplies",
    "6070": "Professional Fees", "6080": "Travel", "7010": "Bank Fees",
}

ESTABLISHED_VENDORS = [
    "Acme Supplies", "Globex Corp", "Initech LLC", "Umbrella Co",
    "Stark Industries", "Hooli Inc", "Vandelay Imports", "Soylent Foods",
    "Massive Dynamic", "Wayne Enterprises", "Cyberdyne Systems", "Tyrell Corp",
]
RARE_VENDOR_STEMS = [
    "Pinecone Partners", "Redrock LLC", "Brightway Group", "Echo Services",
    "Vista Trading Co", "Maple Holdings", "Quantum Ventures", "Summit Holdings",
    "Apex Traders", "Northwind Co", "Beacon LLC", "Cedar & Co",
]
DESCRIPTIONS = [
    "Monthly invoice", "Service charge", "Supplies purchase", "Consulting fee",
    "Subscription renewal", "Maintenance work", "Equipment rental",
    "Vendor payment", "Reimbursement", "Contract milestone",
]


def weekday_date(rng):
    while True:
        d = PERIOD_START + timedelta(days=int(rng.integers(0, SPAN_DAYS + 1)))
        if d.weekday() < 5:
            return d


def weekend_date(rng):
    while True:
        d = PERIOD_START + timedelta(days=int(rng.integers(0, SPAN_DAYS + 1)))
        if d.weekday() >= 5:
            return d


def yearend_date(rng):
    return date(2024, 12, int(rng.integers(22, 32)))


def messy_amount(mean, rng):
    """Realistic amount with cents, never an exact multiple of 100."""
    a = round(max(25.0, float(rng.normal(mean, mean * 0.25))), 2)
    if a % 100 == 0:
        a = round(a + float(rng.uniform(1, 99)), 2)
    return a


def make_dataset(coa, n_rows, single_rate, stacked_rate, seed):
    rng = np.random.default_rng(seed)
    codes = list(coa.keys())
    expense_codes = [c for c in codes if c[0] in ("5", "6", "7")]
    acct_mean = {c: float(rng.uniform(700, 6000)) for c in codes}

    n_single = int(n_rows * single_rate)
    n_stacked = int(n_rows * stacked_rate)
    n_base = n_rows - n_single - n_stacked
    rows, jref = [], 1

    def add(row):
        nonlocal jref
        row["journal_ref"] = f"JE-{jref:05d}"
        rows.append(row)
        jref += 1

    # Baseline: weekday, present description, established vendor, messy amount
    for _ in range(n_base):
        c = codes[int(rng.integers(0, len(codes)))]
        add({
            "date": weekday_date(rng).isoformat(),
            "amount": messy_amount(acct_mean[c], rng),
            "account_code": c, "account_name": coa[c],
            "vendor": ESTABLISHED_VENDORS[int(rng.integers(0, len(ESTABLISHED_VENDORS)))],
            "description": DESCRIPTIONS[int(rng.integers(0, len(DESCRIPTIONS)))],
        })

    # Single-flag anomalies: one signal each (no override)
    kinds = ["weekend", "missing", "new_vendor", "round", "near", "outlier"]
    for _ in range(n_single):
        c = codes[int(rng.integers(0, len(codes)))]
        k = kinds[int(rng.integers(0, len(kinds)))]
        row = {
            "date": weekday_date(rng).isoformat(),
            "amount": messy_amount(acct_mean[c], rng),
            "account_code": c, "account_name": coa[c],
            "vendor": ESTABLISHED_VENDORS[int(rng.integers(0, len(ESTABLISHED_VENDORS)))],
            "description": DESCRIPTIONS[int(rng.integers(0, len(DESCRIPTIONS)))],
        }
        if k == "weekend":
            row["date"] = weekend_date(rng).isoformat()
        elif k == "missing":
            row["description"] = ""
        elif k == "new_vendor":
            stem = RARE_VENDOR_STEMS[int(rng.integers(0, len(RARE_VENDOR_STEMS)))]
            row["vendor"] = f"{stem} #{int(rng.integers(1000, 9999))}"
        elif k == "round":
            row["amount"] = float(int(rng.integers(3, 40)) * 100)
        elif k == "near":
            t = [5000, 10000, 25000][int(rng.integers(0, 3))]
            row["amount"] = round(t * 0.97, 2)
        elif k == "outlier":
            row["amount"] = round(acct_mean[c] * float(rng.uniform(4, 8)), 2)
        add(row)

    # Stacked anomalies: several signals -> fraud_risk_flag -> override -> High
    for i in range(n_stacked):
        c = expense_codes[int(rng.integers(0, len(expense_codes)))]
        t = [5000, 10000, 25000][int(rng.integers(0, 3))]
        amt = float(round(t * 0.96 / 100) * 100)          # round + near-threshold band
        stem = RARE_VENDOR_STEMS[int(rng.integers(0, len(RARE_VENDOR_STEMS)))]
        yearend = (i % 3 == 0)                            # a third land in the year-end window
        add({
            "date": (yearend_date(rng) if yearend else weekend_date(rng)).isoformat(),
            "amount": amt,
            "account_code": c, "account_name": coa[c],
            "vendor": f"{stem} #{int(rng.integers(1000, 9999))}",
            "description": "",
        })

    df = pd.DataFrame(rows, columns=[
        "date", "amount", "account_code", "account_name",
        "vendor", "description", "journal_ref",
    ])
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


SPECS = {
    "sample_gl_clean.csv":     dict(coa=COA_CORP,      n_rows=450, single_rate=0.03, stacked_rate=0.00, seed=11),
    "sample_gl_high_risk.csv": dict(coa=COA_CORP,      n_rows=800, single_rate=0.07, stacked_rate=0.11, seed=22),
    "sample_gl_nonprofit.csv": dict(coa=COA_NONPROFIT, n_rows=550, single_rate=0.05, stacked_rate=0.03, seed=33),
}

if __name__ == "__main__":
    for fname, spec in SPECS.items():
        df = make_dataset(**spec)
        df.to_csv(fname, index=False)
        wk = pd.to_datetime(df["date"]).dt.weekday.ge(5).sum()
        rnd = (df["amount"].abs() % 100 == 0).sum()
        miss = df["description"].fillna("").str.strip().eq("").sum()
        vc = df["vendor"].value_counts()
        newv = df["vendor"].map(vc).lt(3).sum()
        print(f"{fname}: {len(df)} rows | weekend={wk} round={rnd} "
              f"missing_desc={miss} rare_vendor_rows={newv} "
              f"dates {df['date'].min()}..{df['date'].max()}")
