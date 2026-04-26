"""Narrative generation engine.

Produces a short, plain-English executive summary of a reconciliation run
using the aggregated numbers and classified gaps.  Optionally calls Claude
for a polished version; falls back to a deterministic template when the
LLM is disabled.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .aggregator import AggregateSummary
    from .models import GapResult

# ── Feature flag ─────────────────────────────────────────────────────────
# Set to False to skip Claude API calls.  A hard-coded template string
# will be returned instead.
USE_LLM = True

# ── Currency formatting helper ───────────────────────────────────────────

def _inr(value: Decimal | float | int) -> str:
    """Format a number as ₹X,XX,XXX.XX (Indian grouping)."""
    v = Decimal(str(value)).quantize(Decimal("0.01"))
    sign = "-" if v < 0 else ""
    v = abs(v)
    integer_part, _, decimal_part = str(v).partition(".")
    decimal_part = decimal_part or "00"

    # Indian grouping: last 3 digits, then groups of 2
    if len(integer_part) <= 3:
        grouped = integer_part
    else:
        last3 = integer_part[-3:]
        rest = integer_part[:-3]
        chunks: list[str] = []
        while rest:
            chunks.append(rest[-2:])
            rest = rest[:-2]
        chunks.reverse()
        grouped = ",".join(chunks) + "," + last3

    return f"{sign}₹{grouped}.{decimal_part}"


# =====================================================================
# Template-based fallback
# =====================================================================

def _template_narrative(
    summary: AggregateSummary,
    gap_results: list[GapResult],
) -> str:
    """Produce a deterministic narrative without any LLM call."""
    total_gaps = len(gap_results)
    platform = _inr(summary.platform_total)
    bank = _inr(summary.bank_total)
    gap = _inr(summary.total_gap)

    lines: list[str] = [
        f"Your reconciliation shows a {gap} gap between platform "
        f"({platform}) and bank ({bank}).",
    ]

    # Timing
    timing = summary.gap_breakdown.get("TIMING_CROSS_MONTH")
    if timing:
        count, amount = timing
        lines.append(
            f"{_inr(amount)} across {count} transaction(s) is timing — "
            f"these settlements will clear in the first days of next month."
        )

    # Rounding
    if summary.rounding_drift_total != 0:
        lines.append(
            f"{_inr(summary.rounding_drift_total)} is rounding drift across "
            f"{len(summary.matching_rounding_count)} rounding-candidate transactions."
            if hasattr(summary, "matching_rounding_count")
            else f"{_inr(summary.rounding_drift_total)} is aggregate rounding drift "
            f"from bank settlements that settled marginally below platform amounts."
        )

    # Duplicates
    dup_plat = summary.gap_breakdown.get("DUPLICATE_PLATFORM")
    dup_bank = summary.gap_breakdown.get("DUPLICATE_BANK")
    dup_parts: list[str] = []
    if dup_plat:
        dup_parts.append(f"{_inr(dup_plat[1])} in {dup_plat[0]} platform-side duplicate(s)")
    if dup_bank:
        dup_parts.append(f"{_inr(dup_bank[1])} in {dup_bank[0]} bank-side duplicate(s)")
    if dup_parts:
        lines.append(" and ".join(dup_parts) + " need manual review.")

    # Orphan refunds
    orphan = summary.gap_breakdown.get("ORPHAN_REFUND")
    if orphan:
        lines.append(
            f"{_inr(orphan[1])} in {orphan[0]} orphan refund(s) — "
            f"refunds whose parent payment is missing from platform data — "
            f"require investigation."
        )

    # Unknown
    unknown = summary.gap_breakdown.get("UNKNOWN")
    if unknown:
        lines.append(
            f"{unknown[0]} gap(s) totalling {_inr(unknown[1])} could not be "
            f"auto-classified and should be reviewed manually."
        )

    if total_gaps == 0:
        lines.append("No classification gaps were detected.")

    return " ".join(lines)


# =====================================================================
# LLM-based narrative
# =====================================================================

_SYSTEM_PROMPT = (
    "You are a CFO-level financial analyst writing a reconciliation summary "
    "for a non-technical stakeholder. Write exactly 4-5 sentences in plain "
    "English. Use the Indian Rupee symbol (₹) for amounts. Be concise, "
    "specific, and action-oriented. Do NOT use markdown formatting."
)


def _llm_narrative(
    summary: AggregateSummary,
    gap_results: list[GapResult],
) -> str:
    """Call Claude claude-sonnet-4-5 to produce a polished narrative."""
    try:
        from anthropic import Anthropic
        from dotenv import load_dotenv
        load_dotenv()

        # Build a compact data payload for the model
        breakdown_items = {
            gap_type: {"count": count, "total_amount": float(amount)}
            for gap_type, (count, amount) in summary.gap_breakdown.items()
        }

        payload = {
            "platform_total": float(summary.platform_total),
            "bank_total": float(summary.bank_total),
            "total_gap": float(summary.total_gap),
            "rounding_drift_total": float(summary.rounding_drift_total),
            "total_classified_gaps": len(gap_results),
            "gap_breakdown": breakdown_items,
        }

        user_msg = (
            "Here are the reconciliation numbers. Write a 4-5 sentence "
            "executive summary.\n\n"
            f"{json.dumps(payload, indent=2)}"
        )

        client = Anthropic()
        response = client.messages.create(
            model="claude-sonnet-4-5-20250514",
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text.strip()

    except Exception as exc:  # noqa: BLE001
        # If the LLM call fails, fall back to the template
        return _template_narrative(summary, gap_results)


# =====================================================================
# Public entry point
# =====================================================================

def generate_narrative(
    aggregate_summary: AggregateSummary,
    gap_results: list[GapResult],
) -> str:
    """Generate a plain-English executive summary of the reconciliation.

    When ``USE_LLM`` is True (default) the narrative is produced by Claude
    claude-sonnet-4-5.  When False — or if the API call fails — a deterministic
    template is used instead.

    Parameters
    ----------
    aggregate_summary:
        The :class:`AggregateSummary` from :func:`compute_aggregates`.
    gap_results:
        The list of :class:`GapResult` objects from :func:`classify_gaps`.

    Returns
    -------
    str
        A 4-5 sentence narrative suitable for an executive audience.
    """
    if USE_LLM:
        return _llm_narrative(aggregate_summary, gap_results)
    return _template_narrative(aggregate_summary, gap_results)
