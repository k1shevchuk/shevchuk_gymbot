from __future__ import annotations

from typing import List

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db import get_db
from ..models import Workout
from ..services.history import (
    last_workout_summary,
    latest_prs,
    top_exercises_by_tonnage,
    volume_for_period,
    workout_detail,
)
from ..services.users import get_or_create_user

router = Router(name="summary")


def _history_keyboard(items: List[Workout], offset: int, has_next: bool):
    builder = InlineKeyboardBuilder()
    for workout in items:
        builder.button(
            text=workout.started_at.strftime("%d.%m"),
            callback_data=f"history:detail:{workout.id}",
        )
    if offset > 0:
        builder.button(text="« Назад", callback_data=f"summary:page:{max(offset-5,0)}")
    if has_next:
        builder.button(text="Вперёд »", callback_data=f"summary:page:{offset+5}")
    builder.adjust(2)
    return builder.as_markup()


async def _build_summary(telegram_id: int) -> str:
    db = get_db()

    def build(session) -> str:
        user = get_or_create_user(session, telegram_id)
        parts: List[str] = ["Сводка"]
        last = last_workout_summary(session, user.id)
        if last:
            parts.append(
                f"Последняя тренировка: {last['started_at']}\n"
                f"Сеты: {last['total_sets']} | Тоннаж: {last['tonnage']} | Длительность: {last['duration']}"
            )
        week_volume = volume_for_period(session, user.id, 7)
        month_volume = volume_for_period(session, user.id, 28)
        parts.append(f"Объём за 7 дней: {week_volume:.1f}")
        parts.append(f"Объём за 28 дней: {month_volume:.1f}")
        top = top_exercises_by_tonnage(session, user.id)
        if top:
            parts.append("\nТоп упражнений по тоннажу:")
            for name, tonnage in top:
                parts.append(f"• {name}: {tonnage:.1f}")
        prs = latest_prs(session, user.id)
        if prs:
            parts.append("\nПоследние PR:")
            for name, weight, reps, date in prs:
                parts.append(f"• {name}: {weight:.1f} × {reps} ({date})")
        return "\n".join(parts)

    return await db.run(build)


async def _list_workouts(telegram_id: int, offset: int = 0, limit: int = 5):
    db = get_db()

    def fetch(session):
        user = get_or_create_user(session, telegram_id)
        query = (
            session.query(Workout)
            .filter(Workout.user_id == user.id)
            .order_by(Workout.started_at.desc())
        )
        total = query.count()
        items = query.offset(offset).limit(limit).all()
        return user.id, total, items

    return await db.run(fetch)


@router.message(F.text == "Сводка")
async def handle_summary(message: Message) -> None:
    summary = await _build_summary(message.from_user.id)
    await message.answer(summary)


@router.message(F.text == "История")
async def handle_history(message: Message) -> None:
    _, total, items = await _list_workouts(message.from_user.id, offset=0)
    if not items:
        await message.answer("Пока нет сохранённых тренировок")
        return
    lines = ["История тренировок:"]
    for workout in items:
        finished = workout.finished_at.strftime("%d.%m.%Y %H:%M") if workout.finished_at else "в процессе"
        lines.append(f"• {workout.started_at:%d.%m.%Y %H:%M} — {finished}")
    has_next = total > len(items)
    await message.answer("\n".join(lines), reply_markup=_history_keyboard(items, 0, has_next))


@router.callback_query(F.data.startswith("summary:page:"))
async def paginate_history(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    offset = int(callback.data.split(":")[2])
    _, total, items = await _list_workouts(callback.from_user.id, offset=offset)
    if not items:
        await callback.answer("Нет данных")
        return
    lines = ["История тренировок:"]
    for workout in items:
        finished = workout.finished_at.strftime("%d.%m.%Y %H:%M") if workout.finished_at else "в процессе"
        lines.append(f"• {workout.started_at:%d.%m.%Y %H:%M} — {finished}")
    has_next = total > offset + len(items)
    await callback.message.edit_text("\n".join(lines), reply_markup=_history_keyboard(items, offset, has_next))
    await callback.answer()


@router.callback_query(F.data.startswith("history:detail:"))
async def show_history_detail(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    workout_id = int(callback.data.split(":")[2])
    db = get_db()

    def load(session):
        return workout_detail(session, workout_id)

    detail = await db.run(load)
    if detail:
        await callback.message.answer(detail)
    else:
        await callback.message.answer("Тренировка не найдена")
    await callback.answer()
