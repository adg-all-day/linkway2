from __future__ import annotations

import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.affiliates.models import AffiliateLink, ClickTracking
from apps.ai_services.models import AIContentLog, ProductRecommendation
from apps.commissions.calculator import calculate_commission
from apps.commissions.models import Commission, Payout
from apps.orders.models import Order
from apps.products.models import Product, ProductCategory


def _print(title: str, data) -> None:
    print(f"\n=== {title} ===")
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, default=str))
    else:
        print(data)


def run() -> None:
    """
    Manual smoke test hitting key endpoints and flows.

    Run with:
      python manage.py shell --settings=config.settings.testing -c "from scripts.smoke_test_endpoints import run; run()"
    """
    User = get_user_model()

    # Clean tables for a deterministic run
    Order.objects.all().delete()
    Commission.objects.all().delete()
    Payout.objects.all().delete()
    AffiliateLink.objects.all().delete()
    ClickTracking.objects.all().delete()
    ProductRecommendation.objects.all().delete()
    AIContentLog.objects.all().delete()
    Product.objects.all().delete()
    ProductCategory.objects.all().delete()
    User.objects.all().delete()

    # Create core users directly
    admin = User.objects.create_superuser(
        email="admin@example.com",
        password="Admin123!",
        full_name="Admin User",
        role="admin",
    )
    seller = User.objects.create_user(
        email="seller@example.com",
        password="Seller123!",
        full_name="Seller User",
        role="seller",
    )
    marketer = User.objects.create_user(
        email="marketer@example.com",
        password="Marketer123!",
        full_name="Marketer User",
        role="marketer",
    )
    # Configure marketer bank details for payout testing
    marketer.bank_name = "Test Bank"
    marketer.account_number = "0123456789"
    marketer.account_name = "Marketer User"
    marketer.save(update_fields=["bank_name", "account_number", "account_name"])

    _print("Users created", {"admin": admin.email, "seller": seller.email, "marketer": marketer.email})

    # Helper to get JWT token
    def get_token(email: str, password: str) -> str:
        client = APIClient()
        resp = client.post(
            "/api/auth/token/",
            {"email": email, "password": password},
            format="json",
        )
        _print(f"Token response for {email}", {"status": resp.status_code})
        assert resp.status_code == 200, resp.content
        return resp.data["access"]

    admin_token = get_token("admin@example.com", "Admin123!")
    seller_token = get_token("seller@example.com", "Seller123!")
    marketer_token = get_token("marketer@example.com", "Marketer123!")

    # Test /api/auth/me/ for marketer
    marketer_client = APIClient()
    marketer_client.credentials(HTTP_AUTHORIZATION=f"Bearer {marketer_token}")
    resp = marketer_client.get("/api/auth/me/")
    _print("GET /api/auth/me/ (marketer)", {"status": resp.status_code, "data": resp.data})

    # Seller: create category and product via API
    seller_client = APIClient()
    seller_client.credentials(HTTP_AUTHORIZATION=f"Bearer {seller_token}")

    resp = seller_client.post(
        "/api/products/categories/",
        {"name": "Electronics", "slug": "electronics"},
        format="json",
    )
    _print("POST /api/products/categories/", {"status": resp.status_code, "data": resp.data})
    assert resp.status_code == 201
    category_id = resp.data["id"]

    product_payload = {
        "category": category_id,
        "name": "HP Pavilion Laptop 15.6",
        "slug": "hp-pavilion-15-6",
        "description": "Powerful laptop for everyday use.",
        "short_description": "HP laptop",
        "price": "450000.00",
        "compare_at_price": "500000.00",
        "cost_price": "350000.00",
        "commission_rate": "15.0",
        "commission_type": "percentage",
        "stock_quantity": 10,
        "sku": "HP-LAP-2024",
        "is_active": True,
    }
    resp = seller_client.post("/api/products/", product_payload, format="json")
    _print("POST /api/products/", {"status": resp.status_code, "data": resp.data})
    assert resp.status_code == 201, resp.content
    product_id = resp.data["id"]

    # Marketer: generate affiliate link
    resp = marketer_client.post(
        "/api/affiliates/links/generate/",
        {"product_id": product_id},
        format="json",
    )
    _print("POST /api/affiliates/links/generate/", {"status": resp.status_code, "data": resp.data})
    assert resp.status_code == 201
    link_slug = resp.data["unique_slug"]
    product_slug = resp.data["full_url"].split("/p/")[1].split("?")[0]

    # Simulate click on affiliate link
    click_client = APIClient(enforce_csrf_checks=False)
    click_url = f"/api/affiliates/click/p/{product_slug}/?ref={link_slug}"
    resp = click_client.get(click_url, follow=True)
    _print("GET affiliate click", {"status": resp.status_code, "redirect_chain": resp.redirect_chain})

    # Fetch created click and attribution
    click_count = ClickTracking.objects.count()
    _print("ClickTracking count", click_count)

    # Seller: create delivered order attributed to marketer
    order_payload = {
        "order_number": "ORD-1001",
        "product": product_id,
        "seller": str(seller.id),
        "marketer": str(marketer.id),
        "customer_email": "customer@example.com",
        "customer_name": "Customer One",
        "customer_phone": "08000000000",
        "shipping_address": {
            "street": "1 Test Street",
            "city": "Lagos",
            "state": "Lagos",
            "country": "NG",
            "postal_code": "100001",
        },
        "quantity": 1,
        "unit_price": "450000.00",
        "subtotal": "450000.00",
        "shipping_fee": "0.00",
        "tax_amount": "0.00",
        "total_amount": "450000.00",
        "commission_rate": "15.0",
        "status": "delivered",
        "payment_status": "paid",
        "payment_method": "paystack",
        "payment_reference": "PAY-REF-1001",
    }
    resp = seller_client.post("/api/orders/", order_payload, format="json")
    _print("POST /api/orders/", {"status": resp.status_code, "data": resp.data})
    assert resp.status_code == 201, resp.content
    order_id = resp.data["id"]

    # Calculate commission for delivered order
    order = Order.objects.get(id=order_id)
    commission = calculate_commission(order)
    if commission:
        # For testing payout flow, skip holdback and mark as approved.
        commission.status = "approved"
        commission.approved_at = timezone.now()
        commission.save(update_fields=["status", "approved_at"])
    _print("Calculated commission", {"id": str(commission.id) if commission else None})

    # Marketer: list commissions via API
    resp = marketer_client.get("/api/commissions/commissions/")
    _print("GET /api/commissions/commissions/ (marketer)", {"status": resp.status_code, "data": resp.data})

    # Marketer: request payout (full amount)
    resp = marketer_client.post("/api/commissions/payouts/request/", {}, format="json")
    _print("POST /api/commissions/payouts/request/", {"status": resp.status_code, "data": resp.data})

    # AI content generation
    content_payload = {
        "product_id": product_id,
        "content_type": "instagram_caption",
        "platform": "instagram",
        "tone": "enthusiastic",
    }
    resp = marketer_client.post("/api/ai/content/", content_payload, format="json")
    _print("POST /api/ai/content/", {"status": resp.status_code})

    # Product recommendations
    resp = marketer_client.post("/api/ai/recommendations/", {"limit": 5}, format="json")
    _print("POST /api/ai/recommendations/", {"status": resp.status_code, "count": len(resp.data)})

    # Dashboards
    resp = marketer_client.get("/api/analytics/marketer/dashboard/")
    _print("GET /api/analytics/marketer/dashboard/", {"status": resp.status_code})

    seller_dashboard_client = APIClient()
    seller_dashboard_client.credentials(HTTP_AUTHORIZATION=f"Bearer {seller_token}")
    resp = seller_dashboard_client.get("/api/analytics/seller/dashboard/")
    _print("GET /api/analytics/seller/dashboard/", {"status": resp.status_code})

    admin_client = APIClient()
    admin_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")
    resp = admin_client.get("/api/analytics/admin/dashboard/")
    _print("GET /api/analytics/admin/dashboard/", {"status": resp.status_code})

    # Simulate Paystack webhooks
    webhook_client = APIClient()

    # charge.success for order
    resp = webhook_client.post(
        "/api/payments/paystack/webhook/",
        {
            "event": "charge.success",
            "data": {"reference": "PAY-REF-1001"},
        },
        format="json",
    )
    _print("Paystack charge.success webhook", {"status": resp.status_code})

    # transfer.success for latest payout
    latest_payout = Payout.objects.order_by("-requested_at").first()
    if latest_payout and latest_payout.paystack_transfer_reference:
        resp = webhook_client.post(
            "/api/payments/paystack/webhook/",
            {
                "event": "transfer.success",
                "data": {"reference": latest_payout.paystack_transfer_reference, "reason": "OK"},
            },
            format="json",
        )
        _print("Paystack transfer.success webhook", {"status": resp.status_code})

    _print("Smoke test complete", "OK")
