"""Gap classification engine.

Examines every unmatched row produced by the matching engine and assigns a
gap type.  Rule-based classifiers are tried first; anything that remains
``UNKNOWN`` is optionally sent to Claude for a best-guess classification.
"""

from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .matching import MatchingResult
from .models import BankSettlement, GapResult, PlatformTransaction

# ── Feature flag ─────────────────────────────────────────────────────────
# Set to False to skip Claude API calls during testing.  UNKNOWN gaps will
# be stored with confidence=0 and a note that LLM classification is off.
USE_LLM = True

# ── Gap-type constants ───────────────────────────────────────────────────
TIMING_CROSS_MONTH = "TIMING_CROSS_MONTH"
DUPLICATE_PLATFORM = "DUPLICATE_PLATFORM"
DUPLICATE_BANK = "DUPLICATE_BANK"
ORPHAN_REFUND = "ORPHAN_REFUND"
UNKNOWN = "UNKNOWN"

# ── LLM prompts ─────────────────────────────────────────────────────────
_CATEGORIES = """\
1. TIMING_CROSS_MONTH — A platform transaction from near the end of the \
month whose bank settlement landed in the first few days of the next month. \
The amounts match but the settlement falls outside the reconciliation window.

2. DUPLICATE_PLATFORM — The same transaction ID appears more than once in \
the platform data, inflating the platform-side volume.

3. DUPLICATE_BANK — The same bank reference ID appears more than once in \
the bank settlement data, inflating the bank-side volume.

4. ORPHAN_REFUND — A refund transaction on the platform side whose \
parent_txn_id does not correspond to any known payment in the platform data.

5. UNKNOWN — None of the above categories apply or there is insufficient \
information to classify.\
"""

_SYSTEM_PROMPT = (
    "You are a financial reconciliation analyst. "
    "Given details about an unmatched transaction row, classify it into "
    "one of the following categories and explain your reasoning.\n\n"
    f"{_CATEGORIES}\n\n"
    "Respond with a JSON object (no markdown fences) containing exactly:\n"
    '{\n'
    '  "category": "<one of the 5 categories above>",\n'
    '  "confidence": <float between 0 and 1>,\n'
    '  "reasoning": "<one sentence explaining why>"\n'
    '}'
)


# =====================================================================
# Rule-based detectors
# =====================================================================

def _is_timing_cross_month(
    txn_id: str,
    txn_timestamp: Any,
    run_id: int,
    db: Session,
) -> bool:
    """Return True if a bank settlement for *txn_id* exists in the first
    3 days of the month following the transaction's timestamp month.
    """
    ts = _to_datetime(txn_timestamp)
    if ts is None:
        return False

    # First 3 days of next month
    year, month = ts.year, ts.month
    if month == 12:
        next_start = date(year + 1, 1, 1)
    else:
        next_start = date(year, month + 1, 1)
    next_end = next_start + timedelta(days=2)  # inclusive

    count: int = db.execute(
        select(func.count())
        .select_from(BankSettlement)
        .where(
            BankSettlement.run_id == run_id,
            BankSettlement.reference_id == txn_id,
            BankSettlement.settlement_date >= next_start,
            BankSettlement.settlement_date <= next_end,
        )
    ).scalar() or 0
    return count > 0


def _is_duplicate_platform(txn_id: str, run_id: int, db: Session) -> bool:
    """Return True if *txn_id* appears more than once in the platform data."""
    count: int = db.execute(
        select(func.count())
        .select_from(PlatformTransaction)
        .where(
            PlatformTransaction.run_id == run_id,
            PlatformTransaction.txn_id == txn_id,
        )
    ).scalar() or 0
    return count > 1


def _is_duplicate_bank(reference_id: str, run_id: int, db: Session) -> bool:
    """Return True if *reference_id* appears more than once in the bank data."""
    count: int = db.execute(
        select(func.count())
        .select_from(BankSettlement)
        .where(
            BankSettlement.run_id == run_id,
            BankSettlement.reference_id == reference_id,
        )
    ).scalar() or 0
    return count > 1


def _is_orphan_refund(row: dict[str, Any], run_id: int, db: Session) -> bool:
    """Return True if the row is a refund whose parent payment doesn't exist."""
    if row.get("type") != "refund":
        return False

    parent = row.get("parent_txn_id")
    # A refund with no parent at all is inherently orphaned
    if not parent or (isinstance(parent, float) and math.isnan(parent)):
        return True

    count: int = db.execute(
        select(func.count())
        .select_from(PlatformTransaction)
        .where(
            PlatformTransaction.run_id == run_id,
            PlatformTransaction.txn_id == str(parent),
            PlatformTransaction.type == "payment",
        )
    ).scalar() or 0
    return count == 0


# =====================================================================
# Helpers
# =====================================================================

def _to_datetime(value: Any) -> datetime | None:
    """Best-effort conversion to :class:`datetime`."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    # pandas Timestamp
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _make_serialisable(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a row dict so it's JSON-serialisable (NaN, dates, Decimals)."""
    out: dict[str, Any] = {}
    for key, val in row.items():
        if isinstance(val, float) and math.isnan(val):
            out[key] = None
        elif isinstance(val, (datetime, date)):
            out[key] = val.isoformat()
        elif isinstance(val, Decimal):
            out[key] = float(val)
        elif hasattr(val, "item"):  # numpy scalar
            out[key] = val.item()
        else:
            out[key] = val
    return out


def _safe_decimal(value: Any) -> Decimal | None:
    """Best-effort conversion to :class:`Decimal`."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


# =====================================================================
# LLM fallback
# =====================================================================

def _llm_classify(row_details: dict[str, Any]) -> tuple[str, float, str]:
    """Call Claude claude-sonnet-4-5 (claude-sonnet-4-5-20250514) to classify an UNKNOWN gap.

    Returns ``(category, confidence, reasoning)``.  On failure or when
    ``USE_LLM`` is False, returns ``(UNKNOWN, 0.0, <reason>)``.
    """
    if not USE_LLM:
        return UNKNOWN, 0.0, "LLM classification disabled"

    try:
        from anthropic import Anthropic  # lazy import – keeps module importable w/o key
        from dotenv import load_dotenv
        load_dotenv()

        client = Anthropic()  # reads ANTHROPIC_API_KEY from env
        user_msg = (
            "Classify this unmatched reconciliation row:\n\n"
            f"{json.dumps(row_details, indent=2, default=str)}"
        )

        response = client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=256,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text.strip()
        # Strip markdown code fences if the model wraps them anyway
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]

        parsed = json.loads(text)
        category = parsed.get("category", UNKNOWN)
        confidence = min(max(float(parsed.get("confidence", 0.5)), 0.0), 1.0)
        reasoning = str(parsed.get("reasoning", "No reasoning provided"))

        valid_types = {
            TIMING_CROSS_MONTH, DUPLICATE_PLATFORM,
            DUPLICATE_BANK, ORPHAN_REFUND, UNKNOWN,
        }
        if category not in valid_types:
            category = UNKNOWN

        return category, confidence, reasoning

    except Exception as exc:  # noqa: BLE001
        return UNKNOWN, 0.0, f"LLM call failed: {exc}"


# =====================================================================
# Main entry point
# =====================================================================

def classify_gaps(
    matching_result: MatchingResult,
    db_session: Session,
) -> list[GapResult]:
    """Classify every unmatched row from *matching_result* and persist
    :class:`GapResult` records to the database.

    Classification priority (first match wins):

    **Unmatched platform rows**
      1. ``DUPLICATE_PLATFORM`` — txn_id appears >1 time in platform data
      2. ``ORPHAN_REFUND`` — refund whose parent_txn_id has no matching payment
      3. ``TIMING_CROSS_MONTH`` — bank settlement exists in first 3 days of
         the next calendar month
      4. ``UNKNOWN`` → forwarded to Claude if ``USE_LLM`` is True

    **Unmatched bank rows**
      1. ``DUPLICATE_BANK`` — reference_id appears >1 time in bank data
      2. ``UNKNOWN`` → forwarded to Claude if ``USE_LLM`` is True

    Returns the list of persisted :class:`GapResult` objects.
    """
    run_id = matching_result.run_id
    results: list[GapResult] = []

    # ── Unmatched platform rows ──────────────────────────────────────────
    for row in matching_result.unmatched_platform:
        txn_id: str = row.get("txn_id", "")
        safe_row = _make_serialisable(row)
        amount = _safe_decimal(row.get("amount"))

        gap_type = UNKNOWN
        confidence = 1.0
        reasoning: str | None = None

        # Priority: duplicate → orphan refund → timing → unknown
        if _is_duplicate_platform(txn_id, run_id, db_session):
            gap_type = DUPLICATE_PLATFORM
            reasoning = (
                f"txn_id {txn_id} appears more than once in platform data"
            )
        elif _is_orphan_refund(row, run_id, db_session):
            gap_type = ORPHAN_REFUND
            reasoning = (
                f"Refund {txn_id} with parent_txn_id "
                f"{row.get('parent_txn_id')} not found in platform payments"
            )
        elif _is_timing_cross_month(
            txn_id, row.get("timestamp"), run_id, db_session,
        ):
            gap_type = TIMING_CROSS_MONTH
            reasoning = (
                f"Bank settlement for {txn_id} found in "
                f"first 3 days of next month"
            )
        else:
            # No rule matched → try LLM
            gap_type, confidence, reasoning = _llm_classify(safe_row)

        results.append(GapResult(
            run_id=run_id,
            gap_type=gap_type,
            amount=amount,
            source_row_json=safe_row,
            classification_confidence=confidence,
            llm_reasoning=reasoning,
        ))

    # ── Unmatched bank rows ──────────────────────────────────────────────
    for row in matching_result.unmatched_bank:
        ref_id: str = row.get("reference_id", "")
        safe_row = _make_serialisable(row)
        amount = _safe_decimal(row.get("amount"))

        gap_type = UNKNOWN
        confidence = 1.0
        reasoning: str | None = None

        if _is_duplicate_bank(ref_id, run_id, db_session):
            gap_type = DUPLICATE_BANK
            reasoning = (
                f"reference_id {ref_id} appears more than once in bank data"
            )
        else:
            # No rule matched → try LLM
            gap_type, confidence, reasoning = _llm_classify(safe_row)

        results.append(GapResult(
            run_id=run_id,
            gap_type=gap_type,
            amount=amount,
            source_row_json=safe_row,
            classification_confidence=confidence,
            llm_reasoning=reasoning,
        ))

    # ── Orphan refunds (matched platform rows) ───────────────────────────
    # Catch orphan refunds that were MATCHED to a bank settlement (so they
    # didn't surface in unmatched_platform) but whose parent payment is
    # still missing from the platform data.
    # Unmatched orphan refunds are already handled in the loop above via
    # _is_orphan_refund(), so we skip any txn_id already classified there.
    already_classified = {row.get("txn_id") for row in matching_result.unmatched_platform}

    orphan_stmt = select(PlatformTransaction).where(
        PlatformTransaction.run_id == run_id,
        PlatformTransaction.type == "refund"
    )
    refunds = db_session.execute(orphan_stmt).scalars().all()

    payment_stmt = select(PlatformTransaction.txn_id).where(
        PlatformTransaction.run_id == run_id,
        PlatformTransaction.type == "payment"
    )
    payment_ids = set(db_session.execute(payment_stmt).scalars().all())

    for r in refunds:
        if r.txn_id in already_classified:
            continue  # already classified in unmatched_platform loop
        if not r.parent_txn_id or r.parent_txn_id not in payment_ids:
            safe_row = _make_serialisable(r.__dict__)
            safe_row.pop("_sa_instance_state", None)

            results.append(GapResult(
                run_id=run_id,
                gap_type=ORPHAN_REFUND,
                amount=_safe_decimal(r.amount),
                source_row_json=safe_row,
                classification_confidence=1.0,
                llm_reasoning=f"Refund with parent_txn_id {r.parent_txn_id} not found in platform payments"
            ))

    # ── Persist ──────────────────────────────────────────────────────────
    if results:
        db_session.add_all(results)
        db_session.commit()

    return results
