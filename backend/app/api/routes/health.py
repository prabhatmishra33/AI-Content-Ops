from fastapi import APIRouter

from app.core.config import settings
from app.core.observability import metrics_endpoint


router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live():
    return {"status": "live"}


@router.get("/ready")
def ready():
    return {"status": "ready", "env": settings.app_env}


@router.get("/metrics")
async def metrics():
    return await metrics_endpoint()
