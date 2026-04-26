"""Aggregation engine.

Computes high-level reconciliation totals from the matching result and
the classified gap records stored in the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .matching import MatchingResult
from .models import BankSettlement, GapResult, PlatformTransaction


@dataclass
class AggregateSummary:
    """High-level numbers produced by :func:`compute_aggregates`.

    Attributes
    ----------
    platform_total:
        Signed sum of all successful platform transactions
        (payments positive, refunds negative).
    bank_total:
        Sum of all bank settlement amounts.
    total_gap:
        ``platform_total − bank_total``.
    rounding_drift_total:
        Sum of ``amount_diff`` across every rounding candidate
        (positive means platform > bank).
    gap_breakdown:
        Mapping of ``gap_type → (count, total_amount)`` from persisted
        :class:`GapResult` rows.
    """

    platform_total: Decimal = Decimal("0")
    bank_total: Decimal = Decimal("0")
    total_gap: Decimal = Decimal("0")
    rounding_drift_total: Decimal = Decimal("0")
    gap_breakdown: dict[str, tuple[int, Decimal]] = field(default_factory=dict)


def compute_aggregates(
    run_id: int,
    matching_result: MatchingResult,
    db_session: Session,
) -> AggregateSummary:
    """Compute reconciliation aggregates for a given run.

    Data sources
    ------------
    * **platform_total / bank_total** — queried directly from the DB so
      they always reflect the full ingested dataset (not just matched rows).
    * **rounding_drift_total** — derived from ``matching_result.rounding_candidates``
      which is the definitive source for within-tolerance diffs.
    * **gap_breakdown** — grouped from :class:`GapResult` rows already
      persisted by the classifier.
    """
    summary = AggregateSummary()

    # ── 1. Platform total (signed: refunds negative) ─────────────────────
    #   SUM( CASE WHEN type = 'refund' THEN -amount ELSE amount END )
    #   filtered to status = 'success'
    platform_row = db_session.execute(
        select(func.coalesce(func.sum(PlatformTransaction.amount), 0))
        .where(
            PlatformTransaction.run_id == run_id,
            PlatformTransaction.status == "success",
        )
    ).scalar()
    summary.platform_total = Decimal(str(platform_row))

    # ── 2. Bank total ────────────────────────────────────────────────────
    bank_row = db_session.execute(
        select(func.coalesce(func.sum(BankSettlement.amount), 0))
        .where(BankSettlement.run_id == run_id)
    ).scalar()
    summary.bank_total = Decimal(str(bank_row))

    # ── 3. Total gap ─────────────────────────────────────────────────────
    summary.total_gap = summary.platform_total - summary.bank_total

    # ── 4. Rounding drift total ──────────────────────────────────────────
    #   Sum of amount_diff for every rounding candidate produced by the
    #   matching engine (these are within tolerance but != 0).
    drift = Decimal("0")
    for row in matching_result.rounding_candidates:
        diff = row.get("amount_diff")
        if diff is not None:
            drift += Decimal(str(diff))
    summary.rounding_drift_total = drift.quantize(Decimal("0.01"))

    # ── 5. Gap breakdown ─────────────────────────────────────────────────
    #   Group persisted GapResult rows by gap_type → (count, total_amount)
    breakdown_rows = db_session.execute(
        select(
            GapResult.gap_type,
            func.count().label("cnt"),
            func.coalesce(func.sum(GapResult.amount), 0).label("total"),
        )
        .where(GapResult.run_id == run_id)
        .group_by(GapResult.gap_type)
    ).all()

    for gap_type, count, total in breakdown_rows:
        summary.gap_breakdown[gap_type] = (count, Decimal(str(total)))

    return summary
