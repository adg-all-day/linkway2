from rest_framework.routers import DefaultRouter

from .views import CommissionViewSet, PayoutViewSet

router = DefaultRouter()
router.register("commissions", CommissionViewSet, basename="commission")
router.register("payouts", PayoutViewSet, basename="payout")

urlpatterns = router.urls

