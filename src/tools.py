"""
src/tools.py
------------
Tool registry for FinAgent.

Every tool is an async function returning a standardised dict:
    { "success": bool, "data": Any, "error": str | None }

A ``TOOL_REGISTRY`` dict maps tool name → function so the agent loop can
dispatch calls returned by the LLM.

``get_tool_definitions()`` returns the Gemini function-calling schema for
all registered tools.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src import simulated_db as db

# ---------------------------------------------------------------------------
# Type alias for the standard tool result envelope
# ---------------------------------------------------------------------------

ToolResult = dict[str, Any]


def _ok(data: Any) -> ToolResult:
    return {"success": True, "data": data, "error": None}


def _err(msg: str) -> ToolResult:
    return {"success": False, "data": None, "error": msg}


# ---------------------------------------------------------------------------
# Individual tool implementations
# ---------------------------------------------------------------------------


async def search_invoices(company_name: str) -> ToolResult:
    """Search invoices by counterparty / company name (partial, case-insensitive)."""
    if not company_name or not company_name.strip():
        return _err("company_name must be a non-empty string.")
    results = await asyncio.get_event_loop().run_in_executor(
        None, db.search_invoices, company_name.strip()
    )
    return _ok({"invoices": results, "count": len(results)})


async def get_invoice_details(invoice_id: str) -> ToolResult:
    """Retrieve full details for a specific invoice by its ID."""
    if not invoice_id:
        return _err("invoice_id is required.")
    invoice = db.get_invoice(invoice_id.strip())
    if invoice is None:
        return _err(f"Invoice '{invoice_id}' not found.")
    return _ok(invoice)


async def get_pending_invoices() -> ToolResult:
    """List all invoices that currently have status PENDING."""
    pending = db.get_all_pending_invoices()
    return _ok({"invoices": pending, "count": len(pending)})


async def process_payment(invoice_id: str, amount: float) -> ToolResult:
    """
    Process a payment for the specified invoice.

    The payment is approved by the FinAgent system and recorded in the
    payment queue and audit log.
    """
    if not invoice_id:
        return _err("invoice_id is required.")
    if amount <= 0:
        return _err("amount must be a positive number.")
    try:
        record = await asyncio.get_event_loop().run_in_executor(
            None, db.process_payment, invoice_id.strip(), amount, "FinAgent-Automated"
        )
        return _ok(record)
    except ValueError as exc:
        return _err(str(exc))


async def get_contract_details(contract_id: str) -> ToolResult:
    """Retrieve full details for a specific F&O contract."""
    if not contract_id:
        return _err("contract_id is required.")
    contract = db.get_contract(contract_id.strip())
    if contract is None:
        return _err(f"Contract '{contract_id}' not found.")
    return _ok(contract)


async def get_all_positions() -> ToolResult:
    """List all currently open trading positions."""
    positions = db.get_all_positions()
    return _ok({"positions": positions, "count": len(positions)})


async def get_risk_metrics() -> ToolResult:
    """
    Return a real-time risk dashboard snapshot:
    total margin used, total PnL, total open interest, and per-position breakdown.
    """
    metrics = db.get_risk_metrics()
    return _ok(metrics)


async def check_margin_requirements(contract_id: str, quantity: int) -> ToolResult:
    """
    Calculate total margin required for a given contract and lot quantity.

    Parameters
    ----------
    contract_id : str
        The F&O contract identifier.
    quantity : int
        Number of lots to buy/sell.
    """
    if not contract_id:
        return _err("contract_id is required.")
    if quantity <= 0:
        return _err("quantity must be a positive integer.")
    contract = db.get_contract(contract_id.strip())
    if contract is None:
        return _err(f"Contract '{contract_id}' not found.")
    margin_per_lot: float = contract["margin_required"]
    total_margin: float = margin_per_lot * quantity
    return _ok(
        {
            "contract_id": contract_id,
            "quantity_lots": quantity,
            "margin_per_lot": margin_per_lot,
            "total_margin_required": total_margin,
            "currency": "INR",
        }
    )


async def add_compliance_note(entity_id: str, note: str) -> ToolResult:
    """
    Add a compliance / audit note against any entity (invoice, position, contract).

    Parameters
    ----------
    entity_id : str
        Identifier of the entity being annotated (e.g. invoice ID, position ID).
    note : str
        Free-text compliance or audit note.
    """
    if not entity_id or not note:
        return _err("Both entity_id and note are required.")
    entry = db.add_audit_log(
        action="COMPLIANCE_NOTE",
        details={"entity_id": entity_id, "note": note},
    )
    return _ok({"logged": True, "audit_entry": entry})


async def verify_payment_status(invoice_id: str) -> ToolResult:
    """Check whether a specific invoice has been paid."""
    if not invoice_id:
        return _err("invoice_id is required.")
    invoice = db.get_invoice(invoice_id.strip())
    if invoice is None:
        return _err(f"Invoice '{invoice_id}' not found.")
    is_paid = invoice["status"] == "PAID"
    return _ok(
        {
            "invoice_id": invoice_id,
            "status": invoice["status"],
            "is_paid": is_paid,
            "from_company": invoice["from_company"],
            "amount": invoice["amount"],
            "currency": invoice["currency"],
        }
    )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------

TOOL_REGISTRY: dict[str, Any] = {
    "search_invoices": search_invoices,
    "get_invoice_details": get_invoice_details,
    "get_pending_invoices": get_pending_invoices,
    "process_payment": process_payment,
    "get_contract_details": get_contract_details,
    "get_all_positions": get_all_positions,
    "get_risk_metrics": get_risk_metrics,
    "check_margin_requirements": check_margin_requirements,
    "add_compliance_note": add_compliance_note,
    "verify_payment_status": verify_payment_status,
}


# ---------------------------------------------------------------------------
# Gemini function-calling schema definitions
# ---------------------------------------------------------------------------


def get_tool_definitions() -> list[dict[str, Any]]:
    """
    Return function declarations in the format expected by the Gemini
    ``types.Tool(function_declarations=[...])`` constructor.

    Each entry has:
        name        – matches a key in TOOL_REGISTRY
        description – shown to the model
        parameters  – JSON Schema object describing the arguments
    """
    return [
        {
            "name": "search_invoices",
            "description": (
                "Search invoices by counterparty or company name. "
                "Returns all invoices where the company name matches (partial, case-insensitive)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "Name (or partial name) of the company to search for.",
                    }
                },
                "required": ["company_name"],
            },
        },
        {
            "name": "get_invoice_details",
            "description": "Retrieve full details for a specific invoice by its unique invoice ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "string",
                        "description": "The invoice ID, e.g. INV-2026-001.",
                    }
                },
                "required": ["invoice_id"],
            },
        },
        {
            "name": "get_pending_invoices",
            "description": "List all invoices that currently have PENDING status and require payment.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "process_payment",
            "description": (
                "Process a payment for a specific invoice. "
                "Marks the invoice as PAID and records the transaction in the payment queue and audit log. "
                "Use only after verifying the invoice details and confirming the amount."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "string",
                        "description": "The invoice ID to pay.",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Payment amount in the invoice's currency.",
                    },
                },
                "required": ["invoice_id", "amount"],
            },
        },
        {
            "name": "get_contract_details",
            "description": (
                "Retrieve full details for an F&O contract including type (FUTURES/OPTIONS), "
                "underlying, expiry, strike price, lot size, margin requirement, and current price."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_id": {
                        "type": "string",
                        "description": "Contract identifier, e.g. NIFTY50-FUT-OCT26.",
                    }
                },
                "required": ["contract_id"],
            },
        },
        {
            "name": "get_all_positions",
            "description": "List all currently open trading positions with PnL and margin details.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "get_risk_metrics",
            "description": (
                "Return a real-time risk dashboard snapshot: total margin used, "
                "total PnL across all positions, total open interest, and a per-position breakdown."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "check_margin_requirements",
            "description": (
                "Calculate the total margin capital required to hold a given number "
                "of lots for a specific F&O contract."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "contract_id": {
                        "type": "string",
                        "description": "The F&O contract identifier.",
                    },
                    "quantity": {
                        "type": "integer",
                        "description": "Number of lots.",
                    },
                },
                "required": ["contract_id", "quantity"],
            },
        },
        {
            "name": "add_compliance_note",
            "description": (
                "Add a compliance or audit note against any entity "
                "(invoice, position, contract). The note is persisted to the audit log."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "ID of the entity being annotated.",
                    },
                    "note": {
                        "type": "string",
                        "description": "Free-text compliance or audit note.",
                    },
                },
                "required": ["entity_id", "note"],
            },
        },
        {
            "name": "verify_payment_status",
            "description": "Check whether a specific invoice has been paid.",
            "parameters": {
                "type": "object",
                "properties": {
                    "invoice_id": {
                        "type": "string",
                        "description": "The invoice ID to check.",
                    }
                },
                "required": ["invoice_id"],
            },
        },
    ]
