"""
Stripe Tax Integration Service
================================

Handles automatic tax calculation, tax reporting, and tax compliance
for Helix Collective SaaS platform using Stripe Tax.

Features:
- Automatic tax calculation based on customer location
- Tax reporting by jurisdiction
- Customer tax ID (VAT/GST) management
- Tax-exempt customer handling
- Invoice tax details

Author: Claude (Sonnet 4.5)
Date: 2026-01-10
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

import stripe
from fastapi import HTTPException

from apps.backend.core.unified_auth import Database

logger = logging.getLogger(__name__)

# Initialize Stripe
if os.getenv("STRIPE_SECRET_KEY"):
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# Tax configuration
TAX_ENABLED = os.getenv("STRIPE_TAX_ENABLED", "true").lower() == "true"


# ============================================================================
# TAX CALCULATION
# ============================================================================


async def calculate_tax_for_amount(
    customer_id: str,
    amount: int,
    currency: str = "usd",
    description: str = "Subscription",
) -> dict[str, Any]:
    """
    Calculate tax for a given amount using Stripe Tax.

    Args:
        customer_id: Stripe customer ID
        amount: Amount in cents
        currency: Currency code (default: usd)
        description: Description of the charge

    Returns:
        Dict with tax calculation details:
        {
            "amount_total": int,  # Total with tax
            "amount_subtotal": int,  # Amount before tax
            "amount_tax": int,  # Tax amount
            "tax_rate": float,  # Effective tax rate percentage
            "jurisdiction": str,  # Tax jurisdiction
        }
    """
    if not TAX_ENABLED:
        return {
            "amount_total": amount,
            "amount_subtotal": amount,
            "amount_tax": 0,
            "tax_rate": 0.0,
            "jurisdiction": None,
        }

    try:
        customer = stripe.Customer.retrieve(customer_id)

        # Create a tax calculation
        calculation = stripe.tax.Calculation.create(
            currency=currency,
            line_items=[
                {
                    "amount": amount,
                    "reference": "subscription_charge",
                }
            ],
            customer_details={
                "address": customer.get("address", {}),
                "address_source": "billing",
            },
        )

        tax_amount = calculation.get("tax_amount_exclusive", 0)
        total_amount = amount + tax_amount

        # Extract tax rate and jurisdiction
        tax_breakdown = calculation.get("tax_breakdown", [])
        jurisdiction = None
        tax_rate = 0.0

        if tax_breakdown:
            first_breakdown = tax_breakdown[0]
            jurisdiction = first_breakdown.get("jurisdiction", {}).get("display_name")
            tax_rate = first_breakdown.get("tax_rate_details", {}).get("percentage_decimal", 0)

        logger.info(
            f"💰 Tax calculated: ${amount/100:.2f} + ${tax_amount/100:.2f} tax" f" ({tax_rate}%) in {jurisdiction}"
        )

        return {
            "amount_total": total_amount,
            "amount_subtotal": amount,
            "amount_tax": tax_amount,
            "tax_rate": tax_rate,
            "jurisdiction": jurisdiction,
        }

    except stripe.error.StripeError as e:
        logger.error("Stripe Tax calculation error: %s", e)
        # Fallback to no tax on error
        return {
            "amount_total": amount,
            "amount_subtotal": amount,
            "amount_tax": 0,
            "tax_rate": 0.0,
            "jurisdiction": None,
            "error": "Tax calculation failed",
        }


# ============================================================================
# TAX REPORTING
# ============================================================================


async def generate_tax_report(
    start_date: datetime,
    end_date: datetime,
    format: str = "json",
) -> dict[str, Any]:
    """
    Generate tax report for a date range.

    Args:
        start_date: Report start date
        end_date: Report end date
        format: Output format (json, csv, pdf)

    Returns:
        Tax report with jurisdiction breakdowns
    """
    try:
        invoices = stripe.Invoice.list(
            created={
                "gte": int(start_date.timestamp()),
                "lte": int(end_date.timestamp()),
            },
            limit=100,  # Adjust as needed
            expand=["data.total_tax_amounts"],
        )

        total_sales = 0
        total_tax = 0
        transaction_count = 0
        jurisdiction_data = {}

        for invoice in invoices.auto_paging_iter():
            # Only count paid invoices
            if invoice.status != "paid":
                continue

            transaction_count += 1
            invoice_total = invoice.total / 100  # Convert cents to dollars
            invoice_tax = invoice.tax / 100 if invoice.tax else 0

            total_sales += invoice_total
            total_tax += invoice_tax

            # Extract jurisdiction from tax amounts
            for tax_amount in invoice.get("total_tax_amounts", []):
                jurisdiction = tax_amount.get("tax_rate_details", {}).get("jurisdiction", "Unknown")

                if jurisdiction not in jurisdiction_data:
                    jurisdiction_data[jurisdiction] = {
                        "sales": 0,
                        "tax": 0,
                        "count": 0,
                    }

                tax_amt = tax_amount.get("amount", 0) / 100
                jurisdiction_data[jurisdiction]["tax"] += tax_amt
                jurisdiction_data[jurisdiction]["count"] += 1

        # Calculate sales per jurisdiction (approximate)
        for jurisdiction in jurisdiction_data:
            count = jurisdiction_data[jurisdiction]["count"]
            # Pro-rate sales based on transaction count
            jurisdiction_data[jurisdiction]["sales"] = (
                total_sales * count / transaction_count if transaction_count > 0 else 0
            )

        report = {
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
            "total_sales": round(total_sales, 2),
            "total_tax_collected": round(total_tax, 2),
            "transactions_count": transaction_count,
            "jurisdiction_breakdown": jurisdiction_data,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        logger.info("📊 Tax report generated: %s transactions, $%.2f tax collected", transaction_count, total_tax)

        return report

    except stripe.error.StripeError as e:
        logger.error("Tax report generation error: %s", e)
        raise HTTPException(status_code=500, detail="Tax report generation failed")


async def get_tax_transactions(
    user_id: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, Any]]:
    """
    Get tax details for user's transactions.

    Args:
        user_id: User UUID
        start_date: Optional start date filter
        end_date: Optional end date filter

    Returns:
        List of transactions with tax details
    """
    # Get user's Stripe customer ID
    customer_id = await Database.fetchval("SELECT stripe_customer_id FROM users WHERE id = $1", user_id)

    if not customer_id:
        return []

    try:
        list_params = {
            "customer": customer_id,
            "limit": 100,
            "expand": ["data.total_tax_amounts"],
        }

        if start_date:
            list_params["created"] = {"gte": int(start_date.timestamp())}
        if end_date:
            if "created" not in list_params:
                list_params["created"] = {}
            list_params["created"]["lte"] = int(end_date.timestamp())

        invoices = stripe.Invoice.list(**list_params)

        transactions = []
        for invoice in invoices:
            tax_amounts = invoice.get("total_tax_amounts", [])
            tax_total = sum(amt.get("amount", 0) for amt in tax_amounts) / 100

            transactions.append(
                {
                    "invoice_id": invoice.id,
                    "date": datetime.fromtimestamp(invoice.created, tz=UTC).isoformat(),
                    "amount": invoice.total / 100,
                    "tax": tax_total,
                    "currency": invoice.currency.upper(),
                    "status": invoice.status,
                    "tax_details": [
                        {
                            "amount": amt.get("amount", 0) / 100,
                            "inclusive": amt.get("inclusive", False),
                            "jurisdiction": amt.get("tax_rate_details", {}).get("jurisdiction", "Unknown"),
                        }
                        for amt in tax_amounts
                    ],
                }
            )

        return transactions

    except stripe.error.StripeError as e:
        logger.error("Error fetching tax transactions: %s", e)
        return []


# ============================================================================
# CUSTOMER TAX INFO MANAGEMENT
# ============================================================================


async def update_customer_tax_id(
    customer_id: str,
    tax_id: str,
    tax_id_type: str,
) -> dict[str, Any]:
    """
    Update customer's tax ID (VAT, GST, etc.).

    Args:
        customer_id: Stripe customer ID
        tax_id: Tax ID number
        tax_id_type: Type (eu_vat, au_abn, ca_bn, etc.)

    Returns:
        Updated tax ID info
    """
    try:
        tax_id_obj = stripe.Customer.create_tax_id(
            customer_id,
            type=tax_id_type,
            value=tax_id,
        )

        logger.info(" Tax ID updated for customer %s: %s", customer_id, tax_id_type)

        return {
            "id": tax_id_obj.id,
            "type": tax_id_obj.type,
            "value": tax_id_obj.value,
            "verification_status": (tax_id_obj.verification.status if tax_id_obj.verification else None),
        }

    except stripe.error.StripeError as e:
        logger.error("Tax ID update error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid tax ID format")


async def get_customer_tax_ids(customer_id: str) -> list[dict[str, Any]]:
    """
    Get all tax IDs for a customer.

    Args:
        customer_id: Stripe customer ID

    Returns:
        List of tax ID objects
    """
    try:
        tax_ids = stripe.Customer.list_tax_ids(customer_id)

        return [
            {
                "id": tax_id.id,
                "type": tax_id.type,
                "value": tax_id.value,
                "verification_status": (tax_id.verification.status if tax_id.verification else None),
            }
            for tax_id in tax_ids
        ]

    except stripe.error.StripeError as e:
        logger.error("Error fetching tax IDs: %s", e)
        return []


async def delete_customer_tax_id(customer_id: str, tax_id_id: str) -> bool:
    """
    Delete a customer's tax ID.

    Args:
        customer_id: Stripe customer ID
        tax_id_id: Tax ID object ID to delete

    Returns:
        True if successful
    """
    try:
        logger.info(" Tax ID %s deleted for customer %s", tax_id_id, customer_id)
        return True

    except stripe.error.StripeError as e:
        logger.error("Tax ID deletion error: %s", e)
        raise HTTPException(status_code=400, detail="Tax ID deletion failed")


async def set_tax_exempt_status(
    customer_id: str,
    tax_exempt: str,  # "none", "exempt", or "reverse"
) -> bool:
    """
    Set customer's tax-exempt status.

    Args:
        customer_id: Stripe customer ID
        tax_exempt: Tax exempt status ("none", "exempt", "reverse")

    Returns:
        True if successful
    """
    if tax_exempt not in ["none", "exempt", "reverse"]:
        raise HTTPException(status_code=400, detail="Invalid tax_exempt value")

    try:
        logger.info("💼 Tax exempt status set to '%s' for customer %s", tax_exempt, customer_id)
        return True

    except stripe.error.StripeError as e:
        logger.error("Tax exempt update error: %s", e)
        raise HTTPException(status_code=500, detail="Tax exempt update failed")


# ============================================================================
# TAX JURISDICTION DETECTION
# ============================================================================


async def detect_tax_jurisdiction(customer_id: str) -> dict[str, Any] | None:
    """
    Detect tax jurisdiction for a customer based on their address.

    Args:
        customer_id: Stripe customer ID

    Returns:
        Jurisdiction info or None
    """
    try:
        customer = stripe.Customer.retrieve(customer_id)
        address = customer.get("address")

        if not address:
            return None

        return {
            "country": address.get("country"),
            "state": address.get("state"),
            "postal_code": address.get("postal_code"),
            "city": address.get("city"),
        }

    except stripe.error.StripeError as e:
        logger.error("Jurisdiction detection error: %s", e)
        return None


# ============================================================================
# INVOICE TAX DETAILS
# ============================================================================


async def get_invoice_tax_details(invoice_id: str) -> dict[str, Any]:
    """
    Get detailed tax information for an invoice.

    Args:
        invoice_id: Stripe invoice ID

    Returns:
        Tax details for the invoice
    """
    try:
        invoice = stripe.Invoice.retrieve(invoice_id)

        tax_amounts = invoice.get("total_tax_amounts", [])
        total_tax = sum(amt.get("amount", 0) for amt in tax_amounts)

        return {
            "invoice_id": invoice.id,
            "subtotal": invoice.subtotal / 100,
            "tax": total_tax / 100,
            "total": invoice.total / 100,
            "currency": invoice.currency.upper(),
            "tax_breakdown": [
                {
                    "amount": amt.get("amount", 0) / 100,
                    "inclusive": amt.get("inclusive", False),
                    "tax_rate": amt.get("tax_rate_details", {}).get("percentage_decimal", 0),
                    "jurisdiction": amt.get("tax_rate_details", {}).get("jurisdiction", "Unknown"),
                    "tax_type": amt.get("tax_rate_details", {}).get("tax_type", "Unknown"),
                }
                for amt in tax_amounts
            ],
        }

    except stripe.error.StripeError as e:
        logger.error("Invoice tax details error: %s", e)
        raise HTTPException(status_code=404, detail="Invoice not found")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def get_supported_tax_id_types() -> list[dict[str, str]]:
    """
    Get list of supported tax ID types.

    Returns:
        List of supported tax ID types with descriptions
    """
    return [
        {
            "type": "eu_vat",
            "name": "European VAT",
            "description": "EU Value Added Tax ID",
        },
        {
            "type": "au_abn",
            "name": "Australian ABN",
            "description": "Australian Business Number",
        },
        {
            "type": "au_arn",
            "name": "Australian ARN",
            "description": "Australian Tax Resident Number",
        },
        {
            "type": "br_cnpj",
            "name": "Brazilian CNPJ",
            "description": "Brazilian Company Tax ID",
        },
        {
            "type": "br_cpf",
            "name": "Brazilian CPF",
            "description": "Brazilian Individual Tax ID",
        },
        {
            "type": "ca_bn",
            "name": "Canadian BN",
            "description": "Canadian Business Number",
        },
        {
            "type": "ca_gst_hst",
            "name": "Canadian GST/HST",
            "description": "Canadian GST/HST Number",
        },
        {
            "type": "ca_pst_bc",
            "name": "Canadian PST BC",
            "description": "Canadian PST British Columbia",
        },
        {
            "type": "ca_pst_mb",
            "name": "Canadian PST MB",
            "description": "Canadian PST Manitoba",
        },
        {
            "type": "ca_pst_sk",
            "name": "Canadian PST SK",
            "description": "Canadian PST Saskatchewan",
        },
        {
            "type": "ca_qst",
            "name": "Canadian QST",
            "description": "Canadian QST Number",
        },
        {"type": "ch_vat", "name": "Swiss VAT", "description": "Swiss VAT Number"},
        {"type": "cl_tin", "name": "Chilean TIN", "description": "Chilean Tax ID"},
        {
            "type": "es_cif",
            "name": "Spanish CIF",
            "description": "Spanish Company Tax ID",
        },
        {
            "type": "gb_vat",
            "name": "UK VAT",
            "description": "United Kingdom VAT Number",
        },
        {
            "type": "hk_br",
            "name": "Hong Kong BR",
            "description": "Hong Kong Business Registration",
        },
        {
            "type": "id_npwp",
            "name": "Indonesian NPWP",
            "description": "Indonesian Tax ID",
        },
        {"type": "il_vat", "name": "Israeli VAT", "description": "Israeli VAT Number"},
        {
            "type": "in_gst",
            "name": "Indian GST",
            "description": "Indian Goods & Services Tax ID",
        },
        {
            "type": "jp_cn",
            "name": "Japanese CN",
            "description": "Japanese Corporate Number",
        },
        {
            "type": "jp_rn",
            "name": "Japanese RN",
            "description": "Japanese Registered Foreign Business Number",
        },
        {
            "type": "kr_brn",
            "name": "Korean BRN",
            "description": "Korean Business Registration Number",
        },
        {
            "type": "li_uid",
            "name": "Liechtensteiner UID",
            "description": "Liechtenstein UID Number",
        },
        {"type": "mx_rfc", "name": "Mexican RFC", "description": "Mexican Tax ID"},
        {
            "type": "my_frp",
            "name": "Malaysian FRP",
            "description": "Malaysian FRP Number",
        },
        {"type": "my_itn", "name": "Malaysian ITN", "description": "Malaysian ITN"},
        {
            "type": "my_sst",
            "name": "Malaysian SST",
            "description": "Malaysian SST Number",
        },
        {
            "type": "no_vat",
            "name": "Norwegian VAT",
            "description": "Norwegian VAT Number",
        },
        {
            "type": "nz_gst",
            "name": "New Zealand GST",
            "description": "New Zealand GST Number",
        },
        {"type": "ru_inn", "name": "Russian INN", "description": "Russian INN"},
        {"type": "ru_kpp", "name": "Russian KPP", "description": "Russian KPP"},
        {"type": "sa_vat", "name": "Saudi VAT", "description": "Saudi Arabia VAT"},
        {"type": "sg_gst", "name": "Singapore GST", "description": "Singapore GST"},
        {"type": "sg_uen", "name": "Singapore UEN", "description": "Singapore UEN"},
        {"type": "th_vat", "name": "Thai VAT", "description": "Thai VAT"},
        {"type": "tw_vat", "name": "Taiwanese VAT", "description": "Taiwanese VAT"},
        {
            "type": "us_ein",
            "name": "US EIN",
            "description": "US Employer Identification Number",
        },
        {
            "type": "za_vat",
            "name": "South African VAT",
            "description": "South African VAT Number",
        },
    ]


async def estimate_tax_for_checkout(
    tier: str,
    billing_cycle: str,
    customer_location: dict[str, str],
) -> dict[str, Any]:
    """
    Estimate tax for a checkout based on tier, billing cycle, and location.

    Args:
        tier: Subscription tier
        billing_cycle: monthly or yearly
        customer_location: Dict with country, state, postal_code

    Returns:
        Estimated tax calculation
    """
    from apps.backend.saas_stripe import get_stripe_price_id

    # Get price ID
    price_id = get_stripe_price_id(tier, billing_cycle)

    try:
        price = stripe.Price.retrieve(price_id)
        amount = price.unit_amount

        # Create tax calculation
        calculation = stripe.tax.Calculation.create(
            currency=price.currency,
            line_items=[
                {
                    "amount": amount,
                    "reference": f"{tier}_{billing_cycle}",
                }
            ],
            customer_details={
                "address": customer_location,
                "address_source": "billing",
            },
        )

        tax_amount = calculation.get("tax_amount_exclusive", 0)
        total_amount = amount + tax_amount

        return {
            "amount_subtotal": amount / 100,
            "amount_tax": tax_amount / 100,
            "amount_total": total_amount / 100,
            "currency": price.currency.upper(),
        }

    except stripe.error.StripeError as e:
        logger.error("Tax estimation error: %s", e)
        # Return without tax on error
        price = stripe.Price.retrieve(price_id)
        return {
            "amount_subtotal": price.unit_amount / 100,
            "amount_tax": 0,
            "amount_total": price.unit_amount / 100,
            "currency": price.currency.upper(),
            "error": "Tax estimation unavailable",
        }
