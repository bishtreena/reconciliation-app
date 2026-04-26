import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from faker import Faker

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
Faker.seed(SEED)
fake = Faker("en_IN")

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RECON_DIR = os.path.dirname(os.path.dirname(APP_DIR))
SAMPLE_DIR = os.path.join(RECON_DIR, "sample_data")

N_PAYMENTS = 800
N_REFUNDS = 50
N_TIMING = 15
N_ROUNDING = 200
N_DUPLICATES = 3
N_ORPHAN = 5

_txn_seq = 0
_stl_seq = 0


def _next_txn() -> str:
    global _txn_seq
    _txn_seq += 1
    return f"TXN{_txn_seq:07d}"


def _next_stl() -> str:
    global _stl_seq
    _stl_seq += 1
    return f"STL{_stl_seq:07d}"


def _rand_ts(start: datetime, end: datetime) -> datetime:
    span = int((end - start).total_seconds())
    return start + timedelta(seconds=random.randint(0, span))


def _rand_amount() -> float:
    return round(random.uniform(100, 50_000), 2)


def _rand_customer() -> str:
    return f"CUST{fake.uuid4().replace('-', '')[:8].upper()}"


def _batch(d) -> str:
    return f"BATCH{d.strftime('%Y%m%d')}"


def generate() -> None:
    platform: list[dict] = []
    bank: list[dict] = []

    timing_ids: set[str] = set()
    timing_amounts: list[float] = []
    rounding_gaps: list[float] = []
    dup_info: list[dict] = []
    orphan_info: list[dict] = []

    # ── Regular payments (Jan 1-28) ──────────────────────────────────────────
    # Bounded to Jan 1-28 so their settlements (+ 1-2 days) stay within January.
    payment_pool: list[dict] = []
    for _ in range(N_PAYMENTS):
        tid = _next_txn()
        ts = _rand_ts(datetime(2026, 1, 1), datetime(2026, 1, 28, 23, 59, 59))
        amt = _rand_amount()
        platform.append(
            dict(txn_id=tid, timestamp=ts, amount=amt, currency="INR",
                 customer_id=_rand_customer(), type="payment",
                 parent_txn_id=None, status="success")
        )
        payment_pool.append(platform[-1])
        settle_dt = (ts + timedelta(days=random.randint(1, 2))).date()
        bank.append(
            dict(settlement_id=_next_stl(), settlement_date=settle_dt,
                 amount=amt, reference_id=tid, batch_id=_batch(settle_dt))
        )

    # ── Regular refunds (capped to Jan 28 so settlements stay in January) ────
    refund_parents = random.sample(payment_pool, N_REFUNDS)
    for parent in refund_parents:
        tid = _next_txn()
        ts = min(
            parent["timestamp"] + timedelta(days=random.randint(1, 5)),
            datetime(2026, 1, 28, 23, 59, 59),
        )
        amt = parent["amount"]
        platform.append(
            dict(txn_id=tid, timestamp=ts, amount=amt, currency="INR",
                 customer_id=parent["customer_id"], type="refund",
                 parent_txn_id=parent["txn_id"], status="success")
        )
        settle_dt = min(
            (ts + timedelta(days=random.randint(1, 2))).date(),
            datetime(2026, 1, 30).date(),
        )
        bank.append(
            dict(settlement_id=_next_stl(), settlement_date=settle_dt,
                 amount=amt, reference_id=tid, batch_id=_batch(settle_dt))
        )

    # ── GAP 1: Timing ─────────────────────────────────────────────────────────
    # Payments on Jan 30-31 whose bank settlements land in February.
    # In a January reconciliation run these appear as unmatched platform txns.
    for _ in range(N_TIMING):
        tid = _next_txn()
        ts = _rand_ts(datetime(2026, 1, 30), datetime(2026, 1, 31, 23, 59, 59))
        amt = _rand_amount()
        platform.append(
            dict(txn_id=tid, timestamp=ts, amount=amt, currency="INR",
                 customer_id=_rand_customer(), type="payment",
                 parent_txn_id=None, status="success")
        )
        timing_ids.add(tid)
        timing_amounts.append(amt)
        settle_dt = _rand_ts(
            datetime(2026, 2, 1), datetime(2026, 2, 2, 23, 59, 59)
        ).date()
        bank.append(
            dict(settlement_id=_next_stl(), settlement_date=settle_dt,
                 amount=amt, reference_id=tid, batch_id=_batch(settle_dt))
        )

    # ── GAP 2: Rounding drift ─────────────────────────────────────────────────
    # Bank settles ₹0.01–₹0.05 less than the platform amount.
    # Each individual delta is within tolerance but material in aggregate.
    eligible = [b for b in bank if b["reference_id"] not in timing_ids]
    for b in random.sample(eligible, N_ROUNDING):
        drift = round(random.uniform(0.01, 0.05), 2)
        b["amount"] = round(b["amount"] - drift, 2)
        rounding_gaps.append(drift)

    # ── GAP 3: Duplicates ─────────────────────────────────────────────────────
    # Identical row appended to one dataset (side chosen randomly per case).
    for _ in range(N_DUPLICATES):
        side = random.choice(["platform", "bank"])
        if side == "platform":
            src = random.choice(platform)
            platform.append(dict(src))
            dup_info.append({"side": "platform", "ref": src["txn_id"],
                             "amount": src["amount"]})
        else:
            src = random.choice(bank)
            bank.append(dict(src))
            dup_info.append({"side": "bank", "ref": src["settlement_id"],
                             "amount": src["amount"]})

    # ── GAP 4: Orphan refunds ─────────────────────────────────────────────────
    # Refunds whose parent_txn_id references a transaction that doesn't exist.
    existing_ids = {r["txn_id"] for r in platform}
    for i in range(N_ORPHAN):
        ghost = f"TXN_GHOST{i + 1:03d}"
        assert ghost not in existing_ids
        tid = _next_txn()
        ts = _rand_ts(datetime(2026, 1, 5), datetime(2026, 1, 28, 23, 59, 59))
        amt = _rand_amount()
        platform.append(
            dict(txn_id=tid, timestamp=ts, amount=amt, currency="INR",
                 customer_id=_rand_customer(), type="refund",
                 parent_txn_id=ghost, status="success")
        )
        orphan_info.append({"txn_id": tid, "ghost_parent": ghost, "amount": amt})
        settle_dt = (ts + timedelta(days=random.randint(1, 2))).date()
        bank.append(
            dict(settlement_id=_next_stl(), settlement_date=settle_dt,
                 amount=amt, reference_id=tid, batch_id=_batch(settle_dt))
        )

    # ── Write CSVs ────────────────────────────────────────────────────────────
    os.makedirs(SAMPLE_DIR, exist_ok=True)
    platform_df = (
        pd.DataFrame(platform)
        .sort_values("timestamp")
        .reset_index(drop=True)
    )
    bank_df = (
        pd.DataFrame(bank)
        .sort_values("settlement_date")
        .reset_index(drop=True)
    )
    platform_df.to_csv(
        os.path.join(SAMPLE_DIR, "platform_transactions.csv"), index=False
    )
    bank_df.to_csv(
        os.path.join(SAMPLE_DIR, "bank_settlements.csv"), index=False
    )

    # ── Ground-truth summary ──────────────────────────────────────────────────
    total_timing = sum(timing_amounts)
    total_rounding = sum(rounding_gaps)
    total_orphan = sum(o["amount"] for o in orphan_info)
    dup_platform_amt = sum(d["amount"] for d in dup_info if d["side"] == "platform")
    dup_bank_amt = sum(d["amount"] for d in dup_info if d["side"] == "bank")

    W = 64
    SEP = "-" * W
    print("=" * W)
    print(" GROUND TRUTH SUMMARY".center(W))
    print("=" * W)
    print(f"  Platform transactions  : {len(platform_df):>5,}")
    print(f"  Bank settlements       : {len(bank_df):>5,}")
    print()
    print("  PLANTED GAPS")
    print("  " + SEP)

    print(f"  1. Timing  (Jan 30-31 txns settled Feb 1-2)")
    print(f"     Count  : {len(timing_ids):>3}")
    print(f"     Amount : Rs.{total_timing:>12,.2f}")
    print()

    print(f"  2. Rounding drift  (bank short Rs.0.01-0.05 per txn)")
    print(f"     Count  : {N_ROUNDING:>3}")
    print(f"     Gap    : Rs.{total_rounding:>12,.2f}")
    print()

    print(f"  3. Duplicates  (exact row copy in one dataset)")
    print(f"     Cases  : {len(dup_info):>3}")
    for d in dup_info:
        print(f"     * {d['side']:8s}  ref={d['ref']}  Rs.{d['amount']:>10,.2f}")
    print(f"     Inflated platform vol : Rs.{dup_platform_amt:>10,.2f}")
    print(f"     Inflated bank vol     : Rs.{dup_bank_amt:>10,.2f}")
    print()

    print(f"  4. Orphan refunds  (parent_txn_id not in platform data)")
    print(f"     Cases  : {len(orphan_info):>3}")
    for o in orphan_info:
        print(f"     * {o['txn_id']}  ghost={o['ghost_parent']}  Rs.{o['amount']:>10,.2f}")
    print(f"     Amount : Rs.{total_orphan:>12,.2f}")
    print()

    print("  EXPECTED AGGREGATE MONETARY GAP")
    print("  " + SEP)
    print(f"  Rounding drift   (permanent shortfall)      Rs.{total_rounding:>10,.2f}")
    print(f"  Orphan refunds   (unrecoverable credits)    Rs.{total_orphan:>10,.2f}")
    print(f"  Timing           (clears next month)        Rs.{total_timing:>10,.2f}")
    print(f"  {'-' * 52}")
    grand = total_rounding + total_orphan + total_timing
    print(f"  Total                                       Rs.{grand:>10,.2f}")
    print("=" * W)
    print(f"  CSVs -> {SAMPLE_DIR}")
    print("=" * W)


if __name__ == "__main__":
    generate()
