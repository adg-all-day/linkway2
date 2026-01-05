from django.db import models


class AIContentLog(models.Model):
    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="ai_content_logs",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="ai_content_logs",
    )
    content_type = models.CharField(max_length=50)
    prompt = models.TextField()
    generated_content = models.TextField()
    platform = models.CharField(max_length=50)
    tone = models.CharField(max_length=50)
    was_used = models.BooleanField(default=False)
    feedback_rating = models.IntegerField(null=True, blank=True)
    tokens_used = models.IntegerField(null=True, blank=True)
    generation_time_ms = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ProductRecommendation(models.Model):
    marketer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="product_recommendations",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="product_recommendations",
    )
    recommendation_score = models.DecimalField(max_digits=5, decimal_places=4)
    recommendation_reason = models.TextField(blank=True, null=True)
    match_factors = models.JSONField(default=dict, blank=True)
    was_promoted = models.BooleanField(default=False)
    promoted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)

