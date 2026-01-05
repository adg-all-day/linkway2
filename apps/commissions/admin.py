from django.contrib import admin

from .models import Commission, Payout, PayoutCommission


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "marketer", "commission_amount", "net_commission", "status")
    search_fields = ("order__order_number", "marketer__email")
    list_filter = ("status",)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ("id", "marketer", "total_amount", "status", "requested_at", "completed_at")
    search_fields = ("marketer__email", "paystack_transfer_reference")
    list_filter = ("status",)


@admin.register(PayoutCommission)
class PayoutCommissionAdmin(admin.ModelAdmin):
    list_display = ("payout", "commission")

