from decimal import Decimal

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.authentication.permissions import IsAdmin, IsMarketer

from .models import Commission, Payout
from .serializers import CommissionSerializer, PayoutSerializer
from .services import process_payout_request


class CommissionViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CommissionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)
        qs = Commission.objects.select_related("order", "product")
        if role == "admin":
            return qs
        if role == "marketer":
            return qs.filter(marketer=user)
        return qs.none()


class PayoutViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = PayoutSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = getattr(user, "role", None)
        qs = Payout.objects.all()
        if role == "admin":
            return qs
        if role == "marketer":
            return qs.filter(marketer=user)
        return qs.none()

    @action(detail=False, methods=["post"], url_path="request")
    def request_payout(self, request, *args, **kwargs):
        user = request.user
        if getattr(user, "role", None) != "marketer":
            return Response(
                {"detail": "Only marketers can request payouts."},
                status=status.HTTP_403_FORBIDDEN,
            )

        amount = request.data.get("amount")
        requested_amount: Decimal | None = None
        if amount is not None:
            try:
                requested_amount = Decimal(str(amount))
            except (TypeError, ValueError):
                return Response({"detail": "Invalid amount"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            payout = process_payout_request(marketer=user, requested_amount=requested_amount)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        serializer = self.get_serializer(payout)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
