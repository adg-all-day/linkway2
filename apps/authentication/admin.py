from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "full_name",
                    "phone_number",
                    "profile_image_url",
                    "role",
                )
            },
        ),
        (
            "KYC",
            {
                "fields": (
                    "bvn",
                    "nin",
                    "kyc_status",
                    "kyc_verified_at",
                )
            },
        ),
        (
            "Bank details",
            {
                "fields": (
                    "bank_name",
                    "account_number",
                    "account_name",
                )
            },
        ),
        (
            "Roles",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Important dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "role", "password1", "password2"),
            },
        ),
    )
    list_display = ("email", "full_name", "role", "is_active", "is_staff")
    search_fields = ("email", "full_name")
    ordering = ("email",)

