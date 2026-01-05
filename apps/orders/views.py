from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.permissions import IsAdmin, IsBuyer, IsSeller
from apps.analytics.services import detect_fraud
from apps.products.models import Product
from .models import Cart, CartItem, Order
from .serializers import CartSerializer, OrderSerializer


class OrderPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(user, "role", None) in ("admin", "seller")

    def has_object_permission(self, request, view, obj: Order):
        user = request.user
        if request.method in permissions.SAFE_METHODS:
            if getattr(user, "role", None) == "admin":
                return True
            if getattr(user, "role", None) == "seller":
                return obj.seller_id == user.id
            if getattr(user, "role", None) == "marketer":
                return obj.marketer_id == user.id
            return False
        if getattr(user, "role", None) == "admin":
            return True
        if getattr(user, "role", None) == "seller":
            return obj.seller_id == user.id
        return False


class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.select_related("product", "seller", "marketer").all()
    serializer_class = OrderSerializer
    permission_classes = [OrderPermission]
    filterset_fields = ["seller", "marketer", "status", "payment_status"]
    search_fields = ["order_number", "customer_email", "customer_name"]
    ordering_fields = ["created_at", "total_amount"]

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()
        role = getattr(user, "role", None)
        if role == "admin":
            return qs
        if role == "seller":
            return qs.filter(seller=user)
        if role == "marketer":
            return qs.filter(marketer=user)
        return qs.none()

    def perform_create(self, serializer):
        order = serializer.save()
        detect_fraud("order", str(order.id))


class CartView(APIView):
    """
    Minimal cart API for buyers: GET to see cart, POST to add items.
    """

    permission_classes = [permissions.IsAuthenticated, IsBuyer]

    def get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(buyer=user, is_active=True)
        return cart

    def get(self, request, *args, **kwargs):
        cart = self.get_cart(request.user)
        serializer = CartSerializer(cart)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        product_id = request.data.get("product_id")
        quantity_raw = request.data.get("quantity", 1)
        try:
            quantity = int(quantity_raw)
        except (TypeError, ValueError):
            quantity = 1
        if quantity < 1:
            quantity = 1

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({"detail": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

        cart = self.get_cart(request.user)

        item, created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={
                "quantity": quantity,
                "unit_price": product.price,
            },
            )
        if not created:
            item.quantity += quantity
            item.save(update_fields=["quantity"])

        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class CartItemView(APIView):
    """
    Update or remove a single cart item for the current buyer.
    """

    permission_classes = [permissions.IsAuthenticated, IsBuyer]

    def get_object(self, user, item_id: int) -> CartItem:
        try:
            return CartItem.objects.select_related("cart", "product").get(
                id=item_id,
                cart__buyer=user,
                cart__is_active=True,
            )
        except CartItem.DoesNotExist:
            raise Order.DoesNotExist  # reuse 404 handling

    def patch(self, request, item_id: int, *args, **kwargs):
        item = self.get_object(request.user, item_id)
        quantity_raw = request.data.get("quantity")
        try:
            quantity = int(quantity_raw)
        except (TypeError, ValueError):
            return Response({"detail": "Invalid quantity"}, status=status.HTTP_400_BAD_REQUEST)

        if quantity <= 0:
            # Remove item if quantity is zero or negative
            cart = item.cart
            item.delete()
            serializer = CartSerializer(cart)
            return Response(serializer.data, status=status.HTTP_200_OK)

        # Enforce stock limit
        max_available = item.product.stock_quantity or 0
        if max_available and quantity > max_available:
            return Response(
                {"detail": "Quantity exceeds available stock"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.quantity = quantity
        item.save(update_fields=["quantity"])
        serializer = CartSerializer(item.cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, item_id: int, *args, **kwargs):
        item = self.get_object(request.user, item_id)
        cart = item.cart
        item.delete()
        serializer = CartSerializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)
