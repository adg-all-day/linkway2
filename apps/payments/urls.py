from django.urls import path

from .views import PaystackVerifyView, PaystackWebhookView

urlpatterns = [
    path("paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("paystack/verify/", PaystackVerifyView.as_view(), name="paystack-verify"),
]
