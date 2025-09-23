"""Create event and event signup tables.

Revision ID: a1b2c3d4e5f6
Revises: f0e0168717ac
Create Date: 2025-07-04 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f0e0168717ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS_VALUES = ("Assist", "Late", "Tentative", "Absence")
STATUS_CHECK_NAME = "ck_eventsignup_status"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "event" not in inspector.get_table_names():
        op.create_table(
            "event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("title", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="CASCADE"),
        )

    if "eventsignup" not in inspector.get_table_names():
        op.create_table(
            "eventsignup",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("status", sa.String(), nullable=False, server_default="Assist"),
            sa.ForeignKeyConstraint(["event_id"], ["event.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.CheckConstraint(
                f"status IN ({', '.join(repr(v) for v in STATUS_VALUES)})",
                name=STATUS_CHECK_NAME,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "eventsignup" in inspector.get_table_names():
        op.drop_table("eventsignup")

    if "event" in inspector.get_table_names():
        op.drop_table("event")
