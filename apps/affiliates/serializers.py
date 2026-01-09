from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from apps.products.models import Product

from .models import AffiliateLink, Catalogue
from .services import generate_affiliate_link


class AffiliateLinkSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_is_active = serializers.BooleanField(source="product.is_active", read_only=True)
    product_price = serializers.DecimalField(
        source="product.price",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = AffiliateLink
        fields = [
            "id",
            "marketer",
            "product",
            "product_name",
            "product_is_active",
            "product_price",
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


class CatalogueSerializer(serializers.ModelSerializer):
    """
    Serializer used by marketers to manage their own package catalogues.
    Accepts a list of product IDs and resolves them to the marketer's
    active AffiliateLinks for storage.
    """

    product_ids = serializers.ListField(
        child=serializers.UUIDField(),
        write_only=True,
    )
    item_count = serializers.IntegerField(source="links.count", read_only=True)

    class Meta:
        model = Catalogue
        fields = ["id", "name", "slug", "item_count", "product_ids", "created_at"]
        read_only_fields = ["id", "slug", "item_count", "created_at"]

    def create(self, validated_data):
        request = self.context["request"]
        marketer = request.user
        product_ids = validated_data.pop("product_ids", [])

        if not product_ids:
            raise ValidationError({"product_ids": "Select at least one product for this catalogue."})

        catalogue = Catalogue(marketer=marketer, name=validated_data["name"])
        catalogue.generate_unique_slug()
        catalogue.save()

        links = AffiliateLink.objects.filter(
            marketer=marketer,
            product_id__in=product_ids,
            is_active=True,
            product__is_active=True,
        )
        if links.count() != len(set(product_ids)):
            raise ValidationError(
                {"product_ids": "One or more selected products are not being promoted by you or are inactive."}
            )

        catalogue.links.set(links)
        return catalogue

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # product_ids are write-only; frontends typically only need counts + meta here.
        data.pop("product_ids", None)
        return data
