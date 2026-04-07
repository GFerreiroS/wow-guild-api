"""Add character_id to eventsignup table.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("eventsignup")}

    if "character_id" not in columns:
        with op.batch_alter_table("eventsignup") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "character_id",
                    sa.Integer(),
                    sa.ForeignKey("guildmember.character_id", ondelete="SET NULL"),
                    nullable=True,
                )
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("eventsignup")}

    if "character_id" in columns:
        with op.batch_alter_table("eventsignup") as batch_op:
            batch_op.drop_column("character_id")
