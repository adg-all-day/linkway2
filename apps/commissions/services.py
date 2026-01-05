from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os
from typing import Iterable, Optional

import requests
from django.db import transaction
from django.utils import timezone

from apps.authentication.models import User

from .models import Commission, Payout


MINIMUM_PAYOUT_NGN = Decimal("5000")


@dataclass
class PaystackRecipient:
    bank_code: str
    account_number: str
    name: str


def process_payout_request(marketer: User, requested_amount: Optional[Decimal] = None) -> Payout:
    if not marketer.bank_name or not marketer.account_number:
        raise ValueError("Bank details not configured")

    approved_commissions = (
        Commission.objects.filter(
            marketer=marketer,
            status="approved",
            payout__isnull=True,
        )
        .order_by("approved_at", "created_at")
        .select_for_update()
    )

    total_available = sum((c.net_commission or Decimal("0")) for c in approved_commissions)
    if total_available < MINIMUM_PAYOUT_NGN:
        raise ValueError(f"Minimum payout is ₦{MINIMUM_PAYOUT_NGN}")

    if requested_amount is not None:
        payout_amount = min(requested_amount, total_available)
    else:
        payout_amount = total_available

    commissions_to_pay: list[Commission] = []
    running_total = Decimal("0")

    for commission in approved_commissions:
        if running_total + (commission.net_commission or Decimal("0")) <= payout_amount:
            commissions_to_pay.append(commission)
            running_total += commission.net_commission or Decimal("0")
        else:
            break

    if running_total < MINIMUM_PAYOUT_NGN:
        raise ValueError("Not enough approved commissions")

    with transaction.atomic():
        payout = Payout.objects.create(
            marketer=marketer,
            payout_method="bank_transfer",
            total_amount=running_total,
            commission_count=len(commissions_to_pay),
            bank_name=marketer.bank_name,
            account_number=marketer.account_number,
            account_name=marketer.account_name or marketer.full_name,
            status="processing",
        )

        Commission.objects.filter(id__in=[c.id for c in commissions_to_pay]).update(payout=payout)

        recipient = PaystackRecipient(
            bank_code="000",  # Placeholder; map marketer.bank_name to bank_code in real implementation
            account_number=marketer.account_number,
            name=payout.account_name,
        )

        reference = f"linkway-payout-{payout.id}"

        transfer_result = initiate_paystack_transfer(
            amount=int(running_total * 100),
            recipient=recipient,
            reference=reference,
            reason="Affiliate commission payout",
        )

        payout.paystack_transfer_reference = transfer_result.get("reference")
        payout.transfer_code = transfer_result.get("transfer_code")
        payout.status = "processing"
        payout.processed_at = timezone.now()
        payout.save(update_fields=["paystack_transfer_reference", "transfer_code", "status", "processed_at"])

    return payout


def initiate_paystack_transfer(
    amount: int,
    recipient: PaystackRecipient,
    reference: str,
    reason: str,
) -> dict:
    """
    Initiate a Paystack transfer.

    This is a minimal implementation based on the blueprint; you may want
    to enhance error handling and recipient caching in production.
    """
    secret_key = os.getenv("PAYSTACK_SECRET_KEY")
    if not secret_key:
        # Allow local development without Paystack keys by simulating a transfer.
        return {
            "reference": reference,
            "transfer_code": "TEST_TRANSFER_CODE",
            "status": "success",
        }

    base_url = "https://api.paystack.co"
    headers = {
        "Authorization": f"Bearer {secret_key}",
        "Content-Type": "application/json",
    }

    # Create transfer recipient
    recipient_resp = requests.post(
        f"{base_url}/transferrecipient",
        headers=headers,
        json={
            "type": "nuban",
            "name": recipient.name,
            "account_number": recipient.account_number,
            "bank_code": recipient.bank_code,
            "currency": "NGN",
        },
        timeout=20,
    )
    if recipient_resp.status_code not in (200, 201):
        raise RuntimeError(f"Paystack recipient error: {recipient_resp.text}")

    recipient_code = recipient_resp.json()["data"]["recipient_code"]

    # Initiate transfer
    transfer_resp = requests.post(
        f"{base_url}/transfer",
        headers=headers,
        json={
            "source": "balance",
            "amount": amount,
            "recipient": recipient_code,
            "reference": reference,
            "reason": reason,
            "currency": "NGN",
        },
        timeout=20,
    )
    if transfer_resp.status_code not in (200, 201):
        raise RuntimeError(f"Paystack transfer error: {transfer_resp.text}")

    data = transfer_resp.json()["data"]
    return {
        "reference": data.get("reference"),
        "transfer_code": data.get("transfer_code"),
        "status": data.get("status"),
    }
