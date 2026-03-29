from celery import Celery
from kombu import Queue

from app.core.config import settings


celery_app = Celery(
    "ai_content_ops",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.task_default_queue = settings.queue_ai_processing
celery_app.conf.broker_connection_retry_on_startup = True
celery_app.conf.task_acks_late = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.task_track_started = True
celery_app.conf.task_queues = (
    Queue(settings.queue_ai_processing),
    Queue(settings.queue_review),
    Queue(settings.queue_review_p0),
    Queue(settings.queue_review_p1),
    Queue(settings.queue_review_p2),
    Queue(settings.queue_hold),
    Queue(settings.queue_distribution),
    Queue(settings.queue_distribution_youtube),
    Queue(settings.queue_distribution_secondary),
    Queue(settings.queue_report),
    Queue(settings.queue_reward),
    Queue(settings.queue_dlq),
)

celery_app.conf.task_routes = {
    "app.orchestrator.tasks.run_phase_a_task": {"queue": settings.queue_ai_processing},
    "app.orchestrator.tasks.create_gate_1_task": {"queue": settings.queue_review},
    "app.orchestrator.tasks.handle_gate_1_task": {"queue": settings.queue_ai_processing},
    "app.orchestrator.tasks.create_gate_2_task": {"queue": settings.queue_review},
    "app.orchestrator.tasks.finalize_job_task": {"queue": settings.queue_distribution},
    "app.orchestrator.tasks.distribute_content_task": {"queue": settings.queue_distribution},
    "app.orchestrator.tasks.generate_report_task": {"queue": settings.queue_report},
    "app.orchestrator.tasks.issue_reward_task": {"queue": settings.queue_reward},
    "app.orchestrator.tasks.after_review_decision_task": {"queue": settings.queue_review},
}
