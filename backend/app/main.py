import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import SecurityHeadersMiddleware
from app.db.registry import Base
from app.db.session import engine

logger = logging.getLogger("hertex")


async def bootstrap_database() -> None:
    if settings.AUTO_CREATE_TABLES:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("database.tables.ready")
    if settings.AUTO_SEED:
        from app.db.seed import seed_all

        await seed_all()
        logger.info("database.seed.complete")


@asynccontextmanager
async def lifespan(_: FastAPI):
    import app.core.subscribers  # noqa: F401

    await bootstrap_database()
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(SecurityHeadersMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_STR)

    @app.get("/health", tags=["System"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "environment": settings.ENVIRONMENT,
        }

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": settings.PROJECT_NAME, "docs": "/docs", "health": "/health"}

    return app


app = create_app()
