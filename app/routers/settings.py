from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db import get_db
from ..keyboards import reminder_toggle_keyboard
from ..models import User
from ..services.users import get_or_create_user
from ..states import SettingsState

router = Router(name="settings")


def _settings_keyboard(user: User):
    builder = InlineKeyboardBuilder()
    builder.button(text="Часовой пояс", callback_data="settings:timezone")
    builder.button(text="Единицы", callback_data="settings:units")
    builder.button(text="RIR/RPE", callback_data="settings:rir")
    builder.button(text="Напоминания", callback_data="settings:reminder")
    builder.adjust(2)
    return builder.as_markup()


async def _load_user(telegram_id: int) -> User:
    db = get_db()

    def load(session):
        return get_or_create_user(session, telegram_id)

    return await db.run(load)


async def _save_user(telegram_id: int, **updates) -> User:
    db = get_db()

    def save(session):
        user = get_or_create_user(session, telegram_id)
        for key, value in updates.items():
            setattr(user, key, value)
        return user

    return await db.run(save)


@router.message(F.text == "Настройки")
async def show_settings(message: Message, state: FSMContext) -> None:
    user = await _load_user(message.from_user.id)
    text = (
        "Текущие настройки:\n"
        f"Часовой пояс: {user.tz}\n"
        f"Единицы: {user.units}\n"
        f"Формат усилия: {user.rir_format}\n"
        f"Напоминания: {'включены' if user.reminder_enabled else 'выключены'}"
    )
    await message.answer(text, reply_markup=_settings_keyboard(user))
    await state.clear()


@router.callback_query(F.data == "settings:timezone")
async def ask_timezone(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Введите ваш часовой пояс в формате IANA (например, Europe/Moscow)")
    await state.set_state(SettingsState.choosing_timezone)


@router.message(SettingsState.choosing_timezone)
async def set_timezone(message: Message, state: FSMContext) -> None:
    tz_value = (message.text or "").strip()
    try:
        ZoneInfo(tz_value)
    except Exception:
        await message.answer("Некорректный часовой пояс. Попробуйте ещё раз.")
        return
    await _save_user(message.from_user.id, tz=tz_value)
    await message.answer(f"Часовой пояс обновлён на {tz_value}")
    await state.clear()


@router.callback_query(F.data == "settings:units")
async def ask_units(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Выберите единицы: кг или фунты")
    await state.set_state(SettingsState.choosing_units)


@router.message(SettingsState.choosing_units)
async def set_units(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().lower()
    if text not in {"кг", "kg", "фунты", "lb", "lbs"}:
        await message.answer("Допустимые варианты: кг или фунты")
        return
    units = "kg" if text in {"кг", "kg"} else "lb"
    await _save_user(message.from_user.id, units=units)
    await message.answer(f"Единицы измерения: {units}")
    await state.clear()


@router.callback_query(F.data == "settings:rir")
async def ask_rir_format(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Введите желаемый формат: RIR или RPE")
    await state.set_state(SettingsState.choosing_rir_format)


@router.message(SettingsState.choosing_rir_format)
async def set_rir_format(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip().upper()
    if text not in {"RIR", "RPE"}:
        await message.answer("Допустимые значения: RIR или RPE")
        return
    await _save_user(message.from_user.id, rir_format=text)
    await message.answer(f"Формат установлен: {text}")
    await state.clear()


@router.callback_query(F.data == "settings:reminder")
async def toggle_reminder_menu(callback: CallbackQuery) -> None:
    user = await _load_user(callback.from_user.id)
    await callback.answer()
    await callback.message.answer(
        "Управление напоминаниями:",
        reply_markup=reminder_toggle_keyboard(user.reminder_enabled),
    )


@router.callback_query(F.data == "settings:toggle_reminder")
async def toggle_reminder(callback: CallbackQuery) -> None:
    user = await _load_user(callback.from_user.id)
    updated = await _save_user(callback.from_user.id, reminder_enabled=not user.reminder_enabled)
    await callback.answer("Сохранено")
    await callback.message.edit_reply_markup(reminder_toggle_keyboard(updated.reminder_enabled))


def _validate_time(value: str) -> str:
    try:
        hour, minute = value.split(":")
        hour_i, minute_i = int(hour), int(minute)
        if not (0 <= hour_i < 24 and 0 <= minute_i < 60):
            raise ValueError
    except Exception as exc:  # noqa: BLE001
        raise ValueError from exc
    return f"{hour_i:02d}:{minute_i:02d}"


@router.callback_query(F.data == "settings:reminder_weekday")
async def ask_weekday(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Введите время напоминания в будни (HH:MM)")
    await state.set_state(SettingsState.editing_reminder_weekday)


@router.message(SettingsState.editing_reminder_weekday)
async def set_weekday(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    try:
        validated = _validate_time(value)
    except ValueError:
        await message.answer("Некорректное время. Используйте формат HH:MM")
        return
    await _save_user(message.from_user.id, reminder_weekday=validated)
    await message.answer(f"Будни: {validated}")
    await state.clear()


@router.callback_query(F.data == "settings:reminder_weekend")
async def ask_weekend(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Введите время напоминания в выходные (HH:MM)")
    await state.set_state(SettingsState.editing_reminder_weekend)


@router.message(SettingsState.editing_reminder_weekend)
async def set_weekend(message: Message, state: FSMContext) -> None:
    value = (message.text or "").strip()
    try:
        validated = _validate_time(value)
    except ValueError:
        await message.answer("Некорректное время. Используйте формат HH:MM")
        return
    await _save_user(message.from_user.id, reminder_weekend=validated)
    await message.answer(f"Выходные: {validated}")
    await state.clear()
