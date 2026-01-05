from django.urls import path

from .views import (
    AdminDashboardView,
    FraudLogListView,
    MarketerDashboardView,
    SellerDashboardView,
    SystemConfigView,
)

urlpatterns = [
    path("marketer/dashboard/", MarketerDashboardView.as_view(), name="marketer-dashboard"),
    path("seller/dashboard/", SellerDashboardView.as_view(), name="seller-dashboard"),
    path("admin/dashboard/", AdminDashboardView.as_view(), name="admin-dashboard"),
    path("fraud-logs/", FraudLogListView.as_view(), name="fraud-logs"),
    path("system-config/", SystemConfigView.as_view(), name="system-config"),
]
