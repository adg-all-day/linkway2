from celery import shared_task
from django.utils import timezone

from apps.orders.models import Order

from .calculator import calculate_commission
from .models import Commission


@shared_task
def process_pending_commissions() -> int:
    processed = 0
    orders = Order.objects.filter(status="delivered", commissions__isnull=True)
    for order in orders:
        commission = calculate_commission(order)
        if commission:
            processed += 1
    return processed


@shared_task
def release_held_commissions() -> int:
    now = timezone.now()
    qs = Commission.objects.filter(status="earned", holdback_until__lte=now)
    count = qs.update(status="approved", approved_at=now)
    return count


@shared_task
def approve_commission(commission_id: str) -> None:
    try:
        commission = Commission.objects.get(id=commission_id)
    except Commission.DoesNotExist:
        return
    commission.status = "approved"
    commission.approved_at = timezone.now()
    commission.save(update_fields=["status", "approved_at"])

