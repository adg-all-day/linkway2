from django.db import models


class ActivityLog(models.Model):
    user = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=100)
    entity_type = models.CharField(max_length=50, blank=True, null=True)
    entity_id = models.CharField(max_length=255, blank=True, null=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FraudDetectionLog(models.Model):
    entity_type = models.CharField(max_length=20)
    entity_id = models.CharField(max_length=255)
    fraud_type = models.CharField(max_length=50)
    fraud_score = models.DecimalField(max_digits=3, decimal_places=2)
    indicators = models.JSONField(default=dict, blank=True)
    action_taken = models.CharField(max_length=50)
    is_false_positive = models.BooleanField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        "authentication.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_fraud_logs",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    detected_at = models.DateTimeField(auto_now_add=True)

