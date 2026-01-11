from decimal import Decimal

from rest_framework import serializers

from .models import Cart, CartItem, CustomerOrder, Order


class OrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    marketer_name = serializers.CharField(source="marketer.full_name", read_only=True, allow_null=True)
    marketer_email = serializers.CharField(source="marketer.email", read_only=True, allow_null=True)
    marketer_commission_preview = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "paid_at", "shipped_at", "delivered_at"]

    def get_marketer_commission_preview(self, obj: Order) -> str:
        """
        Estimated marketer commission in naira for this order line,
        using the same logic as the commission calculator but without
        creating any records.
        """
        if not obj.marketer_id:
            return "0.00"

        subtotal = obj.subtotal or Decimal("0")
        product = obj.product
        gross_commission = Decimal("0")

        # Percentage-based commission
        if product.commission_type == "percentage" and obj.commission_rate:
            gross_commission = (subtotal * obj.commission_rate) / Decimal("100")
        # Fixed commission per unit
        elif product.commission_type == "fixed" and product.fixed_commission_amount:
            gross_commission = (product.fixed_commission_amount or Decimal("0")) * obj.quantity

        if gross_commission <= 0:
            return "0.00"

        # Apply the same 2.5% platform fee used in the commission calculator
        platform_fee_rate = Decimal("2.5")
        platform_fee_amount = (gross_commission * platform_fee_rate) / Decimal("100")
        net_commission = gross_commission - platform_fee_amount

        return f"{net_commission.quantize(Decimal('0.01'))}"


class CartItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_price = serializers.DecimalField(source="unit_price", max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CartItem
        fields = [
            "id",
            "product",
            "product_name",
            "product_price",
            "quantity",
            "unit_price",
            "added_at",
        ]
        read_only_fields = ["id", "unit_price", "added_at", "product_name", "product_price"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_amount = serializers.SerializerMethodField()

    class Meta:
        model = Cart
        fields = ["id", "items", "total_amount", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at", "items", "total_amount"]

    def get_total_amount(self, obj: Cart) -> Decimal:
        total = Decimal("0")
        for item in obj.items.all():
            total += (item.unit_price or Decimal("0")) * item.quantity
        return total


class CustomerOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerOrder
        fields = "__all__"
        read_only_fields = [
            "id",
            "order_number",
            "buyer",
            "customer_email",
            "subtotal",
            "shipping_fee",
            "tax_amount",
            "total_amount",
            "payment_status",
            "payment_reference",
            "paystack_reference",
            "created_at",
            "updated_at",
            "paid_at",
        ]


class CheckoutInitSerializer(serializers.Serializer):
    """
    Input payload for starting a Paystack checkout from the current cart.
    """

    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    shipping_address = serializers.JSONField()
