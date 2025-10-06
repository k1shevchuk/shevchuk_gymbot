from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from aiogram import Bot

from .db import get_db
from .models import User

logger = logging.getLogger(__name__)


async def _load_users_with_reminders():
    db = get_db()

    def load(session):
        return session.query(User).filter(User.reminder_enabled.is_(True)).all()

    return await db.run(load)


async def send_reminder(bot: Bot, telegram_id: int) -> None:
    try:
        await bot.send_message(telegram_id, "Не забудьте про тренировку сегодня!")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to send reminder to %s: %s", telegram_id, exc)


async def start_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    users = await _load_users_with_reminders()
    for user in users:
        try:
            tz = ZoneInfo(user.tz)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("UTC")
        if user.reminder_weekday:
            trigger = CronTrigger(day_of_week="mon-fri", hour=int(user.reminder_weekday.split(":")[0]), minute=int(user.reminder_weekday.split(":")[1]), timezone=tz)
            scheduler.add_job(send_reminder, trigger, args=(bot, user.telegram_id), id=f"reminder-weekday-{user.id}")
        if user.reminder_weekend:
            trigger = CronTrigger(day_of_week="sat,sun", hour=int(user.reminder_weekend.split(":")[0]), minute=int(user.reminder_weekend.split(":")[1]), timezone=tz)
            scheduler.add_job(send_reminder, trigger, args=(bot, user.telegram_id), id=f"reminder-weekend-{user.id}")
    scheduler.start()
    return scheduler
