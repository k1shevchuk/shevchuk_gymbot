"""allow textual targets for workout exercises

Revision ID: 20240606_0002
Revises: 20240605_0001_init
Create Date: 2024-06-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240606_0002"
down_revision = "20240605_0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "workout_exercises",
        "target_reps",
        existing_type=sa.Integer(),
        nullable=True,
        existing_server_default=sa.text("8"),
    )
    op.add_column(
        "workout_exercises",
        sa.Column("target_reps_display", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "workout_exercises",
        sa.Column("target_rir_display", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workout_exercises", "target_rir_display")
    op.drop_column("workout_exercises", "target_reps_display")
    op.alter_column(
        "workout_exercises",
        "target_reps",
        existing_type=sa.Integer(),
        nullable=False,
        server_default=sa.text("8"),
    )
