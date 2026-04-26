from datetime import datetime, date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class PlatformTxn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    txn_id: str
    timestamp: datetime
    amount: Decimal
    currency: str
    customer_id: str
    type: str
    parent_txn_id: Optional[str] = None
    status: str


class BankSettlement(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    settlement_id: str
    settlement_date: date
    amount: Decimal
    reference_id: str
    batch_id: str


class GapResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    gap_type: str
    amount: Optional[Decimal] = None
    source_row_json: Optional[dict[str, Any]] = None
    classification_confidence: Optional[float] = None
    llm_reasoning: Optional[str] = None


class GapBreakdown(BaseModel):
    gap_type: str
    count: int
    total_amount: Decimal


class ReconSummary(BaseModel):
    run_id: int
    created_at: datetime
    status: str
    total_platform_txns: int
    total_bank_settlements: int
    platform_total: Decimal
    bank_total: Decimal
    total_gap_amount: Decimal
    rounding_drift_total: Decimal
    total_gaps: int
    gap_breakdown: list[GapBreakdown]
    narrative: Optional[str] = None
