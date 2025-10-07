from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone
from tempfile import NamedTemporaryFile
from typing import Dict, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Document, Message
from aiogram.types.input_file import FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

from ..db import get_db
from ..models import Exercise, Set, Workout, WorkoutExercise
from ..services.users import get_or_create_user
from ..states import ImportState

router = Router(name="import_export")
logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = ["Date", "Workout", "Exercise", "Set", "Reps", "Weight", "RIR", "Notes"]


def _menu_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="Экспорт CSV", callback_data="export:csv")
    builder.button(text="Экспорт XLSX", callback_data="export:xlsx")
    builder.button(text="Импорт XLSX", callback_data="import:xlsx")
    builder.adjust(1)
    return builder.as_markup()


@router.message(F.text == "Экспорт/Импорт")
async def show_import_export(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Выберите действие:", reply_markup=_menu_keyboard())


async def _export_dataframe(telegram_id: int) -> pd.DataFrame:
    db = get_db()

    def fetch(session):
        user = get_or_create_user(session, telegram_id)
        rows = (
            session.query(Workout, Set, Exercise)
            .join(Set, Set.workout_id == Workout.id)
            .join(Exercise, Exercise.id == Set.exercise_id)
            .filter(Workout.user_id == user.id)
            .order_by(Workout.started_at, Set.exercise_id, Set.set_index)
            .all()
        )
        data = []
        for workout, workout_set, exercise in rows:
            data.append(
                {
                    "Date": workout.started_at.date().isoformat(),
                    "Workout": workout.notes or f"Workout {workout.id}",
                    "Exercise": exercise.name,
                    "Set": workout_set.set_index,
                    "Reps": workout_set.reps,
                    "Weight": workout_set.weight,
                    "RIR": workout_set.rir,
                    "Notes": workout_set.note or "",
                }
            )
        return pd.DataFrame(data, columns=REQUIRED_COLUMNS)

    return await db.run(fetch)


@router.callback_query(F.data == "export:csv")
async def export_csv(callback: CallbackQuery) -> None:
    df = await _export_dataframe(callback.from_user.id)
    if df.empty:
        await callback.answer("Нет данных для экспорта", show_alert=True)
        return
    with NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as tmp:
        df.to_csv(tmp.name, index=False)
        tmp.flush()
        await callback.message.answer_document(FSInputFile(tmp.name), caption="Экспорт тренировок (CSV)")
    await callback.answer()


@router.callback_query(F.data == "export:xlsx")
async def export_xlsx(callback: CallbackQuery) -> None:
    df = await _export_dataframe(callback.from_user.id)
    if df.empty:
        await callback.answer("Нет данных для экспорта", show_alert=True)
        return
    with NamedTemporaryFile("wb", suffix=".xlsx", delete=False) as tmp:
        df.to_excel(tmp.name, index=False)
        tmp.flush()
        await callback.message.answer_document(FSInputFile(tmp.name), caption="Экспорт тренировок (XLSX)")
    await callback.answer()


@router.callback_query(F.data == "import:xlsx")
async def import_xlsx_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await callback.message.answer("Отправьте XLSX-файл с колонками: " + ", ".join(REQUIRED_COLUMNS))
    await state.set_state(ImportState.waiting_for_file)


async def _import_dataframe(telegram_id: int, dataframe: pd.DataFrame) -> Tuple[int, int]:
    db = get_db()

    def persist(session):
        user = get_or_create_user(session, telegram_id)
        try:
            user_tz = ZoneInfo(user.tz or "UTC")
        except Exception:
            user_tz = timezone.utc
        workouts_cache: Dict[Tuple[str, str], Workout] = {}
        exercises_cache: Dict[str, Exercise] = {
            ex.name: ex for ex in session.query(Exercise).all()
        }
        inserted_workouts = 0
        inserted_sets = 0
        for _, row in dataframe.iterrows():
            date_value = pd.to_datetime(row["Date"]).to_pydatetime()
            if date_value.tzinfo is None:
                localized_start = datetime.combine(
                    date_value.date(),
                    time.min,
                    tzinfo=user_tz,
                )
            else:
                localized_start = date_value.astimezone(user_tz)
            start_utc = localized_start.astimezone(timezone.utc)
            workout_key = (row["Workout"], start_utc.strftime("%Y-%m-%d"))
            workout = workouts_cache.get(workout_key)
            if workout is None:
                workout = Workout(
                    user_id=user.id,
                    started_at=start_utc,
                    finished_at=start_utc + timedelta(hours=1),
                    notes=str(row["Workout"]),
                )
                session.add(workout)
                session.flush()
                workouts_cache[workout_key] = workout
                inserted_workouts += 1
            exercise_name = str(row["Exercise"]).strip()
            exercise = exercises_cache.get(exercise_name)
            if exercise is None:
                exercise = Exercise(name=exercise_name)
                session.add(exercise)
                session.flush()
                exercises_cache[exercise_name] = exercise
            workout_ex = (
                session.query(WorkoutExercise)
                .filter(WorkoutExercise.workout_id == workout.id, WorkoutExercise.exercise_id == exercise.id)
                .one_or_none()
            )
            if workout_ex is None:
                workout_ex = WorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=exercise.id,
                    target_sets=int(dataframe[dataframe["Exercise"] == exercise_name]["Set"].max()),
                    target_reps=int(row["Reps"]),
                    target_rir=float(row["RIR"]) if pd.notna(row["RIR"]) else None,
                )
                session.add(workout_ex)
                session.flush()
            new_set = Set(
                workout_id=workout.id,
                exercise_id=exercise.id,
                set_index=int(row["Set"]),
                reps=int(row["Reps"]),
                weight=float(row["Weight"]),
                rir=float(row["RIR"]) if pd.notna(row["RIR"]) else None,
                note=str(row["Notes"]) if pd.notna(row["Notes"]) else None,
            )
            session.add(new_set)
            inserted_sets += 1
        return inserted_workouts, inserted_sets

    return await db.run(persist)


@router.message(ImportState.waiting_for_file, F.document)
async def handle_import_file(message: Message, state: FSMContext) -> None:
    document: Document = message.document
    if not document.file_name.endswith(".xlsx"):
        await message.answer("Нужен XLSX-файл")
        return
    with NamedTemporaryFile(delete=False) as tmp:
        await message.bot.download(document, destination=tmp.name)
        df = pd.read_excel(tmp.name)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        await message.answer("Нет колонок: " + ", ".join(missing))
        return
    workouts, sets = await _import_dataframe(message.from_user.id, df)
    await message.answer(f"Импортировано тренировок: {workouts}, сетов: {sets}")
    await state.clear()


@router.message(ImportState.waiting_for_file)
async def handle_import_invalid(message: Message) -> None:
    await message.answer("Отправьте XLSX-файл")
