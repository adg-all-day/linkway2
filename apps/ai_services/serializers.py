from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.products.models import Product

from .models import AIContentLog, ProductRecommendation

User = get_user_model()


class GenerateContentSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    content_type = serializers.ChoiceField(
        choices=[
            "instagram_caption",
            "twitter_post",
            "facebook_post",
            "blog_introduction",
            "product_review",
            "email_pitch",
            "poster",
        ]
    )
    platform = serializers.CharField(max_length=50)
    tone = serializers.CharField(max_length=50, default="professional")
    marketer_notes = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found")
        if not product.is_active:
            raise serializers.ValidationError("Product is not active")
        return value


class GenerateImageSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    style = serializers.ChoiceField(
        choices=[
            "social_square",  # e.g. Instagram feed
            "story_vertical",  # e.g. WhatsApp / IG story
            "flyer_poster",  # printable / shareable flyer
        ]
    )
    tone = serializers.CharField(max_length=50, default="bold")
    marketer_notes = serializers.CharField(max_length=500, required=False, allow_blank=True)
    use_product_image = serializers.BooleanField(required=False, default=True)

    def validate_product_id(self, value):
        try:
            product = Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found")
        if not product.is_active:
            raise serializers.ValidationError("Product is not active")
        return value


class AIContentLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AIContentLog
        fields = "__all__"


class ProductRecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductRecommendation
        fields = "__all__"
