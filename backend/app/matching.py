"""Reconciliation matching engine.

Joins platform transactions to bank settlements using Pandas vectorised
operations and classifies each row into one of four buckets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BankSettlement, PlatformTransaction


@dataclass
class MatchingResult:
    """Output of ``run_matching``.

    Each list contains dicts that represent individual rows from the source
    tables, enriched with ``amount_diff`` where applicable.
    """

    run_id: int = 0
    matched: list[dict[str, Any]] = field(default_factory=list)
    rounding_candidates: list[dict[str, Any]] = field(default_factory=list)
    unmatched_platform: list[dict[str, Any]] = field(default_factory=list)
    unmatched_bank: list[dict[str, Any]] = field(default_factory=list)


def _load_platform(run_id: int, db: Session) -> pd.DataFrame:
    """Load all platform transactions for *run_id* into a DataFrame."""
    stmt = select(
        PlatformTransaction.txn_id,
        PlatformTransaction.timestamp,
        PlatformTransaction.amount,
        PlatformTransaction.currency,
        PlatformTransaction.customer_id,
        PlatformTransaction.type,
        PlatformTransaction.parent_txn_id,
        PlatformTransaction.status,
    ).where(PlatformTransaction.run_id == run_id)

    rows = db.execute(stmt).all()
    if not rows:
        return pd.DataFrame(
            columns=[
                "txn_id", "timestamp", "amount", "currency",
                "customer_id", "type", "parent_txn_id", "status",
            ]
        )
    df = pd.DataFrame(rows, columns=[
        "txn_id", "timestamp", "amount", "currency",
        "customer_id", "type", "parent_txn_id", "status",
    ])
    # Ensure amount is a Python Decimal stored as float64 for arithmetic
    df["amount"] = df["amount"].apply(float)
    return df


def _load_bank(run_id: int, db: Session) -> pd.DataFrame:
    """Load all bank settlements for *run_id* into a DataFrame."""
    stmt = select(
        BankSettlement.settlement_id,
        BankSettlement.settlement_date,
        BankSettlement.amount,
        BankSettlement.reference_id,
        BankSettlement.batch_id,
    ).where(BankSettlement.run_id == run_id)

    rows = db.execute(stmt).all()
    if not rows:
        return pd.DataFrame(
            columns=[
                "settlement_id", "settlement_date", "amount",
                "reference_id", "batch_id",
            ]
        )
    df = pd.DataFrame(rows, columns=[
        "settlement_id", "settlement_date", "amount",
        "reference_id", "batch_id",
    ])
    df["amount"] = df["amount"].apply(float)
    return df


def run_matching(
    run_id: int,
    db_session: Session,
    tolerance: Decimal = Decimal("0.10"),
) -> MatchingResult:
    """Execute the core matching logic for a reconciliation run.

    Algorithm
    ---------
    1. Load platform transactions and bank settlements into DataFrames.
    2. Left-join ``platform`` on ``bank`` using ``txn_id == reference_id``.
    3. Compute ``amount_diff = platform.amount − bank.amount`` for every row.
    4. Classify each row:
       - **matched** – reference found **and** ``|amount_diff| ≤ tolerance``
       - **rounding_candidates** – subset of *matched* where
         ``amount_diff ≠ 0`` (within tolerance but not exact)
       - **unmatched_platform** – no bank counterpart
    5. Separately identify **unmatched_bank** – bank settlements whose
       ``reference_id`` has no corresponding platform ``txn_id``.

    Returns a :class:`MatchingResult` dataclass.
    """
    tol = float(tolerance)
    platform_df = _load_platform(run_id, db_session)
    bank_df = _load_bank(run_id, db_session)

    result = MatchingResult(run_id=run_id)

    if platform_df.empty and bank_df.empty:
        return result

    # ── 1. Separate duplicates ───────────────────────────────────────────
    plat_dups_mask = platform_df.duplicated(subset=["txn_id"], keep="first")
    valid_platform_df = platform_df[~plat_dups_mask]
    dup_platform_df = platform_df[plat_dups_mask]

    bank_dups_mask = bank_df.duplicated(subset=["reference_id"], keep="first")
    valid_bank_df = bank_df[~bank_dups_mask]
    dup_bank_df = bank_df[bank_dups_mask]

    # ── 2. Filter bank settlements to the platform's primary month ───────
    # This ensures cross-month timing differences fail to match so they
    # fall into unmatched_platform and can be picked up by the classifier.
    if not valid_platform_df.empty:
        primary_month = valid_platform_df["timestamp"].dt.month.mode()[0]
        primary_year = valid_platform_df["timestamp"].dt.year.mode()[0]
        
        valid_bank_df = valid_bank_df.copy()
        valid_bank_df["_month"] = valid_bank_df["settlement_date"].apply(lambda d: d.month)
        valid_bank_df["_year"] = valid_bank_df["settlement_date"].apply(lambda d: d.year)
        
        is_current_month = (valid_bank_df["_month"] == primary_month) & (valid_bank_df["_year"] == primary_year)
        bank_df_curr = valid_bank_df[is_current_month].drop(columns=["_month", "_year"])
    else:
        bank_df_curr = valid_bank_df.copy()

    # ── 3. Left-join valid_platform → bank_df_curr ───────────────────────
    merged = valid_platform_df.merge(
        bank_df_curr,
        left_on="txn_id",
        right_on="reference_id",
        how="left",
        suffixes=("_platform", "_bank"),
    )

    # ── 4. Compute amount difference ─────────────────────────────────────
    merged["amount_diff"] = merged["amount_platform"] - merged["amount_bank"]

    # ── 5. Boolean masks ─────────────────────────────────────────────────
    has_bank = merged["reference_id"].notna()
    within_tol = merged["amount_diff"].abs() <= tol
    exact_match = merged["amount_diff"] == 0.0

    mask_matched = has_bank & within_tol
    mask_rounding = mask_matched & ~exact_match
    mask_unmatched_platform = ~has_bank

    # ── 6. Populate result lists ─────────────────────────────────────────
    if mask_matched.any():
        result.matched = merged.loc[mask_matched].to_dict(orient="records")

    if mask_rounding.any():
        result.rounding_candidates = merged.loc[mask_rounding].to_dict(orient="records")

    unmatched_plat_list = []
    if mask_unmatched_platform.any():
        unmatched_main = (
            merged.loc[mask_unmatched_platform]
            .drop(columns=[
                "settlement_id", "settlement_date",
                "amount_bank", "reference_id", "batch_id", "amount_diff",
            ])
            .rename(columns={"amount_platform": "amount"})
            .to_dict(orient="records")
        )
        unmatched_plat_list.extend(unmatched_main)
        
    # Append the extracted duplicates
    if not dup_platform_df.empty:
        unmatched_plat_list.extend(dup_platform_df.to_dict(orient="records"))
    
    result.unmatched_platform = unmatched_plat_list

    # ── 7. Unmatched bank ────────────────────────────────────────────────
    # Look only within the current month pool so we don't flag Feb rows
    # identically with `UNKNOWN` gaps. We also add the explicit duplicates.
    unmatched_bank_list = []
    platform_ids = set(valid_platform_df["txn_id"])
    mask_unmatched_bank = ~bank_df_curr["reference_id"].isin(platform_ids)
    
    if mask_unmatched_bank.any():
        unmatched_bank_list.extend(bank_df_curr.loc[mask_unmatched_bank].to_dict(orient="records"))
        
    if not dup_bank_df.empty:
        unmatched_bank_list.extend(dup_bank_df.to_dict(orient="records"))
        
    result.unmatched_bank = unmatched_bank_list

    return result
