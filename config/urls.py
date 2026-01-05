from django.contrib import admin
from django.urls import include, path

from apps.affiliates.views import handle_affiliate_click

urlpatterns = [
    path("admin/", admin.site.urls),
    # Public tracking/redirect endpoint for affiliate links
    path("p/<slug:product_slug>/", handle_affiliate_click, name="affiliate-click-public"),
    path("api/auth/", include("apps.authentication.urls")),
    path("api/products/", include("apps.products.urls")),
    path("api/affiliates/", include("apps.affiliates.urls")),
    path("api/orders/", include("apps.orders.urls")),
    path("api/commissions/", include("apps.commissions.urls")),
    path("api/payments/", include("apps.payments.urls")),
    path("api/ai/", include("apps.ai_services.urls")),
    path("api/analytics/", include("apps.analytics.urls")),
    path("api/notifications/", include("apps.notifications.urls")),
]
