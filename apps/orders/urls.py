from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CartItemView, CartView, CheckoutView, OrderViewSet

router = DefaultRouter()
router.register("", OrderViewSet, basename="order")

urlpatterns = [
    path("cart/", CartView.as_view(), name="cart"),
    path("cart/items/<int:item_id>/", CartItemView.as_view(), name="cart-item"),
    path("checkout/", CheckoutView.as_view(), name="checkout"),
] + router.urls
