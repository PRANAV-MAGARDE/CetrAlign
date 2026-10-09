"""
src/simulated_db.py
-------------------
In-memory simulated database for a Futures & Options (F&O) finance company.
Provides realistic sample data and CRUD-style helper functions used by the
agent's tool layer.  All state is module-level so it persists for the
lifetime of the process (one server run).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Master data – Contracts
# ---------------------------------------------------------------------------

CONTRACTS: dict[str, dict[str, Any]] = {
    "NIFTY50-FUT-OCT26": {
        "contract_id": "NIFTY50-FUT-OCT26",
        "symbol": "NIFTY50OCT26FUT",
        "type": "FUTURES",
        "underlying": "NIFTY 50",
        "expiry": "2026-10-29",
        "lot_size": 50,
        "margin_required": 125000.0,  # INR per lot
        "current_price": 24850.0,
        "open_interest": 1_250_000,  # contracts outstanding
    },
    "BANKNIFTY-FUT-OCT26": {
        "contract_id": "BANKNIFTY-FUT-OCT26",
        "symbol": "BANKNIFTYOCT26FUT",
        "type": "FUTURES",
        "underlying": "BANK NIFTY",
        "expiry": "2026-10-29",
        "lot_size": 15,
        "margin_required": 45000.0,
        "current_price": 52300.0,
        "open_interest": 890_000,
    },
    "NIFTY50-CE-25000-OCT26": {
        "contract_id": "NIFTY50-CE-25000-OCT26",
        "symbol": "NIFTY50OCT2625000CE",
        "type": "OPTIONS",
        "underlying": "NIFTY 50",
        "expiry": "2026-10-29",
        "strike_price": 25000.0,
        "option_type": "CALL",
        "lot_size": 50,
        "margin_required": 15000.0,  # premium-based margin
        "current_price": 320.5,  # option premium
        "open_interest": 2_100_000,
    },
    "NIFTY50-PE-24500-OCT26": {
        "contract_id": "NIFTY50-PE-24500-OCT26",
        "symbol": "NIFTY50OCT2624500PE",
        "type": "OPTIONS",
        "underlying": "NIFTY 50",
        "expiry": "2026-10-29",
        "strike_price": 24500.0,
        "option_type": "PUT",
        "lot_size": 50,
        "margin_required": 12000.0,
        "current_price": 185.75,
        "open_interest": 1_750_000,
    },
    "RELIANCE-FUT-OCT26": {
        "contract_id": "RELIANCE-FUT-OCT26",
        "symbol": "RELIANCEOCT26FUT",
        "type": "FUTURES",
        "underlying": "RELIANCE INDUSTRIES",
        "expiry": "2026-10-29",
        "lot_size": 250,
        "margin_required": 62500.0,
        "current_price": 2985.0,
        "open_interest": 450_000,
    },
}

# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

INVOICES: dict[str, dict[str, Any]] = {
    "INV-2026-001": {
        "invoice_id": "INV-2026-001",
        "from_company": "Zerodha Clearing",
        "amount": 48500.0,
        "currency": "INR",
        "due_date": "2026-10-15",
        "description": "Monthly brokerage & transaction charges – October 2026",
        "status": "PENDING",
        "contract_ref": "NIFTY50-FUT-OCT26",
    },
    "INV-2026-002": {
        "invoice_id": "INV-2026-002",
        "from_company": "NSE Clearing Corp",
        "amount": 250000.0,
        "currency": "INR",
        "due_date": "2026-10-10",
        "description": "Margin call – additional collateral for BANKNIFTY position",
        "status": "PENDING",
        "contract_ref": "BANKNIFTY-FUT-OCT26",
    },
    "INV-2026-003": {
        "invoice_id": "INV-2026-003",
        "from_company": "SEBI",
        "amount": 15000.0,
        "currency": "INR",
        "due_date": "2026-10-20",
        "description": "SEBI turnover fee – Q2 FY2026-27",
        "status": "PENDING",
        "contract_ref": None,
    },
    "INV-2026-004": {
        "invoice_id": "INV-2026-004",
        "from_company": "Bloomberg LP",
        "amount": 8500.0,
        "currency": "USD",
        "due_date": "2026-10-25",
        "description": "Bloomberg Terminal data subscription – November 2026",
        "status": "PENDING",
        "contract_ref": None,
    },
    "INV-2026-005": {
        "invoice_id": "INV-2026-005",
        "from_company": "Zerodha Clearing",
        "amount": 32000.0,
        "currency": "INR",
        "due_date": "2026-09-30",
        "description": "Brokerage charges – September 2026",
        "status": "PAID",
        "contract_ref": "RELIANCE-FUT-OCT26",
    },
}

# ---------------------------------------------------------------------------
# Open positions
# ---------------------------------------------------------------------------

POSITIONS: dict[str, dict[str, Any]] = {
    "POS-001": {
        "position_id": "POS-001",
        "contract_id": "NIFTY50-FUT-OCT26",
        "quantity": 2,  # lots
        "avg_buy_price": 24600.0,
        "current_price": 24850.0,
        "pnl": 25000.0,  # (24850 - 24600) * 50 * 2
        "margin_used": 250000.0,
    },
    "POS-002": {
        "position_id": "POS-002",
        "contract_id": "BANKNIFTY-FUT-OCT26",
        "quantity": 3,
        "avg_buy_price": 51800.0,
        "current_price": 52300.0,
        "pnl": 22500.0,  # (52300 - 51800) * 15 * 3
        "margin_used": 135000.0,
    },
    "POS-003": {
        "position_id": "POS-003",
        "contract_id": "NIFTY50-CE-25000-OCT26",
        "quantity": 4,
        "avg_buy_price": 290.0,
        "current_price": 320.5,
        "pnl": 6100.0,  # (320.5 - 290) * 50 * 4
        "margin_used": 60000.0,
    },
}

# ---------------------------------------------------------------------------
# Queues / logs (mutable at runtime)
# ---------------------------------------------------------------------------

PAYMENT_QUEUE: list[dict[str, Any]] = []
AUDIT_LOG: list[dict[str, Any]] = []

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_invoice(invoice_id: str) -> dict[str, Any] | None:
    """Return the invoice dict for *invoice_id*, or None if not found."""
    return INVOICES.get(invoice_id)


def get_all_pending_invoices() -> list[dict[str, Any]]:
    """Return a list of all invoices whose status is PENDING."""
    return [inv for inv in INVOICES.values() if inv["status"] == "PENDING"]


def get_contract(contract_id: str) -> dict[str, Any] | None:
    """Return the contract dict for *contract_id*, or None if not found."""
    return CONTRACTS.get(contract_id)


def get_position(position_id: str) -> dict[str, Any] | None:
    """Return the position dict for *position_id*, or None if not found."""
    return POSITIONS.get(position_id)


def get_all_positions() -> list[dict[str, Any]]:
    """Return a list of all open positions."""
    return list(POSITIONS.values())


def process_payment(invoice_id: str, amount: float, approved_by: str) -> dict[str, Any]:
    """
    Process a payment for the given invoice.

    Marks the invoice as PAID, adds a record to PAYMENT_QUEUE, and writes
    an AUDIT_LOG entry.  Raises ValueError if the invoice is not found or
    has already been paid.
    """
    invoice = INVOICES.get(invoice_id)
    if invoice is None:
        raise ValueError(f"Invoice {invoice_id!r} not found.")
    if invoice["status"] == "PAID":
        raise ValueError(f"Invoice {invoice_id!r} is already paid.")

    # Mark paid
    invoice["status"] = "PAID"

    # Build payment record
    payment_record: dict[str, Any] = {
        "payment_id": f"PAY-{str(uuid.uuid4())[:8].upper()}",
        "invoice_id": invoice_id,
        "amount": amount,
        "currency": invoice["currency"],
        "approved_by": approved_by,
        "processed_at": datetime.utcnow().isoformat(),
        "status": "SUCCESS",
    }
    PAYMENT_QUEUE.append(payment_record)

    # Audit
    add_audit_log(
        action="PAYMENT_PROCESSED",
        details={
            "invoice_id": invoice_id,
            "amount": amount,
            "approved_by": approved_by,
            "payment_id": payment_record["payment_id"],
        },
    )

    return payment_record


def add_audit_log(action: str, details: dict[str, Any]) -> dict[str, Any]:
    """
    Append an entry to the AUDIT_LOG and return it.

    Parameters
    ----------
    action:
        Short uppercase identifier for the action (e.g. ``"PAYMENT_PROCESSED"``).
    details:
        Arbitrary key-value pairs providing context for the action.
    """
    entry: dict[str, Any] = {
        "log_id": f"AUD-{str(uuid.uuid4())[:8].upper()}",
        "action": action,
        "details": details,
        "timestamp": datetime.utcnow().isoformat(),
    }
    AUDIT_LOG.append(entry)
    return entry


def get_risk_metrics() -> dict[str, Any]:
    """
    Compute and return a risk dashboard snapshot across all open positions.

    Returns
    -------
    dict
        total_margin_used, total_pnl, total_open_interest, position_count,
        and a per-position breakdown.
    """
    total_margin = sum(p["margin_used"] for p in POSITIONS.values())
    total_pnl = sum(p["pnl"] for p in POSITIONS.values())

    # Aggregate open interest from contracts referenced by positions
    seen_contracts: set[str] = set()
    total_oi = 0
    for pos in POSITIONS.values():
        cid = pos["contract_id"]
        if cid not in seen_contracts:
            contract = CONTRACTS.get(cid)
            if contract:
                total_oi += contract["open_interest"]
            seen_contracts.add(cid)

    return {
        "total_margin_used": total_margin,
        "total_pnl": total_pnl,
        "total_open_interest": total_oi,
        "position_count": len(POSITIONS),
        "positions_breakdown": [
            {
                "position_id": p["position_id"],
                "contract_id": p["contract_id"],
                "pnl": p["pnl"],
                "margin_used": p["margin_used"],
            }
            for p in POSITIONS.values()
        ],
    }


def search_invoices(company_name: str) -> list[dict[str, Any]]:
    """
    Return all invoices where *company_name* appears (case-insensitive) in the
    ``from_company`` field.
    """
    query = company_name.lower()
    return [inv for inv in INVOICES.values() if query in inv["from_company"].lower()]
