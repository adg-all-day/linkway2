from datetime import timedelta, timezone
from decimal import Decimal

from django.utils import timezone as dj_timezone

from apps.affiliates.models import AffiliateLink
from apps.orders.models import Order

from .models import Commission


def calculate_commission(order: Order) -> Commission | None:
    if order.status != "delivered" or order.marketer is None:
        return None

    existing = Commission.objects.filter(order=order).first()
    if existing:
        return existing

    product = order.product
    if product.commission_type == "percentage":
        gross_commission = (order.subtotal * product.commission_rate) / Decimal("100")
    else:
        gross_commission = product.fixed_commission_amount * order.quantity

    platform_fee_rate = Decimal("2.5")
    platform_fee_amount = (gross_commission * platform_fee_rate) / Decimal("100")
    net_commission = gross_commission - platform_fee_amount

    delivered_at = order.delivered_at or dj_timezone.now()
    holdback_until = delivered_at + timedelta(days=14)

    commission = Commission.objects.create(
        order=order,
        marketer=order.marketer,
        product=order.product,
        gross_sale_amount=order.subtotal,
        commission_rate=product.commission_rate,
        commission_amount=gross_commission,
        platform_fee_rate=platform_fee_rate,
        platform_fee_amount=platform_fee_amount,
        net_commission=net_commission,
        status="earned",
        earned_at=dj_timezone.now(),
        holdback_until=holdback_until,
    )

    affiliate_link = AffiliateLink.objects.filter(
        marketer=order.marketer,
        product=order.product,
    ).first()
    if affiliate_link:
        affiliate_link.conversion_count += 1
        affiliate_link.total_revenue += order.subtotal
        affiliate_link.total_commission += gross_commission
        affiliate_link.save(update_fields=["conversion_count", "total_revenue", "total_commission"])

    return commission

