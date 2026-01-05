from django.contrib import admin

from .models import PaymentLog


@admin.register(PaymentLog)
class PaymentLogAdmin(admin.ModelAdmin):
    list_display = ("provider", "reference", "created_at")
    search_fields = ("provider", "reference")

