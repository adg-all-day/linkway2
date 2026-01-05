from celery import shared_task


@shared_task
def run_fraud_detection() -> str:
    # Placeholder for fraud detection job
    return "fraud_detection_not_implemented"

