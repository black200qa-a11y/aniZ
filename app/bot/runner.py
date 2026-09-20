from __future__ import annotations

import asyncio

from aniz_pipeline.logging_config import configure_logging

from ..core.config import get_settings
from ..core.database import Mongo
from ..services.admin_service import AdminService
from .admin_bot import AdminBot


async def run_bot() -> None:
    settings = get_settings()
    if not settings.is_pc_role or not settings.telegram_configured:
        raise RuntimeError("The bot runner requires DEPLOYMENT_ROLE=pc and complete Telegram credentials")
    configure_logging(settings.log_level, settings.log_dir)
    mongo = Mongo(settings)
    await mongo.connect()
    bot = AdminBot(settings, mongo, AdminService(settings.log_dir))
    await bot.start()
    try:
        await asyncio.Event().wait()
    finally:
        await bot.stop()
        await mongo.close()


if __name__ == "__main__":
    asyncio.run(run_bot())
