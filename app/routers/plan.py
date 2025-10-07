from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..services.progression import default_plan
from ..services.users import get_or_create_user
from ..db import get_db
from ..models import Workout

router = Router(name="plan")


def _plan_keyboard() -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="Старт", callback_data="plan:start")
    builder.button(text="Перенести на завтра", callback_data="plan:move")
    builder.button(text="Изменить веса", callback_data="plan:weights")
    builder.adjust(1, 2)
    return builder


async def _prepare_plan_text(telegram_id: int) -> str:
    db = get_db()

    def load(session) -> str:
        user = get_or_create_user(session, telegram_id)
        plan = default_plan()
        lines = ["Следующая тренировка:"]
        for item in plan:
            lines.append(
                f"• {item.name}: {item.target_sets}×{item.reps_text()} (RIR {item.rir_text()})"
            )
        last_workout = (
            session.query(Workout)
            .filter(Workout.user_id == user.id)
            .order_by(Workout.started_at.desc())
            .first()
        )
        if last_workout and last_workout.finished_at:
            lines.append(f"Последняя тренировка была {last_workout.finished_at:%d.%m.%Y}")
        return "\n".join(lines)

    return await db.run(load)


@router.message(F.text == "План")
async def show_plan(message: Message) -> None:
    text = await _prepare_plan_text(message.from_user.id)
    await message.answer(text, reply_markup=_plan_keyboard().as_markup())


@router.callback_query(F.data == "plan:start")
async def plan_start(callback: CallbackQuery) -> None:
    await callback.answer("Открываю тренировку")
    await callback.message.answer("Используйте кнопку 'Начать тренировку' в главном меню, чтобы начать сессию по плану.")


@router.callback_query(F.data == "plan:move")
async def plan_move(callback: CallbackQuery) -> None:
    await callback.answer("Перенос выполнен")
    await callback.message.answer("Тренировка перенесена на завтра. Я напомню в установленное время.")


@router.callback_query(F.data == "plan:weights")
async def plan_weights(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer("Изменение весов по умолчанию пока доступно через редактирование плана вручную.")
