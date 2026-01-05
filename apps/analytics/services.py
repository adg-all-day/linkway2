from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Dict, List

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.affiliates.models import AffiliateLink, AttributionTracking, ClickTracking
from apps.analytics.models import FraudDetectionLog
from apps.authentication.models import User
from apps.commissions.models import Commission
from apps.orders.models import Order


def is_bot_user_agent(user_agent: str | None) -> bool:
    if not user_agent:
        return False
    bot_patterns = [
        "bot",
        "crawler",
        "spider",
        "scraper",
        "curl",
        "wget",
        "python-requests",
        "java",
        "scrapy",
    ]
    ua = user_agent.lower()
    return any(pattern in ua for pattern in bot_patterns)


def detect_fraud(entity_type: str, entity_id: str) -> Dict[str, object]:
    fraud_signals: List[str] = []
    fraud_score = 0.0
    now = timezone.now()

    if entity_type == "click":
        try:
            click = ClickTracking.objects.select_related("link").get(id=entity_id)
        except ClickTracking.DoesNotExist:
            return {"fraud_score": 0.0, "signals": [], "action": "none"}

        recent_clicks_same_ip = ClickTracking.objects.filter(
            ip_address=click.ip_address,
            link_id=click.link_id,
            clicked_at__gt=now - timedelta(minutes=5),
        ).count()
        if recent_clicks_same_ip > 5:
            fraud_signals.append("Click spam from same IP")
            fraud_score += 0.4

        clicks_past_minute = ClickTracking.objects.filter(
            ip_address=click.ip_address,
            clicked_at__gt=now - timedelta(minutes=1),
        ).count()
        if clicks_past_minute > 10:
            fraud_signals.append("Impossible click velocity")
            fraud_score += 0.3

        if is_bot_user_agent(click.user_agent or ""):
            fraud_signals.append("Bot user agent detected")
            fraud_score += 0.5

        # Persist basic flags on click
        if fraud_score > 0:
            click.is_suspicious = fraud_score >= 0.3
            click.is_bot = is_bot_user_agent(click.user_agent or "")
            click.fraud_score = Decimal(str(min(fraud_score, 1.0)))
            click.save(update_fields=["is_suspicious", "is_bot", "fraud_score"])

    elif entity_type == "order":
        try:
            order = Order.objects.get(id=entity_id)
        except Order.DoesNotExist:
            return {"fraud_score": 0.0, "signals": [], "action": "none"}

        attribution = None
        if order.attribution_cookie_id:
            attribution = AttributionTracking.objects.filter(
                cookie_id=order.attribution_cookie_id
            ).first()

        if attribution is None:
            fraud_signals.append("No attribution record found")
            fraud_score += 0.6
        else:
            time_since_first_click = (order.created_at - attribution.created_at).total_seconds()
            if time_since_first_click < 10:
                fraud_signals.append("Suspiciously fast conversion")
                fraud_score += 0.5

            click_ip = (
                ClickTracking.objects.filter(cookie_id=order.attribution_cookie_id)
                .order_by("clicked_at")
                .values_list("ip_address", flat=True)
                .first()
            )
            if click_ip:
                orders_same_ip = (
                    Order.objects.filter(
                        created_at__gt=now - timedelta(hours=24),
                        attribution_cookie_id__in=ClickTracking.objects.filter(
                            ip_address=click_ip
                        ).values_list("cookie_id", flat=True),
                    )
                    .distinct()
                    .count()
                )
                if orders_same_ip > 3:
                    fraud_signals.append("Multiple orders from same IP")
                    fraud_score += 0.4

            if order.marketer_id:
                marketer = order.marketer
                marketer_age_days = (now - marketer.created_at).days
                if marketer_age_days < 7 and order.total_amount > 100000:
                    fraud_signals.append("High-value order by new marketer")
                    fraud_score += 0.3

    elif entity_type == "marketer":
        try:
            marketer = User.objects.get(id=entity_id, role="marketer")
        except User.DoesNotExist:
            return {"fraud_score": 0.0, "signals": [], "action": "none"}

        duplicate_accounts = User.objects.filter(
            account_number=marketer.account_number,
        ).exclude(id=marketer.id)
        if marketer.account_number and duplicate_accounts.exists():
            fraud_signals.append("Bank account used by multiple marketers")
            fraud_score += 0.7

        registration_ip = (
            ClickTracking.objects.filter(cookie_id__in=AttributionTracking.objects.filter(
                first_click_link__marketer=marketer
            ).values_list("cookie_id", flat=True))
            .values_list("ip_address", flat=True)
            .first()
        )
        if registration_ip:
            # Placeholder: in a real system, you would track registrations by IP in ActivityLog.
            pass

        total_clicks = AffiliateLink.objects.filter(marketer=marketer).aggregate(
            total=Sum("click_count")
        )["total"] or 0
        total_conversions = (
            Order.objects.filter(marketer=marketer).count()
        )

        if total_clicks > 0:
            conversion_rate = total_conversions / total_clicks
            if conversion_rate > 0.20:
                fraud_signals.append("Abnormally high conversion rate")
                fraud_score += 0.6

    fraud_score = min(fraud_score, 1.0)

    if fraud_score < 0.3:
        action = "none"
    elif fraud_score < 0.7:
        action = "flagged"
    else:
        action = "blocked"

    FraudDetectionLog.objects.create(
        entity_type=entity_type,
        entity_id=str(entity_id),
        fraud_type=", ".join(fraud_signals) if fraud_signals else "none",
        fraud_score=Decimal(str(fraud_score)),
        indicators={
            "signals": fraud_signals,
            "timestamp": timezone.now().isoformat(),
        },
        action_taken=action,
    )

    if action == "blocked":
        if entity_type == "marketer":
            User.objects.filter(id=entity_id).update(is_active=False)
            AffiliateLink.objects.filter(marketer_id=entity_id).update(is_active=False)
        elif entity_type == "order":
            Order.objects.filter(id=entity_id).update(status="cancelled")

    return {
        "fraud_score": fraud_score,
        "signals": fraud_signals,
        "action": action,
    }

