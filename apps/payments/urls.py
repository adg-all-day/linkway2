from django.urls import path

from .views import PaystackWebhookView

urlpatterns = [
    path("paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
]

