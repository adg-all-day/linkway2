import os
import secrets
import string
from datetime import datetime, timedelta, timezone

from django.db import IntegrityError, transaction

from apps.affiliates.models import AffiliateLink, AttributionTracking
from apps.authentication.models import User
from apps.products.models import Product


ALPHABET = string.ascii_letters + string.digits
PUBLIC_BASE_URL = os.getenv("LINKWAY_PUBLIC_BASE_URL", "http://localhost:8000")


def generate_unique_slug(length: int = 12) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def generate_affiliate_link(marketer: User, product: Product) -> AffiliateLink:
    existing = AffiliateLink.objects.filter(marketer=marketer, product=product, is_active=True).first()
    if existing:
        return existing

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_count = AffiliateLink.objects.filter(marketer=marketer, created_at__gt=one_hour_ago).count()
    if recent_count >= 50:
        raise ValueError("Maximum 50 links per hour")

    base = PUBLIC_BASE_URL.rstrip("/")

    for _ in range(5):
        slug = generate_unique_slug(12)
        full_url = f"{base}/p/{product.slug}?ref={slug}"
        try:
            with transaction.atomic():
                link = AffiliateLink.objects.create(
                    marketer=marketer,
                    product=product,
                    unique_slug=slug,
                    full_url=full_url,
                )
            return link
        except IntegrityError:
            continue
    raise RuntimeError("Failed to generate unique slug")


def create_or_update_attribution(cookie_id: str, affiliate_link: AffiliateLink, session_id: str | None = None) -> AttributionTracking:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=30)
    attribution, created = AttributionTracking.objects.get_or_create(
        cookie_id=cookie_id,
        defaults={
            "session_id": session_id,
            "first_click_link": affiliate_link,
            "last_click_link": affiliate_link,
            "attribution_model": "last_click",
            "click_chain": [{"link_id": str(affiliate_link.id), "timestamp": now.isoformat(), "weight": 1.0}],
            "expires_at": expires_at,
        },
    )
    if not created:
        chain = list(attribution.click_chain or [])
        chain.append({"link_id": str(affiliate_link.id), "timestamp": now.isoformat(), "weight": 1.0})
        attribution.last_click_link = affiliate_link
        attribution.click_chain = chain
        attribution.expires_at = expires_at
        attribution.save(update_fields=["last_click_link", "click_chain", "expires_at"])
    return attribution
