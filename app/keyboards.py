from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

MAIN_MENU_BUTTONS = [
    "Начать тренировку",
    "Сводка",
    "План",
    "Мои рекорды",
    "История",
    "Настройки",
    "Экспорт/Импорт",
]


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    for text in MAIN_MENU_BUTTONS:
        builder.button(text=text)
    builder.adjust(3, 4)
    return builder.as_markup(resize_keyboard=True, input_field_placeholder="Выберите действие")


def workout_control_keyboard(exercise_id: int, has_prev: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Ввести данные", callback_data=f"workout:set:{exercise_id}")
    builder.button(text="Закончить упражнение", callback_data=f"workout:finish_ex:{exercise_id}")
    builder.button(text="Пропустить", callback_data=f"workout:skip:{exercise_id}")
    if has_prev:
        builder.button(text="Назад", callback_data="workout:back")
    builder.adjust(2, 2)
    return builder.as_markup()


def set_entry_keyboard(exercise_id: int, set_index: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Следующий сет", callback_data=f"workout:next_set:{exercise_id}:{set_index}")
    builder.button(text="Закончить упражнение", callback_data=f"workout:finish_ex:{exercise_id}")
    return builder.as_markup()


def finish_workout_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Завершить тренировку", callback_data="workout:complete")
    return builder.as_markup()


def summary_navigation_keyboard(offset: int, has_next: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if offset > 0:
        builder.button(text="Назад", callback_data=f"summary:page:{max(offset-5,0)}")
    if has_next:
        builder.button(text="Вперёд", callback_data=f"summary:page:{offset+5}")
    return builder.as_markup()


def history_keyboard(workout_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Открыть тренировку", callback_data=f"history:detail:{workout_id}")
    return builder.as_markup()


def reminder_toggle_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="Включить" if not enabled else "Выключить", callback_data="settings:toggle_reminder")
    builder.button(text="Будни", callback_data="settings:reminder_weekday")
    builder.button(text="Выходные", callback_data="settings:reminder_weekend")
    builder.adjust(1, 2)
    return builder.as_markup()
