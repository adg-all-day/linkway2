from django.utils import timezone
from rest_framework import permissions, status, views
from rest_framework.response import Response

from apps.commissions.models import Commission, Payout
from apps.orders.models import Order

from .models import PaymentLog


class PaystackWebhookView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        event = request.data.get("event")
        data = request.data.get("data", {}) or {}
        reference = data.get("reference") or ""

        PaymentLog.objects.create(provider="paystack", reference=reference, raw_payload=request.data)

        # Handle payment success for orders
        if event == "charge.success" and reference:
            order = Order.objects.filter(payment_reference=reference).first()
            if order:
                order.payment_status = "paid"
                order.paid_at = timezone.now()
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

