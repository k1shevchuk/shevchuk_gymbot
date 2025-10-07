from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..db import get_db
from ..keyboards import main_menu_keyboard
from ..services.users import get_or_create_user

router = Router(name="menu")
logger = logging.getLogger(__name__)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    db = get_db()
    telegram_id = message.from_user.id

    await db.run(lambda session: get_or_create_user(session, telegram_id))
    await message.answer(
        "Привет! Я помогу вести дневник тренировок. Выберите действие в меню.",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("menu"))
async def handle_menu(message: Message) -> None:
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


@router.message(F.text == "Главное меню")
async def handle_explicit_menu(message: Message) -> None:
    await message.answer("Возвращаю меню.", reply_markup=main_menu_keyboard())


@router.message()
async def handle_unknown(message: Message) -> None:
    await message.answer(
        "Не понял сообщение. Используйте меню для выбора действия.",
        reply_markup=main_menu_keyboard(),
    )
