from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.products.models import Product

from .models import AffiliateLink
from .services import generate_affiliate_link


class AffiliateLinkSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_is_active = serializers.BooleanField(source="product.is_active", read_only=True)

    class Meta:
        model = AffiliateLink
        fields = [
            "id",
            "marketer",
            "product",
            "product_name",
            "product_is_active",
            "unique_slug",
            "full_url",
            "custom_alias",
            "is_active",
            "expires_at",
            "click_count",
            "conversion_count",
            "total_revenue",
            "total_commission",
            "created_at",
            "last_clicked_at",
        ]
        read_only_fields = [
            "id",
            "marketer",
            "unique_slug",
            "full_url",
            "click_count",
            "conversion_count",
            "total_revenue",
            "total_commission",
            "created_at",
            "last_clicked_at",
        ]


class GenerateAffiliateLinkSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()

    def create(self, validated_data):
        request = self.context["request"]
        marketer = request.user
        product = Product.objects.get(id=validated_data["product_id"])
        if not product.is_active:
            raise ValidationError({"detail": "This product is no longer available for promotion."})
        link = generate_affiliate_link(marketer=marketer, product=product)
        return link
