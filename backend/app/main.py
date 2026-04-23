from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ai_results, audio_news, audit, auth, distribution, health, media, ops, policies, reports, rewards, reviews, videos, workflow
from app.core.config import settings
from app.core.observability import configure_logging, observability_middleware
from app.db.base import Base
from app.db.session import engine


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title=settings.app_name, debug=settings.debug)
    app.middleware("http")(observability_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    Base.metadata.create_all(bind=engine)

    app.include_router(health.router, prefix="/api/v1")
    app.include_router(auth.router, prefix="/api/v1")
    app.include_router(videos.router, prefix="/api/v1")
    app.include_router(workflow.router, prefix="/api/v1")
    app.include_router(reviews.router, prefix="/api/v1")
    app.include_router(ai_results.router, prefix="/api/v1")
    app.include_router(policies.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(distribution.router, prefix="/api/v1")
    app.include_router(ops.router, prefix="/api/v1")
    app.include_router(rewards.router, prefix="/api/v1")
    app.include_router(audit.router, prefix="/api/v1")
    app.include_router(audio_news.router, prefix="/api/v1")
    app.include_router(media.router, prefix="/api/v1")

    return app


app = create_app()
