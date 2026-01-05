from django.contrib import admin

from .models import Order


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("order_number", "product", "seller", "marketer", "status", "payment_status", "total_amount")
    search_fields = ("order_number", "customer_email", "customer_name")
    list_filter = ("status", "payment_status")

