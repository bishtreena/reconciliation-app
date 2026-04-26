from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Union

import pandas as pd
from sqlalchemy import insert as sa_insert
from sqlalchemy.orm import Session

from .models import BankSettlement, PlatformTransaction, ReconRun

_PathOrFile = Union[str, Path, io.IOBase]

_PLATFORM_COLS = [
    "txn_id", "timestamp", "amount", "currency",
    "customer_id", "type", "parent_txn_id", "status",
]
_BANK_COLS = [
    "settlement_id", "settlement_date", "amount", "reference_id", "batch_id",
]


class IngestionError(ValueError):
    """Raised when uploaded CSV data fails validation. Safe to surface to callers."""


def _require_columns(df: pd.DataFrame, required: list[str], label: str) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise IngestionError(
            f"{label}: missing required columns: {sorted(missing)}"
        )


def _coerce_platform(df: pd.DataFrame) -> list[dict]:
    df = df[_PLATFORM_COLS].copy()

    try:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    except Exception as exc:
        raise IngestionError(
            f"platform_transactions: cannot parse 'timestamp' as datetime: {exc}"
        ) from exc
    if df["timestamp"].isna().any():
        raise IngestionError(
            "platform_transactions: 'timestamp' contains null or unparseable values"
        )

    try:
        df["amount"] = df["amount"].apply(lambda v: Decimal(str(v)))
    except (InvalidOperation, ValueError) as exc:
        raise IngestionError(
            f"platform_transactions: non-numeric value in 'amount': {exc}"
        ) from exc

    # NaN → None so SQLAlchemy stores NULL for the nullable FK column
    df["parent_txn_id"] = df["parent_txn_id"].where(df["parent_txn_id"].notna(), other=None)

    return df.to_dict(orient="records")


def _coerce_bank(df: pd.DataFrame) -> list[dict]:
    df = df[_BANK_COLS].copy()

    try:
        df["settlement_date"] = pd.to_datetime(df["settlement_date"]).dt.date
    except Exception as exc:
        raise IngestionError(
            f"bank_settlements: cannot parse 'settlement_date' as date: {exc}"
        ) from exc
    if df["settlement_date"].isna().any():
        raise IngestionError(
            "bank_settlements: 'settlement_date' contains null or unparseable values"
        )

    try:
        df["amount"] = df["amount"].apply(lambda v: Decimal(str(v)))
    except (InvalidOperation, ValueError) as exc:
        raise IngestionError(
            f"bank_settlements: non-numeric value in 'amount': {exc}"
        ) from exc

    return df.to_dict(orient="records")


def ingest_csvs(
    platform_file: _PathOrFile,
    bank_file: _PathOrFile,
    db: Session,
) -> int:
    """Parse, validate, and persist both CSVs under a new ReconRun.

    Validation is performed before any DB writes; on failure an IngestionError
    is raised and the database is left unchanged.

    Returns the newly created run_id.
    """
    try:
        platform_df = pd.read_csv(platform_file)
    except Exception as exc:
        raise IngestionError(f"Cannot read platform CSV: {exc}") from exc

    try:
        bank_df = pd.read_csv(bank_file)
    except Exception as exc:
        raise IngestionError(f"Cannot read bank CSV: {exc}") from exc

    _require_columns(platform_df, _PLATFORM_COLS, "platform_transactions")
    _require_columns(bank_df, _BANK_COLS, "bank_settlements")

    # Coerce all types before touching the DB so failures are clean
    platform_rows = _coerce_platform(platform_df)
    bank_rows = _coerce_bank(bank_df)

    run = ReconRun(
        created_at=datetime.now(tz=timezone.utc).replace(tzinfo=None),
        status="pending",
    )
    db.add(run)
    db.flush()  # materialise run.id without committing

    db.execute(
        sa_insert(PlatformTransaction),
        [{"run_id": run.id, **row} for row in platform_rows],
    )
    db.execute(
        sa_insert(BankSettlement),
        [{"run_id": run.id, **row} for row in bank_rows],
    )

    db.commit()
    return run.id
