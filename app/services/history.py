from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PR, Exercise, Set, Workout
from .progression import epley_1rm


def _tonnage(weight: float, reps: int) -> float:
    return weight * reps


def last_workout_summary(session: Session, user_id: int) -> Optional[Dict[str, str]]:
    workout = (
        session.query(Workout)
        .filter(Workout.user_id == user_id)
        .order_by(Workout.started_at.desc())
        .first()
    )
    if not workout:
        return None

    total_sets = session.query(func.count(Set.id)).filter(Set.workout_id == workout.id).scalar() or 0
    total_tonnage = (
        session.query(func.coalesce(func.sum(Set.weight * Set.reps), 0)).filter(Set.workout_id == workout.id).scalar()
        or 0.0
    )
    duration = None
    if workout.finished_at:
        duration_delta = workout.finished_at - workout.started_at
        duration = str(duration_delta).split(".")[0]

    return {
        "started_at": workout.started_at.isoformat(),
        "finished_at": workout.finished_at.isoformat() if workout.finished_at else "",
        "total_sets": str(total_sets),
        "tonnage": f"{total_tonnage:.1f}",
        "duration": duration or "",
    }


def volume_for_period(session: Session, user_id: int, days: int) -> float:
    since = datetime.utcnow() - timedelta(days=days)
    return (
        session.query(func.coalesce(func.sum(Set.weight * Set.reps), 0))
        .join(Workout, Workout.id == Set.workout_id)
        .filter(Workout.user_id == user_id, Workout.started_at >= since)
        .scalar()
        or 0.0
    )


def top_exercises_by_tonnage(session: Session, user_id: int, limit: int = 5) -> List[Tuple[str, float]]:
    rows = (
        session.query(Exercise.name, func.sum(Set.weight * Set.reps).label("tonnage"))
        .join(Set, Set.exercise_id == Exercise.id)
        .join(Workout, Workout.id == Set.workout_id)
        .filter(Workout.user_id == user_id)
        .group_by(Exercise.name)
        .order_by(func.sum(Set.weight * Set.reps).desc())
        .limit(limit)
        .all()
    )
    return [(row[0], float(row[1] or 0.0)) for row in rows]


def latest_prs(session: Session, user_id: int, limit: int = 5) -> List[Tuple[str, float, int, str]]:
    rows = (
        session.query(Exercise.name, PR.weight, PR.reps, PR.date)
        .join(Exercise, Exercise.id == PR.exercise_id)
        .filter(PR.user_id == user_id)
        .order_by(PR.date.desc())
        .limit(limit)
        .all()
    )
    return [(name, float(weight), int(reps), date.isoformat()) for name, weight, reps, date in rows]


def workout_detail(session: Session, workout_id: int) -> Optional[str]:
    workout = session.get(Workout, workout_id)
    if workout is None:
        return None

    sets = (
        session.query(Set)
        .filter(Set.workout_id == workout_id)
        .order_by(Set.exercise_id, Set.set_index)
        .all()
    )
    grouped: Dict[int, List[Set]] = defaultdict(list)
    for item in sets:
        grouped[item.exercise_id].append(item)

    lines = [f"Тренировка {workout.started_at:%Y-%m-%d %H:%M}"]
    for exercise_id, data in grouped.items():
        exercise = session.get(Exercise, exercise_id)
        name = exercise.name if exercise else "Упражнение"
        lines.append(f"\n{name}")
        for workout_set in data:
            lines.append(
                f"Сет {workout_set.set_index}: {workout_set.weight:.1f} × {workout_set.reps} (RIR={workout_set.rir or 0:.1f})"
            )
        best = max(epley_1rm(item.weight, item.reps) for item in data)
        lines.append(f"1RM по Эпли: {best:.1f}")

    return "\n".join(lines)
