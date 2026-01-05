from django.contrib import admin

from .models import AffiliateLink, AttributionTracking, ClickTracking, CookieConsent


@admin.register(AffiliateLink)
class AffiliateLinkAdmin(admin.ModelAdmin):
    list_display = ("unique_slug", "product", "marketer", "is_active", "click_count", "conversion_count")
    search_fields = ("unique_slug", "product__name", "marketer__email")
    list_filter = ("is_active",)


@admin.register(ClickTracking)
class ClickTrackingAdmin(admin.ModelAdmin):
    list_display = ("link", "ip_address", "clicked_at", "is_bot", "is_suspicious")
    search_fields = ("ip_address", "user_agent", "link__unique_slug")
    list_filter = ("is_bot", "is_suspicious")


@admin.register(AttributionTracking)
class AttributionTrackingAdmin(admin.ModelAdmin):
    list_display = ("cookie_id", "first_click_link", "last_click_link", "attribution_model", "expires_at")
    search_fields = ("cookie_id",)


@admin.register(CookieConsent)
class CookieConsentAdmin(admin.ModelAdmin):
    list_display = ("cookie_id", "ip_address", "consent_given", "created_at")
    search_fields = ("cookie_id", "ip_address")

