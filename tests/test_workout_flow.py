import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import pandas as pd
import pytest

# Configure environment for tests before importing app modules
TEST_DB_PATH = (Path(__file__).parent / "test.sqlite3").resolve()
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()

os.environ.setdefault("BOT_TOKEN", "TEST_TOKEN")
os.environ.setdefault("TZ", "UTC")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH}"

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Exercise, Set, User, Workout, WorkoutExercise  # noqa: E402
from app.routers.import_export import _import_dataframe  # noqa: E402
from app.routers.workout import (  # noqa: E402
    _ensure_aware_datetime,
    _ensure_workout,
    _finish_workout,
)


@pytest.fixture(autouse=True)
def _setup_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.mark.asyncio
async def test_finish_workout_summary_has_duration_and_1rm():
    with SessionLocal() as session:
        user = User(telegram_id=1)
        session.add(user)
        session.flush()
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        workout = Workout(
            user_id=user.id,
            started_at=start,
            finished_at=start + timedelta(hours=1),
            notes="Test",
        )
        session.add(workout)
        exercise = Exercise(name="Тестовое упражнение")
        session.add(exercise)
        session.flush()
        workout_set = Set(
            workout_id=workout.id,
            exercise_id=exercise.id,
            set_index=1,
            reps=5,
            weight=100.0,
            rir=1.0,
        )
        session.add(workout_set)
        session.commit()

    summary = await _finish_workout(workout.id)

    assert "Длительность: 1:00:00" in summary
    assert "1RM оценка" in summary


@pytest.mark.asyncio
async def test_import_dataframe_creates_timezone_aware_records():
    telegram_id = 42
    df = pd.DataFrame(
        [
            {
                "Date": "2024-05-01",
                "Workout": "Day A",
                "Exercise": "Squat",
                "Set": 1,
                "Reps": 5,
                "Weight": 100,
                "RIR": 2,
                "Notes": "",
            },
            {
                "Date": "2024-05-01",
                "Workout": "Day A",
                "Exercise": "Squat",
                "Set": 2,
                "Reps": 5,
                "Weight": 100,
                "RIR": 1,
                "Notes": "",
            },
        ]
    )

    workouts_count, sets_count = await _import_dataframe(telegram_id, df)

    assert workouts_count == 1
    assert sets_count == 2

    with SessionLocal() as session:
        workout = session.query(Workout).one()
        expected_start = datetime(2024, 5, 1, tzinfo=timezone.utc)
        aware_start = _ensure_aware_datetime(workout.started_at)
        assert aware_start == expected_start
        aware_finish = _ensure_aware_datetime(workout.finished_at)
        assert aware_finish is not None
        sets = session.query(Set).filter_by(workout_id=workout.id).all()
        assert len(sets) == 2
        assert all(s.rir is not None for s in sets)

    summary = await _finish_workout(workout.id)
    assert "Тренировка завершена!" in summary


@pytest.mark.asyncio
async def test_import_dataframe_respects_user_timezone():
    telegram_id = 77
    with SessionLocal() as session:
        user = User(telegram_id=telegram_id, tz="Europe/Moscow")
        session.add(user)
        session.commit()

    df = pd.DataFrame(
        [
            {
                "Date": "2024-06-01",
                "Workout": "Day B",
                "Exercise": "Bench",
                "Set": 1,
                "Reps": 8,
                "Weight": 80,
                "RIR": 2,
                "Notes": "",
            }
        ]
    )

    await _import_dataframe(telegram_id, df)

    with SessionLocal() as session:
        workout = session.query(Workout).one()
        aware_start = _ensure_aware_datetime(workout.started_at)
        assert aware_start == datetime(2024, 5, 31, 21, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_ensure_workout_creates_plan_with_timezone():
    result = await _ensure_workout(telegram_id=555)

    with SessionLocal() as session:
        workout = session.get(Workout, result["workout_id"])
        assert workout is not None
        assert _ensure_aware_datetime(workout.started_at).tzinfo is not None
        exercises = (
            session.query(WorkoutExercise)
            .filter(WorkoutExercise.workout_id == workout.id)
            .all()
        )
        assert len(exercises) > 0
