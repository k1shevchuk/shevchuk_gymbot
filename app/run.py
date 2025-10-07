from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .config import get_settings
from .routers import import_export, menu, plan, settings, summary, workout
from .scheduler import start_scheduler

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    app_settings = get_settings()
    bot = Bot(
        token=app_settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    dp.include_router(workout.router)
    dp.include_router(summary.router)
    dp.include_router(plan.router)
    dp.include_router(settings.router)
    dp.include_router(import_export.router)
    dp.include_router(menu.router)

    scheduler = await start_scheduler(bot)
    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
