from decimal import Decimal

from rest_framework import serializers

from .models import Cart, CartItem, Order


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at", "paid_at", "shipped_at", "delivered_at"]


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
