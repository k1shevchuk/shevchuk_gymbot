"""Initial schema

Revision ID: 20240605_0001_init
Revises: 
Create Date: 2024-06-05 00:01:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240605_0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.Integer(), nullable=False),
        sa.Column("tz", sa.String(length=64), nullable=True, server_default="UTC"),
        sa.Column("units", sa.String(length=16), nullable=True, server_default="kg"),
        sa.Column("rir_format", sa.String(length=8), nullable=True, server_default="RIR"),
        sa.Column("reminder_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("reminder_weekday", sa.String(length=5), nullable=True),
        sa.Column("reminder_weekend", sa.String(length=5), nullable=True),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("muscle_group", sa.String(length=64), nullable=True),
        sa.UniqueConstraint("name", name="uq_exercise_name"),
    )

    op.create_table(
        "workouts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(length=512), nullable=True),
    )
    op.create_index("ix_workouts_user", "workouts", ["user_id"])

    op.create_table(
        "workout_exercises",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_sets", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("target_reps", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("target_rir", sa.Float(), nullable=True),
        sa.UniqueConstraint("workout_id", "exercise_id", name="uq_workout_exercise"),
    )

    op.create_table(
        "metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("bodyweight", sa.Float(), nullable=True),
        sa.Column("sleep_h", sa.Float(), nullable=True),
        sa.Column("calories", sa.Integer(), nullable=True),
    )
    op.create_index("ix_metrics_user_date", "metrics", ["user_id", "date"], unique=True)

    op.create_table(
        "prs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
    )
    op.create_index("ix_prs_user_exercise", "prs", ["user_id", "exercise_id"])

    op.create_table(
        "sets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workout_id", sa.Integer(), sa.ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("exercise_id", sa.Integer(), sa.ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False),
        sa.Column("set_index", sa.Integer(), nullable=False),
        sa.Column("reps", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("rir", sa.Float(), nullable=True),
        sa.Column("note", sa.String(length=256), nullable=True),
    )
    op.create_index("ix_sets_workout", "sets", ["workout_id"])


def downgrade() -> None:
    op.drop_index("ix_sets_workout", table_name="sets")
    op.drop_table("sets")
    op.drop_index("ix_prs_user_exercise", table_name="prs")
    op.drop_table("prs")
    op.drop_index("ix_metrics_user_date", table_name="metrics")
    op.drop_table("metrics")
    op.drop_table("workout_exercises")
    op.drop_index("ix_workouts_user", table_name="workouts")
    op.drop_table("workouts")
    op.drop_table("exercises")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
