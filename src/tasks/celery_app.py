from celery import Celery

from config.settings import get_settings

settings = get_settings()

app = Celery(
    "law_by_ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend_url,
)
