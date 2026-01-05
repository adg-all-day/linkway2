from rest_framework import permissions, viewsets

from .models import Product, ProductCategory
from .serializers import ProductCategorySerializer, ProductSerializer


class IsSellerOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.role == "seller")

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.seller == request.user


class ProductCategoryViewSet(viewsets.ModelViewSet):
    queryset = ProductCategory.objects.all()
    serializer_class = ProductCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.select_related("seller", "category").all()
    serializer_class = ProductSerializer
    permission_classes = [IsSellerOrReadOnly]
    filterset_fields = ["category", "seller", "is_active", "is_featured"]
    search_fields = ["name", "slug", "description"]
    ordering_fields = ["created_at", "price", "total_sales"]
