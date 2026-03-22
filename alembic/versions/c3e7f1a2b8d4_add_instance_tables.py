"""Add expansion, instance and encounter tables.

Revision ID: c3e7f1a2b8d4
Revises: a1b2c3d4e5f6
Create Date: 2026-03-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3e7f1a2b8d4"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "expansion" not in tables:
        op.create_table(
            "expansion",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
        )
        op.create_index("ix_expansion_name", "expansion", ["name"], unique=True)

    if "instance" not in tables:
        op.create_table(
            "instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("blizzard_id", sa.Integer(), nullable=False),
            sa.Column("expansion_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("img", sa.String(), nullable=True),
            sa.Column("instance_type", sa.String(), nullable=False),
            sa.Column("is_current_season", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["expansion_id"], ["expansion.id"], name="fk_instance_expansion"),
        )
        op.create_index("ix_instance_blizzard_id", "instance", ["blizzard_id"], unique=True)

    if "encounter" not in tables:
        op.create_table(
            "encounter",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("blizzard_id", sa.Integer(), nullable=False),
            sa.Column("instance_id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("creature_display_id", sa.Integer(), nullable=True),
            sa.Column("img", sa.String(), nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.ForeignKeyConstraint(["instance_id"], ["instance.id"], name="fk_encounter_instance"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    if "encounter" in tables:
        op.drop_table("encounter")

    if "instance" in tables:
        op.drop_index("ix_instance_blizzard_id", table_name="instance")
        op.drop_table("instance")

    if "expansion" in tables:
        op.drop_index("ix_expansion_name", table_name="expansion")
        op.drop_table("expansion")
