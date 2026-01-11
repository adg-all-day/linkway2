import uuid
from collections import defaultdict
from decimal import Decimal

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.affiliates.models import AttributionTracking
from apps.authentication.permissions import IsAdmin, IsBuyer, IsSeller
from apps.analytics.services import detect_fraud
from apps.products.models import Product
from .models import Cart, CartItem, CustomerOrder, Order
from .serializers import CartSerializer, CheckoutInitSerializer, OrderSerializer


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


def _generate_order_number(prefix: str = "ORD") -> str:
    """
    Simple unique-ish order number generator.
    """
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


class CheckoutView(APIView):
    """
    Create a CustomerOrder + per-seller Orders from the current cart,
    then initialize a Paystack transaction and return the authorization URL.
    """

    permission_classes = [permissions.IsAuthenticated, IsBuyer]

    def get_cart(self, user) -> Cart:
        cart, _ = Cart.objects.get_or_create(buyer=user, is_active=True)
        return cart

    def post(self, request, *args, **kwargs):
        serializer = CheckoutInitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        user = request.user
        cart = self.get_cart(user)
        items = list(cart.items.select_related("product", "product__seller"))
        if not items:
            return Response({"detail": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)

        customer_name = data.get("customer_name") or getattr(user, "full_name", "") or user.email
        customer_phone = data.get("customer_phone") or getattr(user, "phone_number", "") or ""
        customer_email = user.email
        shipping_address = data["shipping_address"]

        # Attribution cookie & marketer detection
        attribution_cookie_id = request.COOKIES.get("linkway_attr")
        attribution = None
        if attribution_cookie_id:
            attribution = (
                AttributionTracking.objects.select_related("last_click_link__marketer", "last_click_link__product")
                .filter(cookie_id=attribution_cookie_id)
                .first()
            )

        # Compute totals and group cart items per seller
        seller_items: dict[str, list[CartItem]] = defaultdict(list)
        subtotal = Decimal("0")
        for item in items:
            seller_items[str(item.product.seller_id)].append(item)
            line_total = (item.unit_price or Decimal("0")) * item.quantity
            subtotal += line_total

        shipping_fee = Decimal("0")
        tax_amount = Decimal("0")
        total_amount = subtotal + shipping_fee + tax_amount

        # Ensure Paystack is configured
        secret_key = getattr(settings, "PAYSTACK_SECRET_KEY", "") or ""
        if not secret_key:
            return Response(
                {"detail": "Payment provider is not configured. Please try again later."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "")
        if frontend_base:
            callback_url = f"{frontend_base.rstrip('/')}/checkout/callback"
        else:
            callback_url = None

        payment_reference = uuid.uuid4().hex

        with transaction.atomic():
            customer_order = CustomerOrder.objects.create(
                order_number=_generate_order_number(prefix="CO"),
                buyer=user,
                customer_email=customer_email,
                customer_name=customer_name,
                customer_phone=customer_phone,
                shipping_address=shipping_address,
                subtotal=subtotal,
                shipping_fee=shipping_fee,
                tax_amount=tax_amount,
                total_amount=total_amount,
                payment_status="pending",
                payment_reference=payment_reference,
            )

            # Create a seller-level Order for each cart line (one product per order)
            created_orders: list[Order] = []
            now = timezone.now()

            for item in items:
                product = item.product
                seller = product.seller
                quantity = item.quantity
                unit_price = item.unit_price or product.price
                line_subtotal = unit_price * quantity

                marketer = None
                if attribution and attribution.last_click_link and attribution.last_click_link.product_id == product.id:
                    marketer = attribution.last_click_link.marketer

                order = Order.objects.create(
                    order_number=_generate_order_number(prefix="ORD"),
                    customer_order=customer_order,
                    product=product,
                    seller=seller,
                    marketer=marketer,
                    customer_email=customer_email,
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    shipping_address=shipping_address,
                    quantity=quantity,
                    unit_price=unit_price,
                    subtotal=line_subtotal,
                    shipping_fee=Decimal("0"),
                    tax_amount=Decimal("0"),
                    total_amount=line_subtotal,
                    commission_rate=getattr(product, "commission_rate", None),
                    commission_amount=Decimal("0"),
                    status="pending",
                    payment_status="pending",
                    payment_method="paystack",
                    payment_reference=None,
                    paystack_reference=None,
                    attribution_cookie_id=attribution_cookie_id,
                    notes="",
                )
                created_orders.append(order)
                detect_fraud("order", str(order.id))

            # Mark attribution as converted (if present)
            if attribution:
                attribution.converted = True
                attribution.converted_at = now
                # Link to the first order created for analytics purposes
                if created_orders:
                    attribution.order = created_orders[0]
                attribution.save(update_fields=["converted", "converted_at", "order"])

            # Clear the cart
            cart.items.all().delete()
            cart.is_active = False
            cart.save(update_fields=["is_active"])

        # Initialize Paystack transaction
        amount_kobo = int(total_amount * 100)
        headers = {
            "Authorization": f"Bearer {secret_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "email": customer_email,
            "amount": amount_kobo,
            "reference": payment_reference,
        }
        if callback_url:
            payload["callback_url"] = callback_url

        try:
            resp = requests.post("https://api.paystack.co/transaction/initialize", json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            # Roll back payment intent but keep orders pending so we can retry later if needed.
            return Response(
                {"detail": "Failed to contact payment provider. Please try again.", "error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        data = resp.json() or {}
        if not data.get("status"):
            return Response(
                {"detail": "Payment initialization failed", "provider_response": data},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        auth_url = data.get("data", {}).get("authorization_url")
        paystack_ref = data.get("data", {}).get("reference")

        # Persist Paystack reference on the customer order
        customer_order.paystack_reference = paystack_ref or payment_reference
        customer_order.save(update_fields=["paystack_reference"])

        return Response(
            {
                "authorization_url": auth_url,
                "reference": customer_order.payment_reference,
                "customer_order_id": str(customer_order.id),
                "total_amount": str(total_amount),
            },
            status=status.HTTP_201_CREATED,
        )
