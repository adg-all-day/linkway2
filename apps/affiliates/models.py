import uuid

from django.db import models
from django.utils.text import slugify


class AffiliateLink(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    marketer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="affiliate_links",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.CASCADE,
        related_name="affiliate_links",
    )
    unique_slug = models.CharField(max_length=12, unique=True)
    full_url = models.TextField()
    custom_alias = models.CharField(max_length=50, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    click_count = models.IntegerField(default=0)
    conversion_count = models.IntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total_commission = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    last_clicked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("marketer", "product")

    def __str__(self) -> str:
        return f"{self.product.name} - {self.unique_slug}"


class Catalogue(models.Model):
    """
    A marketer-defined catalogue (bundle) of products they're promoting.

    This is used for "package catalogues" – curated sets of affiliate products.
    The "main catalogue" (all promoted products) is derived dynamically and
    does not need a dedicated row.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    marketer = models.ForeignKey(
        "authentication.User",
        on_delete=models.CASCADE,
        related_name="catalogues",
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    links = models.ManyToManyField(AffiliateLink, related_name="catalogues", blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.marketer.email})"

    def generate_unique_slug(self) -> None:
        base = slugify(self.name) or "catalogue"
        candidate = base
        idx = 1
        while Catalogue.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
            idx += 1
            candidate = f"{base}-{idx}"
        self.slug = candidate


class ClickTracking(models.Model):
    id = models.BigAutoField(primary_key=True)
    link = models.ForeignKey(
        AffiliateLink,
        on_delete=models.CASCADE,
        related_name="clicks",
    )
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    device_type = models.CharField(max_length=20, blank=True, null=True)
    browser = models.CharField(max_length=50, blank=True, null=True)
    operating_system = models.CharField(max_length=50, blank=True, null=True)
    referrer_url = models.TextField(blank=True, null=True)
    landing_page_url = models.TextField(blank=True, null=True)
    country_code = models.CharField(max_length=2, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    cookie_id = models.CharField(max_length=100, blank=True, null=True)
    clicked_at = models.DateTimeField(auto_now_add=True)
    is_bot = models.BooleanField(default=False)
    is_suspicious = models.BooleanField(default=False)
    fraud_score = models.DecimalField(max_digits=3, decimal_places=2, default=0)


class AttributionTracking(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    cookie_id = models.CharField(max_length=100, unique=True)
    session_id = models.CharField(max_length=100, blank=True, null=True)
    first_click_link = models.ForeignKey(
        AffiliateLink,
        on_delete=models.SET_NULL,
        related_name="first_click_attributions",
        null=True,
        blank=True,
    )
    last_click_link = models.ForeignKey(
        AffiliateLink,
        on_delete=models.SET_NULL,
        related_name="last_click_attributions",
        null=True,
        blank=True,
    )
    attribution_model = models.CharField(max_length=20, default="last_click")
    click_chain = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    converted = models.BooleanField(default=False)
    converted_at = models.DateTimeField(blank=True, null=True)
    order = models.ForeignKey(
        "orders.Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attributions",
    )


class CookieConsent(models.Model):
    id = models.BigAutoField(primary_key=True)
    cookie_id = models.CharField(max_length=100, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True, null=True)
    consent_given = models.BooleanField(default=False)
    consent_types = models.JSONField(default=dict, blank=True)
    consent_given_at = models.DateTimeField(blank=True, null=True)
    consent_withdrawn_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
