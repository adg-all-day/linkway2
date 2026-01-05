import uuid

from django.db import models


class Commission(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("earned", "Earned"),
        ("held", "Held"),
        ("approved", "Approved"),
        ("paid", "Paid"),
        ("reversed", "Reversed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="commissions",
    )
    marketer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="commissions",
    )
    product = models.ForeignKey(
        "products.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commissions",
    )
    gross_sale_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=2)
    commission_amount = models.DecimalField(max_digits=12, decimal_places=2)
    platform_fee_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.5)
    platform_fee_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    net_commission = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    earned_at = models.DateTimeField(blank=True, null=True)
    holdback_until = models.DateTimeField(blank=True, null=True)
    approved_at = models.DateTimeField(blank=True, null=True)
    payout = models.ForeignKey(
        "commissions.Payout",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="commissions",
    )
    paid_at = models.DateTimeField(blank=True, null=True)
    reversal_reason = models.TextField(blank=True, null=True)
    reversed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Payout(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    marketer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="payouts",
    )
    payout_method = models.CharField(max_length=20, default="bank_transfer")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    commission_count = models.IntegerField()
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=10, blank=True, null=True)
    account_name = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    paystack_transfer_reference = models.CharField(max_length=100, blank=True, null=True)
    transfer_code = models.CharField(max_length=100, blank=True, null=True)
    failure_reason = models.TextField(blank=True, null=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)


class PayoutCommission(models.Model):
    payout = models.ForeignKey(Payout, on_delete=models.CASCADE)
    commission = models.ForeignKey(Commission, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("payout", "commission")

