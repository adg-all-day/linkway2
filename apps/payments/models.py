from django.db import models


class PaymentLog(models.Model):
    provider = models.CharField(max_length=50)
    reference = models.CharField(max_length=100, unique=True)
    raw_payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

