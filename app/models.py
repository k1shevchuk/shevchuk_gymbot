from __future__ import annotations

from datetime import datetime, date
from typing import List, Optional

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    tz: Mapped[str] = mapped_column(String(64), default="UTC")
    units: Mapped[str] = mapped_column(String(16), default="kg")
    rir_format: Mapped[str] = mapped_column(String(8), default="RIR")
    reminder_enabled: Mapped[bool] = mapped_column(default=False)
    reminder_weekday: Mapped[Optional[str]] = mapped_column(String(5))
    reminder_weekend: Mapped[Optional[str]] = mapped_column(String(5))

    workouts: Mapped[List["Workout"]] = relationship(
        "Workout", back_populates="user", cascade="all, delete-orphan"
    )
    metrics: Mapped[List["Metric"]] = relationship(
        "Metric", back_populates="user", cascade="all, delete-orphan"
    )
    prs: Mapped[List["PR"]] = relationship("PR", back_populates="user", cascade="all, delete-orphan")


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    muscle_group: Mapped[Optional[str]] = mapped_column(String(64))

    workout_exercises: Mapped[List["WorkoutExercise"]] = relationship("WorkoutExercise", back_populates="exercise")
    sets: Mapped[List["Set"]] = relationship("Set", back_populates="exercise")
    prs: Mapped[List["PR"]] = relationship("PR", back_populates="exercise")


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(String(512))

    user: Mapped[User] = relationship("User", back_populates="workouts")
    exercises: Mapped[List["WorkoutExercise"]] = relationship(
        "WorkoutExercise", back_populates="workout", cascade="all, delete-orphan"
    )
    sets: Mapped[List["Set"]] = relationship("Set", back_populates="workout", cascade="all, delete-orphan")


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    target_sets: Mapped[int] = mapped_column(Integer, default=3)
    target_reps: Mapped[int] = mapped_column(Integer, default=8)
    target_rir: Mapped[Optional[float]] = mapped_column(Float)

    workout: Mapped[Workout] = relationship("Workout", back_populates="exercises")
    exercise: Mapped[Exercise] = relationship("Exercise", back_populates="workout_exercises")

    __table_args__ = (UniqueConstraint("workout_id", "exercise_id", name="uq_workout_exercise"),)


class Set(Base):
    __tablename__ = "sets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workout_id: Mapped[int] = mapped_column(ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    set_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)
    rir: Mapped[Optional[float]] = mapped_column(Float)
    note: Mapped[Optional[str]] = mapped_column(String(256))

    workout: Mapped[Workout] = relationship("Workout", back_populates="sets")
    exercise: Mapped[Exercise] = relationship("Exercise", back_populates="sets")

    __table_args__ = (Index("ix_sets_workout", "workout_id"),)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    bodyweight: Mapped[Optional[float]] = mapped_column(Float)
    sleep_h: Mapped[Optional[float]] = mapped_column(Float)
    calories: Mapped[Optional[int]] = mapped_column(Integer)

    user: Mapped[User] = relationship("User", back_populates="metrics")

    __table_args__ = (Index("ix_metrics_user_date", "user_id", "date", unique=True),)


class PR(Base):
    __tablename__ = "prs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    weight: Mapped[float] = mapped_column(Float, nullable=False)

    user: Mapped[User] = relationship("User", back_populates="prs")
    exercise: Mapped[Exercise] = relationship("Exercise", back_populates="prs")

    __table_args__ = (Index("ix_prs_user_exercise", "user_id", "exercise_id"),)
