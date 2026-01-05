from django.contrib import admin

from .models import ActivityLog, FraudDetectionLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("user", "action", "entity_type", "entity_id", "created_at")
    search_fields = ("user__email", "action", "entity_type", "entity_id")


@admin.register(FraudDetectionLog)
class FraudDetectionLogAdmin(admin.ModelAdmin):
    list_display = ("entity_type", "entity_id", "fraud_score", "action_taken", "detected_at")
    search_fields = ("entity_type", "entity_id")
    list_filter = ("action_taken",)

