"""Add BNet OAuth fields to user table.

Revision ID: d4e5f6a7b8c9
Revises: c3e7f1a2b8d4
Create Date: 2026-04-07 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3e7f1a2b8d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {col["name"] for col in inspector.get_columns("user")}

    with op.batch_alter_table("user") as batch_op:
        # Make password nullable (BNet users have no password)
        if "password" in columns:
            batch_op.alter_column("password", nullable=True)

        if "bnet_id" not in columns:
            batch_op.add_column(sa.Column("bnet_id", sa.String(), nullable=True))

        if "bnet_battletag" not in columns:
            batch_op.add_column(sa.Column("bnet_battletag", sa.String(), nullable=True))

        if "primary_character_id" not in columns:
            batch_op.add_column(
                sa.Column(
                    "primary_character_id",
                    sa.Integer(),
                    sa.ForeignKey("guildmember.character_id", ondelete="SET NULL"),
                    nullable=True,
                )
            )

    # Add unique index on bnet_id if it doesn't exist
    indexes = {idx["name"] for idx in inspector.get_indexes("user")}
    if "ix_user_bnet_id" not in indexes:
        op.create_index("ix_user_bnet_id", "user", ["bnet_id"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("user")}

    if "ix_user_bnet_id" in indexes:
        op.drop_index("ix_user_bnet_id", table_name="user")

    with op.batch_alter_table("user") as batch_op:
        columns = {col["name"] for col in inspector.get_columns("user")}
        if "primary_character_id" in columns:
            batch_op.drop_column("primary_character_id")
        if "bnet_battletag" in columns:
            batch_op.drop_column("bnet_battletag")
        if "bnet_id" in columns:
            batch_op.drop_column("bnet_id")
        if "password" in columns:
            batch_op.alter_column("password", nullable=False)
