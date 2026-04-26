"""End-to-end reconciliation tests.

Runs data_generator with seed=42, ingests the CSVs produced, executes
the matching engine, and asserts that the gap buckets reflect the planted
anomalies.

NOTE on timing gaps
───────────────────
The data generator creates 15 platform txns (Jan 30-31) whose bank
settlements land in February.  Because ``ingest_csvs`` loads the entire
CSV — including those Feb settlements — the matching engine *does* find
a bank counterpart for every timing txn and classifies them as matched.
In a production system the reconciliation run would be scoped to a
calendar month, so those 15 would surface as unmatched.  The tests below
verify the behaviour of the *current* pipeline (no date filtering).

NOTE on duplicates
──────────────────
• 2 platform-side duplicates: the left-join maps each copy to the same
  bank settlement, adding 2 extra matched rows.
• 1 bank-side duplicate: the left-join expands the single platform row
  into 2 matches, adding 1 extra matched row.
Together they add 3 extra rows to the matched set (872 base → 875?
Actually total matched = 873 because only the net extras are counted).
"""

from __future__ import annotations

import importlib
import os
import random
import sys
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

# Ensure the package root is importable
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.models import Base, PlatformTransaction, BankSettlement as BankSettlementModel
from app.ingestion import ingest_csvs
from app.matching import run_matching, MatchingResult


# ─── Constants from data_generator (seed=42) ────────────────────────────
N_PAYMENTS = 800
N_REFUNDS = 50
N_TIMING = 15
N_ROUNDING = 200
N_DUPLICATES = 3       # 2 platform-side, 1 bank-side with seed=42
N_ORPHAN = 5

# With seed=42 the generator produces:
#   Platform rows : 800 + 50 + 15 + 2 (plat dups) + 5 (orphans) = 872
#   Bank rows     : 800 + 50 + 15 + 1 (bank dup)  + 5 (orphans) = 871
EXPECTED_PLATFORM_ROWS = 872
EXPECTED_BANK_ROWS = 871


from sqlalchemy.pool import StaticPool

@pytest.fixture(scope="module")
def db_engine():
    """Create an in-memory SQLite engine with schema."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def run_id_and_result(db_engine):
    """Generate data, ingest, and run matching — once for the module."""
    # Re-run the generator to (re-)produce the CSVs (idempotent with seed=42)
    # Reset seeds before generating to guarantee reproducibility
    import app.data_generator as dg
    # Reset global counters for fresh generation
    dg._txn_seq = 0
    dg._stl_seq = 0
    random.seed(42)
    np.random.seed(42)
    from faker import Faker
    Faker.seed(42)
    dg.fake = Faker("en_IN")
    dg.generate()

    sample_dir = Path(dg.SAMPLE_DIR)
    platform_csv = sample_dir / "platform_transactions.csv"
    bank_csv = sample_dir / "bank_settlements.csv"

    with Session(db_engine) as db:
        rid = ingest_csvs(str(platform_csv), str(bank_csv), db)
        result = run_matching(rid, db, tolerance=Decimal("0.10"))
    return rid, result


@pytest.fixture(scope="module")
def run_id(run_id_and_result):
    return run_id_and_result[0]


@pytest.fixture(scope="module")
def result(run_id_and_result) -> MatchingResult:
    return run_id_and_result[1]


# ─── Ingestion sanity checks ────────────────────────────────────────────

class TestIngestion:

    def test_platform_row_count(self, db_engine, run_id):
        with Session(db_engine) as db:
            count = db.query(PlatformTransaction).filter_by(run_id=run_id).count()
        assert count == EXPECTED_PLATFORM_ROWS, (
            f"Expected {EXPECTED_PLATFORM_ROWS} platform txns, got {count}"
        )

    def test_bank_row_count(self, db_engine, run_id):
        with Session(db_engine) as db:
            count = db.query(BankSettlementModel).filter_by(run_id=run_id).count()
        assert count == EXPECTED_BANK_ROWS, (
            f"Expected {EXPECTED_BANK_ROWS} bank settlements, got {count}"
        )


# ─── Matching result assertions ──────────────────────────────────────────

class TestMatching:
    """Verify that the matching engine classifies rows correctly.

    The matching engine filters the bank settlements to the primary month 
    of the platform data (January). Consequently, cross-month timing 
    settlements (February) are not matched. Also, duplicates are separated 
    before the join, so they don't inflate the matched count.

    • Timing txns (15) have bank counterparts in February, so they are unmatched.
    • Duplicates (2 platform, 1 bank) are separated.
    • The 200 rounding-drifted bank rows differ by ≤ Rs.0.05.
    """

    # ── matched ──────────────────────────────────────────────────────────
    def test_matched_count(self, result: MatchingResult):
        """Total matched rows = valid platform rows in primary month.

        Base: 872 platform rows.
        - 2 platform dups
        - 15 timing (bank settlement in Feb)
        Total = 855
        """
        matched = len(result.matched)
        assert matched == 855, (
            f"Expected 855 matched rows, got {matched}"
        )

    # ── rounding candidates ──────────────────────────────────────────────
    def test_rounding_candidates(self, result: MatchingResult):
        """200 rounding drifts planted. Bank duplicate is separated, so 
        exactly 200 rounding candidates."""
        rc = len(result.rounding_candidates)
        assert rc == 200, (
            f"Expected 200 rounding candidates, got {rc}"
        )

    def test_rounding_amounts_within_tolerance(self, result: MatchingResult):
        """Every rounding candidate must have |amount_diff| ≤ 0.10."""
        for row in result.rounding_candidates:
            diff = abs(row["amount_diff"])
            assert diff <= 0.10, (
                f"Rounding candidate has amount_diff={diff} > tolerance 0.10"
            )
            assert diff > 0, "Rounding candidate should not be an exact match"

    # ── unmatched platform ───────────────────────────────────────────────
    def test_unmatched_platform_count(self, result: MatchingResult):
        """15 timing txns + 2 platform dups = 17 unmatched platform."""
        up = len(result.unmatched_platform)
        assert up == 17, (
            f"Expected 17 unmatched platform, got {up}"
        )

    # ── unmatched bank ───────────────────────────────────────────────────
    def test_unmatched_bank_count(self, result: MatchingResult):
        """1 bank dup = 1 unmatched bank."""
        ub = len(result.unmatched_bank)
        assert ub == 1, (
            f"Expected 1 unmatched bank, got {ub}"
        )

    # ── result type ──────────────────────────────────────────────────────
    def test_result_is_dataclass(self, result: MatchingResult):
        assert hasattr(result, "matched")
        assert hasattr(result, "rounding_candidates")
        assert hasattr(result, "unmatched_platform")
        assert hasattr(result, "unmatched_bank")

    # ── total coverage ───────────────────────────────────────────────────
    def test_all_platform_txns_accounted_for(self, result: MatchingResult):
        """matched + unmatched_platform should cover every platform row."""
        total = len(result.matched) + len(result.unmatched_platform)
        assert total == 872

    def test_rounding_is_subset_of_matched(self, result: MatchingResult):
        """Every rounding candidate must also appear in matched."""
        matched_ids = {
            (r["txn_id"], r.get("settlement_id"))
            for r in result.matched
        }
        for r in result.rounding_candidates:
            key = (r["txn_id"], r.get("settlement_id"))
            assert key in matched_ids, (
                f"Rounding candidate {key} not found in matched set"
            )

    def test_no_matched_row_exceeds_tolerance(self, result: MatchingResult):
        """Sanity: every matched row has |amount_diff| ≤ 0.10."""
        for row in result.matched:
            assert abs(row["amount_diff"]) <= 0.10

# ─── End-to-End API Test ──────────────────────────────────────────────
from fastapi.testclient import TestClient
from app.main import app, get_db
from unittest.mock import patch
import json
from decimal import Decimal as D

client = TestClient(app)

# Ground-truth constants from data_generator.py (seed=42)
GT_PLATFORM_TXNS     = 872
GT_BANK_SETTLEMENTS  = 871
GT_ROUNDING_DRIFT    = D("6.00")
GT_TIMING_COUNT      = 15
GT_TIMING_AMOUNT     = D("371228.27")
GT_DUP_PLATFORM      = 2
GT_DUP_BANK          = 1
GT_ORPHAN_COUNT      = 5
GT_ORPHAN_AMOUNT     = D("125375.56")
GT_TOTAL_GAPS        = 23   # 15 timing + 2 plat_dup + 1 bank_dup + 5 orphan


def test_full_e2e_reconciliation(db_engine):
    """Upload CSVs → reconcile → fetch results and verify against ground truth."""

    def override_get_db():
        with Session(db_engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    import app.data_generator as dg
    sample_dir = Path(dg.SAMPLE_DIR)

    # ── Step 1: Upload ────────────────────────────────────────────────────
    with open(sample_dir / "platform_transactions.csv", "rb") as fp, \
         open(sample_dir / "bank_settlements.csv", "rb") as fb:
        upload_res = client.post("/upload", files={
            "platform": ("platform.csv", fp, "text/csv"),
            "bank":     ("bank.csv",     fb, "text/csv"),
        })
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    run_id = upload_res.json()["run_id"]

    # Patch both LLM flags so no real API calls are made
    with patch("app.classifier.USE_LLM", False), \
         patch("app.narrator.USE_LLM", False):

        # ── Step 2: Reconcile ─────────────────────────────────────────────
        recon_res = client.post(f"/reconcile/{run_id}")
        assert recon_res.status_code == 200, f"Reconcile failed: {recon_res.text}"

        # ── Step 3: Fetch results ─────────────────────────────────────────
        results_res = client.get(f"/results/{run_id}")
        assert results_res.status_code == 200, f"Results failed: {results_res.text}"
        data = results_res.json()

        print("\n\n================ FULL JSON RESPONSE ================")
        print(json.dumps(data, indent=2, default=str))
        print("=====================================================\n")

        summary = data["summary"]
        gaps    = data["gaps"]

        # ── Step 4a: Row counts ───────────────────────────────────────────
        assert summary["total_platform_txns"]    == GT_PLATFORM_TXNS
        assert summary["total_bank_settlements"] == GT_BANK_SETTLEMENTS

        # ── Step 4b: Rounding drift ───────────────────────────────────────
        assert D(str(summary["rounding_drift_total"])) == GT_ROUNDING_DRIFT, (
            f"rounding_drift_total: expected {GT_ROUNDING_DRIFT}, "
            f"got {summary['rounding_drift_total']}"
        )

        # ── Step 4c: Total gap count ──────────────────────────────────────
        assert summary["total_gaps"] == GT_TOTAL_GAPS, (
            f"total_gaps: expected {GT_TOTAL_GAPS}, got {summary['total_gaps']}"
        )

        # ── Step 4d: Per-type counts and amounts (±1 tolerance on counts) ──
        gap_counts  = {b["gap_type"]: b["count"]        for b in summary["gap_breakdown"]}
        gap_amounts = {b["gap_type"]: D(str(b["total_amount"])) for b in summary["gap_breakdown"]}

        assert abs(gap_counts.get("TIMING_CROSS_MONTH", 0) - GT_TIMING_COUNT)   <= 1
        assert abs(gap_counts.get("DUPLICATE_PLATFORM", 0) - GT_DUP_PLATFORM)   <= 1
        assert abs(gap_counts.get("DUPLICATE_BANK",     0) - GT_DUP_BANK)       <= 1
        assert abs(gap_counts.get("ORPHAN_REFUND",      0) - GT_ORPHAN_COUNT)   <= 1

        # Amounts must match exactly (they come straight from the CSV amounts)
        assert gap_amounts.get("TIMING_CROSS_MONTH", D("0")) == GT_TIMING_AMOUNT, (
            f"TIMING amount mismatch: {gap_amounts.get('TIMING_CROSS_MONTH')}"
        )
        assert gap_amounts.get("ORPHAN_REFUND", D("0")) == GT_ORPHAN_AMOUNT, (
            f"ORPHAN amount mismatch: {gap_amounts.get('ORPHAN_REFUND')}"
        )

        # ── Step 4e: All 4 gap types present in the gaps dict ─────────────
        for gt in ("TIMING_CROSS_MONTH", "DUPLICATE_PLATFORM",
                   "DUPLICATE_BANK", "ORPHAN_REFUND"):
            assert gt in gaps, f"Gap type {gt!r} missing from results"
            assert len(gaps[gt]) > 0, f"No rows for gap type {gt!r}"

        # ── Step 4f: No gap has null confidence (rule-based = 1.0) ────────
        for gap_type, rows in gaps.items():
            for row in rows:
                assert row["classification_confidence"] is not None, (
                    f"Gap id={row['id']} ({gap_type}) has null confidence"
                )

        # ── Step 4g: Narrative is present and non-empty ───────────────────
        assert summary["narrative"], "Narrative should be a non-empty string"
