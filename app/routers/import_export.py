from __future__ import annotations

import logging
import re
from datetime import datetime, time, timedelta, timezone
from tempfile import NamedTemporaryFile
from typing import Dict, Optional, Tuple
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


def _clean_cell(value) -> Optional[str]:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    return text


def _normalize(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return text.replace("\u2013", "-").replace("\u2212", "-")


def _first_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    normalized = _normalize(text)
    if not normalized:
        return None
    match = re.search(r"\d+", normalized)
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:
        return None


def _pure_int(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    normalized = _normalize(text)
    if normalized and re.fullmatch(r"\d+", normalized):
        try:
            return int(normalized)
        except ValueError:
            return None
    return None


def _first_float(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    normalized = _normalize(text)
    if not normalized:
        return None
    match = re.search(r"\d+(?:[.,]\d+)?", normalized)
    if not match:
        return None
    try:
        return float(match.group().replace(",", "."))
    except ValueError:
        return None


def _to_float(value) -> Optional[float]:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = _clean_cell(value)
    if cleaned is None:
        return None
    return _first_float(cleaned)


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
        max_sets_cache: Dict[str, Optional[int]] = {}
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
            reps_text = _clean_cell(row["Reps"])
            rir_text = _clean_cell(row["RIR"])
            notes_text = _clean_cell(row["Notes"])
            set_text = _clean_cell(row["Set"])
            if exercise_name not in max_sets_cache:
                exercise_sets = []
                for value in dataframe[dataframe["Exercise"].astype(str).str.strip() == exercise_name]["Set"]:
                    exercise_sets.append(_first_int(_clean_cell(value)))
                max_sets_cache[exercise_name] = (
                    max((v for v in exercise_sets if v is not None), default=None)
                )
            target_sets_value = max_sets_cache.get(exercise_name) or 0
            target_reps_value = _first_int(reps_text)
            target_rir_value = _first_float(rir_text)
            workout_ex = (
                session.query(WorkoutExercise)
                .filter(WorkoutExercise.workout_id == workout.id, WorkoutExercise.exercise_id == exercise.id)
                .one_or_none()
            )
            if workout_ex is None:
                workout_ex = WorkoutExercise(
                    workout_id=workout.id,
                    exercise_id=exercise.id,
                    target_sets=target_sets_value,
                    target_reps=target_reps_value,
                    target_reps_display=reps_text,
                    target_rir=target_rir_value,
                    target_rir_display=rir_text,
                )
                session.add(workout_ex)
                session.flush()
            else:
                if target_sets_value:
                    workout_ex.target_sets = target_sets_value
                if target_reps_value is not None:
                    workout_ex.target_reps = target_reps_value
                if reps_text:
                    workout_ex.target_reps_display = reps_text
                if target_rir_value is not None:
                    workout_ex.target_rir = target_rir_value
                if rir_text:
                    workout_ex.target_rir_display = rir_text
            set_index_value = _pure_int(set_text)
            reps_value = _pure_int(reps_text)
            weight_value = _to_float(row["Weight"])
            rir_value = _first_float(rir_text)
            if set_index_value is not None and reps_value is not None:
                new_set = Set(
                    workout_id=workout.id,
                    exercise_id=exercise.id,
                    set_index=set_index_value,
                    reps=reps_value,
                    weight=weight_value if weight_value is not None else 0.0,
                    rir=rir_value,
                    note=notes_text,
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
