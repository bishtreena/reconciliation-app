from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, JSON,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ReconRun(Base):
    __tablename__ = "recon_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)

    platform_txns: Mapped[list["PlatformTransaction"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    bank_settlements: Mapped[list["BankSettlement"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    gap_results: Mapped[list["GapResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class PlatformTransaction(Base):
    __tablename__ = "platform_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recon_runs.id"), nullable=False, index=True
    )
    txn_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    parent_txn_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    run: Mapped["ReconRun"] = relationship(back_populates="platform_txns")


class BankSettlement(Base):
    __tablename__ = "bank_settlements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recon_runs.id"), nullable=False, index=True
    )
    settlement_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    settlement_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    batch_id: Mapped[str] = mapped_column(String(64), nullable=False)

    run: Mapped["ReconRun"] = relationship(back_populates="bank_settlements")


class GapResult(Base):
    __tablename__ = "gap_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("recon_runs.id"), nullable=False, index=True
    )
    gap_type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), nullable=True)
    source_row_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    classification_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    llm_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    run: Mapped["ReconRun"] = relationship(back_populates="gap_results")
