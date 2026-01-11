import json
import os

import requests
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.commissions.models import Commission, Payout
from apps.orders.models import CustomerOrder, Order

from .models import PaymentLog


class PaystackWebhookView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        event = request.data.get("event")
        data = request.data.get("data", {}) or {}
        reference = data.get("reference") or ""

        # Persist raw webhook for audit/debugging
        PaymentLog.objects.create(provider="paystack", reference=reference, raw_payload=request.data)

        # Handle payment success for aggregated customer orders
        if event == "charge.success" and reference:
            customer_order = CustomerOrder.objects.filter(payment_reference=reference).first()
            now = timezone.now()
            if customer_order:
                customer_order.payment_status = "paid"
                customer_order.paid_at = now
                customer_order.paystack_reference = data.get("reference") or customer_order.paystack_reference
                customer_order.save(update_fields=["payment_status", "paid_at", "paystack_reference"])

                # Propagate status to linked seller orders
                customer_order.orders.update(payment_status="paid", paid_at=now, paystack_reference=customer_order.paystack_reference)
            else:
                # Backwards compatibility for legacy single-order payments
                order = Order.objects.filter(payment_reference=reference).first()
                if order:
                    order.payment_status = "paid"
                    order.paid_at = now
                    order.save(update_fields=["payment_status", "paid_at"])

        # Handle transfer status for payouts
        if event in ("transfer.success", "transfer.failed") and reference:
            payout = Payout.objects.filter(paystack_transfer_reference=reference).first()
            if payout:
                if event == "transfer.success":
                    payout.status = "completed"
                    payout.completed_at = timezone.now()
                    payout.save(update_fields=["status", "completed_at"])
                    Commission.objects.filter(payout=payout).update(status="paid", paid_at=timezone.now())
                else:
                    payout.status = "failed"
                    payout.failure_reason = data.get("reason", "")
                    payout.save(update_fields=["status", "failure_reason"])

        return Response({"status": "ok"}, status=status.HTTP_200_OK)


class PaystackVerifyView(views.APIView):
    """
    Verify a Paystack transaction after the buyer is redirected back
    from Paystack using the `reference` query parameter.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, *args, **kwargs):
        reference = request.query_params.get("reference")
        if not reference:
            return Response({"detail": "Missing reference"}, status=status.HTTP_400_BAD_REQUEST)

        secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "") or os.getenv("PAYSTACK_SECRET_KEY", "")
        if not secret_key:
            return Response(
                {"detail": "Payment provider is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        customer_order = CustomerOrder.objects.filter(payment_reference=reference).first()
        if not customer_order:
            # Fallback to legacy single-order payments
            order = Order.objects.filter(payment_reference=reference).first()
            if not order:
                return Response({"detail": "Order not found for this reference."}, status=status.HTTP_404_NOT_FOUND)
        else:
            order = None

        # Call Paystack verify endpoint
        url = f"https://api.paystack.co/transaction/verify/{reference}"
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            return Response(
                {"detail": "Failed to verify payment with Paystack.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payload = resp.json() or {}
        data = payload.get("data") or {}
        status_str = data.get("status")
        amount_kobo = data.get("amount")
        paid_amount = None
        if amount_kobo is not None:
            try:
                paid_amount = int(amount_kobo) / 100.0
            except (TypeError, ValueError):
                paid_amount = None

        if status_str == "success":
            now = timezone.now()
            if customer_order:
                customer_order.payment_status = "paid"
                customer_order.paid_at = now
                customer_order.paystack_reference = data.get("reference") or customer_order.paystack_reference
                customer_order.save(update_fields=["payment_status", "paid_at", "paystack_reference"])
                customer_order.orders.update(
                    payment_status="paid",
                    paid_at=now,
                    paystack_reference=customer_order.paystack_reference,
                )
            elif order:
                order.payment_status = "paid"
                order.paid_at = now
                order.paystack_reference = data.get("reference") or order.paystack_reference
                order.save(update_fields=["payment_status", "paid_at", "paystack_reference"])

        response_body = {
            "provider_status": status_str,
            "amount": paid_amount,
            "raw": payload,
        }
        if customer_order:
            response_body["customer_order_id"] = str(customer_order.id)
        if order:
            response_body["order_number"] = order.order_number

        return Response(response_body, status=status.HTTP_200_OK)
