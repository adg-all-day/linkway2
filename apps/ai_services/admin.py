from django.contrib import admin

from .models import AIContentLog, ProductRecommendation


@admin.register(AIContentLog)
class AIContentLogAdmin(admin.ModelAdmin):
    list_display = ("user", "product", "content_type", "platform", "tokens_used", "created_at")
    search_fields = ("user__email", "product__name", "content_type", "platform")


@admin.register(ProductRecommendation)
class ProductRecommendationAdmin(admin.ModelAdmin):
    list_display = ("marketer", "product", "recommendation_score", "expires_at")
    search_fields = ("marketer__email", "product__name")

