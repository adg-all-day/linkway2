from rest_framework.routers import DefaultRouter

from .views import ProductCategoryViewSet, ProductViewSet

router = DefaultRouter()
router.register("categories", ProductCategoryViewSet, basename="product-category")
router.register("", ProductViewSet, basename="product")

urlpatterns = router.urls

