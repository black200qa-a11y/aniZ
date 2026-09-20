from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from aniz_pipeline.logging_config import configure_logging

from .api.catalog import router as catalog_router
from .api.streaming import router as streaming_router
from .core.config import get_settings
from .core.database import Mongo
from .core.telegram_client import TelegramClientManager
from .services.stream_service import TelegramStreamService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    mongo = Mongo(settings)
    telegram = TelegramClientManager(settings)
    await mongo.connect()
    await telegram.start()
    app.state.mongo = mongo
    app.state.telegram = telegram
    app.state.streamer = TelegramStreamService(telegram, settings.effective_max_concurrent_streams, settings.stream_chunk_size)
    try:
        yield
    finally:
        await telegram.stop()
        await mongo.close()


def create_app() -> FastAPI:
    app = FastAPI(title="Aniz API", version="0.2.0", lifespan=lifespan)
    app.include_router(catalog_router)
    app.include_router(streaming_router)

    @app.get("/api/v1/health")
    async def health(request: Request):
        mongo_ok = await request.app.state.mongo.ping()
        telegram_ok = await request.app.state.telegram.health()
        status = "ok" if mongo_ok and telegram_ok else "degraded"
        return {"status": status, "mongodb": mongo_ok, "telegram": telegram_ok, "storage": "telegram" if telegram_ok else "unavailable"}

    return app


app = create_app()


def run() -> None:
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.api_host, port=settings.api_port, reload=False)


if __name__ == "__main__":
    run()
