from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AffiliateLinkViewSet, handle_affiliate_click

router = DefaultRouter()
router.register("links", AffiliateLinkViewSet, basename="affiliate-link")

urlpatterns = router.urls + [
    path("click/p/<slug:product_slug>/", handle_affiliate_click, name="affiliate-click"),
]

