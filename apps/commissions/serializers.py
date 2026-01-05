from rest_framework import serializers

from .models import Commission, Payout


class CommissionSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    order_number = serializers.CharField(source="order.order_number", read_only=True)

    class Meta:
        model = Commission
        fields = [
            "id",
            "order",
            "order_number",
            "marketer",
            "product",
            "product_name",
            "gross_sale_amount",
            "commission_rate",
            "commission_amount",
            "platform_fee_rate",
            "platform_fee_amount",
            "net_commission",
            "status",
            "earned_at",
            "holdback_until",
            "approved_at",
            "payout",
            "paid_at",
            "reversal_reason",
            "reversed_at",
            "created_at",
        ]


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payout
        fields = "__all__"
