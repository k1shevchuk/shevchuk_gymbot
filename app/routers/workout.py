from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from ..db import get_db
from ..keyboards import finish_workout_keyboard, set_entry_keyboard, workout_control_keyboard
from ..models import Exercise, Set, Workout, WorkoutExercise
from ..services.progression import default_plan, ensure_plan_for_workout, epley_1rm
from ..services.prs import update_pr
from ..services.users import get_or_create_user
from ..states import EnterSetData, WorkoutNavigation

router = Router(name="workout")
logger = logging.getLogger(__name__)


@dataclass
class ExerciseCard:
    workout_id: int
    exercise_id: int
    exercise_name: str
    target_sets: int
    target_reps: int
    target_rir: Optional[float]
    completed_sets: int
    last_result: Optional[str]


async def _ensure_workout(telegram_id: int) -> Dict[str, int]:
    db = get_db()

    def create_workout(session) -> Dict[str, int]:
        user = get_or_create_user(session, telegram_id)
        workout = (
            session.query(Workout)
            .filter(Workout.user_id == user.id, Workout.finished_at.is_(None))
            .order_by(Workout.started_at.desc())
            .first()
        )
        if workout is None:
            workout = Workout(user_id=user.id, started_at=datetime.utcnow())
            session.add(workout)
            session.flush()
        ensure_plan_for_workout(session, workout, default_plan())
        session.flush()
        first_exercise = (
            session.query(WorkoutExercise)
            .filter(WorkoutExercise.workout_id == workout.id)
            .order_by(WorkoutExercise.id)
            .first()
        )
        return {"workout_id": workout.id, "exercise_id": first_exercise.exercise_id if first_exercise else 0}

    return await db.run(create_workout)


async def _load_exercise_card(workout_id: int, exercise_id: int) -> Optional[ExerciseCard]:
    db = get_db()

    def load(session) -> Optional[ExerciseCard]:
        workout = session.get(Workout, workout_id)
        if workout is None:
            return None
        workout_ex = (
            session.query(WorkoutExercise)
            .filter(WorkoutExercise.workout_id == workout_id, WorkoutExercise.exercise_id == exercise_id)
            .one_or_none()
        )
        if workout_ex is None:
            return None
        exercise = session.get(Exercise, exercise_id)
        completed_sets = (
            session.query(Set)
            .filter(Set.workout_id == workout_id, Set.exercise_id == exercise_id)
            .count()
        )
        last_workout = (
            session.query(Workout)
            .join(Set, Set.workout_id == Workout.id)
            .filter(
                Workout.user_id == workout.user_id,
                Set.exercise_id == exercise_id,
                Workout.id != workout_id,
                Workout.finished_at.isnot(None),
            )
            .order_by(Workout.finished_at.desc())
            .first()
        )
        last_result: Optional[str] = None
        if last_workout:
            sets = (
                session.query(Set)
                .filter(Set.workout_id == last_workout.id, Set.exercise_id == exercise_id)
                .order_by(Set.set_index)
                .all()
            )
            sets_str = ", ".join(f"{s.weight:.1f}×{s.reps}" for s in sets)
            avg_rir = sum((s.rir or 0) for s in sets) / len(sets) if sets else 0
            last_result = f"{last_workout.started_at:%d.%m.%Y}: {sets_str} (RIR {avg_rir:.1f})"
        return ExerciseCard(
            workout_id=workout_id,
            exercise_id=exercise_id,
            exercise_name=exercise.name if exercise else "Упражнение",
            target_sets=workout_ex.target_sets,
            target_reps=workout_ex.target_reps,
            target_rir=workout_ex.target_rir,
            completed_sets=completed_sets,
            last_result=last_result,
        )

    return await db.run(load)


async def _find_next_exercise(workout_id: int, completed: List[int]) -> Optional[int]:
    db = get_db()

    def select_next(session) -> Optional[int]:
        exercises = (
            session.query(WorkoutExercise)
            .filter(WorkoutExercise.workout_id == workout_id)
            .order_by(WorkoutExercise.id)
            .all()
        )
        for item in exercises:
            if item.exercise_id not in completed:
                return item.exercise_id
        return None

    return await db.run(select_next)


async def _count_sets(workout_id: int, exercise_id: int) -> int:
    db = get_db()

    def count(session) -> int:
        return (
            session.query(Set)
            .filter(Set.workout_id == workout_id, Set.exercise_id == exercise_id)
            .count()
        )

    return await db.run(count)


async def _save_set(
    workout_id: int,
    exercise_id: int,
    set_index: int,
    reps: int,
    weight: float,
    rir: float,
) -> Dict[str, float]:
    db = get_db()

    from sqlalchemy import func

    def save(session):
        workout = session.get(Workout, workout_id)
        if workout is None:
            raise ValueError("Workout not found")
        new_set = Set(
            workout_id=workout_id,
            exercise_id=exercise_id,
            set_index=set_index,
            reps=reps,
            weight=weight,
            rir=rir,
        )
        session.add(new_set)
        session.flush()
        update_pr(session, workout.user_id, exercise_id)
        tonnage_rows = (
            session.query(Set)
            .filter(Set.workout_id == workout_id, Set.exercise_id == exercise_id)
            .with_entities(Set.weight * Set.reps)
            .all()
        )
        total_tonnage = sum(value[0] for value in tonnage_rows)
        sets_done = len(tonnage_rows)
        avg_rir = (
            session.query(func.avg(Set.rir))
            .filter(Set.workout_id == workout_id, Set.exercise_id == exercise_id)
            .scalar()
        )
        return {"tonnage": total_tonnage, "sets": sets_done, "avg_rir": float(avg_rir or 0.0)}

    return await db.run(save)


async def _finish_workout(workout_id: int) -> str:
    db = get_db()

    def finalize(session) -> str:
        workout = session.get(Workout, workout_id)
        if workout is None:
            raise ValueError("Workout not found")
        if workout.finished_at is None:
            workout.finished_at = datetime.utcnow()
        sets = (
            session.query(Set)
            .filter(Set.workout_id == workout_id)
            .order_by(Set.exercise_id, Set.set_index)
            .all()
        )
        total_tonnage = sum(item.weight * item.reps for item in sets)
        per_exercise: Dict[int, List[Set]] = defaultdict(list)
        for item in sets:
            per_exercise[item.exercise_id].append(item)

        lines: List[str] = [
            f"Тренировка завершена!",
            f"Начало: {workout.started_at:%d.%m.%Y %H:%M}",
            f"Завершено: {workout.finished_at:%d.%m.%Y %H:%M}",
            f"Тоннаж: {total_tonnage:.1f}",
        ]
        duration = workout.finished_at - workout.started_at
        lines.append(f"Длительность: {duration}")

        for exercise_id, exercise_sets in per_exercise.items():
            exercise = session.get(Exercise, exercise_id)
            name = exercise.name if exercise else "Упражнение"
            lines.append(f"\n{name}")
            best_1rm = 0.0
            for workout_set in exercise_sets:
                lines.append(
                    f"Сет {workout_set.set_index}: {workout_set.weight:.1f} × {workout_set.reps} (RIR={workout_set.rir or 0:.1f})"
                )
                best_1rm = max(best_1rm, epley_1rm(workout_set.weight, workout_set.reps))
            lines.append(f"1RM оценка: {best_1rm:.1f}")
        return "\n".join(lines)

    return await db.run(finalize)


async def _render_and_send_card(message: Message, state: FSMContext, workout_id: int, exercise_id: Optional[int]) -> None:
    if exercise_id is None:
        await message.answer("Все упражнения завершены. Готовы подвести итог?", reply_markup=finish_workout_keyboard())
        await state.update_data(current_exercise=None)
        return

    card = await _load_exercise_card(workout_id, exercise_id)
    if card is None:
        await message.answer("Не удалось загрузить упражнение.")
        return

    data = await state.get_data()
    completed = data.get("completed", [])
    await state.update_data(current_exercise=exercise_id)
    last_line = f"\nПрошлый раз: {card.last_result}" if card.last_result else ""
    text = (
        f"{card.exercise_name}\n"
        f"План: {card.target_sets}×{card.target_reps} (RIR {card.target_rir if card.target_rir is not None else '-'})\n"
        f"Сделано сетов: {card.completed_sets}{last_line}"
    )
    await message.answer(text, reply_markup=workout_control_keyboard(card.exercise_id, has_prev=bool(completed)))


@router.message(F.text == "Начать тренировку")
async def start_workout(message: Message, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    creation = await _ensure_workout(telegram_id)
    workout_id = creation["workout_id"]
    first_exercise_id = creation.get("exercise_id") or None
    await state.update_data(workout_id=workout_id, completed=[])
    await message.answer("Запускаем тренировку!")
    await _render_and_send_card(message, state, workout_id, first_exercise_id)
    await state.set_state(WorkoutNavigation.awaiting_action)


@router.callback_query(F.data.startswith("workout:set:"))
async def prompt_set_entry(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    if not workout_id:
        await callback.answer("Нет активной тренировки", show_alert=True)
        return
    exercise_id = int(callback.data.split(":")[2])
    set_index = await _count_sets(workout_id, exercise_id) + 1
    await state.update_data(pending_exercise=exercise_id, pending_set_index=set_index)
    await callback.answer()
    await callback.message.answer(f"Введите вес для сета №{set_index}")
    await state.set_state(EnterSetData.weight)


@router.message(EnterSetData.weight)
async def handle_weight(message: Message, state: FSMContext) -> None:
    try:
        weight = float((message.text or "").replace(",", "."))
    except ValueError:
        await message.answer("Введите число в диапазоне 0-1000")
        return
    if not 0 <= weight <= 1000:
        await message.answer("Вес должен быть от 0 до 1000")
        return
    await state.update_data(weight=weight)
    await message.answer("Теперь количество повторов (1-100)")
    await state.set_state(EnterSetData.reps)


@router.message(EnterSetData.reps)
async def handle_reps(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("Введите целое число от 1 до 100")
        return
    reps = int(text)
    if not 1 <= reps <= 100:
        await message.answer("Введите целое число от 1 до 100")
        return
    await state.update_data(reps=reps)
    await message.answer("RIR (0-10, допускаются десятичные)")
    await state.set_state(EnterSetData.rir)


@router.message(EnterSetData.rir)
async def handle_rir(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        rir = float(text.replace(",", "."))
    except ValueError:
        await message.answer("Введите значение от 0 до 10")
        return
    if not 0 <= rir <= 10:
        await message.answer("Введите значение от 0 до 10")
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    exercise_id = data.get("pending_exercise")
    set_index = data.get("pending_set_index")
    reps = data.get("reps")
    weight = data.get("weight")
    if not all([workout_id, exercise_id, set_index, reps, weight]):
        await message.answer("Не удалось сохранить сет, попробуйте ещё раз")
        await state.set_state(WorkoutNavigation.awaiting_action)
        return
    stats = await _save_set(workout_id, exercise_id, set_index, reps, weight, rir)
    await message.answer(
        (
            f"Сет сохранён: {weight:.1f} × {reps} (RIR {rir:.1f}).\n"
            f"Всего сетов: {stats['sets']} | Тоннаж: {stats['tonnage']:.1f} | Средний RIR: {stats['avg_rir']:.1f}"
        ),
        reply_markup=set_entry_keyboard(exercise_id, stats["sets"] + 1),
    )
    await state.update_data(weight=None, reps=None, pending_exercise=exercise_id, pending_set_index=stats["sets"] + 1)
    await state.set_state(WorkoutNavigation.awaiting_action)


@router.callback_query(F.data.startswith("workout:next_set:"))
async def handle_next_set(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    if not workout_id:
        await callback.answer("Нет активной тренировки", show_alert=True)
        return
    exercise_id = int(callback.data.split(":")[2])
    set_index = await _count_sets(workout_id, exercise_id) + 1
    await state.update_data(pending_exercise=exercise_id, pending_set_index=set_index)
    await callback.answer()
    await callback.message.answer(f"Введите вес для сета №{set_index}")
    await state.set_state(EnterSetData.weight)


@router.callback_query(F.data.startswith("workout:finish_ex:"))
async def finish_exercise(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    completed = data.get("completed", [])
    exercise_id = int(callback.data.split(":")[2])
    if exercise_id not in completed:
        completed.append(exercise_id)
    await state.update_data(completed=completed)
    await callback.answer("Упражнение завершено")
    next_exercise = await _find_next_exercise(workout_id, completed)
    await _render_and_send_card(callback.message, state, workout_id, next_exercise)


@router.callback_query(F.data.startswith("workout:skip:"))
async def skip_exercise(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    completed = data.get("completed", [])
    exercise_id = int(callback.data.split(":")[2])
    if exercise_id not in completed:
        completed.append(exercise_id)
    await state.update_data(completed=completed)
    await callback.answer("Упражнение пропущено")
    next_exercise = await _find_next_exercise(workout_id, completed)
    await _render_and_send_card(callback.message, state, workout_id, next_exercise)


@router.callback_query(F.data == "workout:back")
async def go_back(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    completed = data.get("completed", [])
    if completed:
        exercise_id = completed.pop()
    else:
        exercise_id = data.get("current_exercise")
    await state.update_data(completed=completed)
    await callback.answer()
    await _render_and_send_card(callback.message, state, workout_id, exercise_id)


@router.callback_query(F.data == "workout:complete")
async def complete_workout(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    workout_id = data.get("workout_id")
    await callback.answer()
    summary = await _finish_workout(workout_id)
    await callback.message.answer(summary)
    await state.clear()
