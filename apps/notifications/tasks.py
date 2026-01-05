from celery import shared_task


@shared_task
def send_commission_earned_email(marketer_id: str, commission_id: str) -> None:
    # Integrate with email provider
    return None


@shared_task
def send_payout_initiated_email(marketer_id: str, payout_id: str) -> None:
    return None


@shared_task
def send_payout_completed_email(marketer_id: str, payout_id: str) -> None:
    return None


@shared_task
def send_fraud_alert(entity_type: str, entity_id: str, fraud_score: float) -> None:
    return None

