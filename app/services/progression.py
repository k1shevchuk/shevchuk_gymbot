from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy.orm import Session

from ..models import Exercise, Set, Workout, WorkoutExercise


@dataclass
class PlanExercise:
    name: str
    target_sets: int
    target_reps: Optional[int]
    target_rir: Optional[float]
    target_reps_display: Optional[str] = None
    target_rir_display: Optional[str] = None
    muscle_group: Optional[str] = None

    def reps_text(self) -> str:
        if self.target_reps_display:
            return self.target_reps_display
        if self.target_reps is None:
            return "-"
        return str(self.target_reps)

    def rir_text(self) -> str:
        if self.target_rir_display:
            return self.target_rir_display
        if self.target_rir is None:
            return "-"
        return f"{self.target_rir:g}"


DEFAULT_PLAN: List[PlanExercise] = [
    PlanExercise(name="Присед со штангой", target_sets=4, target_reps=6, target_rir=2.0, muscle_group="Ноги"),
    PlanExercise(name="Жим лёжа", target_sets=4, target_reps=6, target_rir=1.5, muscle_group="Грудь"),
    PlanExercise(name="Тяга верхнего блока", target_sets=3, target_reps=10, target_rir=2.5, muscle_group="Спина"),
]


def epley_1rm(weight: float, reps: int) -> float:
    if reps <= 1:
        return float(weight)
    return float(weight * (1 + reps / 30))


def suggest_next_weight(last_weight: Optional[float], achieved_rir: Optional[float], target_rir: Optional[float]) -> float:
    if last_weight is None:
        return 20.0
    adjustment = 0.0
    if achieved_rir is not None and target_rir is not None:
        delta = target_rir - achieved_rir
        adjustment = delta * 2.5
    return max(0.0, last_weight + adjustment)


def ensure_plan_for_workout(session: Session, workout: Workout, plan: Iterable[PlanExercise]) -> None:
    existing_ids = {we.exercise.name for we in workout.exercises}
    for item in plan:
        if item.name in existing_ids:
            continue
        exercise = session.query(Exercise).filter_by(name=item.name).one_or_none()
        if exercise is None:
            exercise = Exercise(name=item.name, muscle_group=item.muscle_group)
            session.add(exercise)
            session.flush()
        workout_exercise = WorkoutExercise(
            workout_id=workout.id,
            exercise_id=exercise.id,
            target_sets=item.target_sets,
            target_reps=item.target_reps,
            target_reps_display=item.target_reps_display
            or (str(item.target_reps) if item.target_reps is not None else None),
            target_rir=item.target_rir,
            target_rir_display=item.target_rir_display
            or (f"{item.target_rir:g}" if item.target_rir is not None else None),
        )
        session.add(workout_exercise)


def calculate_workout_1rm_summary(session: Session, workout: Workout) -> float:
    best_1rm = 0.0
    for workout_set in session.query(Set).filter_by(workout_id=workout.id).all():
        best_1rm = max(best_1rm, epley_1rm(workout_set.weight, workout_set.reps))
    return best_1rm


def default_plan() -> List[PlanExercise]:
    return list(DEFAULT_PLAN)
