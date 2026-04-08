"""Add guild_settings table and instance_blizzard_id to event.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "guildsettings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("raid_start", sa.String(), nullable=False, server_default="20:00"),
        sa.Column("raid_end", sa.String(), nullable=False, server_default="23:00"),
    )
    # Seed the single settings row
    op.execute("INSERT INTO guildsettings (id, raid_start, raid_end) VALUES (1, '20:00', '23:00')")

    with op.batch_alter_table("event") as batch_op:
        batch_op.add_column(
            sa.Column("instance_blizzard_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_event_instance_blizzard_id",
            "instance",
            ["instance_blizzard_id"],
            ["blizzard_id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("event") as batch_op:
        batch_op.drop_constraint("fk_event_instance_blizzard_id", type_="foreignkey")
        batch_op.drop_column("instance_blizzard_id")
    op.drop_table("guildsettings")
