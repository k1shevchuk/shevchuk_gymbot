from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..models import PR, Set
from .progression import epley_1rm


def update_pr(session: Session, user_id: int, exercise_id: int) -> Optional[PR]:
    sets = (
        session.query(Set)
        .filter(Set.exercise_id == exercise_id)
        .order_by(desc(Set.weight * Set.reps))
        .limit(1)
        .all()
    )
    if not sets:
        return None

    best_set = sets[0]
    candidate_1rm = epley_1rm(best_set.weight, best_set.reps)

    existing = (
        session.query(PR)
        .filter(PR.user_id == user_id, PR.exercise_id == exercise_id)
        .order_by(PR.date.desc())
        .first()
    )

    if existing and epley_1rm(existing.weight, existing.reps) >= candidate_1rm:
        return existing

    new_pr = PR(
        user_id=user_id,
        exercise_id=exercise_id,
        date=date.today(),
        reps=best_set.reps,
        weight=best_set.weight,
    )
    session.add(new_pr)
    return new_pr
