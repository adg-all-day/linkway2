from rest_framework import serializers

from .models import FraudDetectionLog


class FraudDetectionLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FraudDetectionLog
        fields = [
            "id",
            "entity_type",
            "entity_id",
            "fraud_type",
            "fraud_score",
            "indicators",
            "action_taken",
            "is_false_positive",
            "reviewed_by",
            "reviewed_at",
            "detected_at",
        ]

